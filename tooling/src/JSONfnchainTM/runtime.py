"""Sequential driver and bounded fork-join execution; no external side-effect rollback."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
from contextvars import copy_context
import json
from uuid import uuid4
from bindings2bindingsTM import validate, RuntimeValueError as B2BRuntimeValueError
from .compiler import FlowPlan
from .errors import FlowRuntimeError, MaxIterationsExceededError
from .grammar import CallNode, BranchNode, MapNode, LoopNode, ParallelNode
from .interceptor import FlowAttemptContext, FlowInterceptor
from .vocab import FunctionVocab


def _runtime_error(exc, path, *, code='step_failed'):
    if isinstance(exc, FlowRuntimeError): return exc
    if isinstance(exc, B2BRuntimeValueError):
        detail = exc.details
        return FlowRuntimeError(detail['code'], (*path, *detail['path']),
                                f'Expression/return validation failed at {path!r}: {exc}',
                                expected=detail['expected'], actual=detail['actual'], cause=exc)
    return FlowRuntimeError(code, path,
                            f'Execution failed at {path!r}: {type(exc).__name__}: {exc}',
                            actual=type(exc).__name__, cause=exc)


def execute_flow(plan: FlowPlan, source_values: dict, *, vocab: FunctionVocab,
                 interceptor: FlowInterceptor | None = None, host_context=None,
                 max_concurrency: int = 8):
    """Run a compiled flow atomically from the caller's perspective.

    Registrations are snapshotted before work starts. Concurrent work uses one pool;
    submitted tasks always settle before an error escapes. External calls and hooks
    are NOT rolled back. Do not mutate source_values during execution.
    """
    if not isinstance(plan, FlowPlan):
        raise FlowRuntimeError('invalid_plan', message='execute_flow requires a verified FlowPlan')
    if not isinstance(vocab, FunctionVocab):
        raise FlowRuntimeError('invalid_vocab', message='vocab must be FunctionVocab')
    if type(source_values) is not dict:
        raise FlowRuntimeError('invalid_sources', message='source_values must be a dictionary')
    if type(max_concurrency) is not int or max_concurrency < 1:
        raise FlowRuntimeError('invalid_concurrency', message='max_concurrency must be a positive integer')
    if interceptor is None: interceptor = FlowInterceptor()
    if not isinstance(interceptor, FlowInterceptor):
        raise FlowRuntimeError('invalid_interceptor', message='interceptor must be FlowInterceptor')
    # This snapshot is taken atomically; later register/replace changes cannot affect
    # an executing flow. The immutable plan references names/contracts, not callables.
    entries = vocab.snapshot({name: json.loads(contract) for name, contract in plan._contracts.items()})
    execution_id = str(uuid4())

    def binding(expr, values, path):
        try: return expr.plan.evaluate(values)
        except Exception as exc:
            err = _runtime_error(exc, path, code='binding_failed')
            raise err from exc

    def start_call(node, args, path, map_indices, loop_iterations):
        ctx = FlowAttemptContext(execution_id=execution_id, attempt_id=str(uuid4()),
                                 node_path=path, map_indices=map_indices,
                                 loop_iterations=loop_iterations, host_context=host_context)
        entry = entries[node.fn]
        try:
            interceptor.before_step(ctx, deepcopy(args))
            result = entry.fn(deepcopy(args), ctx)
            validate(result, entry.output, (*path, 'output'))
            interceptor.after_step(ctx, deepcopy(args), deepcopy(result))
            return deepcopy(result)
        except Exception as exc:
            try:
                interceptor.on_step_error(ctx, deepcopy(args), exc)
            except Exception as hook_exc:
                wrapped = _runtime_error(hook_exc, path, code='error_hook_failed')
                raise wrapped from hook_exc
            wrapped = _runtime_error(exc, path, code='call_failed')
            raise wrapped from exc

    def bounded(items, limit, callback):
        """Bound queue occupancy, preserve order, settle started work on first failure."""
        result = [None] * len(items)
        waiting = {}
        next_item = 0
        failures = {}
        ceiling = min(limit, max_concurrency)
        while next_item < len(items) or waiting:
            while not failures and next_item < len(items) and len(waiting) < ceiling:
                i = next_item; next_item += 1
                waiting[pool.submit(copy_context().run, callback, i, items[i])] = i
            if not waiting: break
            done, _ = wait(tuple(waiting), return_when=FIRST_COMPLETED)
            for future in done:
                i = waiting.pop(future)
                try: result[i] = future.result()
                except Exception as exc: failures[i] = exc
        if failures:
            # Stable selection even if threads complete in a nondeterministic order.
            index = min(failures)
            raise failures[index]
        return result

    def run_block(nodes, scope, path=(), maps=(), loops=()):
        local = dict(scope)
        for node in nodes:
            at = (*path, node.id)
            try:
                if isinstance(node, CallNode):
                    args = binding(node.args, local, (*at, 'args'))
                    output = start_call(node, args, at, maps, loops)
                elif isinstance(node, BranchNode):
                    decision = binding(node.predicate, local, (*at, 'if'))
                    arm = node.then if decision else node.otherwise
                    arm_name = 'then' if decision else 'else'
                    child_scope = run_block(arm.nodes, local, (*at, arm_name), maps, loops)
                    output = (binding(arm.returns, child_scope, (*at, arm_name, 'returns'))
                              if node.valued else {})
                elif isinstance(node, MapNode):
                    items = binding(node.over, local, (*at, 'map', 'over'))
                    def run_item(i, item):
                        inner = dict(local)
                        inner['current'] = item; inner['index'] = i
                        inner[node.alias] = item
                        evaluated = run_block(node.body.nodes, inner, (*at, 'map', i),
                                              (*maps, i), loops)
                        return binding(node.body.returns, evaluated, (*at, 'map', i, 'returns'))
                    if node.parallel:
                        output = bounded(items, node.max_concurrency, run_item)
                    else:
                        output = [run_item(i, item) for i, item in enumerate(items)]
                elif isinstance(node, LoopNode):
                    state = binding(node.init, local, (*at, 'loop', 'init'))
                    iteration = 0
                    while True:
                        context = dict(local); context['state'] = state; context['iteration'] = iteration
                        keep_going = binding(node.predicate, context, (*at, 'loop', 'while'))
                        if not keep_going: break
                        if iteration >= node.maximum:
                            if node.on_max == 'raise':
                                raise MaxIterationsExceededError('max_iterations', at,
                                    f'Loop {node.id!r} reached {node.maximum} iterations with guard still true',
                                    expected='guard false', actual=iteration)
                            break
                        body_scope = run_block(node.body.nodes, context,
                                               (*at, 'loop', iteration), maps,
                                               (*loops, iteration))
                        state = binding(node.update, body_scope, (*at, 'loop', iteration, 'update'))
                        iteration += 1
                    final = dict(local); final['state'] = state; final['iteration'] = iteration
                    output = (binding(node.returns, final, (*at, 'loop', 'returns'))
                              if node.returns else deepcopy(state))
                elif isinstance(node, ParallelNode):
                    # Preflight every child binding before dispatching any function.
                    prepared = [(child, binding(child.args, local,
                                                  (*at, 'parallel', child.id, 'args')))
                                for child in node.calls]
                    def parallel_call(i, prepared_item):
                        child, args = prepared_item
                        return start_call(child, args, (*at, 'parallel', child.id), maps, loops)
                    values = bounded(prepared, max_concurrency, parallel_call)
                    output = {child.id: values[i] for i, child in enumerate(node.calls)}
                else:
                    raise FlowRuntimeError('invalid_instruction', at, 'Unknown verified flow node')
                local[node.id] = output
            except Exception as exc:
                wrapped = _runtime_error(exc, at)
                raise wrapped from exc
        return local

    with ThreadPoolExecutor(max_workers=max_concurrency, thread_name_prefix='jsonfnchain') as pool:
        # The lexical parent scope is detached from the externally owned mapping;
        # b2b itself performs validated, detached reads at each selected projection.
        final_scope = run_block(plan._nodes, source_values)
        return binding(plan._returns, final_scope, ('flow', 'returns'))

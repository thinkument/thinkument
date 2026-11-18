"""Approved pure transforms and explicit, trusted host vendor adapters.

Vendor adapters execute through Layer A; environment flags never synthesize results.
"""
import re
from bindings2bindingsTM import Str, Float, Int, Dict, List, Map, Nullable, Any
from JSONfnchainTM import FunctionVocab

def create_default_vocab():
    vocab = FunctionVocab()
    def add(name, inputs, output, fn):
        vocab.register(name=name, inputs=Dict(inputs), output=Dict(output), fn=fn, version='1')
    def template(args, ctx):
        return {'text': re.sub(r'\{\{\s*([A-Za-z_]\w*)\s*\}\}',
                              lambda m: args['vars'][m[1]], args['template'])}
    add('text.template', {'template': Str, 'vars': Map(Str)}, {'text': Str}, template)
    add('text.concat', {'parts': List(Str), 'sep': Str}, {'text': Str},
        lambda a, c: {'text': a['sep'].join(a['parts'])})
    add('math.add', {'a': Float, 'b': Float}, {'result': Float}, lambda a, c: {'result': a['a'] + a['b']})
    add('math.multiply', {'a': Float, 'b': Float}, {'result': Float}, lambda a, c: {'result': a['a'] * a['b']})
    add('data.extract', {'source': Map(Str), 'key': Str}, {'value': Nullable(Str)},
        lambda a, c: {'value': a['source'].get(a['key'])})

    def await_result_fn(args, ctx):
        val = args['promise']
        if type(val) is dict and 'ref' in val and 'status' in val:
            from authoring_w_persistence_async.handle import AsyncWorkHandle
            handle = AsyncWorkHandle(val['ref'])
            timeout = args.get('timeout_seconds') or 60.0
            handle.wait_until_done(timeout_seconds=timeout)
            outcome = handle.get_outcome()
            if outcome != 'success':
                from JSONfnchainTM.errors import FlowRuntimeError
                raise FlowRuntimeError('async_work_failed', message=f"Task {val['ref']} ended with {outcome}: {handle.get_error()}")
            return {'result': handle.get_result() or {}, 'outcome': outcome}
        return {'result': val if isinstance(val, dict) else {'value': val}, 'outcome': 'immediate_sync'}

    add('asyncwork.await_result',
        {'promise': Map(Any), 'timeout_seconds': Nullable(Float)},
        {'result': Any, 'outcome': Str},
        await_result_fn)

    def poll_fn(args, ctx):
        val = args['promise']
        if type(val) is dict and 'ref' in val and 'status' in val:
            from authoring_w_persistence_async.handle import AsyncWorkHandle
            handle = AsyncWorkHandle(val['ref'])
            done = handle.is_done()
            return {
                'is_done': "true" if done else "false",
                'outcome': handle.get_outcome() or 'ongoing',
                'result': handle.get_result() if done else {}
            }
        return {'is_done': "true", 'outcome': 'immediate_sync', 'result': val if isinstance(val, dict) else {}}

    add('asyncwork.poll',
        {'promise': Map(Any)},
        {'is_done': Str, 'outcome': Str, 'result': Any},
        poll_fn)

    def vendor(name):
        def invoke(args, ctx):
            binding = ctx.host_context['vendor_bindings'].get(name)
            if binding is None:
                raise ValueError('No trusted vendor binding configured for ' + name)
            return binding.execute(ctx, args)
        return invoke
    add('vendor.llm.chat_completion', {'prompt': Str, 'model': Nullable(Str), 'temperature': Nullable(Float)},
        {'text': Str, 'usage': Dict({'prompt_tokens': Int, 'completion_tokens': Int})}, vendor('vendor.llm.chat_completion'))
    add('vendor.embeddings.generate', {'text': Str, 'model': Nullable(Str)},
        {'vector': List(Float), 'dimensions': Int}, vendor('vendor.embeddings.generate'))
    add('vendor.media.image_generation',
        {'prompt': Str, 'model': Nullable(Str), 'size': Str, 'count': Int},
        {'asset': Dict({'asset_id': Str, 'url': Str, 'content_type': Str, 'size_bytes': Int})},
        vendor('vendor.media.image_generation'))
    return vocab

THINKUMENT_GLOBAL_VOCAB = create_default_vocab()

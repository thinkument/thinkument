# Shared strict authoring

Import `StrictServiceWidget`, `strict_widget`, the type constructors, `Promise`, and `D`
from this package. Define unique ordinary widget IDs in your own pack. Give output
ports closed records; input ports may have any supported type. The decorator
normalizes metadata on the ordinary class configuration and registers it through
public kernel registration. There is no second widget registry. Runtime imports
load neither teaching programs nor the Higher-P compiler.

## The Law of Wire Typing Symmetry & Asynchronous Promises
1. **Producer Specification**: Output ports declare whether data is produced synchronously or as an asynchronous promise:
   ```python
   @strict_widget(
       outputs={'analysis': Promise(Dict({'summary': Str, 'score': Float}))}
   )
   class DocAnalyzerWidget(StrictServiceWidget):
       def on_generate(self):
           handle = self.submit_async_work_v1(target='ai.analyze', args={'doc_id': 10})
           self.outputs.write('analysis', {'ref': handle.ref, 'status': 'ongoing'})
           return True
   ```
2. **Consumer Specification**: Consumer input ports are **never promise-knowing**. They declare the semantic type required:
   ```python
   @strict_widget(
       inputs={'analysis': Dict({'summary': Str, 'score': Float})}
   )
   class DocReviewerWidget(StrictServiceWidget):
       def on_mount(self):
           val = self.mouth.read('analysis')
           # Polymorphic: val may be synchronous data or a promise descriptor {'ref': ...}
           return True
   ```
3. **Compile-Time Validation**: A wire from `Promise[T]` to an input expecting `T` is valid if `compatible(Promise[T].item, T)`.


Every mount/fill/signal handler returns True or Reexplode and explicitly writes
every output key. `outputs.write`, `write_port` and `write_many` validate before
staging; batches stage atomically. Repeated writes replace the same staged key.
`read` returns previously accepted detached values; `keep`/`keep_port` explicitly
carry them forward. Mount has no accepted outputs. `write_null`, `read_or` and
`require_value` distinguish null from false, zero and empty values. Deletion and
public durable attribute assignment are unsupported. Use detached `configuration`
for ordinary args, `mouth.read`/`read_or`/`require_value` for captured typed inputs,
and private ephemeral helpers for domain computation. Private-state tampering is
outside the guarantee.

The strict transition runs inside the existing Analytica operation. Direct and
inherited handlers use the existing wrappers; signals must use
`analytica_signal_catcher`. Preparation, mouth capture, handler execution, complete
write checking and publication therefore occur between audit-ins and audit-outs
or audit-error. Failures retain accepted outputs. Service transactions retain
ordinary persistence/rollback behavior. Existing vendor auditing, Formreact,
roles, signals, limits and exhaustion policies remain available. Admission errors
before the handler and analytics input preparation are existing platform failures
and are not promised to become widget audit errors.

Own semantic state has separate `strict_outputs_v1`, `strict_mouths_v1` and
`strict_configuration_v1` pockets. It stores no raw rows, __kernel packet or prior
shell. `replacement_shell` retains lifecycle/presentation metadata while dropping
raw kernel packets and generated binding args. Framework-owned lifecycle state
and mandatory analytics snapshots still incur their existing costs.

Compile Higher P explicitly before publishing:

```python
from authoring_funnel.b_service_ready_typed_PSMCW_authoring import D, compile_strict_tape
# Add bindings on ordinary logical widget declarations:
bindings = {
    "sources": {"draft": {"widget": "writer", "port": "result"}},
    "parameters": {"label": {"type": str, "value": "$ui.label"}},
    "inputs": {"context": D.text(D.ref("parameters", "label"), ": ", D.ref("draft", "title"))},
}
# tape = compile_strict_tape(HIGHER_P, SM, C)
```

The ordinary skeleton, appearance overrides, symbols and C remain ordinary.
`overrides.bindings[logical]` replaces each named source, parameter declaration or
input expression as a whole. The reserved local source `parameters` resolves via
ordinary symbols; constants within D expressions are literal. Generated args
`strict_binding_recipe_v1` and `strict_binding_parameters_v1`, and wire
`strict_sources_v1`, are reserved. All widgets in certified programs are strict;
every input is bound. Sources choose latest earlier appearances, including
`{"self":"previous"}`, with no same-step/future references or historical windows.
Multiple ports of one source appearance share one wire row. Unused source
declarations are checked but do not emit wires. Recipes escape dollar signs and
carry domain dict keys inside opaque JSON strings. Parameter args still obey
ordinary P's recursive authoring restrictions. Later incompatible C values fail
runtime parameter checking, even after an export has been serialized.

Source availability relies on the framework's first mounting rows, not constant
time datum lookup. Every source-step widget is mount-shelling, all mounting rows
are recorded before dispatch, and those references materialize the appearance's
latest accepted lifecycle state. Generated caps cover the entire source step.
Tests exercise 26-source steps and repeated explosions with a cap of one. The
underlying query scans step writes before filtering by datum; mandatory analytics
also copies selected wire states and snapshots local state. Those costs are
separate from projection-only binding evaluation. Revalidate changed programs,
SM/C combinations or registered contracts. Undo first unwinds subsequent automatic
work; a second undo may be needed to make the prior manual action redoable.

A future UI uses `describe`, `describe_widgets`, `validate` and `compile` from a
creativity AuthoringProfile. Drafts contain profile_id, W (selected registered IDs),
P, SM and C. Exports contain profile_id, ordinary P/SM/C, widget_ids and a contract
fingerprint. Typed profiles refine W/P only; SM/C use public existing validation
and routing. Descriptors are inert JSON and catalogues describe trusted registered
Python implementations. Drafts do not carry callables or arbitrary import paths.
Switching profiles requires revalidation; unsupported drafts return structured
path errors. Each pack publishes its optional profile provider alongside its
ordinary manifest in the one local central table; Packito remains default and
packs without refinements use the base profile. Adopt TypedAuthoringProfile with
your own pack/profile IDs and widget_ids for another pack. No authoring UI,
compiler HTTP endpoint or launch protocol is added.

Accepted-output preservation follows transition induction: staging validates each
key without changing accepted outputs; only complete successful transitions
replace accepted outputs; failed transitions restore the previous accepted pockets.
The guarantee covers structural types, complete writes and supported APIs, not
termination, handler/domain meaning or hostile Python changing private internals.

A later incompatible parameter rejects automatic mount inside an analytics
operation. The highest facade's subsequent context preparation may propagate the
RuntimeValueError directly; an ordinary dispatch error packet is not guaranteed
for automatic mounting. Service transactions may also roll back emitted events.
This is an inherited routing/persistence behavior, not a new typed launch mode.

Source selection uses static topology. Program, flow and logical widget IDs must
be nonempty literal strings without dollar signs or surrounding whitespace. This
prevents ordinary symbol routing or ID normalization from changing a generated
source step after compilation. Typed parameter defaults must already satisfy
their declarations; compile_strict_tape then checks effective C separately.
Ordinary analytics prohibits nested lifecycle operations: inherit a handler
directly, or override it without calling another wrapped lifecycle handler.

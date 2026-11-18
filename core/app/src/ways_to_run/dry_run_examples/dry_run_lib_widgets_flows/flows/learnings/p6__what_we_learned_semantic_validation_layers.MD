# P6 — What we learned about semantic validation layers

## One datum, two validation layers

A current ThinkWidget datum exposes an executable shell:

```text
current-effective shell
    ├─ identity and presentation
    ├─ micros: names, types, requiredness, validators
    ├─ lifecycle policy
    └─ authored args plus __kernel observation
```

The shell is not only renderer metadata. It is the current input grammar.

```python
{
    "name": "platform_number",
    "type": "integer",
    "required": True,
    "validators": [
        {
            "path": "...:min_number",
            "args": {"min_value": 10},
        }
    ],
}
```

A reexplosion replaces the current-effective shell. Validator sets are not
implicitly accumulated from older shells.

## Exact transition order

For a touched datum:

```text
working fill + submitted fill
    -> candidate datum-local fill
    -> partial platform semantic validation
    -> lifecycle handler
    -> blocked | done | reexplode
    -> final required/semantic validity before ordinary commit
```

Partial validation checks supplied nonblank values but does not require every
required field to be present. Therefore a signal-only request can reach a signal
catcher while required micros remain blank.

A signal is a command addressed to a datum. It is not itself a micro value.

## Platform rejection

P6 submits a number below the shell minimum together with a valid custom signal.

The exact canonical suffix is:

```text
controller.loop.start
controller.loop.end
```

The middle is asserted to be exactly empty. Neither signal catcher nor fill
handler ran.

The end is still a successful controller outcome:

```text
payload.outcome = "success"
payload.result.last_error["semantic_probe"] = ...
```

At the highest facade:

```text
applied=True
dispatch_outcome="semantic_rejected"
write_committed=False
```

Platform rejection does not consume a widget-authored lifecycle branch and does
not allow the widget to emit guidance.

## Lifecycle functional rejection

P6 next submits a platform-valid number and a code that violates a stateful
widget rule.

The canonical suffix includes:

```text
controller.loop.start
semantic_validation.lifecycle_observed
datum.message(error)
controller.loop.end
```

The widget can inspect state, args, wires, signal information, and the complete
candidate fill. It may emit arbitrary app events and author the next shell.

That power comes later in the transition and a `Reexplode` consumes lifecycle
budget. The rejection is not automatically written to the engine-owned
`U.last_error` slot.

## Structural satisfaction is not full domain validity

`q["structurally_satisfied"]` means required micros are present and nonblank
under platform blank semantics. It does not mean every domain rule is true.

Use platform validators for stable shell-declared admission facts:

* numeric bounds;
* formats and patterns;
* allowed choices;
* reusable cross-field rules that should stop before widget execution.

Use lifecycle validation for creative/stateful workflow decisions:

* attempt limits;
* history-dependent acceptance;
* contextual coaching;
* signal-sensitive behavior;
* dynamic next-shell design;
* accumulation and progression.

## Relationship to P7

P6 semantic rejection:

```text
start
end(outcome="success", result.last_error populated)
```

P7 datum exception:

```text
start
end(outcome="system_error", system_error populated)
```

Both were admitted. Only the latter is a systematic execution failure.

## Final author rule

```text
shell says what data may enter
platform validates the candidate at the wall
widget decides what admitted data means
widget emits events and may author the next shell
authoritative satisfaction moves the flow
```

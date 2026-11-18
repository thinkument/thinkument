# Sheet A — thinkwidgetTM top-down docsheet

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                     thinkwidgetTM CLASS WIDGET SURFACE                       │
│        ergonomic class shell lowered into datomatonTM lifecycle function      │
│                                                                              │
│  AUTHOR WRITES                                                                │
│  ─────────────                                                                │
│                                                                              │
│  @thinkwidgetTM_config("my.widget", overwrite=True,                           │
│      missing_signal_handler_outcome="raise" | "fallback_to_fill_handler")     │
│  class MyWidget(DatumLifecycleWidget):                                        │
│                                                                              │
│      def _on_mount(self, position, fill_data, limits, stats):                 │
│          ...                                                                 │
│          return True | Reexplode(...)                                         │
│                                                                              │
│      def _on_fill(self, signal, position, fill_data, limits, stats):          │
│          ...                                                                 │
│          return True | Reexplode(...)                                         │
│                                                                              │
│      @signal_catcher("refresh")                                               │
│      def refresh(self, signal, position, fill_data, limits, stats):           │
│          ...                                                                 │
│          return True | Reexplode(...)                                         │
│                                                                              │
│                                                                              │
│  LOWERING                                                                     │
│  ────────                                                                     │
│                                                                              │
│  class definition                                                             │
│       │                                                                       │
│       ▼                                                                       │
│  compile_datum_widget_class(cls)                                              │
│       │                                                                       │
│       ├─ requires subclass of DatumLifecycleWidget                            │
│       ├─ requires concrete _on_mount(...)                                     │
│       ├─ requires concrete _on_fill(...)                                      │
│       ├─ collects @signal_catcher methods by Python MRO                       │
│       ├─ validates missing-signal policy                                      │
│       └─ returns plain datomaton-compatible function(q)                       │
│                                                                              │
│       │                                                                       │
│       ▼                                                                       │
│  register_datum_widget_v1("my.widget", compiled_fn)                           │
│                                                                              │
│                                                                              │
│  RUNTIME ENTRY                                                                │
│  ─────────────                                                                │
│                                                                              │
│  step fn emits multiframespec                                                 │
│       │                                                                       │
│       ├─ app_form_id                                                          │
│       ├─ frames[]                                                             │
│       ├─ spans[].owns[]                                                       │
│       ├─ datums[]                                                             │
│       └─ datum.lifecycle.widget == "my.widget"                                │
│                                                                              │
│       │                                                                       │
│       ▼                                                                       │
│  datomatonTM engine builds q exactly as before                                │
│       │                                                                       │
│       ├─ q["form_id"], q["frame_id"], q["span_id"], q["datum_id"]             │
│       ├─ q["datum"]              current-effective datum shell                │
│       ├─ q["raw_fill"]           raw candidate                                │
│       ├─ q["partial_fill"]       accepted/canonical current fill              │
│       ├─ q["prefill"]            current prefill/default hint                 │
│       ├─ q["state"]              previous widget state                        │
│       ├─ q["messages"]           bounded previous messages                    │
│       ├─ q["proc_notes"]         bounded previous lower proc notes            │
│       ├─ q["structurally_satisfied"]                                          │
│       ├─ q["reexplode_count"]                                                │
│       ├─ q["max_reexplosions"], q["max_messages"], q["max_proc_notes"]        │
│       ├─ q["signal"] = {"kind": ..., "info": ...}                             │
│       └─ q["emit"] immediate event sink                                       │
│                                                                              │
│       │                                                                       │
│       ▼                                                                       │
│  class adapter constructs instance                                            │
│       │                                                                       │
│       ├─ self._q        raw lower q, private                                  │
│       ├─ self._state    dict(q["state"])                                      │
│       ├─ self.foo       reads/writes self._state["foo"]                       │
│       ├─ self.message() emits UI event + appends result message               │
│       └─ adapter-private state keeps last_precomputed_fills                   │
│                                                                              │
│       │                                                                       │
│       ▼                                                                       │
│  adapter derives ergonomic method inputs                                      │
│                                                                              │
│  position                                                                     │
│    ├─ form_id                                                                 │
│    ├─ frame_id                                                                │
│    ├─ span_id                                                                 │
│    └─ datum_id                                                                │
│                                                                              │
│  fill_data                                                                    │
│    ├─ fill_shell                  q["datum"] current shell                    │
│    ├─ current_fills               q["partial_fill"]                           │
│    ├─ prefill_hints               q["prefill"]                                │
│    ├─ pre_computed_fills          previous Reexplode.pre_computed_fills       │
│    ├─ changed_fills               current_fills Δ pre_computed_fills          │
│    └─ shell_satisfaction_check    q["structurally_satisfied"]                 │
│                                                                              │
│  limits                                                                       │
│    ├─ max_reexplosions                                                        │
│    └─ max_messages                                                            │
│                                                                              │
│  stats                                                                        │
│    ├─ reexplode_count                                                         │
│    └─ num_messages                                                            │
│                                                                              │
│  signal                                                                       │
│    ├─ kind                                                                     │
│    └─ info                                                                     │
│                                                                              │
│       │                                                                       │
│       ▼                                                                       │
│  dispatch                                                                     │
│                                                                              │
│    signal.kind == "mount" ─────────────▶ instance.on_mount()                  │
│                                           └─ _on_mount(position, fill_data,   │
│                                                        limits, stats)         │
│                                                                              │
│    signal.kind == "fill" ──────────────▶ instance.on_fill()                   │
│                                           └─ _on_fill(signal, position,       │
│                                                      fill_data, limits, stats)│
│                                                                              │
│    signal.kind in @signal_catcher map ──▶ custom method(signal, position,     │
│                                                          fill_data, limits,   │
│                                                          stats)               │
│                                                                              │
│    unknown custom signal                                                      │
│       ├─ policy "fallback_to_fill_handler" ─▶ _on_fill(...), signal preserved │
│       └─ policy "raise" ───────────────────▶ NotImplementedError              │
│                                                                              │
│       │                                                                       │
│       ▼                                                                       │
│  author method body                                                           │
│                                                                              │
│    can run ordinary Python                                                    │
│    can call helpers / inherited methods / MRO overrides                       │
│    can read method inputs                                                     │
│    can set self.some_state = value                                            │
│    can call self.message(level, text)                                         │
│    returns exactly:                                                           │
│       True                                                                    │
│       or Reexplode(next_fill_shell, pre_computed_fills?, prefill_hints?)      │
│                                                                              │
│       │                                                                       │
│       ▼                                                                       │
│  adapter lowers return into datomatonTM result                                │
│                                                                              │
│    True                                                                       │
│       └─ {"status": "done",                                                   │
│           "state": self._state,                                               │
│           "messages": self._messages}                                         │
│                                                                              │
│    Reexplode                                                                  │
│       └─ {"status": "reexplode",                                              │
│           "datum": next_fill_shell,                                           │
│           "fill": pre_computed_fills if provided,                             │
│           "prefill": prefill_hints if provided,                               │
│           "state": self._state plus adapter reserved state,                   │
│           "messages": self._messages}                                         │
│                                                                              │
│       preserves prior shell metadata if omitted from next shell:              │
│           roles, role, tags, system_flags, authoritative                      │
│                                                                              │
│       │                                                                       │
│       ▼                                                                       │
│  datomatonTM engine continues verbatim                                        │
│                                                                              │
│    done                                                                       │
│       ├─ lifecycle satisfied                                                  │
│       ├─ normal accepted fill may commit                                      │
│       └─ state/messages become current lifecycle row                          │
│                                                                              │
│    reexplode                                                                  │
│       ├─ datum becomes next current-effective shell                           │
│       ├─ fill becomes working fill / next current_fills source                │
│       ├─ prefill becomes next prefill hint source                             │
│       ├─ state becomes next self state                                        │
│       ├─ messages append into bounded lifecycle messages                      │
│       ├─ reexplode_count increments                                           │
│       └─ same span remains open until authoritative datums are satisfied      │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Necessary components for a base widget class

A legal thinkwidgetTM class has this minimum shape:

```python
@thinkwidgetTM_config("your.widget.name", overwrite=True)
class YourWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        return True  # or Reexplode(...)

    def _on_fill(self, signal, position, fill_data, limits, stats):
        return True  # or Reexplode(...)
```

The compiler enforces both handlers, even when a particular datum uses `mount_explode=False`. Custom signals are optional:

```python
@signal_catcher("refresh")
def refresh(self, signal, position, fill_data, limits, stats):
    return Reexplode(...)
```

The datum that uses the widget must point at the registered name:

```python
{
    "id": "Q",
    "title": "Q",
    "micros": [],
    "lifecycle": {
        "widget": "your.widget.name",
        "mount_explode": True,
        "max_reexplosions": 10,
        "max_messages": 8,
        "max_proc_notes": 0,
    },
}
```

## Semantic split: `self`, inputs, and outputs

The class adapter exists to separate three things that are mixed together in raw `q`.

`self` is the widget’s Markovian lifecycle memory. `self.phase = "email"` means the next call receives `q["state"]["phase"] == "email"`, and the next instance exposes `self.phase`. It is not global app state. It is current-effective state for this logical datum lifecycle.

Method inputs are read-only observations of the current program position, current shell, current fill overlay, signal, limits, and stats. They tell the method where it is and what happened.

The return value is the next lifecycle move. `True` means “this datum is done.” `Reexplode(...)` means “replace this datum’s current shell and keep the span alive.”

## Input grammar seen by class methods

```text
position =
{
  "form_id": str,
  "frame_id": str,
  "span_id": str,
  "datum_id": str,
}

fill_data =
{
  "fill_shell": current effective datum shell,       # q["datum"]
  "current_fills": current accepted/canonical fill, # q["partial_fill"]
  "prefill_hints": current prefill/defaults,        # q["prefill"]
  "pre_computed_fills": previous adapter fill seed,
  "changed_fills": value delta from previous pre_computed_fills,
  "shell_satisfaction_check": bool,
}

limits =
{
  "max_reexplosions": int,
  "max_messages": int,
}

stats =
{
  "reexplode_count": int,
  "num_messages": int,
}

signal =
{
  "kind": "fill" | "mount" | custom string,
  "info": dict,
}
```

Important details:

`changed_fills` is a value delta, not proof of user causality. On mount, `changed_fills` is always `{}`. A mount may still see existing `current_fills` if the same datum is mounted again later on another span.

`fill_shell` is the current-effective datum. After a reexplode, it is the previous `Reexplode.next_fill_shell`, not necessarily the original step-function datum.

`current_fills` is the accepted/canonical datum-local fill. It is not the raw submit. Raw-vs-canonical behavior belongs to the lower datomaton/datacore path.

## Output grammar from class methods

The ergonomic class grammar is intentionally smaller than the raw datomaton result grammar.

```text
HandlerReturn =
    True
  | Reexplode(
        next_fill_shell: Mapping[str, Any],
        pre_computed_fills: Optional[Mapping[str, Any]] = None,
        prefill_hints: Optional[Mapping[str, Any]] = None,
    )
```

`True` lowers to:

```python
{
    "status": "done",
    "state": self._state,
    "messages": self._messages,
}
```

`Reexplode(...)` lowers to:

```python
{
    "status": "reexplode",
    "datum": next_fill_shell,
    "fill": pre_computed_fills,   # only if provided
    "prefill": prefill_hints,     # only if provided
    "state": self._state,
    "messages": self._messages,
}
```

`self.message(level, text)` is the class-level event/message helper. It validates `level in {"success", "info", "warning", "error"}`, immediately emits a runtime event through lower `q["emit"]`, and appends the same message to the eventual platform result.

The class adapter does not directly expose ergonomic `blocked`, `proc_notes`, or returned `events`. Those exist in the lower datomaton function grammar. A class widget that needs the full raw grammar should use the lower `register_datum_widget_v1(name, fn)` surface directly instead of the class adapter.

## Full lower datomaton result grammar underneath

The lower lifecycle function still supports:

```text
result.status =
    "done"
  | "blocked"
  | "reexplode"

common optional result fields =
{
  "state": dict dead-json,
  "message": message | string,
  "messages": list[message],
  "events": list[event spec],
}

reexplode-only fields =
{
  "datum": replacement datum shell,  # required for reexplode
  "fill": working fill overlay,
  "prefill": working prefill overlay,
  "proc_notes": diagnostic/provenance dict,
}
```

The class adapter maps only into `"done"` and `"reexplode"`.

## Shell grammar and fill formalism

A reexploded shell is the next datum surface. The class adapter treats it as a dead-json mapping and preserves controller/compiler metadata if the next shell omits it:

```text
preserved keys =
    roles
  | role
  | tags
  | system_flags
  | authoritative
```

The effective fill language for a live shell is determined by its micros:

```text
DatumShell S =
{
  "id": str,
  "title": str,
  "micros": list[MicroDecl],
  "lifecycle": LifecycleFlags,
  ...optional shell metadata...
}

MicroDecl m =
{
  "name": str,
  "type": key in MICRO_TYPES,
  "required": bool,
  "args": dict,
  "validators": list[ValidatorSpec],
  "style": dict,
  "tags": list,
  ...dead-json renderer/datacore metadata...
}

LegalPartialFill(S) =
  mappings from micro names in S.micros
  to values accepted by the datum validator for present micros.

LegalCompleteFill(S) =
  LegalPartialFill(S)
  plus all required micros present
  plus micro validators pass
  plus macro validators pass.
```

So a widget’s `Reexplode.next_fill_shell` defines the next space of meaningful fill submissions. A widget’s `pre_computed_fills` defines the initial working overlay and the next comparison base for `changed_fills`. A widget’s `prefill_hints` defines renderer/default hints.

The pasted code does not define a finite vocabulary of every possible micro `system_flags`. It shows that shell-level `system_flags` are preserved across class reexplosions when omitted from the replacement shell. The open-ended micro vocabulary comes from datacore `MICRO_TYPES`, attached validators, macro validators, and dead-json shell metadata.

## Signal formalism

For a widget class `W`:

```text
HandledSignals(W) =
    {"mount" if lifecycle.mount_explode}
  ∪ {"fill"}
  ∪ {names declared by @signal_catcher(name)}
```

With `missing_signal_handler_outcome="raise"`:

```text
custom signal kind not in @signal_catcher map -> NotImplementedError
```

With `missing_signal_handler_outcome="fallback_to_fill_handler"`:

```text
custom signal kind not in @signal_catcher map -> _on_fill(signal, ...)
```

The fallback preserves the original custom `signal["kind"]`, so `_on_fill` can still branch on it.

Controller/API signals are datum-targeted. In the highest controller façade, `signal.info` is enriched with:

```python
{
    "datum_id": <target datum id>,
    "source": "controller_action",
}
```

Signals are not a side channel. They are normal lifecycle inputs that can change the reexplosion path for the same current shell and same fill.

## Degrees of freedom

A thinkwidgetTM author can legally vary:

1. The Python class design: inheritance, helper methods, overridden handlers, MRO-based signal catchers.
2. The lifecycle state shape: any dead-json stored through `self.some_attr`.
3. The shell sequence: every `Reexplode.next_fill_shell` can replace title, micros, lifecycle, validators, args, styles, and renderer metadata.
4. The fill overlays: `pre_computed_fills` can seed or preserve working values.
5. The prefill hints: `prefill_hints` can suggest defaults independently from accepted fills.
6. The signal vocabulary: any custom signal names can be caught by `@signal_catcher`.
7. The message/event stream: `self.message(...)` emits immediate UI events and appends result messages.
8. The convergence policy: shell sequence plus `max_reexplosions` determines whether the widget converges, forced-completes, or hard-blocks at the lower engine layer.

Those choices affect behavior as follows:

```text
return True
  -> datum lifecycle satisfied
  -> span may advance if authoritative requirements are met
  -> current accepted fill can commit through normal form-fill path

return Reexplode(next shell)
  -> current datum shape changes
  -> same span remains live
  -> reexplode_count increments
  -> next render uses new micros/fill/prefill surface
  -> next fill/signaled action targets the new surface

add @signal_catcher("x")
  -> controller can target this datum with signal.kind == "x"
  -> same current fill can cause a different next shell than ordinary fill

choose fallback_to_fill_handler
  -> all custom signals remain legal inputs to _on_fill

choose raise
  -> only declared catchers are legal custom signals

change required micros / validators
  -> changes the language of legal fills
  -> changes structural satisfaction
  -> changes which fills can complete the span

carry large history in self
  -> legal but state grows
  -> current-only storage does not prevent a widget from encoding history itself
```

# Footnote — how datums are used by programs

A step function emits a `multiframespec`:

```python
{
    "app_form_id": "FORM",
    "datums": [...],
    "frames": [
        {
            "id": "F",
            "spans": [
                {"id": "S", "owns": ["A", "Q", "B"]}
            ],
        }
    ],
    "fills": {...},
}
```

The engine traverses frames and spans. A span is the manual progression unit. A span behaves like a product vector of its owned datums.

Plain datums are satisfied by structurally valid fills. Lifecycle datums are satisfied by lifecycle status: `done` or `forced_done`.

A span can declare authoritative datums:

```python
{
    "id": "S",
    "owns": ["A", "Q", "B"],
    "my_authoritative_datums": ["Q"],
}
```

Accepted aliases are:

```text
my_authoritative_datums
authoritative_datums
authoritative_owns
authoritative
```

If no authoritative set is declared, all owned datums are authoritative. If declared, it must be a non-empty subset of `owns`. Non-authoritative datums may still be filled, and invalid touched non-authoritative fills can reject the whole submit.

Lifecycle datum flags:

```python
"lifecycle": {
    "widget": "my.widget",
    "state": {...},
    "mount_explode": True | False,
    "max_reexplosions": int,
    "exhausted_means_satisfied": True | False,
    "max_proc_notes": int,
    "max_messages": int,
}
```

Meanings:

```text
widget
  registered lifecycle widget name.

state
  first lifecycle seed. After first call, returned state becomes current state.

mount_explode
  False: widget does not run before first fill.
  True: widget receives signal.kind == "mount" before first render on that span.

max_reexplosions
  cap on status="reexplode" transitions.

exhausted_means_satisfied
  default True.
  True: max-reexplode exhaustion forces satisfied / forced_done.
  False: exhaustion blocks and keeps datum unsatisfied.

max_proc_notes
  lower datomaton cap for lifecycle row proc_notes only.
  The class adapter does not expose proc_notes ergonomically.

max_messages
  cap for lifecycle row messages only.
  Does not cap state, fills, prefills, runtime writes, or reexplosions.
```

Mount is span-local. The same logical datum id can appear on a later span; with `mount_explode=True`, it receives a fresh mount signal there while seeing prior current-effective `self` state.

Touched-field law: on fill, only touched or signaled pending lifecycle datums are evaluated. A sibling lifecycle datum should not assume it runs on every submit.

# Sheet B — full-aspects example class

```python
from __future__ import annotations

from typing import Any, Dict, Mapping

from sessions.programming.thinkprogramTM.thinkwidgetTM import (
    DatumLifecycleWidget,
    MISSING_SIGNAL_FALLBACK_TO_FILL,
    Reexplode,
    signal_catcher,
    thinkwidgetTM_config,
)


WIDGET_NAME = "docs.profile.full_aspects.v1"


def text_micro(name: str, *, required: bool = True) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "text",
        "required": required,
    }


@thinkwidgetTM_config(
    WIDGET_NAME,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
)
class FullAspectsProfileWidget(DatumLifecycleWidget):
    """
    Demonstrates:
      - mount-generated first shell
      - fill-driven reexplosion
      - custom controller signal
      - fallback custom-signal policy
      - self-backed lifecycle state
      - pre_computed_fills
      - prefill_hints
      - message/event emission
      - shell metadata preservation by adapter
    """

    def _base_lifecycle(self, fill_data: Mapping[str, Any]) -> Dict[str, Any]:
        prior = dict(fill_data["fill_shell"].get("lifecycle") or {})
        return {
            **prior,
            "widget": WIDGET_NAME,
            "mount_explode": True,
            "max_reexplosions": 20,
            "max_messages": 8,
            "max_proc_notes": 0,
        }

    def _profile_shell(
        self,
        fill_data: Mapping[str, Any],
        *,
        title: str,
        micros: list[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        shell = dict(fill_data["fill_shell"])
        return {
            **shell,
            "title": title,
            "micros": list(micros),
            "lifecycle": self._base_lifecycle(fill_data),
        }

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        # Mount may see current_fills from a previous span, but changed_fills
        # must be empty on mount.
        assert fill_data["changed_fills"] == {}

        self.phase = "name"
        self.mounts = list(getattr(self, "mounts", []) or []) + [
            position["span_id"]
        ]
        self.last_position = dict(position)
        self.mount_seen_current_fills = dict(fill_data["current_fills"])

        self.message("info", f"mounted profile on {position['span_id']}")

        return Reexplode(
            next_fill_shell=self._profile_shell(
                fill_data,
                title="Profile: name",
                micros=[text_micro("name")],
            ),
            pre_computed_fills={
                "name": "",
            },
            prefill_hints={
                "name": "Ada",
            },
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        self.last_signal_seen = dict(signal)
        self.last_changed_fills = dict(fill_data["changed_fills"])
        self.last_stats_seen = dict(stats)

        current = dict(fill_data["current_fills"])

        if getattr(self, "phase", None) == "name" and current.get("name"):
            self.phase = "email"
            self.name = str(current["name"])

            self.message("info", "name accepted; asking for email")

            return Reexplode(
                next_fill_shell=self._profile_shell(
                    fill_data,
                    title="Profile: email",
                    micros=[text_micro("email")],
                ),
                pre_computed_fills={
                    "email": "",
                },
                prefill_hints={
                    "email": f"{self.name.lower()}@example.com",
                },
            )

        if getattr(self, "phase", None) == "email" and current.get("email"):
            self.phase = "done"
            self.email = str(current["email"])

            self.message("success", "profile complete")
            return True

        # Class adapter has no ergonomic blocked return.
        # For graceful recoverable blocked behavior, use lower datomatonTM fn.
        raise ValueError(
            f"unexpected profile surface: phase={getattr(self, 'phase', None)!r}, "
            f"current={current!r}, signal={signal!r}"
        )

    @signal_catcher("refresh")
    def refresh(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        self.refresh_count = int(getattr(self, "refresh_count", 0) or 0) + 1
        self.refresh_signal_seen = dict(signal)
        self.refresh_current_fills_seen = dict(fill_data["current_fills"])

        self.message("info", "profile surface refreshed")

        # Preserve the current shell and current fills. This proves a custom
        # signal can re-run the lifecycle without being an ordinary fill.
        return Reexplode(
            next_fill_shell=dict(fill_data["fill_shell"]),
            pre_computed_fills=dict(fill_data["current_fills"]),
            prefill_hints=dict(fill_data["prefill_hints"]),
        )

    @signal_catcher("skip_email")
    def skip_email(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        current = dict(fill_data["current_fills"])

        self.phase = "done"
        self.email = str(
            current.get("email")
            or signal.get("info", {}).get("default_email")
            or "unknown@example.com"
        )
        self.skipped_email = True

        self.message("success", "email skipped by controller signal")
        return True
```

## Why this class uses all formal aspects

It uses class registration through `@thinkwidgetTM_config`, required `_on_mount` and `_on_fill`, custom signal dispatch through `@signal_catcher`, fallback policy for undeclared custom signals, `self` lifecycle state, `position`, `fill_data`, `limits`, `stats`, `signal`, `Reexplode.next_fill_shell`, `pre_computed_fills`, `prefill_hints`, and `self.message(...)`.

Its behavior is:

```text
mount
  -> phase = "name"
  -> shell becomes micros=[name]
  -> precomputed fill {"name": ""}
  -> prefill hint {"name": "Ada"}

fill name
  -> phase = "email"
  -> shell becomes micros=[email]
  -> precomputed fill {"email": ""}
  -> prefill hint based on submitted name

signal refresh
  -> custom signal catcher runs
  -> current shell/fill/prefill preserved
  -> refresh_count increments

fill email
  -> phase = "done"
  -> returns True
  -> lifecycle satisfied
  -> final fill commits normally

signal skip_email
  -> custom signal catcher can finish without another shell
```

## End-to-end usage sketch

```python
from typing import Any, Dict, Mapping

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
from _thinkengine.runme.runme_offline_debug_against_actionscript import (
    SessionProgramScriptedHeadlessRunner,
)


def register_step(name: str, multiframespec: Mapping[str, Any]) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": dict(multiframespec)}

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def manifest(step_name: str) -> list[dict[str, Any]]:
    return [
        {
            "public_step_name": "profile_widget_demo",
            "step_fn": step_name,
            "fn_args": {},
        }
    ]


form_id = "docs.profile.full_aspects.form"
step_name = "docs.profile.full_aspects.step"

register_step(
    step_name,
    {
        "app_form_id": form_id,
        "datums": [
            {
                "id": "PROFILE",
                "title": "Profile",
                "micros": [],
                "roles": ["maker"],
                "system_flags": {"example_flag": True},
                "lifecycle": {
                    "widget": WIDGET_NAME,
                    "mount_explode": True,
                    "max_reexplosions": 20,
                    "max_messages": 8,
                    "max_proc_notes": 0,
                },
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["PROFILE"],
                    }
                ],
            }
        ],
    },
)

api = get_concrete_session_api(enable_persistence=False)
session = api.create_VM_session(
    manifest=manifest(step_name),
    initial_parameter_overrides={},
    session_metadata={
        "manual_io": {
            "persistence": "disabled",
            "include_forms_emitted_order_in_ctx": False,
        }
    },
)
sid = str(session["session_id"])
runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

ctx = runner.step_until_stop()
assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
assert ctx["current_span"] == "S"
assert "name" in str(ctx["datum_widget_decls"]["PROFILE"])

ctx = runner.step(fill={"PROFILE": {"name": "Ada"}})
assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
assert "email" in str(ctx["datum_widget_decls"]["PROFILE"])

ctx = api.step_session(
    sid,
    signal={
        "datum_id": "PROFILE",
        "kind": "refresh",
        "info": {"reason": "demo"},
    },
)
assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

ctx = runner.step(fill={"PROFILE": {"email": "ada@example.com"}})
assert ctx["kind"] in {"ATCOMPLETION", "ATCOMPLETE"}

out = api.get_outputs(sid)
assert out["form_fills"]["PROFILE"] == {"email": "ada@example.com"}

state = api._get(sid).state["_datum_lifecycle_v1"]
profile_row = state["forms"][form_id]["datums"]["PROFILE"]

assert profile_row["status"] == "done"
assert profile_row["state"]["phase"] == "done"
assert profile_row["state"]["name"] == "Ada"
assert profile_row["state"]["email"] == "ada@example.com"
assert profile_row["state"]["refresh_count"] == 1
```

The key confirmation is that the developer never touches the lower `q` function directly. The class is lowered into that function, the lower engine lifecycle runs verbatim, and the class author thinks in terms of `self`, method inputs, `True`, `Reexplode`, and `self.message(...)`.

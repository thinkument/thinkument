from __future__ import annotations

"""
dry_run_lib_widgets_flows thinkwidgetTM pack
==============================

The widgets intentionally exercise distinct lifecycle and authoring shapes:

Wa / NumberGuessWidget
    A bounded, resetting, signal-aware reexploding game.

Wb / DailyNumberWidget
    A one-shell widget with configuration-dependent fields and a custom
    signal that changes its minimum accepted number.

Wc / CumulativeBoardWidget
    A deliberately non-terminating cumulative board. It is useful as an
    authoritative datum for a looping span and as a non-authoritative datum
    for an ordinary progressing span.

Wd / WiringObserverWidget
    A one-shell proof widget. On every mount it emits one ``wiring.proof``
    event containing exact authored args and the normalized public
    ``__kernel.past_wires`` view. Its second appearance demonstrates the
    self-previous shorthand arriving through the same wire container.

We / InductiveCompletenessWidget
    A compact proof widget for history=all, optional self-history, missing
    signal fallback, prefills versus pre-computed fills, direct custom events,
    changed_fills deltas.

Wp / ProgramAuthoringProbeWidget
    A mount-time witness for symbols, puppeteering, appearance overrides,
    kernel flags, and authoritative lowering.

The public ThinkWidget runtime-argument/history-wire sugars used by the proof
widgets are defined directly in this module. This test sheet therefore does
not import ``thinkwidget_mould.thinkwidget_runtime_sugars``.

All messages use ``self.message(...)``. Therefore each message is both:

* appended to lifecycle message memory; and
* emitted synchronously as a ``datum.message`` session event.

That event appears between the surrounding controller start/end packets when
the lifecycle handler runs during a public dispatch.
"""

from copy import deepcopy
from random import Random
from typing import Any, Dict, Iterable, Mapping, Optional

from _thinkprogram.thinkwidgetTM.base import (
    DatumLifecycleWidget,
)
from _thinkprogram.thinkwidgetTM.constants import (
    MISSING_SIGNAL_RAISE,
)
from _thinkprogram.thinkwidgetTM.decorators import (
    signal_catcher,
    thinkwidgetTM_config,
)
from _thinkprogram.thinkwidgetTM.types import Reexplode


# ---------------------------------------------------------------------------
# Embedded ThinkWidget runtime sugars
# ---------------------------------------------------------------------------
#
# These helpers read only the public lifecycle-handler seam:
#
#     fill_data["fill_shell"]["args"]
#     fill_data["fill_shell"]["args"]["__kernel"]["past_wires"]
#
# They intentionally know no application widget.
# ---------------------------------------------------------------------------


def authored_widget_args_v1(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    raw = dict(fill_shell or {}).get("args")
    args = dict(raw or {}) if isinstance(raw, Mapping) else {}
    args.pop("__kernel", None)
    return deepcopy(args)


def authored_widget_arg_v1(
    fill_shell: Mapping[str, Any],
    name: str,
) -> Any:
    args = authored_widget_args_v1(fill_shell)
    key = str(name)

    if key not in args:
        raise KeyError(
            f"authored widget arg is absent: {key!r}"
        )

    return deepcopy(args[key])


def kernel_observation_v1(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    raw_args = dict(fill_shell or {}).get("args")

    if not isinstance(raw_args, Mapping):
        raise TypeError(
            "fill shell args must be a mapping"
        )

    raw_kernel = raw_args.get("__kernel")

    if not isinstance(raw_kernel, Mapping):
        raise TypeError(
            "fill shell args.__kernel must be a mapping"
        )

    return deepcopy(dict(raw_kernel))


def past_wires_v1(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    kernel = kernel_observation_v1(fill_shell)
    raw = kernel.get("past_wires")

    if not isinstance(raw, Mapping):
        raise TypeError(
            "__kernel.past_wires must be a mapping"
        )

    return deepcopy(dict(raw))


def wire_rows_v1(
    fill_shell: Mapping[str, Any],
    wire_name: str,
) -> list[Dict[str, Any]]:
    """Normalize one public wire slot to ``list[row]``."""
    wires = past_wires_v1(fill_shell)
    key = str(wire_name)

    if key not in wires:
        return []

    raw = wires[key]

    if isinstance(raw, Mapping):
        return [deepcopy(dict(raw))]

    if isinstance(raw, list):
        if not all(
            isinstance(row, Mapping)
            for row in raw
        ):
            raise TypeError(
                f"wire {key!r} list must contain mapping rows"
            )

        return [
            deepcopy(dict(row))
            for row in raw
        ]

    raise TypeError(
        f"wire {key!r} must materialize as "
        "mapping or list[mapping]"
    )


def wire_container_kind_v1(
    fill_shell: Mapping[str, Any],
    wire_name: str,
) -> str:
    wires = past_wires_v1(fill_shell)
    key = str(wire_name)

    if key not in wires:
        return "absent"

    if isinstance(wires[key], Mapping):
        return "one_row"

    if isinstance(wires[key], list):
        return "row_list"

    raise TypeError(
        f"wire {key!r} has unsupported container "
        f"{type(wires[key]).__name__}"
    )


def runtime_write_row_state_v1(
    row: Mapping[str, Any],
) -> Dict[str, Any]:
    """Read the exact ``row['value']['state']`` lifecycle-state pocket."""
    if "value" not in row:
        raise KeyError(
            "runtime write row is missing exact key 'value'"
        )

    value = row["value"]

    if not isinstance(value, Mapping):
        raise TypeError(
            "runtime write row['value'] must be a mapping"
        )

    if "state" not in value:
        raise KeyError(
            "runtime write row['value'] is missing "
            "exact key 'state'"
        )

    state = value["state"]

    if not isinstance(state, Mapping):
        raise TypeError(
            "runtime write row['value']['state'] "
            "must be a mapping"
        )

    return deepcopy(dict(state))


def runtime_write_row_identity_v1(
    row: Mapping[str, Any],
) -> Dict[str, str]:
    """Read exact source identity fields from one kernel history row."""
    public_step_name = row.get("public_step_name")
    datum_id = row.get("key")
    value_ref = row.get("value_ref")

    if (
        not isinstance(public_step_name, str)
        or not public_step_name
    ):
        raise TypeError(
            "runtime write row['public_step_name'] "
            "must be non-empty str"
        )

    if not isinstance(datum_id, str) or not datum_id:
        raise TypeError(
            "runtime write row['key'] must be non-empty str"
        )

    if not isinstance(value_ref, Mapping):
        raise TypeError(
            "runtime write row['value_ref'] must be a mapping"
        )

    ref_datum_id = value_ref.get("datum_id")

    if ref_datum_id != datum_id:
        raise ValueError(
            "runtime write row identity mismatch: "
            "row['value_ref']['datum_id'] != row['key']"
        )

    return {
        "public_step_name": public_step_name,
        "datum_id": datum_id,
    }


def wire_state_index_v1(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build a uniform wire-name -> ordered source-state observation."""
    wires = past_wires_v1(fill_shell)
    out: Dict[str, Any] = {}

    for wire_name in sorted(wires):
        rows = wire_rows_v1(
            fill_shell,
            wire_name,
        )

        out[wire_name] = {
            "container_kind": wire_container_kind_v1(
                fill_shell,
                wire_name,
            ),
            "row_count": len(rows),
            "rows": [
                {
                    "source": runtime_write_row_identity_v1(
                        row
                    ),
                    "state": runtime_write_row_state_v1(
                        row
                    ),
                }
                for row in rows
            ],
        }

    return out


def one_wire_state_v1(
    fill_shell: Mapping[str, Any],
    wire_name: str,
) -> Dict[str, Any]:
    rows = wire_rows_v1(
        fill_shell,
        wire_name,
    )

    if len(rows) != 1:
        raise ValueError(
            f"wire {wire_name!r} expected exactly one row; "
            f"got {len(rows)}"
        )

    return runtime_write_row_state_v1(
        rows[0]
    )


def many_wire_states_v1(
    fill_shell: Mapping[str, Any],
    wire_name: str,
) -> list[Dict[str, Any]]:
    return [
        runtime_write_row_state_v1(row)
        for row in wire_rows_v1(
            fill_shell,
            wire_name,
        )
    ]


# ---------------------------------------------------------------------------
# Widget pack
# ---------------------------------------------------------------------------


WA_WIDGET = (
    "ways_to_run.dry_run_examples."
    "dry_run_lib_widgets_flows.number_guess.v1"
)
WB_WIDGET = (
    "ways_to_run.dry_run_examples."
    "dry_run_lib_widgets_flows.daily_number.v1"
)
WC_WIDGET = (
    "ways_to_run.dry_run_examples."
    "dry_run_lib_widgets_flows.cumulative_board.v1"
)
WD_WIDGET = (
    "ways_to_run.dry_run_examples."
    "dry_run_lib_widgets_flows.wiring_observer.v1"
)
WE_WIDGET = (
    "ways_to_run.dry_run_examples."
    "dry_run_lib_widgets_flows.inductive_completeness.v1"
)
WP_WIDGET = (
    "ways_to_run.dry_run_examples."
    "dry_run_lib_widgets_flows.program_authoring_probe.v1"
)

_MISSING = object()


def _args(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    raw = dict(fill_shell or {}).get("args")

    return (
        dict(raw or {})
        if isinstance(raw, Mapping)
        else {}
    )


def _kernel(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    args = _args(fill_shell)
    raw = args.get("__kernel")

    return (
        dict(raw or {})
        if isinstance(raw, Mapping)
        else {}
    )


def _history_rows(
    fill_shell: Mapping[str, Any],
    wire_name: str,
) -> list[Dict[str, Any]]:
    """
    Return normalized history rows from the ThinkProgramTM ``__kernel`` packet.

    Kernel implementations may materialize one-wire history as one mapping and
    many-wire history as a list. The quick-start widgets accept both.
    """
    past = _kernel(fill_shell).get("past_wires")

    if not isinstance(past, Mapping):
        return []

    raw = past.get(str(wire_name))

    if raw is None:
        return []

    if isinstance(raw, Mapping):
        return [
            deepcopy(dict(raw))
        ]

    if isinstance(raw, list):
        return [
            deepcopy(dict(row))
            for row in raw
            if isinstance(row, Mapping)
        ]

    return []


def _mapping_path(
    value: Any,
    *path: str,
) -> Any:
    current = value

    for key in path:
        if not isinstance(current, Mapping):
            return _MISSING

        if key not in current:
            return _MISSING

        current = current[key]

    return current


def _ordinary_int(
    value: Any,
) -> Optional[int]:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if (
        isinstance(value, float)
        and value.is_integer()
    ):
        return int(value)

    if isinstance(value, str):
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return None

    return None


def _history_lifecycle_value(
    row: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = row.get("value")

    return (
        dict(value)
        if isinstance(value, Mapping)
        else {}
    )


def _history_state(
    row: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _history_lifecycle_value(row)
    state = value.get("state")

    return (
        dict(state)
        if isinstance(state, Mapping)
        else {}
    )


def _daily_number_from_history_row(
    row: Mapping[str, Any],
) -> Optional[int]:
    return _ordinary_int(
        _mapping_path(
            _history_state(row),
            "representative_number",
        )
    )


def _previous_game_from_history_row(
    row: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    state = _history_state(row)

    number = _ordinary_int(
        _mapping_path(
            state,
            "target_number",
        )
    )

    if number is None:
        return None

    raw_hint = _mapping_path(
        state,
        "hint",
    )

    hint = (
        str(raw_hint)
        if (
            raw_hint is not _MISSING
            and raw_hint is not None
        )
        else ""
    )

    return {
        "number": number,
        "hint": hint,
    }


def _number_values_for_prefix(
    fill_data: Mapping[str, Any],
    *,
    prefix: str,
) -> list[int]:
    changed = dict(
        fill_data.get("changed_fills") or {}
    )
    out: list[int] = []

    for name, raw_value in changed.items():
        if not str(name).startswith(prefix):
            continue

        value = _ordinary_int(raw_value)

        if value is not None:
            out.append(value)

    return out


def _number_micro(
    name: str,
    *,
    required: bool = True,
) -> Dict[str, Any]:
    return {
        "name": str(name),
        "type": "number",
        "required": bool(required),
    }


def _text_micro(
    name: str,
    *,
    required: bool = True,
) -> Dict[str, Any]:
    return {
        "name": str(name),
        "type": "text",
        "required": bool(required),
    }


def _checkbox_micro(
    name: str,
    *,
    required: bool = True,
) -> Dict[str, Any]:
    return {
        "name": str(name),
        "type": "checkbox",
        "required": bool(required),
    }


def _guess_shell(
    *,
    prior: Mapping[str, Any],
    phase: int,
    count: int,
) -> Dict[str, Any]:
    shell = deepcopy(
        dict(prior)
    )
    shell["title"] = "Guess the number"
    shell["micros"] = [
        _number_micro(
            f"guess_{phase}_{index}"
        )
        for index in range(
            1,
            count + 1,
        )
    ]

    return shell


def _daily_shell(
    *,
    prior: Mapping[str, Any],
    mode: str,
) -> Dict[str, Any]:
    shell = deepcopy(
        dict(prior)
    )
    args = _args(prior)

    micros = [
        _number_micro(
            "representative_number"
        )
    ]

    if mode == "checkbox":
        micros.append(
            _checkbox_micro(
                "good_day"
            )
        )
    else:
        micros.append(
            _text_micro(
                "day_reflection"
            )
        )

    shell["title"] = str(
        args.get("title")
        or "How are you today?"
    )
    shell["micros"] = micros

    return shell


def _board_shell(
    *,
    prior: Mapping[str, Any],
    accepted_rounds: Iterable[
        Mapping[str, Any]
    ],
) -> Dict[str, Any]:
    shell = deepcopy(
        dict(prior)
    )
    micros: list[Dict[str, Any]] = []

    # New editable row first.
    for index in range(1, 4):
        micros.append(
            _number_micro(
                f"new_{index}"
            )
        )

    # Accepted historical rows remain visible
    # and prefilled underneath.
    for round_index, row in enumerate(
        accepted_rounds,
        start=1,
    ):
        del row

        for item_index in range(1, 4):
            micros.append(
                {
                    **_number_micro(
                        (
                            f"accepted_"
                            f"{round_index}_"
                            f"{item_index}"
                        ),
                        required=False,
                    ),
                    "read_only": True,
                }
            )

    shell["title"] = (
        "Cumulative number board"
    )
    shell["micros"] = micros

    return shell


def _completeness_shell(
    *,
    prior: Mapping[str, Any],
    prefill_note: str,
) -> Dict[str, Any]:
    """
    Build the P5 proof shell.

    ``prefill`` is presentation guidance only. It is deliberately not copied
    into ``pre_computed_fills`` during mount.
    """
    shell = deepcopy(
        dict(prior)
    )

    note_micro = _text_micro(
        "note"
    )
    note_micro["prefill"] = str(
        prefill_note
    )

    shell["title"] = (
        "Inductive completeness probe"
    )
    shell["micros"] = [
        _text_micro("token"),
        note_micro,
    ]

    return shell


@thinkwidgetTM_config(
    WA_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_RAISE,
    enforce_no_premount_shell=True,
    args={
        "number": {
            "type": "int",
            "required": False,
            "default": 17,
        },
        "hint": {
            "type": "str",
            "required": False,
            "default": "It is between 1 and 30.",
        },
    },
    wires={
        "previous_game": {
            "multiplicity": "one",
            "required": False,
        },
        "daily_number": {
            "multiplicity": "one",
            "required": False,
        },
    },
)
class NumberGuessWidget(
    DatumLifecycleWidget
):
    """A two-round number guessing datum with reset/no-count signals."""

    def _configure_game(
        self,
        fill_shell: Mapping[str, Any],
    ) -> tuple[int, str]:
        args = _args(fill_shell)

        previous_rows = _history_rows(
            fill_shell,
            "previous_game",
        )
        daily_rows = _history_rows(
            fill_shell,
            "daily_number",
        )

        if previous_rows:
            previous = (
                _previous_game_from_history_row(
                    previous_rows[0]
                )
            )

            if previous is not None:
                return (
                    int(
                        previous["number"]
                    ),
                    str(
                        previous["hint"]
                        or args.get("hint")
                        or "Try what worked before."
                    ),
                )

        if daily_rows:
            daily_number = (
                _daily_number_from_history_row(
                    daily_rows[0]
                )
            )

            if daily_number is not None:
                return (
                    daily_number,
                    str(
                        args.get("hint")
                        or (
                            "Use today's "
                            "representative number."
                        )
                    ),
                )

        return (
            int(
                args.get(
                    "number",
                    17,
                )
            ),
            str(
                args.get("hint")
                or "It is between 1 and 30."
            ),
        )

    def _restart(
        self,
        fill_shell: Mapping[str, Any],
    ) -> Reexplode:
        target_number, hint = (
            self._configure_game(
                fill_shell
            )
        )

        self.phase = 1
        self.round = 1
        self.counted_failures = 0
        self.target_number = target_number
        self.hint = hint
        self.game_done = False
        self.outcome = "playing"
        self.last_guesses = []

        self.message(
            "info",
            "game has started",
        )
        self.message(
            "info",
            f"the hint is: {self.hint}",
        )

        return Reexplode(
            next_fill_shell=_guess_shell(
                prior=fill_shell,
                phase=1,
                count=3,
            ),
            pre_computed_fills={},
        )

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats

        return self._restart(
            fill_data["fill_shell"]
        )

    def _evaluate_guesses(
        self,
        *,
        fill_shell: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        count_life: bool,
    ) -> Any:
        guesses = _number_values_for_prefix(
            fill_data,
            prefix="guess_",
        )

        if not guesses:
            self.message(
                "error",
                "submit at least one numeric guess",
            )

            return Reexplode(
                next_fill_shell=deepcopy(
                    dict(fill_shell)
                ),
                pre_computed_fills=dict(
                    fill_data.get(
                        "current_fills"
                    )
                    or {}
                ),
            )

        self.last_guesses = list(
            guesses
        )

        if int(
            self.target_number
        ) in guesses:
            self.game_done = True
            self.outcome = "correct"

            self.message(
                "success",
                (
                    "the game ended and "
                    "you guessed correctly"
                ),
            )

            return True

        closest = min(
            guesses,
            key=lambda value: abs(
                value
                - int(
                    self.target_number
                )
            ),
        )

        self.message(
            "info",
            (
                f"closest guess was {closest}; "
                "try again"
            ),
        )

        if count_life:
            self.counted_failures = (
                int(
                    getattr(
                        self,
                        "counted_failures",
                        0,
                    )
                )
                + 1
            )

        phase = int(
            getattr(
                self,
                "phase",
                1,
            )
        )

        if phase == 1:
            self.phase = 2
            self.round = 2

            return Reexplode(
                next_fill_shell=_guess_shell(
                    prior=fill_shell,
                    phase=2,
                    count=2,
                ),
                pre_computed_fills={},
            )

        self.game_done = True
        self.outcome = "incorrect"

        self.message(
            "error",
            "the game ended",
        )

        return True

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats

        return self._evaluate_guesses(
            fill_shell=fill_data[
                "fill_shell"
            ],
            fill_data=fill_data,
            count_life=True,
        )

    @signal_catcher("reset")
    def reset(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats

        return self._restart(
            fill_data["fill_shell"]
        )

    @signal_catcher("do_not_count")
    def do_not_count(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats

        if not fill_data.get(
            "changed_fills"
        ):
            raise ValueError(
                "do_not_count requires fill data"
            )

        return self._evaluate_guesses(
            fill_shell=fill_data[
                "fill_shell"
            ],
            fill_data=fill_data,
            count_life=False,
        )


@thinkwidgetTM_config(
    WB_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_RAISE,
    enforce_no_premount_shell=True,
    args={
        "response_mode": {
            "type": "str",
            "required": False,
            "default": "checkbox",
        },
        "min_number_accepted": {
            "type": "int",
            "required": False,
            "default": 0,
        },
        "paragraph_must_contain": {
            "type": "str",
            "required": False,
            "default": "",
        },
        "adjust_min_seed": {
            "type": "int",
            "required": False,
            "default": 7,
        },
    },
    wires={},
)
class DailyNumberWidget(
    DatumLifecycleWidget
):
    """One-shell daily sentiment widget with a signal-driven min adjustment."""

    def _mode(
        self,
        fill_shell: Mapping[str, Any],
    ) -> str:
        raw = str(
            _args(
                fill_shell
            ).get(
                "response_mode"
            )
            or "checkbox"
        )

        return (
            "paragraph"
            if raw == "paragraph"
            else "checkbox"
        )

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats

        args = _args(
            fill_data["fill_shell"]
        )

        self.min_number_accepted = int(
            args.get(
                "min_number_accepted",
                0,
            )
        )
        self.adjustments = []

        return Reexplode(
            next_fill_shell=_daily_shell(
                prior=fill_data[
                    "fill_shell"
                ],
                mode=self._mode(
                    fill_data[
                        "fill_shell"
                    ]
                ),
            ),
            pre_computed_fills={},
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats

        changed = dict(
            fill_data.get(
                "changed_fills"
            )
            or {}
        )

        number = _ordinary_int(
            changed.get(
                "representative_number"
            )
        )

        if number is None:
            self.message(
                "error",
                (
                    "representative_number "
                    "is required"
                ),
            )

            return Reexplode(
                next_fill_shell=deepcopy(
                    dict(
                        fill_data[
                            "fill_shell"
                        ]
                    )
                ),
                pre_computed_fills=dict(
                    fill_data.get(
                        "current_fills"
                    )
                    or {}
                ),
            )

        minimum = int(
            getattr(
                self,
                "min_number_accepted",
                0,
            )
        )

        if number < minimum:
            self.message(
                "error",
                (
                    "number must be at least "
                    f"{minimum}"
                ),
            )

            return Reexplode(
                next_fill_shell=deepcopy(
                    dict(
                        fill_data[
                            "fill_shell"
                        ]
                    )
                ),
                pre_computed_fills=dict(
                    fill_data.get(
                        "current_fills"
                    )
                    or {}
                ),
            )

        args = _args(
            fill_data["fill_shell"]
        )

        if (
            self._mode(
                fill_data["fill_shell"]
            )
            == "paragraph"
        ):
            required_text = str(
                args.get(
                    "paragraph_must_contain"
                )
                or ""
            ).strip()

            paragraph = str(
                changed.get(
                    "day_reflection"
                )
                or ""
            )

            if (
                required_text
                and required_text.lower()
                not in paragraph.lower()
            ):
                self.message(
                    "error",
                    (
                        "day_reflection must "
                        "contain "
                        f"{required_text!r}"
                    ),
                )

                return Reexplode(
                    next_fill_shell=deepcopy(
                        dict(
                            fill_data[
                                "fill_shell"
                            ]
                        )
                    ),
                    pre_computed_fills=dict(
                        fill_data.get(
                            "current_fills"
                        )
                        or {}
                    ),
                )

        self.representative_number = (
            number
        )
        self.last_submission = deepcopy(
            changed
        )

        self.message(
            "success",
            "I believe in you!",
        )

        return True

    @signal_catcher("adjust_min")
    def adjust_min(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats

        if fill_data.get(
            "changed_fills"
        ):
            raise ValueError(
                (
                    "adjust_min is signal-only; "
                    "fill data is invalid"
                )
            )

        info = dict(
            signal.get("info")
            or {}
        )
        raw_many = info.get(
            "mins"
        )

        if (
            isinstance(
                raw_many,
                list,
            )
            and raw_many
        ):
            candidates = [
                int(value)
                for value in raw_many
            ]

            seed = int(
                _args(
                    fill_data[
                        "fill_shell"
                    ]
                ).get(
                    "adjust_min_seed",
                    7,
                )
            )

            new_min = Random(
                seed
                + len(
                    self.adjustments
                )
            ).choice(
                candidates
            )

        elif "min" in info:
            new_min = int(
                info["min"]
            )

        else:
            raise ValueError(
                (
                    "adjust_min requires "
                    "info.min or info.mins"
                )
            )

        self.min_number_accepted = (
            new_min
        )
        self.adjustments = [
            *list(
                getattr(
                    self,
                    "adjustments",
                    [],
                )
            ),
            new_min,
        ]

        self.message(
            "info",
            (
                "minimum adjusted to "
                f"{new_min}"
            ),
        )

        return Reexplode(
            next_fill_shell=_daily_shell(
                prior=fill_data[
                    "fill_shell"
                ],
                mode=self._mode(
                    fill_data[
                        "fill_shell"
                    ]
                ),
            ),
            pre_computed_fills={},
        )


@thinkwidgetTM_config(
    WC_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_RAISE,
    enforce_no_premount_shell=True,
    args={
        "sum_should_not_exceed": {
            "type": "int",
            "required": True,
        },
    },
    wires={},
)
class CumulativeBoardWidget(
    DatumLifecycleWidget
):
    """An indefinitely reexploding cumulative three-number board."""

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats

        self.accepted_rounds = []
        self.total = 0

        return Reexplode(
            next_fill_shell=_board_shell(
                prior=fill_data[
                    "fill_shell"
                ],
                accepted_rounds=[],
            ),
            pre_computed_fills={},
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats

        changed = dict(
            fill_data.get(
                "changed_fills"
            )
            or {}
        )

        numbers = [
            value
            for name in (
                "new_1",
                "new_2",
                "new_3",
            )
            if (
                value := _ordinary_int(
                    changed.get(name)
                )
            )
            is not None
        ]

        if len(numbers) != 3:
            self.message(
                "error",
                (
                    "submit exactly three "
                    "new numbers"
                ),
            )

            return Reexplode(
                next_fill_shell=deepcopy(
                    dict(
                        fill_data[
                            "fill_shell"
                        ]
                    )
                ),
                pre_computed_fills=dict(
                    fill_data.get(
                        "current_fills"
                    )
                    or {}
                ),
            )

        # This is lifecycle-level semantic rejection.
        # The supplied public thinkwidgetTM adapter
        # does not expose a micro semantic-validator
        # registration surface.
        evens = [
            value
            for value in numbers
            if value % 2 == 0
        ]

        if evens:
            self.message(
                "error",
                (
                    "even numbers are not "
                    f"accepted: {evens}"
                ),
            )

            return Reexplode(
                next_fill_shell=deepcopy(
                    dict(
                        fill_data[
                            "fill_shell"
                        ]
                    )
                ),
                pre_computed_fills=dict(
                    fill_data.get(
                        "current_fills"
                    )
                    or {}
                ),
            )

        proposed_total = (
            int(
                getattr(
                    self,
                    "total",
                    0,
                )
            )
            + sum(numbers)
        )

        max_total = int(
            _args(
                fill_data[
                    "fill_shell"
                ]
            )[
                "sum_should_not_exceed"
            ]
        )

        if proposed_total > max_total:
            self.message(
                "error",
                (
                    "added these numbers: "
                    f"{numbers}; "
                    "sum exceeded the max "
                    f"total of {max_total}"
                ),
            )

            return Reexplode(
                next_fill_shell=deepcopy(
                    dict(
                        fill_data[
                            "fill_shell"
                        ]
                    )
                ),
                pre_computed_fills=dict(
                    fill_data.get(
                        "current_fills"
                    )
                    or {}
                ),
            )

        accepted = {
            f"number_{index}": value
            for index, value in enumerate(
                numbers,
                start=1,
            )
        }

        self.accepted_rounds = [
            *list(
                getattr(
                    self,
                    "accepted_rounds",
                    [],
                )
            ),
            accepted,
        ]
        self.total = proposed_total

        self.message(
            "info",
            (
                "progress: accepted "
                f"{numbers}; cumulative "
                f"total is {self.total}"
            ),
        )

        precomputed: Dict[
            str,
            Any,
        ] = {}

        for round_index, row in enumerate(
            self.accepted_rounds,
            start=1,
        ):
            for item_index in range(
                1,
                4,
            ):
                precomputed[
                    (
                        f"accepted_"
                        f"{round_index}_"
                        f"{item_index}"
                    )
                ] = row[
                    f"number_{item_index}"
                ]

        return Reexplode(
            next_fill_shell=_board_shell(
                prior=fill_data[
                    "fill_shell"
                ],
                accepted_rounds=(
                    self.accepted_rounds
                ),
            ),
            pre_computed_fills=(
                precomputed
            ),
        )


@thinkwidgetTM_config(
    WD_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_RAISE,
    enforce_no_premount_shell=True,
    args={
        "lesson_label": {
            "type": "str",
            "required": True,
        },
        "expected_many_count": {
            "type": "int",
            "required": True,
        },
    },
    wires={
        "one_source": {
            "multiplicity": "one",
            "required": True,
        },
        "many_sources": {
            "multiplicity": "many",
            "required": True,
        },
        "self_previous": {
            "multiplicity": "one",
            "required": False,
        },
    },
)
class WiringObserverWidget(
    DatumLifecycleWidget
):
    """
    Emit the exact public wire/arg observation available to a class widget.

    This widget does not discover state attribute names. It publishes the
    complete flat state mapping already stored at row["value"]["state"].
    Consumers choose keys from that mapping according to the source widget's
    documented class-state contract.
    """

    def _proof(
        self,
        fill_shell: Mapping[str, Any],
    ) -> Dict[str, Any]:
        args = (
            authored_widget_args_v1(
                fill_shell
            )
        )

        expected_many_count = int(
            args[
                "expected_many_count"
            ]
        )

        one_rows = wire_rows_v1(
            fill_shell,
            "one_source",
        )
        many_rows = wire_rows_v1(
            fill_shell,
            "many_sources",
        )
        self_rows = wire_rows_v1(
            fill_shell,
            "self_previous",
        )

        if len(one_rows) != 1:
            raise AssertionError(
                (
                    "one_source contract "
                    "must materialize "
                    "exactly one row"
                )
            )

        if (
            len(many_rows)
            != expected_many_count
        ):
            raise AssertionError(
                (
                    "many_sources "
                    "materialized an "
                    "unexpected row count: "
                    f"expected="
                    f"{expected_many_count}, "
                    f"actual="
                    f"{len(many_rows)}"
                )
            )

        if (
            wire_container_kind_v1(
                fill_shell,
                "one_source",
            )
            != "one_row"
        ):
            raise AssertionError(
                (
                    "one_source must use "
                    "the one-row container"
                )
            )

        if (
            wire_container_kind_v1(
                fill_shell,
                "many_sources",
            )
            != "row_list"
        ):
            raise AssertionError(
                (
                    "many_sources must use "
                    "the row-list container"
                )
            )

        return {
            "args": args,
            "wire_state_index": (
                wire_state_index_v1(
                    fill_shell
                )
            ),
            "self_previous_present": bool(
                self_rows
            ),
        }

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats

        fill_shell = fill_data[
            "fill_shell"
        ]
        proof = self._proof(
            fill_shell
        )

        self.mount_number = (
            int(
                getattr(
                    self,
                    "mount_number",
                    0,
                )
            )
            + 1
        )

        self.last_wire_proof = deepcopy(
            proof
        )

        self._emit(
            {
                "proof": proof,
            },
            name="wiring.proof",
        )

        self.message(
            "info",
            (
                "wiring proof mounted; "
                "acknowledge to continue"
            ),
        )

        next_shell = deepcopy(
            dict(fill_shell)
        )
        next_shell["title"] = (
            "Inspect exact wire and arg inputs"
        )
        next_shell["micros"] = [
            _text_micro(
                "acknowledgement"
            ),
        ]

        return Reexplode(
            next_fill_shell=next_shell,
            pre_computed_fills={},
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats

        acknowledgement = str(
            dict(
                fill_data.get(
                    "changed_fills"
                )
                or {}
            ).get(
                "acknowledgement"
            )
            or ""
        ).strip()

        if not acknowledgement:
            self.message(
                "error",
                (
                    "acknowledgement "
                    "is required"
                ),
            )

            return Reexplode(
                next_fill_shell=deepcopy(
                    dict(
                        fill_data[
                            "fill_shell"
                        ]
                    )
                ),
                pre_computed_fills=dict(
                    fill_data.get(
                        "current_fills"
                    )
                    or {}
                ),
            )

        self.acknowledgement = (
            acknowledgement
        )

        self.message(
            "success",
            (
                "wiring proof "
                "acknowledged"
            ),
        )

        return True


@thinkwidgetTM_config(
    WE_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=(
        "fallback_to_fill_handler"
    ),
    enforce_no_premount_shell=True,
    args={
        "lesson_label": {
            "type": "str",
            "required": True,
        },
        "required_token": {
            "type": "str",
            "required": True,
        },
        "prefill_note": {
            "type": "str",
            "required": True,
        },
    },
    wires={
        "all_daily": {
            "multiplicity": "many",
            "required": True,
        },
        "self_previous": {
            "multiplicity": "one",
            "required": False,
        },
    },
)
class InductiveCompletenessWidget(
    DatumLifecycleWidget
):
    """
    Close the remaining ordinary ThinkWidgetTM authoring seams used by P5.

    The widget proves:

    * ``history.select="all"`` preserves distinct physical source writes;
    * an optional self-history wire may be absent on one appearance and present
      on the next;
    * an unrecognized signal can be delegated to ``_on_fill``;
    * a micro prefill remains presentation guidance rather than a committed
      pre-computed fill;
    * a rejected submission can preserve the current fill snapshot, causing
      the next ``changed_fills`` mapping to contain only the actual delta;
    * custom dead-JSON events can be emitted directly; and
    """

    def _proof(
        self,
        fill_shell: Mapping[str, Any],
    ) -> Dict[str, Any]:
        daily_rows = wire_rows_v1(
            fill_shell,
            "all_daily",
        )
        self_rows = wire_rows_v1(
            fill_shell,
            "self_previous",
        )

        kernel = (
            kernel_observation_v1(
                fill_shell
            )
        )

        kernel_flags = dict(
            kernel.get(
                "kernel_flags"
            )
            or {}
        )

        if (
            wire_container_kind_v1(
                fill_shell,
                "all_daily",
            )
            != "row_list"
        ):
            raise AssertionError(
                (
                    "all_daily must use "
                    "the row-list container"
                )
            )

        if len(daily_rows) != 2:
            raise AssertionError(
                (
                    "history=all must expose "
                    "both physical daily "
                    "runtime writes: "
                    f"actual="
                    f"{len(daily_rows)}"
                )
            )

        daily_numbers = [
            _daily_number_from_history_row(
                row
            )
            for row in daily_rows
        ]

        if any(
            number is None
            for number in daily_numbers
        ):
            raise AssertionError(
                (
                    "every all_daily history "
                    "row must expose "
                    "representative_number"
                )
            )

        compact_scope = (
            kernel_flags.get(
                (
                    "copy_form_frame_span_args_"
                    "into_each_datum"
                )
            )
            is False
        )

        return {
            "all_daily_count": len(
                daily_rows
            ),
            "self_previous_present": bool(
                self_rows
            ),
            "compact_scope": (
                compact_scope
            ),
        }

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats

        fill_shell = deepcopy(
            dict(
                fill_data[
                    "fill_shell"
                ]
            )
        )

        args = (
            authored_widget_args_v1(
                fill_shell
            )
        )
        proof = self._proof(
            fill_shell
        )

        self.lesson_label = str(
            args["lesson_label"]
        )
        self.required_token = str(
            args["required_token"]
        )
        self.prefill_note = str(
            args["prefill_note"]
        )

        self.last_completeness_proof = (
            deepcopy(
                proof
            )
        )
        self.saw_rejected_token = False

        self._emit(
            {
                "proof": proof,
            },
            name="completeness.proof",
        )

        self.message(
            "info",
            (
                "completeness probe "
                "mounted"
            ),
        )

        return Reexplode(
            next_fill_shell=(
                _completeness_shell(
                    prior=fill_shell,
                    prefill_note=(
                        self.prefill_note
                    ),
                )
            ),
            # The note appears only as a micro
            # prefill at mount. It is not a
            # committed fill and therefore must
            # not enter changed_fills through
            # the pre-computed overlay.
            pre_computed_fills={},
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats

        signal_packet = dict(
            signal
            or {}
        )

        signal_kind = str(
            signal_packet.get(
                "kind"
            )
            or ""
        ).strip()

        changed = dict(
            fill_data.get(
                "changed_fills"
            )
            or {}
        )
        current = dict(
            fill_data.get(
                "current_fills"
            )
            or {}
        )

        # This path is reached through the widget's
        # declared missing-signal fallback policy.
        # No @signal_catcher is registered for
        # refresh_view.
        if (
            signal_kind
            and not changed
        ):
            self.last_fallback_signal = (
                deepcopy(
                    signal_packet
                )
            )

            self.message(
                "info",
                (
                    "fallback signal "
                    f"{signal_kind}"
                ),
            )

            return Reexplode(
                next_fill_shell=deepcopy(
                    dict(
                        fill_data[
                            "fill_shell"
                        ]
                    )
                ),
                pre_computed_fills=(
                    current
                ),
            )

        token = str(
            current.get(
                "token",
                changed.get(
                    "token",
                    "",
                ),
            )
            or ""
        )

        note = str(
            current.get(
                "note",
                changed.get(
                    "note",
                    "",
                ),
            )
            or ""
        )

        if token != str(
            self.required_token
        ):
            self.saw_rejected_token = (
                True
            )
            self.last_rejected_snapshot = (
                deepcopy(
                    current
                )
            )

            self.message(
                "error",
                (
                    "token must equal "
                    f"{self.required_token!r}"
                ),
            )

            return Reexplode(
                next_fill_shell=deepcopy(
                    dict(
                        fill_data[
                            "fill_shell"
                        ]
                    )
                ),
                # Preserve the complete working
                # snapshot. On the next action,
                # resubmitting the same note
                # with a corrected token should
                # produce:
                #
                # changed_fills={"token": ...}
                pre_computed_fills=(
                    current
                ),
            )

        if getattr(
            self,
            "saw_rejected_token",
            False,
        ):
            changed_keys = set(
                changed
            )

            if changed_keys != {
                "token"
            }:
                raise AssertionError(
                    (
                        "after preserving the "
                        "rejected snapshot, "
                        "only token may appear "
                        "in changed_fills; "
                        f"actual="
                        f"{sorted(changed_keys)!r}"
                    )
                )

        self.accepted_token = token
        self.accepted_note = note
        self.last_changed_fills = deepcopy(
            changed
        )

        self.message(
            "success",
            (
                "completeness probe "
                "accepted"
            ),
        )

        return True


@thinkwidgetTM_config(
    WP_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_RAISE,
    enforce_no_premount_shell=True,
    args={
        "lesson_label": {
            "type": "str",
            "required": True,
        },
        "structured_payload": {
            "type": "dict",
            "required": True,
        },
        "first_choice": {
            "type": "str",
            "required": True,
        },
        "effective_minimum": {
            "type": "int",
            "required": True,
        },
    },
    wires={},
)
class ProgramAuthoringProbeWidget(
    DatumLifecycleWidget
):
    """
    Emit a public mount-time witness for ThinkProgramTM authoring semantics.

    The event deliberately reports only surfaces available to an ordinary
    class-authored widget:

        fill_shell presentation metadata
        authored args

    It therefore proves symbol binding, launch puppeteering, appearance
    overrides, kernel flags, and authoritative lowering
    without reading engine-private state.
    """

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats

        fill_shell = deepcopy(
            dict(
                fill_data[
                    "fill_shell"
                ]
            )
        )

        args = (
            authored_widget_args_v1(
                fill_shell
            )
        )
        kernel = (
            kernel_observation_v1(
                fill_shell
            )
        )

        proof = {
            "presentation": {
                "title": (
                    fill_shell.get(
                        "title"
                    )
                ),
                "tags": list(
                    fill_shell.get(
                        "tags"
                    )
                    or []
                ),
                "system_flags": dict(
                    fill_shell.get(
                        "system_flags"
                    )
                    or {}
                ),
            },
            "args": args,
            "kernel_flags": dict(
                kernel.get(
                    "kernel_flags"
                )
                or {}
            ),
            "authoritative": bool(
                kernel.get(
                    "authoritative",
                    False,
                )
            ),
            "past_wire_keys": sorted(
                dict(
                    kernel.get(
                        "past_wires"
                    )
                    or {}
                )
            ),
        }

        self.last_program_authoring_proof = (
            deepcopy(
                proof
            )
        )

        self._emit(
            {
                "proof": proof,
            },
            name="program_sessions.proof",
        )

        self.message(
            "info",
            (
                "program authoring proof "
                "mounted; acknowledge "
                "to continue"
            ),
        )

        next_shell = deepcopy(
            fill_shell
        )
        next_shell["micros"] = [
            _text_micro(
                "acknowledgement"
            )
        ]

        return Reexplode(
            next_fill_shell=next_shell,
            pre_computed_fills={},
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats

        acknowledgement = str(
            dict(
                fill_data.get(
                    "changed_fills"
                )
                or {}
            ).get(
                "acknowledgement"
            )
            or ""
        ).strip()

        if not acknowledgement:
            self.message(
                "error",
                (
                    "acknowledgement "
                    "is required"
                ),
            )

            return Reexplode(
                next_fill_shell=deepcopy(
                    dict(
                        fill_data[
                            "fill_shell"
                        ]
                    )
                ),
                pre_computed_fills=dict(
                    fill_data.get(
                        "current_fills"
                    )
                    or {}
                ),
            )

        self.acknowledgement = (
            acknowledgement
        )

        self.message(
            "success",
            (
                "program authoring proof "
                "acknowledged"
            ),
        )

        return True


dry_run_lib_widgets_flows_WIDGET_CLASSES = (
    NumberGuessWidget,
    DailyNumberWidget,
    CumulativeBoardWidget,
    WiringObserverWidget,
    InductiveCompletenessWidget,
    ProgramAuthoringProbeWidget,
)


__all__ = [
    "dry_run_lib_widgets_flows_WIDGET_CLASSES",
    "CumulativeBoardWidget",
    "DailyNumberWidget",
    "InductiveCompletenessWidget",
    "NumberGuessWidget",
    "ProgramAuthoringProbeWidget",
    "WiringObserverWidget",
    "WA_WIDGET",
    "WB_WIDGET",
    "WC_WIDGET",
    "WD_WIDGET",
    "WE_WIDGET",
    "WP_WIDGET",
]
from __future__ import annotations

"""
P4 — exact ThinkProgramTM wire and arg observation.

What this program proves E2E
----------------------------

1. A widget does not receive one flat global dictionary of prior widget attrs.
   It receives ``fill_shell["args"]["__kernel"]["past_wires"]``, keyed first by
   the authored wire name.

2. The value under a wire name is determined by the registered contract:

       multiplicity="one"  -> one runtime-write row mapping
       multiplicity="many" -> list[runtime-write row mapping]

   An unresolved optional wire is absent.

3. Every row carries the source widget lifecycle value at ``row["value"]``.
   Class-authored state attrs are the flat mapping at
   ``row["value"]["state"]``. Therefore the consumer must know the source
   widget's documented state keys when selecting one attribute, but it can
   inspect or forward the complete state mapping without guessing.

4. ``from={"self": "previous"}`` is authoring shorthand only. At runtime it
   arrives through the same ordinary ``past_wires`` structure under the
   authored wire name ``self_previous``.

5. Authored widget args and wires are separate:

       authored args -> fill_shell["args"] excluding "__kernel"
       runtime wiring -> fill_shell["args"]["__kernel"]["past_wires"]

6. Mount/reexplosion sees both surfaces together. WiringObserverWidget emits a
   ``wiring.proof`` event during mount, so downstream pollers hear the proof
   between the dispatch's controller start and end.

Program flow
------------

    daily
      -> guess (wired from daily)
      -> observer appearance 1
           one_source  = latest daily row
           many_sources = latest daily row + latest guess row
           self_previous absent
      -> observer appearance 2
           same one/many wires
           self_previous = observer appearance 1 row
"""

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import (
    STEP,
    base_widgets,
    message_event,
    program,
    trident,
    wiring_observer_widget,
    wiring_proof_event,
)


WIDGETS = base_widgets()
WIDGETS["guess"]["wires"] = {
    "daily_number": {
        "from": "daily",
        "history": {
            "select": "latest",
            "required": True,
            "max_results": 20,
        },
    },
}
WIDGETS["observer"] = wiring_observer_widget()


PROGRAM = program(
    program_id="dry_run_lib_widgets_flows_p4",
    title="Basic expose P4 — exact wiring observation",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "source_daily",
            "title": "Create a Wb source row",
            "widgets": ["daily"],
            "authoritative": [True],
        },
        {
            "id": "source_guess",
            "title": "Create a Wa source row wired from Wb",
            "widgets": ["guess"],
            "authoritative": [True],
        },
        {
            "id": "observe_one_and_many",
            "title": "Observe one-row and many-row wire containers",
            "widgets": ["observer"],
            "authoritative": [True],
        },
        {
            "id": "observe_self_previous",
            "title": "Observe self-previous through the same runtime grammar",
            "widgets": ["observer"],
            "authoritative": [True],
        },
    ],
)

PUPPET = None

expected_unrolling = [
    STEP(
        expect=trident(
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Enter P4 and mount the daily source widget.",
    ),
    STEP(
        fill={
            "daily": {
                "representative_number": 9,
                "good_day": True,
            }
        },
        expect=trident(
            message_event("daily", level="success", contains="believe"),
            message_event("guess", level="info", contains="started"),
            message_event("guess", level="info", contains="hint"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Persist Wb state and mount Wa, which consumes one Wb wire row.",
    ),
    STEP(
        fill={
            "guess": {
                "guess_1_1": 9,
                "guess_1_2": 3,
                "guess_1_3": 5,
            }
        },
        expect=trident(
            message_event("guess", level="success", contains="correct"),
            wiring_proof_event(
                "observer",
                self_previous_present=False,
            ),
            message_event(
                "observer",
                level="info",
                contains="wiring proof mounted",
            ),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note=(
            "Mount observer #1. one_source is a mapping, many_sources is a "
            "two-row list, and the optional self_previous wire is absent."
        ),
    ),
    STEP(
        fill={
            "observer": {
                "acknowledgement": "first wiring view understood",
            }
        },
        expect=trident(
            message_event(
                "observer",
                level="success",
                contains="acknowledged",
            ),
            wiring_proof_event(
                "observer",
                self_previous_present=True,
            ),
            message_event(
                "observer",
                level="info",
                contains="wiring proof mounted",
            ),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note=(
            "Complete observer #1 and mount observer #2. The authored "
            "self-previous shorthand now materializes as one ordinary row."
        ),
    ),
    STEP(
        fill={
            "observer": {
                "acknowledgement": "self previous wiring understood",
            }
        },
        expect=trident(
            message_event(
                "observer",
                level="success",
                contains="acknowledged",
            ),
            event_kind="ATCOMPLETION",
            finished=True,
        ),
        note="Complete the second observer and P4.",
    ),
]


__all__ = ["PROGRAM", "PUPPET", "expected_unrolling"]
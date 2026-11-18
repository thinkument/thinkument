from __future__ import annotations

"""App-local FunkTM versions used by Program 12.

Every filler routes from ``request.pending_datums`` and each datum's current
active micro grammar. No filler reaches into widget instances, raw engine
state, future spans, or incidental title text.

Receipts are intentionally bounded diagnostic dead data.
"""

from typing import Any, Dict, Mapping

from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    FunkTMRequest,
    FunkTMResult,
    register_chainreactiontm_version,
)


PUZZLE_GENERATOR_FUNK_V1 = (
    "ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.p12.puzzle_generator_funk.v1"
)
PUZZLE_SOLVER_FUNK_V1 = (
    "ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.p12.puzzle_solver_funk.v1"
)


def _active_micros(decl: Mapping[str, Any]) -> list[Dict[str, Any]]:
    datum_args = (
        decl.get("datum_args")
        if isinstance(decl.get("datum_args"), Mapping)
        else {}
    )
    for candidate in (
        datum_args.get("micro_input_fields"),
        datum_args.get("micros"),
        decl.get("micro_input_fields"),
        decl.get("micros"),
    ):
        if isinstance(candidate, list):
            rows = [
                dict(row)
                for row in candidate
                if isinstance(row, Mapping)
            ]
            if rows:
                return rows
    return []


def _allowed_answer(micro: Mapping[str, Any]) -> str | None:
    for validator in list(micro.get("validators") or []):
        if not isinstance(validator, Mapping):
            continue
        path = str(validator.get("path") or "")
        if not path.endswith("validators.choice:in_allowed"):
            continue
        args = validator.get("args")
        args = args if isinstance(args, Mapping) else {}
        options = args.get("options")
        if isinstance(options, list) and options:
            return str(options[0])
    return None


def _active_micro_names(decl: Mapping[str, Any]) -> set[str]:
    return {
        str(micro.get("name") or "").strip()
        for micro in _active_micros(decl)
        if str(micro.get("name") or "").strip()
    }


def _validate_generator_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
    puzzle_text = str(raw.get("puzzle_text", "What is 6 × 7?")).strip()
    if not puzzle_text:
        raise ValueError("puzzle_text must be non-empty")

    return {
        "puzzle_text": puzzle_text,
        "answer_key": int(raw.get("answer_key", 42)),
    }


def _run_generator(request: FunkTMRequest) -> FunkTMResult:
    fill: Dict[str, Any] = {}

    for row in request.pending_datums:
        datum_id = str(row["datum_id"])
        decl = row.get("decl") if isinstance(row.get("decl"), Mapping) else {}
        names = _active_micro_names(decl)
        macro: Dict[str, Any] = {}

        if "puzzle_text" in names:
            macro["puzzle_text"] = request.args["puzzle_text"]
        if "answer_key" in names:
            macro["answer_key"] = request.args["answer_key"]

        if macro:
            fill[datum_id] = macro

    return FunkTMResult(
        fill=fill,
        signal=None,
        receipt={
            "kind": "program12_puzzle_generator_receipt_v1",
            "role": request.role,
            "filled_datums": sorted(fill),
            "history_rows_seen": len(request.history.get("rows") or []),
            "events_seen": len(request.events),
        },
    )


def _validate_solver_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "wrong_first": bool(raw.get("wrong_first", False)),
        "wrong_answer": str(raw.get("wrong_answer", "__wrong__")),
    }


def _run_solver(request: FunkTMRequest) -> FunkTMResult:
    retrying = bool(
        request.semantic_errors_in_row > 0
        or request.last_error
    )
    fill: Dict[str, Any] = {}

    for row in request.pending_datums:
        datum_id = str(row["datum_id"])
        decl = row.get("decl") if isinstance(row.get("decl"), Mapping) else {}
        macro: Dict[str, Any] = {}

        for micro in _active_micros(decl):
            name = str(micro.get("name") or "value")
            allowed = _allowed_answer(micro)

            if name == "approval":
                macro[name] = "approve"
            elif name == "answer":
                macro[name] = (
                    request.args["wrong_answer"]
                    if request.args["wrong_first"] and not retrying
                    else allowed or "42"
                )
            else:
                macro[name] = allowed or "semantically filled"

        if not macro:
            macro = {"value": "semantically filled"}

        fill[datum_id] = macro

    return FunkTMResult(
        fill=fill,
        signal=None,
        receipt={
            "kind": "program12_puzzle_solver_receipt_v1",
            "role": request.role,
            "filled_datums": sorted(fill),
            "retrying_after_semantic_error": retrying,
            "semantic_errors_in_row_seen": request.semantic_errors_in_row,
            "had_last_error": bool(request.last_error),
            "history_rows_seen": len(request.history.get("rows") or []),
            "events_seen": len(request.events),
        },
    )


def register_program12_funked_fillers_v1() -> None:
    register_chainreactiontm_version(
        name=PUZZLE_GENERATOR_FUNK_V1,
        run=_run_generator,
        validate_args=_validate_generator_args,
        replace=True,
    )
    register_chainreactiontm_version(
        name=PUZZLE_SOLVER_FUNK_V1,
        run=_run_solver,
        validate_args=_validate_solver_args,
        replace=True,
    )


__all__ = [
    "PUZZLE_GENERATOR_FUNK_V1",
    "PUZZLE_SOLVER_FUNK_V1",
    "register_program12_funked_fillers_v1",
]
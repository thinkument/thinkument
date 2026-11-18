from __future__ import annotations

"""Packito chainreactionTM fillers.

The fillers route only from the public request: pending datums, active micro
schemas, bounded history/events, semantic-error context, role, and app args.
They never reach into widget instances or future spans.
"""

from typing import Any, Dict, Mapping

from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    FunkTMRequest,
    FunkTMResult,
    register_chainreactiontm_version,
)


PUZZLE_SEED_FUNK_V1 = "packito.funk.puzzle_seed.v1"
PUZZLE_SOLVER_FUNK_V1 = "packito.funk.puzzle_solver.v1"


def _active_micros(decl: Mapping[str, Any]) -> list[Dict[str, Any]]:
    datum_args = decl.get("datum_args")
    datum_args = datum_args if isinstance(datum_args, Mapping) else {}

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


def _allowed_choice(micro: Mapping[str, Any]) -> str | None:
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


def _validate_seed_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
    text = str(
        raw.get("puzzle_text", "What is 6 x 7?")
    ).strip()

    if not text:
        raise ValueError("puzzle_text must be non-empty")

    return {
        "puzzle_text": text,
        "answer_key": int(raw.get("answer_key", 42)),
    }


def _run_seed(request: FunkTMRequest) -> FunkTMResult:
    fill: Dict[str, Any] = {}

    for row in request.pending_datums:
        datum_id = str(row["datum_id"])

        decl = (
            row.get("decl")
            if isinstance(row.get("decl"), Mapping)
            else {}
        )

        names = {
            str(micro.get("name") or "")
            for micro in _active_micros(decl)
        }

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
            "kind": "packito_puzzle_seed_receipt_v1",
            "role": request.role,
            "filled_datums": sorted(fill),
            "history_rows_seen": len(
                request.history.get("rows") or []
            ),
            "events_seen": len(request.events),
        },
    )


def _validate_solver_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "wrong_first": bool(raw.get("wrong_first", False)),
        "wrong_answer": str(
            raw.get("wrong_answer", "__wrong__")
        ),
    }


def _run_solver(request: FunkTMRequest) -> FunkTMResult:
    retrying = bool(
        request.semantic_errors_in_row > 0
        or request.last_error
    )

    fill: Dict[str, Any] = {}

    for row in request.pending_datums:
        datum_id = str(row["datum_id"])

        decl = (
            row.get("decl")
            if isinstance(row.get("decl"), Mapping)
            else {}
        )

        macro: Dict[str, Any] = {}

        for micro in _active_micros(decl):
            name = str(micro.get("name") or "value")

            if name == "approval":
                macro[name] = "approve"

            elif name == "answer":
                expected = _allowed_choice(micro) or "42"

                macro[name] = (
                    request.args["wrong_answer"]
                    if (
                        request.args["wrong_first"]
                        and not retrying
                    )
                    else expected
                )

            else:
                macro[name] = (
                    _allowed_choice(micro)
                    or "generated"
                )

        if macro:
            fill[datum_id] = macro

    return FunkTMResult(
        fill=fill,
        signal=None,
        receipt={
            "kind": "packito_puzzle_solver_receipt_v1",
            "role": request.role,
            "filled_datums": sorted(fill),
            "retrying_after_semantic_error": retrying,
            "semantic_errors_in_row_seen": (
                request.semantic_errors_in_row
            ),
            "had_last_error": bool(request.last_error),
            "history_rows_seen": len(
                request.history.get("rows") or []
            ),
            "events_seen": len(request.events),
        },
    )


def register_packito_funked_fillers_v1() -> None:
    """Register every chainreactionTM filler owned by Packito."""

    register_chainreactiontm_version(
        name=PUZZLE_SEED_FUNK_V1,
        run=_run_seed,
        validate_args=_validate_seed_args,
        replace=True,
    )

    register_chainreactiontm_version(
        name=PUZZLE_SOLVER_FUNK_V1,
        run=_run_solver,
        validate_args=_validate_solver_args,
        replace=True,
    )


def register_funks_v1() -> None:
    """Backward-compatible alias for the Packito funk registrar."""

    register_packito_funked_fillers_v1()


__all__ = [
    "PUZZLE_SEED_FUNK_V1",
    "PUZZLE_SOLVER_FUNK_V1",
    "register_packito_funked_fillers_v1",
    "register_funks_v1",
]
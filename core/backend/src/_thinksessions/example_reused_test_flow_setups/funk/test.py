from __future__ import annotations

"""
Semantic-shell-aware FunkTM fillers used by the final E2E demo.

The primary version routes exclusively from the active datum shell. It reads:

- micro name and type;
- micro args;
- attached micro validator path and args;
- datum-level macro validator path and args;
- current semantic error feedback;
- role-modulated ctx and bounded readable history supplied by chainreactionTM.

Four registered policies make the operational space explicit:

``demo.semantic_shell_funk.v1``
    Always produces values intended to satisfy every demo shell.

``demo.semantic_shell_retry_once_funk.v1``
    Deliberately fails the first attempt on each new shell, then uses
    ``last_error`` / ``semantic_errors_in_row`` to repair the next attempt.

``demo.semantic_shell_always_invalid_funk.v1``
    Deliberately produces invalid values and is used to prove the semantic
    retry cap.

``demo.semantic_shell_signal_funk.v1``
    Uses ordinary fill on the describe shell, then completes the confirmation
    shell with a generated custom signal rather than a fill.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping, Sequence

from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    FunkTMRequest,
    FunkTMResult,
    register_chainreactiontm_version,
)


FUNK_VERSION = "demo.semantic_shell_funk.v1"
FUNK_RETRY_VERSION = "demo.semantic_shell_retry_once_funk.v1"
FUNK_ALWAYS_INVALID_VERSION = "demo.semantic_shell_always_invalid_funk.v1"
FUNK_SIGNAL_VERSION = "demo.semantic_shell_signal_funk.v1"

_DEMO_FUNK_REQUEST_LOG: list[FunkTMRequest] = []


def clear_demo_funk_request_log_v1() -> None:
    _DEMO_FUNK_REQUEST_LOG.clear()


def demo_funk_request_log_v1() -> list[FunkTMRequest]:
    return list(_DEMO_FUNK_REQUEST_LOG)


def validate_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "default_text": str(
            raw.get("default_text") or "Generated semantic value"
        ),
        "default_integer": int(raw.get("default_integer", 3)),
        "default_number": float(raw.get("default_number", 8)),
        "default_boolean": bool(raw.get("default_boolean", True)),
    }


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


def _macro_validator_rows(decl: Mapping[str, Any]) -> list[Dict[str, Any]]:
    datum_args = (
        decl.get("datum_args")
        if isinstance(decl.get("datum_args"), Mapping)
        else {}
    )
    for candidate in (
        datum_args.get("macro_validation_lambdas"),
        decl.get("macro_validation_lambdas"),
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


def _validator_rows(micro: Mapping[str, Any]) -> list[Dict[str, Any]]:
    raw = micro.get("validators")
    if not isinstance(raw, list):
        return []
    return [
        dict(row)
        for row in raw
        if isinstance(row, Mapping)
    ]


def _merged_semantics(micro: Mapping[str, Any]) -> Dict[str, Any]:
    args = (
        dict(micro.get("args") or {})
        if isinstance(micro.get("args"), Mapping)
        else {}
    )
    semantics = dict(args)

    for validator in _validator_rows(micro):
        v_args = validator.get("args")
        if isinstance(v_args, Mapping):
            semantics.update(dict(v_args))

        path = str(validator.get("path") or "")
        if path:
            semantics.setdefault("validator_paths", []).append(path)

    return semantics


def _first_option(semantics: Mapping[str, Any]) -> str:
    options = semantics.get("options")
    if isinstance(options, Sequence) and not isinstance(
        options,
        (str, bytes, bytearray),
    ):
        values = [str(value) for value in options]
        if values:
            for preferred in (
                "accept",
                "approve",
                "released",
                "yes",
            ):
                if preferred in values:
                    return preferred
            return values[0]
    return "yes"


def _text_for_semantics(
    *,
    name: str,
    semantics: Mapping[str, Any],
    default_text: str,
) -> str:
    minimum = int(
        semantics.get(
            "min_words",
            semantics.get("minimum_words", 1),
        )
        or 1
    )
    seed = {
        "description": "Complete deterministic event surface proof",
        "long_description": (
            "Describe every downstream event surface branch completely"
        ),
        "comment": "Reviewed and approved",
        "requirement": (
            "Implement deterministic bounded event broadcasting"
        ),
        "note": "Optional support note",
    }.get(name, default_text)

    words = seed.split()
    while len(words) < minimum:
        words.append("complete")
    return " ".join(words)


def _valid_value_for_micro(
    micro: Mapping[str, Any],
    args: Mapping[str, Any],
) -> Any:
    name = str(micro.get("name") or "value")
    typ = str(micro.get("type") or micro.get("kind") or "text").lower()
    semantics = _merged_semantics(micro)

    if typ == "email":
        return "demo@example.com"
    if typ == "date":
        return "2026-07-13"
    if typ == "code":
        return "value = 1\nprint(value)"
    if typ == "latex_math":
        return "x^2 + y^2"
    if typ == "slug":
        return "event-surface-proof"
    if typ == "image_url":
        return "https://example.com/image.png"
    if typ == "image_filepath":
        return "./images/example.png"
    if typ == "select":
        return _first_option(semantics)
    if typ in {"checkbox", "boolean", "bool", "hidden-pause"}:
        return args["default_boolean"]
    if typ in {"integer", "int"}:
        minimum = int(
            semantics.get(
                "min_value",
                semantics.get("minimum", args["default_integer"]),
            )
        )
        maximum = int(
            semantics.get(
                "max_value",
                semantics.get("maximum", minimum),
            )
        )
        return min(maximum, max(minimum, args["default_integer"]))
    if typ in {"number", "float"}:
        minimum = float(
            semantics.get(
                "min_value",
                semantics.get("minimum", args["default_number"]),
            )
        )
        maximum = float(
            semantics.get(
                "max_value",
                semantics.get("maximum", minimum),
            )
        )
        return min(maximum, max(minimum, args["default_number"]))
    if typ == "object-json":
        return {
            "generated_by": FUNK_VERSION,
            "micro_name": name,
            "semantic_name": semantics.get("semantic_name"),
        }

    return _text_for_semantics(
        name=name,
        semantics=semantics,
        default_text=args["default_text"],
    )


def _invalid_value_for_micro(micro: Mapping[str, Any]) -> Any:
    typ = str(micro.get("type") or micro.get("kind") or "text").lower()
    semantics = _merged_semantics(micro)

    if typ in {"text", "textarea", "code", "latex_math"}:
        return ""
    if typ == "slug":
        return "INVALID SLUG"
    if typ == "email":
        return "not-an-email"
    if typ == "date":
        return "not-a-date"
    if typ == "image_url":
        return "not-a-url"
    if typ == "image_filepath":
        return "not-a-path"
    if typ == "select":
        return "__not_allowed__"
    if typ in {"checkbox", "boolean", "bool", "hidden-pause"}:
        return None
    if typ in {"integer", "int", "number", "float"}:
        maximum = semantics.get("max_value", semantics.get("maximum", 10))
        try:
            return float(maximum) + 1000
        except Exception:
            return "not-a-number"
    if typ == "object-json":
        return {"invalid_policy_marker": True}
    return ""


def _build_fill(
    request: FunkTMRequest,
    *,
    invalid: bool,
    exclude_datum_ids: set[str] | None = None,
) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    fill: Dict[str, Any] = {}
    shell_proofs: list[Dict[str, Any]] = []
    excluded = set(exclude_datum_ids or set())

    for pending in request.pending_datums:
        datum_id = str(pending["datum_id"])
        if datum_id in excluded:
            continue

        decl = (
            pending.get("decl")
            if isinstance(pending.get("decl"), Mapping)
            else {}
        )
        micros = _active_micros(decl)
        macro: Dict[str, Any] = {}

        for micro in micros:
            name = str(micro.get("name") or "value")
            macro[name] = (
                _invalid_value_for_micro(micro)
                if invalid
                else _valid_value_for_micro(micro, request.args)
            )

        if not macro:
            macro = {
                "value": (
                    ""
                    if invalid
                    else request.args["default_text"]
                )
            }

        fill[datum_id] = macro
        shell_proofs.append(
            {
                "datum_id": datum_id,
                "micro_names": [
                    str(micro.get("name") or "value")
                    for micro in micros
                ],
                "micro_types": [
                    str(micro.get("type") or "text")
                    for micro in micros
                ],
                "validator_paths": [
                    str(validator.get("path") or "")
                    for micro in micros
                    for validator in _validator_rows(micro)
                    if validator.get("path")
                ],
                "macro_validator_paths": [
                    str(validator.get("path") or "")
                    for validator in _macro_validator_rows(decl)
                    if validator.get("path")
                ],
            }
        )

    return fill, shell_proofs


def _receipt(
    request: FunkTMRequest,
    *,
    kind: str,
    fill: Mapping[str, Any],
    shell_proofs: list[Mapping[str, Any]],
    signal: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "kind": kind,
        "role": request.role,
        "filled_datums": sorted(fill),
        "signal": None if signal is None else dict(signal),
        "shell_proofs": [dict(row) for row in shell_proofs],
        "semantic_errors_in_row_seen": request.semantic_errors_in_row,
        "had_last_error": bool(request.last_error),
        "history": {
            "readable_roles": list(
                request.history.get("readable_roles") or []
            ),
            "row_count": len(request.history.get("rows") or []),
            "truncated_by_size": bool(
                request.history.get("truncated_by_size", False)
            ),
        },
        "events": {
            "count": len(request.events),
            "kinds": [
                str(event.get("kind") or "")
                for event in list(request.events)
                if isinstance(event, Mapping)
            ],
        },
    }


def run(request: FunkTMRequest) -> FunkTMResult:
    _DEMO_FUNK_REQUEST_LOG.append(request)
    fill, shell_proofs = _build_fill(request, invalid=False)
    return FunkTMResult(
        fill=fill,
        signal=None,
        receipt=_receipt(
            request,
            kind="demo_semantic_shell_funk_receipt_v1",
            fill=fill,
            shell_proofs=shell_proofs,
        ),
    )


def run_retry_once(request: FunkTMRequest) -> FunkTMResult:
    _DEMO_FUNK_REQUEST_LOG.append(request)
    should_fail = not request.last_error and request.semantic_errors_in_row == 0
    fill, shell_proofs = _build_fill(request, invalid=should_fail)
    return FunkTMResult(
        fill=fill,
        signal=None,
        receipt=_receipt(
            request,
            kind=(
                "demo_semantic_shell_retry_intentional_failure_v1"
                if should_fail
                else "demo_semantic_shell_retry_repair_v1"
            ),
            fill=fill,
            shell_proofs=shell_proofs,
        ),
    )


def run_always_invalid(request: FunkTMRequest) -> FunkTMResult:
    _DEMO_FUNK_REQUEST_LOG.append(request)
    fill, shell_proofs = _build_fill(request, invalid=True)
    return FunkTMResult(
        fill=fill,
        signal=None,
        receipt=_receipt(
            request,
            kind="demo_semantic_shell_always_invalid_receipt_v1",
            fill=fill,
            shell_proofs=shell_proofs,
        ),
    )


def run_signal(request: FunkTMRequest) -> FunkTMResult:
    _DEMO_FUNK_REQUEST_LOG.append(request)

    signal_target: str | None = None
    signal_proof: Dict[str, Any] | None = None
    for pending in request.pending_datums:
        datum_id = str(pending["datum_id"])
        decl = (
            pending.get("decl")
            if isinstance(pending.get("decl"), Mapping)
            else {}
        )
        names = {
            str(micro.get("name") or "")
            for micro in _active_micros(decl)
        }
        if datum_id == "complex" and "decision" in names:
            signal_target = datum_id
            signal_proof = {
                "datum_id": datum_id,
                "micro_names": sorted(names),
                "mode": "signal-only-confirmation",
            }
            break

    excluded = {signal_target} if signal_target else set()
    fill, shell_proofs = _build_fill(
        request,
        invalid=False,
        exclude_datum_ids=excluded,
    )

    signal = None
    if signal_target is not None:
        signal = {
            "datum_id": signal_target,
            "kind": "accept_generated",
            "info": {
                "generated_by": FUNK_SIGNAL_VERSION,
                "mode": "signal-only",
            },
        }
        shell_proofs.append(dict(signal_proof or {}))

    return FunkTMResult(
        fill=fill,
        signal=signal,
        receipt=_receipt(
            request,
            kind="demo_semantic_shell_signal_funk_receipt_v1",
            fill=fill,
            shell_proofs=shell_proofs,
            signal=signal,
        ),
    )


def register_demo_semantic_shell_funk_v1() -> None:
    registrations = (
        (FUNK_VERSION, run),
        (FUNK_RETRY_VERSION, run_retry_once),
        (FUNK_ALWAYS_INVALID_VERSION, run_always_invalid),
        (FUNK_SIGNAL_VERSION, run_signal),
    )
    for name, fn in registrations:
        register_chainreactiontm_version(
            name=name,
            run=fn,
            validate_args=validate_args,
            replace=True,
        )


__all__ = [
    "FUNK_ALWAYS_INVALID_VERSION",
    "FUNK_RETRY_VERSION",
    "FUNK_SIGNAL_VERSION",
    "FUNK_VERSION",
    "clear_demo_funk_request_log_v1",
    "demo_funk_request_log_v1",
    "register_demo_semantic_shell_funk_v1",
    "run",
    "run_always_invalid",
    "run_retry_once",
    "run_signal",
    "validate_args",
]
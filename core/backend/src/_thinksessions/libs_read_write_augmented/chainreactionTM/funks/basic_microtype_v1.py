from __future__ import annotations

from typing import Any, Dict, Mapping

from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    FunkTMRequest,
    FunkTMResult,
    register_chainreactiontm_version,
)


def validate_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "text_value": str(raw.get("text_value", "x")),
        "int_value": int(raw.get("int_value", 1)),
        "number_value": float(raw.get("number_value", 1.0)),
        "boolean_value": bool(raw.get("boolean_value", True)),
    }


def _micro_value(micro: Mapping[str, Any], args: Mapping[str, Any]) -> Any:
    typ = str(micro.get("type") or micro.get("kind") or "text").lower()

    if typ in {"int", "integer"}:
        return args["int_value"]
    if typ in {"number", "float"}:
        return args["number_value"]
    if typ in {"bool", "boolean"}:
        return args["boolean_value"]

    return args["text_value"]


def run(request: FunkTMRequest) -> FunkTMResult:
    fill: Dict[str, Any] = {}

    for row in request.pending_datums:
        datum_id = str(row["datum_id"])
        decl = row.get("decl") if isinstance(row.get("decl"), Mapping) else {}
        datum_args = decl.get("datum_args") if isinstance(decl.get("datum_args"), Mapping) else {}

        micros = (
            datum_args.get("micro_input_fields")
            or datum_args.get("micros")
            or []
        )

        if not isinstance(micros, list) or not micros:
            fill[datum_id] = {"value": request.args["text_value"]}
            continue

        macro: Dict[str, Any] = {}
        for micro in micros:
            if not isinstance(micro, Mapping):
                continue
            name = str(micro.get("name") or "value")
            macro[name] = _micro_value(micro, request.args)

        fill[datum_id] = macro

    return FunkTMResult(
        fill=fill,
        signal=None,
        receipt={
            "kind": "basic_microtype_v1_receipt",
            "filled_datums": sorted(fill.keys()),
        },
    )


def register() -> None:
    register_chainreactiontm_version(
        name="basic_microtype_v1",
        run=run,
        validate_args=validate_args,
        replace=True,
    )
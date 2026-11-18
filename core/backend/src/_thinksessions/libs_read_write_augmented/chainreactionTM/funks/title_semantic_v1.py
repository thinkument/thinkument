from __future__ import annotations

import re
from typing import Any, Dict, Mapping

from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    FunkTMRequest,
    FunkTMResult,
    register_chainreactiontm_version,
)


def validate_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "default_text": str(raw.get("default_text", "semantically filled")),
        "min_value": int(raw.get("min_value", 0)),
        "max_value": int(raw.get("max_value", 999)),
    }


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", text or "")


def _value_for_title(title: str, micro: Mapping[str, Any], args: Mapping[str, Any]) -> Any:
    lower = title.lower()
    micro_name = str(micro.get("name") or "").lower()
    typ = str(micro.get("type") or "text").lower()

    if "word count" in lower or "num words" in lower or micro_name in {"num_words", "word_count"}:
        return len(_words(title))

    if "minimum" in lower or " min " in f" {lower} " or micro_name == "min":
        return args["min_value"]

    if "maximum" in lower or " max " in f" {lower} " or micro_name == "max":
        return args["max_value"]

    if typ in {"int", "integer", "number", "float"}:
        return args["max_value"] if "max" in lower else args["min_value"]

    return args["default_text"]


def run(request: FunkTMRequest) -> FunkTMResult:
    fill: Dict[str, Any] = {}

    for row in request.pending_datums:
        datum_id = str(row["datum_id"])
        decl = row.get("decl") if isinstance(row.get("decl"), Mapping) else {}
        datum_args = decl.get("datum_args") if isinstance(decl.get("datum_args"), Mapping) else {}
        title = str(datum_args.get("title") or decl.get("title") or datum_id)

        micros = (
            datum_args.get("micro_input_fields")
            or datum_args.get("micros")
            or []
        )

        if not isinstance(micros, list) or not micros:
            fill[datum_id] = {"value": _value_for_title(title, {}, request.args)}
            continue

        macro: Dict[str, Any] = {}
        for micro in micros:
            if not isinstance(micro, Mapping):
                continue
            name = str(micro.get("name") or "value")
            macro[name] = _value_for_title(title, micro, request.args)

        fill[datum_id] = macro

    return FunkTMResult(
        fill=fill,
        signal=None,
        receipt={
            "kind": "title_semantic_v1_receipt",
            "filled_datums": sorted(fill.keys()),
            "semantic_errors_in_row_seen": request.semantic_errors_in_row,
        },
    )


def register() -> None:
    register_chainreactiontm_version(
        name="title_semantic_v1",
        run=run,
        validate_args=validate_args,
        replace=True,
    )
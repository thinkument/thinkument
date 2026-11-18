from __future__ import annotations

"""
authoring_funneling.c_one_JSONic_programming_language_widgets_inline_or_published_imported.extractor
====================================================================================================

Extracts inline JSONic widget manifests from program definitions, computes
content-addressed synthetic runtime identifiers, compiles in-memory classes,
and produces a lowered program suitable for typed D-binding compilation.
"""

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Dict, List, Mapping, Optional, Tuple

from bindings2bindingsTM import CompilationError
from ..b_typed_JSON_widget_declaration.manifest import normalize_manifest_v1
from ..b_typed_JSON_widget_declaration.factory import (
    PreparedJsonWidgetV1,
    prepare_json_widget_v1,
    register_prepared_json_widget_v1,
)


@dataclass(frozen=True)
class InlineWidgetExtractionResult:
    """The result of extracting inline widgets from an authored program."""
    program: Dict[str, Any]
    prepared_artifacts: List[PreparedJsonWidgetV1]
    inline_metadata: Dict[str, Dict[str, Any]]


def compute_inline_widget_synthetic_id(manifest: Mapping[str, Any]) -> Tuple[str, str, str]:
    """Compute canonical JSON, SHA256 fingerprint, and synthetic runtime ID for a manifest.

    Returns:
        (canonical_json, fingerprint, synthetic_id)
    """
    manifest_dict = normalize_manifest_v1(manifest)
    manifest_json = json.dumps(
        manifest_dict,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    )
    fingerprint = sha256(
        ('json_widget_v1\0' + manifest_json).encode('utf-8')
    ).hexdigest()
    synthetic_id = f"synthetic_inline_{fingerprint[:16]}"
    return manifest_json, fingerprint, synthetic_id


def extract_inline_widgets_v1(
    program: Mapping[str, Any],
    *,
    register_in_kernel: bool = False,
    vocab: Optional[Any] = None,
    vendor_bindings: Optional[Any] = None,
) -> InlineWidgetExtractionResult:
    """Scan program widgets for inline JSON manifests, prepare in-memory classes,
    and replace manifest objects with their synthetic runtime identifiers.

    Args:
        program: The input program dictionary (e.g. kind=unified_typed_jsonic_think_program_v1).
        register_in_kernel: Whether to immediately publish prepared classes to the process kernel.
        vocab: Optional custom FunctionVocab for JSONfnchainTM.
        vendor_bindings: Optional trusted host vendor bindings.

    Returns:
        InlineWidgetExtractionResult containing the rewritten program, list of
        prepared artifacts, and metadata dictionary keyed by logical widget ID.
    """
    if not isinstance(program, Mapping):
        raise CompilationError("invalid_program", ("P",))

    p = deepcopy(dict(program))
    try:
        widgets = p["run"]["program"]["widgets"]
    except (KeyError, TypeError) as exc:
        raise CompilationError("invalid_program", ("P",)) from exc

    if not isinstance(widgets, Mapping):
        raise CompilationError("invalid_program_structure", ("P", "widgets"))

    prepared_artifacts: List[PreparedJsonWidgetV1] = []
    inline_metadata: Dict[str, Dict[str, Any]] = {}
    dedup_by_id: Dict[str, PreparedJsonWidgetV1] = {}

    for logical_id, declaration in widgets.items():
        if not isinstance(declaration, Mapping):
            continue

        raw_manifest = None
        if isinstance(declaration.get("widget"), Mapping):
            raw_manifest = declaration["widget"]
        elif isinstance(declaration.get("inline_widget"), Mapping):
            raw_manifest = declaration["inline_widget"]

        if raw_manifest is None:
            # Widget is referenced by published shorthand string or Python class
            continue

        manifest_kind = raw_manifest.get("kind")
        if manifest_kind != "json_widget_v1":
            raise CompilationError(
                "unsupported_inline_widget_kind",
                ("P", "widgets", logical_id, "kind"),
            )

        try:
            manifest_json, fingerprint, synthetic_id = compute_inline_widget_synthetic_id(
                raw_manifest
            )
        except Exception as exc:
            raise CompilationError(
                "invalid_inline_widget_manifest",
                ("P", "widgets", logical_id),
            ) from exc

        if synthetic_id not in dedup_by_id:
            try:
                artifact = prepare_json_widget_v1(
                    raw_manifest,
                    widget_id=synthetic_id,
                    vocab=vocab,
                    vendor_bindings=vendor_bindings,
                )
            except Exception as exc:
                raise CompilationError(
                    "inline_widget_preparation_failed",
                    ("P", "widgets", logical_id),
                ) from exc

            if register_in_kernel:
                register_prepared_json_widget_v1(artifact)

            dedup_by_id[synthetic_id] = artifact
            prepared_artifacts.append(artifact)
        else:
            artifact = dedup_by_id[synthetic_id]

        # Rewrite program declaration so widget points to synthetic_id string
        declaration_copy = dict(declaration)
        declaration_copy["widget"] = synthetic_id
        declaration_copy.pop("inline_widget", None)
        widgets[logical_id] = declaration_copy

        inline_metadata[logical_id] = {
            "synthetic_id": synthetic_id,
            "fingerprint": fingerprint,
            "manifest_name": artifact.widget_class.__name__,
            "manifest": normalize_manifest_v1(raw_manifest),
        }

    return InlineWidgetExtractionResult(
        program=p,
        prepared_artifacts=prepared_artifacts,
        inline_metadata=inline_metadata,
    )


__all__ = [
    "InlineWidgetExtractionResult",
    "compute_inline_widget_synthetic_id",
    "extract_inline_widgets_v1",
]

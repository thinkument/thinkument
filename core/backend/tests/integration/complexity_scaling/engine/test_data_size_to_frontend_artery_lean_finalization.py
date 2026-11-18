"""
Data-weight regression tests for the backend-to-frontend session artery.

These tests validate the intended roled-interaction response law:

- Rendering may produce HTML because HTML is the frontend product.
- The response should not also return raw controller ctx when callers explicitly
  choose include_ctx=False.
- A tiny ctx_report should remain available for logs/debug/UI bookkeeping.
- Expert/debug callers can still opt into raw ctx by passing include_ctx=True.

Boundary:

This sheet tests the response-shape policy itself with synthetic large ctx
objects. Full controller/render integration belongs in the page-flow/session
integration tests. Keeping this sheet focused makes the data-weight law stable
even if renderer internals evolve.

Pedagogical law:

    HTML is product payload.
    Raw ctx is backend/controller payload.
    Browser/service render paths should not receive both unless they explicitly
    opt into ctx for expert/debug use.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Dict


def _compact_json_size(obj: Any) -> int:
    return len(json.dumps(obj, separators=(",", ":"), sort_keys=True, default=repr))


def _make_large_ctx(
    *,
    emitted_forms: int = 40,
    fields_per_form: int = 8,
    payload_chars: int = 256,
) -> Dict[str, Any]:
    """
    Build a deliberately heavy controller ctx.

    This ctx contains exactly the kinds of data that should not be duplicated
    into a rendered frontend response:

    - historical multiframespecs
    - prefill values
    - fill values
    - datum_widget_fills
    - nested metadata/help payloads

    The tests below verify that include_ctx=False removes this object and
    replaces it with a tiny ctx_report containing only identity/count metadata.
    """

    forms_emitted: Dict[str, Any] = {}
    form_prefills: Dict[str, Any] = {}
    form_fills: Dict[str, Any] = {}
    datum_widget_fills: Dict[str, Any] = {}

    for form_idx in range(emitted_forms):
        form_id = f"form_{form_idx:04d}"
        fields = []

        for field_idx in range(fields_per_form):
            field_id = f"{form_id}.field_{field_idx}"
            fields.append(
                {
                    "id": field_id,
                    "label": f"Field {field_idx}",
                    "type": "text",
                    "help": "h" * payload_chars,
                    "metadata": {
                        "payload": "m" * payload_chars,
                    },
                }
            )
            form_prefills[field_id] = {
                "value": "p" * payload_chars,
                "source": "test",
            }
            form_fills[field_id] = {
                "value": "f" * payload_chars,
                "source": "test",
            }
            datum_widget_fills[field_id] = "v" * payload_chars

        forms_emitted[form_id] = {
            "id": form_id,
            "title": f"Form {form_id}",
            "fields": fields,
        }

    pending_multiframespec_id = f"form_{emitted_forms - 1:04d}"

    return {
        # Intentionally set to render. Some tests use an outer dispatch event of
        # submit/noop to prove the response event is authoritative for ctx_report.
        "event_kind": "render",
        "cursor": {
            "index": emitted_forms - 1,
            "total": emitted_forms,
        },
        "form_id": pending_multiframespec_id,
        "app_form_id": pending_multiframespec_id,
        "frame_id": "frame_main",
        "current_frame_id": "frame_main",
        "span_id": "span_main",
        "current_span": "span_main",
        "datum_widgets_on_this_span": [
            f"{pending_multiframespec_id}.field_{idx}"
            for idx in range(fields_per_form)
        ],
        "state": {
            "forms_emitted": forms_emitted,
            "forms_emitted_order": list(forms_emitted),
            "form_prefills": form_prefills,
            "form_fills": form_fills,
            "datum_widget_fills": datum_widget_fills,
        },
        "last_error": None,
    }


def _make_html(payload_chars: int = 10_000) -> str:
    """
    Model rendered HTML as the large-but-legitimate frontend product.

    The lean-response law is not "small at all costs." It is:

        send HTML when HTML is the product;
        do not also send raw backend ctx unless explicitly requested.
    """

    return (
        "<!doctype html>"
        "<html>"
        "<head><title>Thinkument</title></head>"
        "<body>"
        "<main>"
        f"{'x' * payload_chars}"
        "</main>"
        "</body>"
        "</html>"
    )


def _make_ui_ctx_report_v1(
    ctx: Mapping[str, Any] | None,
    *,
    event_kind: Any = None,
) -> Dict[str, Any]:
    """
    Local contract model for the production ctx_report shape.

    The authoritative event kind is the outer dispatch response event. A stale
    ctx["event_kind"] must not override out["event_kind"].
    """

    ctx = ctx if isinstance(ctx, Mapping) else {}
    state = ctx.get("state") if isinstance(ctx.get("state"), Mapping) else {}
    cursor = ctx.get("cursor") if isinstance(ctx.get("cursor"), Mapping) else {}

    return {
        "kind": "ui_ctx_report_v1",
        "event_kind": event_kind if event_kind is not None else ctx.get("event_kind"),
        "cursor": {
            "index": cursor.get("index"),
            "total": cursor.get("total"),
        },
        "form_id": ctx.get("form_id") or ctx.get("app_form_id"),
        "frame_id": ctx.get("frame_id") or ctx.get("current_frame_id"),
        "span_id": ctx.get("span_id") or ctx.get("current_span") or ctx.get("current_span_id"),
        "datum_widgets_on_this_span_count": len(ctx.get("datum_widgets_on_this_span") or []),
        "state_counts": {
            "form_prefills": len(state.get("form_prefills") or {}),
            "form_fills": len(state.get("form_fills") or {}),
            "forms_emitted": len(state.get("forms_emitted") or {}),
            "datum_widget_fills": len(state.get("datum_widget_fills") or {}),
        },
        "last_error": ctx.get("last_error"),
    }


def _apply_frontend_artery_policy(
    raw_out: Dict[str, Any],
    *,
    render: bool,
    include_ctx: bool,
) -> Dict[str, Any]:
    """
    Contract model of dispatch_ui_action response policy.

    The production function should:

    - include html when render=True;
    - preserve ctx when include_ctx=True;
    - omit ctx and include ctx_report when include_ctx=False.

    This local model keeps the complexity sheet independent from controller and
    renderer fixtures. A smaller number of full integration tests should cover
    the production dispatch function directly.
    """

    out = dict(raw_out)

    if render and "content" not in out:
        out["content"] = _make_html()

    if not include_ctx:
        ctx = out.get("ctx") or {}
        out["ctx_report"] = _make_ui_ctx_report_v1(
            ctx,
            event_kind=out.get("event_kind"),
        )
        out.pop("ctx", None)

    return out


def test_frontend_dispatch_rendered_response_can_omit_raw_ctx() -> None:
    """
    Main artery invariant:

    The browser/service path can ask for rendered HTML without receiving raw
    controller ctx alongside it.
    """

    ctx = _make_large_ctx(emitted_forms=50, fields_per_form=8, payload_chars=256)

    raw_out = {
        "ok": True,
        "event_kind": "render",
        "ctx": ctx,
        "content": _make_html(payload_chars=12_000),
    }

    lean = _apply_frontend_artery_policy(raw_out, render=True, include_ctx=False)

    assert lean["ok"] is True
    assert "content" in lean
    assert "ctx" not in lean
    assert "ctx_report" in lean

    report = lean["ctx_report"]
    assert report["kind"] == "ui_ctx_report_v1"
    assert report["event_kind"] == "render"
    assert report["form_id"] == "form_0049"
    assert report["frame_id"] == "frame_main"
    assert report["span_id"] == "span_main"
    assert report["datum_widgets_on_this_span_count"] == 8
    assert report["state_counts"]["forms_emitted"] == 50
    assert report["state_counts"]["form_prefills"] == 400
    assert report["state_counts"]["form_fills"] == 400
    assert report["state_counts"]["datum_widget_fills"] == 400


def test_frontend_dispatch_include_ctx_true_preserves_raw_ctx_for_expert_callers() -> None:
    """
    Compatibility invariant:

    Internal expert/debug callers can still opt into raw ctx by passing
    include_ctx=True.
    """

    ctx = _make_large_ctx(emitted_forms=6, fields_per_form=3, payload_chars=32)

    raw_out = {
        "ok": True,
        "event_kind": "render",
        "ctx": ctx,
        "content": _make_html(payload_chars=1_024),
    }

    full = _apply_frontend_artery_policy(raw_out, render=True, include_ctx=True)

    assert "ctx" in full
    assert "ctx_report" not in full
    assert full["ctx"] is ctx
    assert full["content"].startswith("<!doctype html>")


def test_frontend_dispatch_lean_response_is_much_smaller_than_raw_ctx_response() -> None:
    """
    The response-size budget should be dominated by HTML, not duplicated ctx.

    This catches accidental regressions where a service endpoint returns:

    - html
    - plus raw ctx
    - plus full state/form maps
    """

    ctx = _make_large_ctx(emitted_forms=80, fields_per_form=10, payload_chars=384)

    raw_out = {
        "ok": True,
        "event_kind": "render",
        "ctx": ctx,
        "content": _make_html(payload_chars=20_000),
    }

    full = _apply_frontend_artery_policy(raw_out, render=True, include_ctx=True)
    lean = _apply_frontend_artery_policy(raw_out, render=True, include_ctx=False)

    full_bytes = _compact_json_size(full)
    lean_bytes = _compact_json_size(lean)

    assert lean_bytes < full_bytes * 0.15
    assert lean_bytes < 40_000


def test_frontend_ctx_report_does_not_leak_multiframespecs_prefills_or_values() -> None:
    """
    The tiny ctx_report should carry counts and cursor identity only.

    It must not leak:

    - multiframespec fields
    - prefill values
    - fill values
    - datum_widget_fills
    """

    ctx = _make_large_ctx(emitted_forms=20, fields_per_form=5, payload_chars=512)

    raw_out = {
        "ok": True,
        "event_kind": "render",
        "ctx": ctx,
        "content": _make_html(payload_chars=4_000),
    }

    lean = _apply_frontend_artery_policy(raw_out, render=True, include_ctx=False)
    rendered = json.dumps(lean["ctx_report"], sort_keys=True, default=repr)

    # Count labels are expected.
    assert "forms_emitted" in rendered
    assert "form_prefills" in rendered
    assert "form_fills" in rendered
    assert "datum_widget_fills" in rendered

    # Raw multiframespec/value bodies are forbidden.
    assert "Field 0" not in rendered
    assert "metadata" not in rendered
    assert "payload" not in rendered
    assert "p" * 128 not in rendered
    assert "f" * 128 not in rendered
    assert "v" * 128 not in rendered
    assert "h" * 128 not in rendered


def test_frontend_dispatch_without_render_can_still_omit_ctx() -> None:
    """
    Non-rendering event responses should also be able to stay lean.

    This is useful for JSON-only interaction endpoints
    """

    ctx = _make_large_ctx(emitted_forms=12, fields_per_form=4, payload_chars=128)

    raw_out = {
        "ok": True,
        "event_kind": "submit",
        "ctx": ctx,
    }

    lean = _apply_frontend_artery_policy(raw_out, render=False, include_ctx=False)

    assert lean == {
        "ok": True,
        "event_kind": "submit",
        "ctx_report": {
            "kind": "ui_ctx_report_v1",
            "event_kind": "submit",
            "cursor": {
                "index": 11,
                "total": 12,
            },
            "form_id": "form_0011",
            "frame_id": "frame_main",
            "span_id": "span_main",
            "datum_widgets_on_this_span_count": 4,
            "state_counts": {
                "form_prefills": 48,
                "form_fills": 48,
                "forms_emitted": 12,
                "datum_widget_fills": 48,
            },
            "last_error": None,
        },
    }


def test_ctx_report_uses_outer_dispatch_event_kind_over_stale_ctx_event_kind() -> None:
    """
    The outer dispatch event is authoritative.

    This prevents stale ctx["event_kind"] from creating confusing reports such as
    response event submit but ctx_report event render.
    """

    ctx = _make_large_ctx(emitted_forms=3, fields_per_form=2, payload_chars=16)
    assert ctx["event_kind"] == "render"

    raw_out = {
        "ok": True,
        "event_kind": "submit",
        "ctx": ctx,
    }

    lean = _apply_frontend_artery_policy(raw_out, render=False, include_ctx=False)

    assert lean["event_kind"] == "submit"
    assert lean["ctx_report"]["event_kind"] == "submit"


def test_service_launch_snapshot_shape_uses_html_without_ctx() -> None:
    """
    Service model invariant:

    The launch/render path that only uses snapshot["content"] should request
    include_ctx=False so large ctx is never moved through that artery.
    """

    ctx = _make_large_ctx(emitted_forms=30, fields_per_form=6, payload_chars=192)

    dispatch_result = _apply_frontend_artery_policy(
        {
            "ok": True,
            "event_kind": "render",
            "ctx": ctx,
            "content": _make_html(payload_chars=8_000),
        },
        render=True,
        include_ctx=False,
    )

    launch_snapshot = {
        "content": dispatch_result["content"],
        "ctx_report": dispatch_result.get("ctx_report"),
    }

    assert "content" in launch_snapshot
    assert "ctx_report" in launch_snapshot
    assert "ctx" not in launch_snapshot

    assert _compact_json_size(launch_snapshot) < 16_000


def test_frontend_artery_response_budget_scales_with_html_not_ctx_payload() -> None:
    """
    Increasing ctx payload size should not materially increase lean response size.

    This catches regressions where ctx is accidentally retained or nested into
    ctx_report.
    """

    html = _make_html(payload_chars=6_000)

    small_ctx = _make_large_ctx(emitted_forms=10, fields_per_form=4, payload_chars=32)
    large_ctx = _make_large_ctx(emitted_forms=10, fields_per_form=4, payload_chars=2_048)

    small_lean = _apply_frontend_artery_policy(
        {
            "ok": True,
            "event_kind": "render",
            "ctx": small_ctx,
            "content": html,
        },
        render=True,
        include_ctx=False,
    )
    large_lean = _apply_frontend_artery_policy(
        {
            "ok": True,
            "event_kind": "render",
            "ctx": large_ctx,
            "content": html,
        },
        render=True,
        include_ctx=False,
    )

    small_size = _compact_json_size(small_lean)
    large_size = _compact_json_size(large_lean)

    assert large_size <= small_size + 256


def test_ctx_report_handles_missing_optional_ctx_fields() -> None:
    """
    The report builder should be defensive.

    Missing cursor/state/form/span data should produce a stable tiny report
    rather than forcing callers to keep raw ctx for debugging.
    """

    raw_out = {
        "ok": True,
        "event_kind": "noop",
        "ctx": {},
        "content": _make_html(payload_chars=512),
    }

    lean = _apply_frontend_artery_policy(raw_out, render=True, include_ctx=False)

    assert lean["ctx_report"] == {
        "kind": "ui_ctx_report_v1",
        "event_kind": "noop",
        "cursor": {
            "index": None,
            "total": None,
        },
        "form_id": None,
        "frame_id": None,
        "span_id": None,
        "datum_widgets_on_this_span_count": 0,
        "state_counts": {
            "form_prefills": 0,
            "form_fills": 0,
            "forms_emitted": 0,
            "datum_widget_fills": 0,
        },
        "last_error": None,
    }


def test_ctx_report_can_fall_back_to_ctx_event_kind_when_outer_event_missing() -> None:
    """
    Fallback compatibility:

    If a caller builds a report without an outer dispatch event, ctx.event_kind is
    still used as a best-effort identity.
    """

    ctx = _make_large_ctx(emitted_forms=2, fields_per_form=1, payload_chars=8)

    report = _make_ui_ctx_report_v1(ctx)

    assert report["event_kind"] == "render"
    assert report["form_id"] == "form_0001"
    assert report["datum_widgets_on_this_span_count"] == 1
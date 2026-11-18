from __future__ import annotations

"""
Executable final sheet for role modulation.

===============================================================================
0. PURPOSE
===============================================================================

This file is intentionally both:

    1. an executable integration/unit sheet; and
    2. the markovian feature formalism for role modulation.

A reader should be able to understand the full feature from this file alone.

===============================================================================
1. FINAL FEATURE LAW
===============================================================================

The engine remains roleless.

Role modulation is a public boundary layer:

    roleless ctx U + viewer_role + session_metadata
        -> role-modulated ctx U_role

and a write-side guard:

    roleless ctx U + viewer_role + submitted fill F
        -> allow or PermissionError

The stable session metadata keys are:

    session_metadata["roles"]
    session_metadata["role_mismatch_policy"]

The final role law is:

    read:
        role R may read datums guarded by R.
        role R may also read datums guarded by any role listed in
        roles[R].read_roles.

    write:
        role R may write only datums guarded by R.
        read_roles never grant write permission.

Therefore old/simple behavior is not a compatibility mode. It is the minimal
configuration:

    roles = {
        "maker": {"label": "Maker"},
        "reviewer": {"label": "Reviewer"},
    }

No read_roles means each role reads and writes only itself.

===============================================================================
2. FINAL METADATA SURFACE
===============================================================================

    {
        "roles": {
            "maker": {
                "label": "Maker",
                "read_roles": ["reviewer"]
            },
            "reviewer": {
                "label": "Reviewer"
            },
            "auditor": {
                "label": "Auditor",
                "read_roles": ["maker", "reviewer"]
            }
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                "maker": "redacted",
                "reviewer": "redacted",
                "auditor": "redacted"
            }
        }
    }

The role rows may carry app-owned JSON-safe presentation metadata. The machinery
only interprets read_roles.

role_mismatch_policy is explicit:

    default: fallback mode
    role_modes: viewer-role-specific mode override

Unknown top-level policy keys are rejected.

Live callables are rejected from metadata. Executable behavior belongs behind
registries and is referenced by declarative strings.

===============================================================================
3. DATUM ROLE ASSIGNMENT
===============================================================================

Let D be a current-frame datum.
Let Span(D) be the span that owns D.

    required_roles(D)
        = D.roles
          if D.roles is present and non-empty

        = [D.role]
          if D.roles is absent/empty and D.role is present

        = Span(D).roles
          if datum role data is absent/empty and Span(D).roles is present
          and non-empty

        = [Span(D).role]
          if datum role data is absent/empty and Span(D).role is present

        = []
          otherwise

Datum-level non-empty roles override span-level roles.

Current machinery intentionally treats an explicit empty datum roles list as
"no datum-level override", not as "unguarded override". Therefore a datum with:

    D.roles = []
    Span(D).roles = ["maker"]

resolves to:

    required_roles(D) = ["maker"]

A datum is unguarded only when the final resolved role assignment is empty.

===============================================================================
4. READ MISMATCH
===============================================================================

    effective_read_roles(None) = {}

    effective_read_roles(R)
        = {R} ∪ roles[R].read_roles

A datum is read-visible iff:

    required_roles(D) is empty
    OR required_roles(D) intersects effective_read_roles(viewer_role)

Otherwise the datum is role-mismatch redacted.

===============================================================================
5. WRITE GUARD
===============================================================================

A submitted fill for datum D is write-allowed iff:

    required_roles(D) is empty
    OR viewer_role is in required_roles(D)

This intentionally ignores read_roles.

Therefore:

    maker with read_roles=["reviewer"]
        can see reviewer datum data
        cannot fill reviewer datum data

===============================================================================
6. CURRENT-FRAME LAW
===============================================================================

Role modulation first constrains ctx to the current public frame. Future frames,
future spans, future datums, and future fills are not visible and are not counted
in mismatch reports.

The write guard is current-active-span scoped. It prevents writes to guarded
active datums that the viewer cannot write. It is not a global future-manifest
validator.

===============================================================================
7. POLICY MODE LAW
===============================================================================

A mismatch chooses its obfuscation mode by:

    role_mismatch_policy.role_modes[viewer_role]
    else role_mismatch_policy.default

Modes are declarative strings resolved by the runtime obfuscation mode registry.

Read permission bypasses obfuscation entirely. A datum readable through an
adjacent role is not obfuscated just because the viewer role differs from the
datum role.

===============================================================================
8. PERFORMANCE LAW
===============================================================================

Runtime work is linear in active current-frame datums:

    collect active assignments once
    build role/mismatch info once
    obfuscate only mismatched active datums
    write guard checks submitted datum ids against active assignment rows

No full-program role scan is needed on ordinary UI turns.
"""

import json
from copy import deepcopy
from typing import Any, Dict, Mapping, Optional

import pytest

from _thinksessions.libs_read_write_augmented.rolebasedRWmodulatorTM._obfuscation_runtime import (
    _augment_ctx_with_role_and_role_mismatch_info,
    _obfuscate_ctx_for_specific_viewer_role,
    _this_viewer_role_is_allowed_this_submission,
    current_datum_role_assignments,
)
from _thinksessions.libs_read_write_augmented.rolebasedRWmodulatorTM.obfuscation_api import role_modulation
from _thinksessions.sesh_metadata.__sesh_meta_rolebasedRWmodulatorTM_config_surface import (
    effective_read_roles_for_role,
    role_can_read_required_roles,
    role_can_write_required_roles,
    role_mismatch_mode_for_viewer_role,
    role_modulation_surface_sheet_v1,
    sanitize_role_mismatch_policy_for_metadata,
    validate_role_modulation_surface,
)
from _thinksessions.sesh_metadata.sesh_metadata_surface import (
    coerce_session_metadata,
    merge_session_metadata,
    session_args_metadata_surface_sheet_v1,
)


ROLE_MISMATCH_KIND = "role_mismatch_obfuscated_datum_v1"
ROLE_MISMATCH_INFO_KIND = "role_mismatch_modulation_info_v1"
ROLE_MISMATCH_FILL_MARKER = {
    "kind": ROLE_MISMATCH_KIND,
    "obfuscated": True,
    "reason": "role_mismatch",
}


FINAL_ROLE_METADATA = {
    "roles": {
        "maker": {
            "label": "Maker",
            "read_roles": ["reviewer"],
        },
        "reviewer": {
            "label": "Reviewer",
        },
        "auditor": {
            "label": "Auditor",
            "read_roles": ["maker", "reviewer"],
        },
    },
    "role_mismatch_policy": {
        "default": "redacted",
        "role_modes": {
            "maker": "redacted",
            "reviewer": "readonly_redacted",
            "auditor": "redacted",
        },
    },
}


SIMPLE_ROLE_METADATA = {
    "roles": {
        "maker": {"label": "Maker"},
        "reviewer": {"label": "Reviewer"},
    },
    "role_mismatch_policy": {
        "default": "redacted",
        "role_modes": {
            "maker": "redacted",
            "reviewer": "redacted",
        },
    },
}


def _metadata(*, final: bool = True) -> Dict[str, Any]:
    return deepcopy(FINAL_ROLE_METADATA if final else SIMPLE_ROLE_METADATA)


def _ctx(
    *,
    metadata: Optional[Mapping[str, Any]] = None,
    datum_project_roles: Optional[list[str]] = None,
    datum_review_roles: Optional[list[str]] = None,
    datum_public_roles: Optional[list[str]] = None,
    span_roles: Optional[list[str]] = None,
) -> Dict[str, Any]:
    project: Dict[str, Any] = {
        "id": "PROJECT",
        "title": "Project",
        "micros": [
            {
                "name": "name",
                "type": "text",
                "required": True,
                "placeholder": "Project secret placeholder",
            }
        ],
    }
    review: Dict[str, Any] = {
        "id": "REVIEW",
        "title": "Private Review",
        "micros": [
            {
                "name": "note",
                "type": "text",
                "required": True,
                "placeholder": "Secret review placeholder",
            }
        ],
    }
    public: Dict[str, Any] = {
        "id": "PUBLIC",
        "title": "Public",
        "micros": [
            {
                "name": "value",
                "type": "text",
                "required": False,
                "placeholder": "Public placeholder",
            }
        ],
    }

    if datum_project_roles is not None:
        project["roles"] = list(datum_project_roles)
    if datum_review_roles is not None:
        review["roles"] = list(datum_review_roles)
    if datum_public_roles is not None:
        public["roles"] = list(datum_public_roles)

    span: Dict[str, Any] = {
        "id": "S",
        "owns": ["PROJECT", "REVIEW", "PUBLIC"],
        "tags": [],
    }
    if span_roles is None:
        span["role"] = "maker"
        span["roles"] = ["maker"]
    else:
        span["roles"] = list(span_roles)

    return {
        "kind": "MANUALFILLNEEDEDSTEP",
        "current_frame_id": "F",
        "current_span": "S",
        "current_span_id": "S",
        "session_metadata": deepcopy(dict(metadata or FINAL_ROLE_METADATA)),
        "multiframespec": {
            "app_form_id": "role.test",
            "boxed": None,
            "datums": [project, review, public],
            "fills": {
                "PROJECT": {"name": "Apollo"},
                "REVIEW": {"note": "Approve privately"},
                "PUBLIC": {"value": "Visible to all"},
            },
            "frames": [
                {
                    "id": "F",
                    "title": "Frame",
                    "spans": [span],
                    "tags": [],
                }
            ],
            "refs": [],
            "tokens": None,
        },
        "frames": [
            {
                "id": "F",
                "name": "F",
                "fillspans": [{"name": "S"}],
                "field_ids": ["PROJECT", "REVIEW", "PUBLIC"],
            }
        ],
        "span_order": ["S"],
        "span_to_datum_widgets": {"S": ["PROJECT", "REVIEW", "PUBLIC"]},
        "datum_widgets_on_this_span": ["PROJECT", "REVIEW", "PUBLIC"],
        "step": {
            "frame_id": "F",
            "span_id": "S",
            "datum_widgets_on_this_span": ["PROJECT", "REVIEW", "PUBLIC"],
            "span_authoritative": ["PROJECT", "REVIEW", "PUBLIC"],
            "span_owns": ["PROJECT", "REVIEW", "PUBLIC"],
        },
        "datum_widget_decls": {
            "PROJECT": {
                "field_id": "PROJECT",
                "fillspan_name": "S",
                "datum_args": {
                    "id": "PROJECT",
                    "title": "Secret Project",
                    "micro_input_fields": [
                        {
                            "name": "name",
                            "type": "text",
                            "placeholder": "Secret project placeholder",
                        }
                    ],
                },
                "micros": ["name"],
            },
            "REVIEW": {
                "field_id": "REVIEW",
                "fillspan_name": "S",
                "datum_args": {
                    "id": "REVIEW",
                    "title": "Private Review",
                    "micro_input_fields": [
                        {
                            "name": "note",
                            "type": "text",
                            "placeholder": "Secret review placeholder",
                        }
                    ],
                },
                "micros": ["note"],
            },
            "PUBLIC": {
                "field_id": "PUBLIC",
                "fillspan_name": "S",
                "datum_args": {
                    "id": "PUBLIC",
                    "title": "Public",
                    "micro_input_fields": [
                        {
                            "name": "value",
                            "type": "text",
                            "placeholder": "Public placeholder",
                        }
                    ],
                },
                "micros": ["value"],
            },
        },
        "datum_widget_fills": {
            "PROJECT": {"name": "Apollo"},
            "REVIEW": {"note": "Approve privately"},
            "PUBLIC": {"value": "Visible to all"},
        },
        "last_error": None,
    }


def _two_frame_ctx() -> Dict[str, Any]:
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    ctx["current_frame_id"] = "MAKER_FRAME"
    ctx["current_span"] = "S_PROJECT"
    ctx["current_span_id"] = "S_PROJECT"

    ctx["multiframespec"]["frames"] = [
        {
            "id": "MAKER_FRAME",
            "title": "Maker brief",
            "spans": [
                {
                    "id": "S_PROJECT",
                    "owns": ["PROJECT"],
                    "role": "maker",
                    "roles": ["maker"],
                    "tags": [],
                }
            ],
            "tags": [],
        },
        {
            "id": "REVIEW_FRAME",
            "title": "Future Secret Review Frame",
            "spans": [
                {
                    "id": "S_REVIEW",
                    "owns": ["REVIEW"],
                    "role": "reviewer",
                    "roles": ["reviewer"],
                    "tags": [],
                }
            ],
            "tags": [],
        },
    ]

    ctx["frames"] = [
        {
            "id": "MAKER_FRAME",
            "name": "MAKER_FRAME",
            "fillspans": [{"name": "S_PROJECT"}],
            "field_ids": ["PROJECT"],
        },
        {
            "id": "REVIEW_FRAME",
            "name": "REVIEW_FRAME",
            "fillspans": [{"name": "S_REVIEW"}],
            "field_ids": ["REVIEW"],
        },
    ]

    ctx["span_order"] = ["S_PROJECT", "S_REVIEW"]
    ctx["span_to_datum_widgets"] = {
        "S_PROJECT": ["PROJECT"],
        "S_REVIEW": ["REVIEW"],
    }
    ctx["datum_widgets_on_this_span"] = ["PROJECT"]
    ctx["step"] = {
        "frame_id": "MAKER_FRAME",
        "span_id": "S_PROJECT",
        "datum_widgets_on_this_span": ["PROJECT"],
        "span_authoritative": ["PROJECT"],
        "span_owns": ["PROJECT"],
    }

    return ctx


def _rendered(ctx: Mapping[str, Any]) -> str:
    return json.dumps(ctx, sort_keys=True)


def _assert_review_visible(out: Mapping[str, Any]) -> None:
    rendered = _rendered(out)
    assert "REVIEW" in out["datum_widget_decls"]
    assert out["datum_widget_fills"]["REVIEW"] == {"note": "Approve privately"}
    assert "Private Review" in rendered
    assert "Secret review placeholder" in rendered
    assert "Approve privately" in rendered


def _assert_review_redacted(out: Mapping[str, Any], *, viewer_role: Optional[str]) -> None:
    review_decl = out["datum_widget_decls"]["REVIEW"]
    assert review_decl["kind"] == ROLE_MISMATCH_KIND
    assert review_decl["role_mismatch_obfuscated"] is True
    assert review_decl["fillspan_name"] is None
    assert review_decl["micros"] == []
    assert review_decl["micro_names"] == []
    assert review_decl["datum_args"] == {
        "help_text": "This datum is hidden because of a role mismatch.",
        "id": "REVIEW",
        "kind": ROLE_MISMATCH_KIND,
        "required_roles": ["reviewer"],
        "role_mismatch_obfuscated": True,
        "title": "Unavailable",
        "viewer_role": viewer_role,
    }

    assert out["datum_widget_fills"]["REVIEW"] == ROLE_MISMATCH_FILL_MARKER
    assert out["multiframespec"]["fills"]["REVIEW"] == ROLE_MISMATCH_FILL_MARKER
    assert "REVIEW" not in out["datum_widgets_on_this_span"]
    assert "REVIEW" not in out["span_to_datum_widgets"]["S"]
    assert "REVIEW" not in out["frames"][0]["field_ids"]
    assert "REVIEW" not in out["step"]["span_owns"]
    assert "REVIEW" not in out["step"]["span_authoritative"]
    assert "REVIEW" not in out["step"]["datum_widgets_on_this_span"]
    assert "REVIEW" not in out["multiframespec"]["frames"][0]["spans"][0]["owns"]

    rendered = _rendered(out)
    assert "Private Review" not in rendered
    assert "Secret review placeholder" not in rendered
    assert "Approve privately" not in rendered


def _assert_project_redacted(out: Mapping[str, Any], *, viewer_role: Optional[str]) -> None:
    project_decl = out["datum_widget_decls"]["PROJECT"]
    assert project_decl["kind"] == ROLE_MISMATCH_KIND
    assert project_decl["role_mismatch_obfuscated"] is True
    assert project_decl["datum_args"]["viewer_role"] == viewer_role
    assert project_decl["datum_args"]["required_roles"] == ["maker"]

    assert out["datum_widget_fills"]["PROJECT"] == ROLE_MISMATCH_FILL_MARKER
    assert "PROJECT" not in out["datum_widgets_on_this_span"]
    assert "PROJECT" not in out["span_to_datum_widgets"]["S"]

    rendered = _rendered(out)
    assert "Secret Project" not in rendered
    assert "Project secret placeholder" not in rendered
    assert "Secret project placeholder" not in rendered
    assert "Apollo" not in rendered


def test_session_metadata_surface_publishes_role_modulation_sheet():
    sheet = session_args_metadata_surface_sheet_v1()

    assert sheet["kind"] == "session_args_metadata_surface_v1"
    assert "roles" in sheet["keys"]
    assert "role_mismatch_policy" in sheet["keys"]
    assert sheet["subsurfaces"]["role_modulation"]["metadata_keys"] == [
        "roles",
        "role_mismatch_policy",
    ]


def test_role_modulation_surface_sheet_documents_final_read_write_law():
    sheet = role_modulation_surface_sheet_v1()

    assert sheet["v"] == 1
    assert sheet["metadata_keys"] == ["roles", "role_mismatch_policy"]

    laws = " ".join(sheet["laws"])
    assert "read_roles grants read visibility" in laws
    assert "never grants write permission" in laws
    assert "engine remains roleless" in laws

    assert sheet["mode_resolution"]["law"]
    assert "datum.roles if present" in sheet["required_roles_resolution"]


def test_policy_accepts_final_shape_and_injects_defaults():
    assert sanitize_role_mismatch_policy_for_metadata(
        {
            "default": "redacted",
            "role_modes": {"maker": "redacted"},
        }
    ) == {
        "default": "redacted",
        "role_modes": {"maker": "redacted"},
    }

    assert sanitize_role_mismatch_policy_for_metadata(None) == {
        "default": "redacted",
        "role_modes": {},
    }


def test_policy_rejects_old_on_mismatch_shape():
    with pytest.raises(ValueError, match="on_mismatch"):
        sanitize_role_mismatch_policy_for_metadata({"on_mismatch": "error"})


def test_policy_rejects_flat_role_mode_shape():
    with pytest.raises(KeyError, match="unknown role_mismatch_policy key"):
        sanitize_role_mismatch_policy_for_metadata(
            {
                "default": "redacted",
                "maker": "redacted",
            }
        )


def test_policy_rejects_live_callable_role_mode():
    with pytest.raises(TypeError, match="live callable"):
        sanitize_role_mismatch_policy_for_metadata(
            {
                "default": "redacted",
                "role_modes": {"maker": lambda ctx: ctx},
            }
        )


def test_role_rows_reject_live_callable_metadata():
    with pytest.raises(TypeError, match="live callable"):
        coerce_session_metadata(
            {
                "roles": {
                    "maker": {
                        "label": "Maker",
                        "bad": lambda: None,
                    },
                },
                "role_mismatch_policy": {"default": "redacted"},
            }
        )


def test_session_metadata_coercion_canonicalizes_role_read_aliases_and_dedupes():
    meta = coerce_session_metadata(
        {
            "roles": {
                "maker": {
                    "label": "Maker",
                    "can_read": ["reviewer", "reviewer"],
                    "view_roles": "auditor",
                },
                "reviewer": {"label": "Reviewer"},
                "auditor": {"label": "Auditor"},
            },
            "role_mismatch_policy": {
                "default": "redacted",
                "role_modes": {
                    "maker": "redacted",
                    "reviewer": "redacted",
                    "auditor": "redacted",
                },
            },
        }
    )

    assert meta["roles"]["maker"] == {
        "label": "Maker",
        "read_roles": ["reviewer", "auditor"],
    }


def test_session_metadata_validation_rejects_unknown_read_role():
    with pytest.raises(KeyError, match="unknown role"):
        coerce_session_metadata(
            {
                "roles": {
                    "maker": {"read_roles": ["ghost"]},
                },
                "role_mismatch_policy": {"default": "redacted"},
            }
        )


def test_session_metadata_validation_rejects_unknown_policy_role_mode():
    with pytest.raises(KeyError, match="role_modes references unknown role"):
        validate_role_modulation_surface(
            roles={"maker": {}},
            role_mismatch_policy={
                "default": "redacted",
                "role_modes": {"ghost": "redacted"},
            },
        )


def test_merge_session_metadata_revalidates_final_combined_surface():
    base = {
        "roles": {"maker": {}, "reviewer": {}},
        "role_mismatch_policy": {"default": "redacted"},
    }

    merged = merge_session_metadata(
        base,
        {
            "roles": {
                "maker": {"read_roles": ["reviewer"]},
                "reviewer": {},
            }
        },
    )

    assert merged["roles"]["maker"]["read_roles"] == ["reviewer"]

    with pytest.raises(KeyError, match="unknown role"):
        merge_session_metadata(
            base,
            {
                "roles": {
                    "maker": {"read_roles": ["ghost"]},
                    "reviewer": {},
                }
            },
        )


def test_effective_read_roles_are_self_plus_adjacent_roles():
    roles = FINAL_ROLE_METADATA["roles"]

    assert effective_read_roles_for_role(roles, role="maker") == {
        "maker",
        "reviewer",
    }
    assert effective_read_roles_for_role(roles, role="reviewer") == {
        "reviewer",
    }
    assert effective_read_roles_for_role(roles, role="auditor") == {
        "auditor",
        "maker",
        "reviewer",
    }
    assert effective_read_roles_for_role(roles, role=None) == set()


def test_role_mismatch_mode_resolution_is_policy_specific_per_viewer_role():
    policy = sanitize_role_mismatch_policy_for_metadata(
        FINAL_ROLE_METADATA["role_mismatch_policy"]
    )

    assert role_mismatch_mode_for_viewer_role(policy, role="maker") == "redacted"
    assert role_mismatch_mode_for_viewer_role(policy, role="reviewer") == (
        "readonly_redacted"
    )
    assert role_mismatch_mode_for_viewer_role(policy, role="auditor") == "redacted"
    assert role_mismatch_mode_for_viewer_role(policy, role=None) == "redacted"


def test_read_and_write_predicates_are_intentionally_different():
    roles = FINAL_ROLE_METADATA["roles"]

    assert role_can_read_required_roles(
        roles,
        role="maker",
        required_roles=["reviewer"],
    ) is True
    assert role_can_write_required_roles(
        role="maker",
        required_roles=["reviewer"],
    ) is False

    assert role_can_read_required_roles(
        roles,
        role="maker",
        required_roles=["maker"],
    ) is True
    assert role_can_write_required_roles(
        role="maker",
        required_roles=["maker"],
    ) is True


def test_unguarded_datums_are_readable_and_writable_by_any_viewer():
    roles = FINAL_ROLE_METADATA["roles"]

    assert role_can_read_required_roles(roles, role=None, required_roles=[]) is True
    assert role_can_write_required_roles(role=None, required_roles=[]) is True
    assert role_can_read_required_roles(roles, role="maker", required_roles=[]) is True
    assert role_can_write_required_roles(role="maker", required_roles=[]) is True


def test_datum_roles_override_span_roles():
    ctx = _ctx(
        metadata=_metadata(final=False),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
        span_roles=["maker"],
    )

    assert current_datum_role_assignments(ctx) == [
        {"datum_id": "PROJECT", "roles": ["maker"], "role_source": "datum"},
        {"datum_id": "REVIEW", "roles": ["reviewer"], "role_source": "datum"},
        {"datum_id": "PUBLIC", "roles": ["maker"], "role_source": "span"},
    ]


def test_span_roles_are_default_when_datum_has_no_roles():
    ctx = _ctx(
        metadata=_metadata(final=False),
        span_roles=["maker"],
    )

    assert current_datum_role_assignments(ctx) == [
        {"datum_id": "PROJECT", "roles": ["maker"], "role_source": "span"},
        {"datum_id": "REVIEW", "roles": ["maker"], "role_source": "span"},
        {"datum_id": "PUBLIC", "roles": ["maker"], "role_source": "span"},
    ]


def test_simple_roles_have_exact_read_write_behavior():
    ctx = _ctx(
        metadata=_metadata(final=False),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    maker_out = _obfuscate_ctx_for_specific_viewer_role(ctx, role="maker")
    reviewer_out = _obfuscate_ctx_for_specific_viewer_role(ctx, role="reviewer")

    assert maker_out["role_mismatch_modulation_info"]["read_role_names"] == ["maker"]
    assert maker_out["role_mismatch_modulation_info"]["mismatch_datum_ids"] == [
        "REVIEW"
    ]
    _assert_review_redacted(maker_out, viewer_role="maker")

    assert reviewer_out["role_mismatch_modulation_info"]["read_role_names"] == [
        "reviewer"
    ]
    assert reviewer_out["role_mismatch_modulation_info"]["mismatch_datum_ids"] == [
        "PROJECT",
        "PUBLIC",
    ]
    _assert_project_redacted(reviewer_out, viewer_role="reviewer")


def test_adjacent_read_role_sees_data_without_obfuscation():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    out = _obfuscate_ctx_for_specific_viewer_role(ctx, role="maker")
    info = out["role_mismatch_modulation_info"]

    assert info["read_role_names"] == ["maker", "reviewer"]
    assert info["mismatch_datum_ids"] == []
    assert out["datum_widgets_on_this_span"] == ["PROJECT", "REVIEW", "PUBLIC"]
    assert out["span_to_datum_widgets"]["S"] == ["PROJECT", "REVIEW", "PUBLIC"]
    assert out["frames"][0]["field_ids"] == ["PROJECT", "REVIEW", "PUBLIC"]

    _assert_review_visible(out)


def test_adjacent_read_role_does_not_grant_write_power():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    out = _augment_ctx_with_role_and_role_mismatch_info(ctx, role="maker")
    assignments = {
        row["datum_id"]: row
        for row in out["role_mismatch_modulation_info"]["assignments"]
    }

    assert assignments["REVIEW"]["read_allowed"] is True
    assert assignments["REVIEW"]["write_allowed"] is False

    with pytest.raises(PermissionError, match="REVIEW"):
        _this_viewer_role_is_allowed_this_submission(
            ctx,
            role="maker",
            fill={"REVIEW.note": "maker may read but may not write"},
        )


def test_owner_role_can_write_own_datum():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    assert (
        _this_viewer_role_is_allowed_this_submission(
            ctx,
            role="maker",
            fill={"PROJECT.name": "new"},
        )
        is True
    )

    assert (
        _this_viewer_role_is_allowed_this_submission(
            ctx,
            role="reviewer",
            fill={"REVIEW.note": "new"},
        )
        is True
    )


def test_auditor_can_read_all_configured_roles_but_write_none_of_them():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    out = _obfuscate_ctx_for_specific_viewer_role(ctx, role="auditor")
    info = out["role_mismatch_modulation_info"]

    assert info["read_role_names"] == ["auditor", "maker", "reviewer"]
    assert info["mismatch_datum_ids"] == []
    assert out["datum_widgets_on_this_span"] == ["PROJECT", "REVIEW", "PUBLIC"]
    assert out["datum_widget_fills"]["PROJECT"] == {"name": "Apollo"}
    assert out["datum_widget_fills"]["REVIEW"] == {"note": "Approve privately"}

    with pytest.raises(PermissionError, match="PROJECT"):
        _this_viewer_role_is_allowed_this_submission(
            ctx,
            role="auditor",
            fill={"PROJECT.name": "nope"},
        )

    with pytest.raises(PermissionError, match="REVIEW"):
        _this_viewer_role_is_allowed_this_submission(
            ctx,
            role="auditor",
            fill={"REVIEW.note": "nope"},
        )


def test_multi_role_datum_allows_any_listed_owner_to_write_and_adjacent_reader_to_read():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker", "reviewer"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    maker_out = _augment_ctx_with_role_and_role_mismatch_info(ctx, role="maker")
    reviewer_out = _augment_ctx_with_role_and_role_mismatch_info(ctx, role="reviewer")
    auditor_out = _augment_ctx_with_role_and_role_mismatch_info(ctx, role="auditor")

    maker_assignment = {
        row["datum_id"]: row
        for row in maker_out["role_mismatch_modulation_info"]["assignments"]
    }["PROJECT"]
    reviewer_assignment = {
        row["datum_id"]: row
        for row in reviewer_out["role_mismatch_modulation_info"]["assignments"]
    }["PROJECT"]
    auditor_assignment = {
        row["datum_id"]: row
        for row in auditor_out["role_mismatch_modulation_info"]["assignments"]
    }["PROJECT"]

    assert maker_assignment["read_allowed"] is True
    assert maker_assignment["write_allowed"] is True

    assert reviewer_assignment["read_allowed"] is True
    assert reviewer_assignment["write_allowed"] is True

    assert auditor_assignment["read_allowed"] is True
    assert auditor_assignment["write_allowed"] is False


def test_unknown_viewer_role_is_rejected():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    with pytest.raises(KeyError, match="ghost"):
        _augment_ctx_with_role_and_role_mismatch_info(ctx, role="ghost")


def test_unknown_required_role_is_rejected():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["ghost"],
        datum_public_roles=[],
    )

    with pytest.raises(KeyError, match="ghost"):
        _augment_ctx_with_role_and_role_mismatch_info(ctx, role="maker")


def test_obfuscation_removes_hidden_datum_from_all_fillability_vectors():
    ctx = _ctx(
        metadata=_metadata(final=False),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    out = _obfuscate_ctx_for_specific_viewer_role(ctx, role="maker")

    assert out["datum_widgets_on_this_span"] == ["PROJECT", "PUBLIC"]
    assert out["span_to_datum_widgets"]["S"] == ["PROJECT", "PUBLIC"]
    assert out["frames"][0]["field_ids"] == ["PROJECT", "PUBLIC"]
    assert out["step"]["datum_widgets_on_this_span"] == ["PROJECT", "PUBLIC"]
    assert out["step"]["span_authoritative"] == ["PROJECT", "PUBLIC"]
    assert out["step"]["span_owns"] == ["PROJECT", "PUBLIC"]
    assert out["multiframespec"]["frames"][0]["spans"][0]["owns"] == [
        "PROJECT",
        "PUBLIC",
    ]

    _assert_review_redacted(out, viewer_role="maker")


def test_role_specific_policy_mode_is_attached_to_mismatch_rows():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=None,
        span_roles=[],
    )

    out = _augment_ctx_with_role_and_role_mismatch_info(ctx, role="reviewer")
    mismatches = out["role_mismatch_modulation_info"]["mismatches"]

    assert [row["datum_id"] for row in mismatches] == ["PROJECT"]
    assert mismatches[0]["obfuscation_mode"] == "readonly_redacted"


def test_read_permission_bypasses_role_specific_mismatch_obfuscation():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    # maker has read_roles=["reviewer"], so REVIEW is visible. The maker's
    # mismatch policy mode is irrelevant because there is no mismatch.
    out = _obfuscate_ctx_for_specific_viewer_role(ctx, role="maker")

    assert out["role_mismatch_modulation_info"]["mismatch_datum_ids"] == []
    _assert_review_visible(out)


def test_last_error_is_projected_by_the_same_datum_read_assignments():
    """Aggregate semantic errors must not become a side-channel around U."""
    ctx = _ctx(
        metadata=_metadata(final=False),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=None,
        span_roles=[],
    )
    ctx["last_error"] = {
        "PROJECT": "maker-only semantic detail",
        "PROJECT.name": "maker-only micro detail",
        "REVIEW": "reviewer-visible semantic detail",
        "PUBLIC": "unguarded semantic detail",
        "__SPAN__": "public aggregate span detail",
        "GHOST": "unknown datum-like detail must fail closed",
    }
    source_before = deepcopy(ctx)

    reviewer = role_modulation.modulate(ctx, role="reviewer")

    assert reviewer["last_error"] == {
        "REVIEW": "reviewer-visible semantic detail",
        "PUBLIC": "unguarded semantic detail",
        "__SPAN__": "public aggregate span detail",
    }
    assert "maker-only semantic detail" not in _rendered(reviewer)
    assert "maker-only micro detail" not in _rendered(reviewer)
    assert "unknown datum-like detail" not in _rendered(reviewer)

    # Projection is a release copy, never a canonical/session mutation.
    assert ctx == source_before


def test_last_error_normalizes_to_none_when_viewer_can_read_no_failing_datum():
    ctx = _ctx(
        metadata=_metadata(final=False),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=["maker"],
        span_roles=[],
    )
    ctx["last_error"] = {
        "PROJECT": "maker-only detail",
        "PUBLIC": "also maker-only detail",
    }

    reviewer = role_modulation.modulate(ctx, role="reviewer")

    assert reviewer["last_error"] is None
    assert "maker-only detail" not in _rendered(reviewer)
    assert "also maker-only detail" not in _rendered(reviewer)

    
def test_obfuscated_ctx_does_not_leak_source_or_provenance_copies():
    ctx = _ctx(
        metadata=_metadata(final=False),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )
    ctx["session_metadata"]["provenance"] = {
        "source_program": [
            {
                "kind": "think_kernel_step_v1",
                "datums": [
                    {
                        "id": "PROJECT",
                        "title": "Visible project source copy",
                        "widget": "x",
                        "micros": [
                            {
                                "name": "name",
                                "placeholder": "visible copied placeholder",
                            }
                        ],
                    },
                    {
                        "id": "REVIEW",
                        "title": "Copied private review title",
                        "widget": "x",
                        "micros": [
                            {
                                "name": "note",
                                "placeholder": "copied private review placeholder",
                            }
                        ],
                        "system_flags": {"secret": "copied private review flag"},
                    },
                ],
            }
        ],
    }

    out = _obfuscate_ctx_for_specific_viewer_role(ctx, role="maker")
    rendered = _rendered(out)

    assert "Copied private review title" not in rendered
    assert "copied private review placeholder" not in rendered
    assert "copied private review flag" not in rendered
    assert "Visible project source copy" in rendered


def test_current_frame_scoping_happens_before_role_accounting():
    ctx = _two_frame_ctx()

    out = _obfuscate_ctx_for_specific_viewer_role(ctx, role="maker")
    rendered = _rendered(out)

    assert out["current_frame_id"] == "MAKER_FRAME"
    assert out["current_span_id"] == "S_PROJECT"
    assert out["current_span"] == "S_PROJECT"

    assert out["frames"] == [
        {
            "id": "MAKER_FRAME",
            "name": "MAKER_FRAME",
            "fillspans": [{"name": "S_PROJECT"}],
            "field_ids": ["PROJECT"],
        }
    ]
    assert out["span_order"] == ["S_PROJECT"]
    assert out["span_to_datum_widgets"] == {"S_PROJECT": ["PROJECT"]}
    assert list(out["datum_widget_decls"].keys()) == ["PROJECT"]
    assert list(out["datum_widget_fills"].keys()) == ["PROJECT"]
    assert [d["id"] for d in out["multiframespec"]["datums"]] == ["PROJECT"]
    assert list(out["multiframespec"]["fills"].keys()) == ["PROJECT"]
    assert [f["id"] for f in out["multiframespec"]["frames"]] == ["MAKER_FRAME"]

    assert out["role_mismatch_modulation_info"]["assignments"] == [
        {
            "datum_id": "PROJECT",
            "is_mismatch": False,
            "obfuscation_mode": "redacted",
            "read_allowed": True,
            "read_role_names": ["maker", "reviewer"],
            "role_data_by_role": {
                "maker": {
                    "label": "Maker",
                    "read_roles": ["reviewer"],
                },
            },
            "role_source": "datum",
            "role_viewing": "maker",
            "roles": ["maker"],
            "write_allowed": True,
        }
    ]

    assert "REVIEW_FRAME" not in rendered
    assert "S_REVIEW" not in rendered
    assert "Future Secret Review Frame" not in rendered
    assert "Private Review" not in rendered
    assert "Secret review placeholder" not in rendered
    assert "Approve privately" not in rendered
    assert '"REVIEW"' not in rendered


def test_submission_guard_is_current_frame_scoped_not_future_global():
    ctx = _two_frame_ctx()

    assert (
        _this_viewer_role_is_allowed_this_submission(
            ctx,
            role="maker",
            fill={"PROJECT.name": "New"},
        )
        is True
    )

    # Future-frame REVIEW is outside current public scope. The guard is not a
    # global manifest validator.
    assert (
        _this_viewer_role_is_allowed_this_submission(
            ctx,
            role="maker",
            fill={"REVIEW.note": "future write"},
        )
        is True
    )


def test_none_and_empty_fill_are_allowed_after_role_validation():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    assert (
        _this_viewer_role_is_allowed_this_submission(ctx, role="maker", fill=None)
        is True
    )
    assert (
        _this_viewer_role_is_allowed_this_submission(ctx, role="maker", fill={})
        is True
    )


def test_public_role_modulation_facade_exposes_only_high_level_operations():
    ctx = _ctx(
        metadata=_metadata(final=True),
        datum_project_roles=["maker"],
        datum_review_roles=["reviewer"],
        datum_public_roles=[],
    )

    assignments = role_modulation.current_datum_role_assignments(ctx)
    assert [row["datum_id"] for row in assignments] == [
        "PROJECT",
        "REVIEW",
        "PUBLIC",
    ]

    assert role_modulation.effective_read_roles(
        FINAL_ROLE_METADATA["roles"],
        role="maker",
    ) == {"maker", "reviewer"}

    modulated = role_modulation.modulate(ctx, role="maker")
    assert modulated["role_mismatch_modulation_info"]["mismatch_datum_ids"] == []

    role_modulation.assert_submission_allowed(
        ctx,
        role="maker",
        fill={"PROJECT.name": "ok"},
    )

    with pytest.raises(PermissionError, match="REVIEW"):
        role_modulation.assert_submission_allowed(
            ctx,
            role="maker",
            fill={"REVIEW.note": "not ok"},
        )


def test_runtime_is_linear_in_active_span_datums(monkeypatch):
    import _thinksessions.libs_read_write_augmented.rolebasedRWmodulatorTM._obfuscation_runtime as runtime

    n = 25
    datums = []
    owns = []
    decls = {}
    fills = {}

    for i in range(n):
        did = f"D{i}"
        owns.append(did)
        datums.append(
            {
                "id": did,
                "title": did,
                "roles": ["maker"] if i % 2 == 0 else ["reviewer"],
                "micros": [{"name": "value", "type": "text"}],
            }
        )
        decls[did] = {
            "field_id": did,
            "fillspan_name": "S",
            "datum_args": {"id": did, "title": f"title {i}"},
            "micros": ["value"],
        }
        fills[did] = {"value": f"value {i}"}

    ctx = {
        "kind": "MANUALFILLNEEDEDSTEP",
        "current_frame_id": "F",
        "current_span": "S",
        "current_span_id": "S",
        "session_metadata": _metadata(final=False),
        "multiframespec": {
            "datums": datums,
            "fills": deepcopy(fills),
            "frames": [
                {
                    "id": "F",
                    "spans": [
                        {
                            "id": "S",
                            "owns": list(owns),
                            "role": "maker",
                            "roles": ["maker"],
                        }
                    ],
                }
            ],
        },
        "frames": [
            {
                "id": "F",
                "field_ids": list(owns),
                "fillspans": [{"name": "S"}],
            }
        ],
        "span_order": ["S"],
        "span_to_datum_widgets": {"S": list(owns)},
        "datum_widgets_on_this_span": list(owns),
        "step": {
            "frame_id": "F",
            "span_id": "S",
            "datum_widgets_on_this_span": list(owns),
            "span_authoritative": list(owns),
            "span_owns": list(owns),
        },
        "datum_widget_decls": decls,
        "datum_widget_fills": fills,
        "last_error": None,
    }

    calls = {"assignments": 0}
    original = runtime.current_datum_role_assignments

    def counted_assignments(ctx_arg):
        calls["assignments"] += 1
        return original(ctx_arg)

    monkeypatch.setattr(runtime, "current_datum_role_assignments", counted_assignments)

    out = runtime._obfuscate_ctx_for_specific_viewer_role(ctx, role="maker")

    assert calls["assignments"] == 1
    assert len(out["role_mismatch_modulation_info"]["mismatch_datum_ids"]) == n // 2
    assert out["datum_widgets_on_this_span"] == [
        f"D{i}" for i in range(n) if i % 2 == 0
    ]
    assert out["step"]["span_owns"] == [f"D{i}" for i in range(n) if i % 2 == 0]


def test_final_contract_summary():
    contract = {
        "engine_roleless": True,
        "metadata_keys": ["roles", "role_mismatch_policy"],
        "read": "self plus roles[viewer].read_roles",
        "write": "self only for guarded data",
        "mismatch": "no read power means redacted blackout",
        "old_simple_usage": "roles without read_roles",
        "empty_datum_roles": "falls back to span roles",
        "current_frame_first": True,
        "linear_active_datums": True,
        "mode_policy": "role_modes[viewer] else default",
    }

    assert contract["engine_roleless"] is True
    assert contract["metadata_keys"] == ["roles", "role_mismatch_policy"]
    assert contract["read"] == "self plus roles[viewer].read_roles"
    assert contract["write"] == "self only for guarded data"
    assert contract["mismatch"] == "no read power means redacted blackout"
    assert contract["old_simple_usage"] == "roles without read_roles"
    assert contract["empty_datum_roles"] == "falls back to span roles"
    assert contract["current_frame_first"] is True
    assert contract["linear_active_datums"] is True
    assert contract["mode_policy"] == "role_modes[viewer] else default"
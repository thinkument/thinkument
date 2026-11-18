from __future__ import annotations

"""
Stable role-modulation API façade.

This module is the clean boundary between UI/controller-facing code and the
lower-level role-modulation runtime.

Runtime responsibilities stay in ``_obfuscation_runtime`` and surface
coercion/validation stays in
``runme_surfaces_in.__sesh_meta_rolebasedRWmodulatorTM_config_surface``:

- role metadata validation and read/write formalism;
- role sheet extraction;
- viewing-role validation;
- datum-level role assignment resolution;
- active-span scalar role fallback;
- ctx role/mismatch augmentation;
- mismatch obfuscation;
- write-side submission gating.

Higher layers should import only one symbol from this module:

    role_modulation

The central read-side operation is:

    role_modulation.modulate(U, role=role)

where ``U`` is the renderer/controller-facing UI context vector.

No main-interaction façade module owns role mechanics. Main interaction code
only calls this façade when creating role metadata, releasing U/ctx, and gating
submissions.
"""

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
)

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_active_span_record_from_ctx,
)
from _thinksessions.libs_read_write_augmented.rolebasedRWmodulatorTM import (
    _obfuscation_runtime as runtime,
)
from _thinksessions.libs_read_write_augmented.rolebasedRWmodulatorTM._obfuscation_modes import (
    DEFAULT_OBFUSCATION_MODE,
    obfuscation_mode_names,
    obfuscation_mode_sheet_v1,
    register_obfuscation_mode,
)
from _thinksessions.sesh_metadata.sesh_metadata_surface import (
    coerce_session_metadata,
)
from _thinksessions.sesh_metadata.__sesh_meta_rolebasedRWmodulatorTM_config_surface import (
    coerce_session_roles,
    effective_read_roles_for_role,
    role_can_read_required_roles,
    role_can_write_required_roles,
    role_modulation_surface_sheet_v1,
    sanitize_role_mismatch_policy_for_metadata,
    validate_role_modulation_surface,
)


RoleMap = Dict[str, Dict[str, Any]]
RoleMismatchPolicy = Dict[str, Any]


@dataclass(frozen=True)
class RoleModulationAPI:
    """
    Stable public role-modulation façade.

    This object is the single import surface higher interaction layers need.
    It intentionally hides lower-level runtime function names and all role
    bookkeeping details.
    """

    def register_mode(
        self,
        name: str,
        fn: Callable[..., MutableMapping[str, Any]] | None = None,
        *,
        base_mode: str = DEFAULT_OBFUSCATION_MODE,
        receipt_fields: Sequence[str] = (),
        overwrite: bool = False,
    ) -> None:
        register_obfuscation_mode(
            name,
            fn,
            base_mode=base_mode,
            receipt_fields=receipt_fields,
            overwrite=overwrite,
        )

    def mode_names(self) -> list[str]:
        return obfuscation_mode_names()

    def mode_sheet(self) -> Dict[str, Any]:
        return obfuscation_mode_sheet_v1()

    def current_datum_role_assignments(
        self,
        U: Mapping[str, Any],
    ) -> list[Dict[str, Any]]:
        """
        Return active-span datum role assignments in active span ownership order.

        Each row has:

            {
                "datum_id": str,
                "roles": list[str],
                "role_source": "datum" | "span" | "",
            }
        """
        return runtime.current_datum_role_assignments(U)

    def current_span_role(
        self,
        U: Mapping[str, Any],
    ) -> Optional[str]:
        """
        Return the first active guarded datum role.

        If the active datum assignments are unguarded, this falls back to the
        opaque active-span ``role`` extension for older instrumentation data
        that still records role at span level only.
        """
        for assignment in self.current_datum_role_assignments(U):
            roles = list(assignment.get("roles") or [])
            if roles:
                return str(roles[0])

        record = get_active_span_record_from_ctx(
            U,
            include_span_keys=("role",),
        )
        if not isinstance(record, Mapping):
            return None

        value = record.get("role")
        if value is None:
            return None

        normalized = str(value).strip()
        return normalized or None

    def role_sheet_from_context(
        self,
        U: Mapping[str, Any],
    ) -> Tuple[RoleMap, RoleMismatchPolicy]:
        """
        Read role configuration from generic session metadata.
        """
        return runtime.role_sheet_from_context(U)

    def validate_viewing_role(
        self,
        *,
        role: Optional[str],
        roles: Mapping[str, Any],
    ) -> None:
        """
        Reject a named viewer role absent from the session role sheet.
        """
        runtime.validate_viewing_role(role=role, roles=roles)

    def effective_read_roles(
        self,
        roles: Mapping[str, Any],
        *,
        role: Optional[str],
    ) -> set[str]:
        """
        Return the guarded role names this viewer role may read.
        """
        return effective_read_roles_for_role(
            roles,
            role=role,
        )

    def can_read_roles(
        self,
        roles: Mapping[str, Any],
        *,
        role: Optional[str],
        required_roles: list[str],
    ) -> bool:
        return role_can_read_required_roles(
            roles,
            role=role,
            required_roles=required_roles,
        )

    def can_write_roles(
        self,
        *,
        role: Optional[str],
        required_roles: list[str],
    ) -> bool:
        return role_can_write_required_roles(
            role=role,
            required_roles=required_roles,
        )

    def surface_sheet(self) -> Dict[str, Any]:
        """
        Return documentation-as-data for the finalized role modulation surface.
        """
        return role_modulation_surface_sheet_v1()

    def validate_metadata(
        self,
        *,
        roles: Mapping[str, Any],
        role_mismatch_policy: Mapping[str, Any],
    ) -> None:
        validate_role_modulation_surface(
            roles=roles,
            role_mismatch_policy=role_mismatch_policy,
        )

    def augment(
        self,
        U: Mapping[str, Any],
        *,
        role: Optional[str],
    ) -> Dict[str, Any]:
        """
        Return ``U`` with exact datum-level role mismatch bookkeeping attached.

        This does not intentionally redact or obfuscate renderer-facing data.
        Public read surfaces should use ``modulate`` instead.
        """
        return runtime._augment_ctx_with_role_and_role_mismatch_info(
            U,
            role=role,
        )

    def modulate(
        self,
        U: Mapping[str, Any],
        *,
        role: Optional[str],
    ) -> Dict[str, Any]:
        """
        Return a role-modulated renderer/controller-facing UI context vector.

        This is the canonical one-line read-side operation for callers outside
        the role-modulation runtime.
        """
        return runtime._obfuscate_ctx_for_specific_viewer_role(
            U,
            role=role,
        )

    def event_visible(
        self,
        event: Mapping[str, Any],
        *,
        role: Optional[str],
        context_candidates: list[Mapping[str, Any]]
        | tuple[Mapping[str, Any], ...] = (),
    ) -> bool:
        """
        Return whether one live source event may be released to a viewer role.

        This is the event-plane sibling of ``modulate``:

        - controller-loop events are visible and have payload.U projected by the
          caller;
        - datum lifecycle events are dropped unless the viewer role can read the
          event datum by the same datum/span role formalism used for ctx release.
        """
        return runtime.event_visible_for_viewer_role(
            event,
            role=role,
            context_candidates=context_candidates,
        )

    def datum_readable(
        self,
        *,
        datum_id: str,
        role: Optional[str],
        context_candidates: list[Mapping[str, Any]]
        | tuple[Mapping[str, Any], ...],
    ) -> bool:
        """Apply the canonical datum read predicate to an event action target."""
        return runtime.datum_readable_for_viewer_role(
            datum_id=datum_id,
            role=role,
            context_candidates=context_candidates,
        )

    def assert_submission_allowed(
        self,
        U: Mapping[str, Any],
        *,
        role: Optional[str],
        fill: Optional[Mapping[str, Any]] = None,
        signal: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """
        Reject mismatched fill/signal submissions before the roleless backend
        sees them.

        This is a write-side permission guard, not a read-side obfuscation
        operation.
        """
        runtime._this_viewer_role_is_allowed_this_submission(
            U,
            role=role,
            fill=fill,
            signal=signal,
        )


role_modulation = RoleModulationAPI()


__all__ = [
    "RoleMap",
    "RoleMismatchPolicy",
    "RoleModulationAPI",
    "role_modulation",
]
from __future__ import annotations

"""Server-agnostic live-run launching over the standard P / SM / C tape.

A live demo is intentionally smaller than a dry run.

Dry runs own a complete P / SM / C / A / E proof formalism. Live runs reuse
only the authored run inputs:

    P   ThinkProgram
    SM  session metadata, including role surface
    C   initial parameter / puppeteering overrides

The live-run atelier does not apply scripted A packets and does not assert E.
Its only job is to launch one authored P / SM / C tape through a concrete host,
expose the host's role-sealed browser URLs, keep the host alive, and close it.

Concrete hosts implement :class:`BaseLiveDemoLauncherV1`. Host-neutral source,
role, receipt, lifecycle, opinionation-selection grammar, and the one canonical
legacy-host P/SM/C materialization seam stay here so Flask, Django, and future
hosts expose one authoring contract.
"""

import argparse
import json
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

PrepareRuntimeV1 = Callable[[], Any]
LiveDemoHandleV1 = Any


def _route_joint_symbol_surfaces_v1(
    *,
    surfaces: Mapping[str, Any],
    initial_parameter_overrides: Mapping[str, Any],
) -> Mapping[str, Any]:
    # Lazy import keeps the host-neutral source/CLI grammar importable before
    # the concrete thinksession runtime has been composed.
    from _thinksessions.sesh_metadata.sesh_metadata_surface_puppeteering import (
        route_puppeteering_overlay_to_symbol_surfaces_v1,
    )

    return route_puppeteering_overlay_to_symbol_surfaces_v1(
        surfaces=surfaces,
        initial_parameter_overrides=initial_parameter_overrides,
    )


def _bind_session_metadata_symbols_v1(
    session_metadata: Mapping[str, Any],
) -> Mapping[str, Any]:
    from _thinksessions.sesh_metadata.sesh_metadata_surface_puppeteering import (
        bind_session_metadata_symbols_v1,
    )

    return bind_session_metadata_symbols_v1(session_metadata)


@dataclass(frozen=True, slots=True)
class LiveRunTapeV1:
    """One exact authored live-run tape.

    The mappings are copied when the tape is constructed so a hosting adapter
    cannot accidentally mutate the authoring module's reusable constants.
    """

    program: Mapping[str, Any]
    session_metadata: Mapping[str, Any]
    initial_parameter_overrides: Mapping[str, Any]
    source: str = ""

    @property
    def P(self) -> Mapping[str, Any]:
        return self.program

    @property
    def SM(self) -> Mapping[str, Any]:
        return self.session_metadata

    @property
    def C(self) -> Mapping[str, Any]:
        return self.initial_parameter_overrides


@dataclass(frozen=True, slots=True)
class EffectiveLiveRunSurfacesV1:
    """Effective P + SM after applying one launch C over both symbol surfaces.

    Canonical service/session launchers that already accept P/SM/C separately
    should keep doing so. This materialized pair is for older host seams that
    accept only an already-effective program plus already-resolved SM.
    """

    program: Mapping[str, Any]
    session_metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class LiveDemoOpinionationSelectionV1:
    """One host-level frontend opinionation choice for a concrete launch.

    ``use_installed_default=True`` with ``module=None`` means the host must omit
    a per-launch override and let the aggregate static registry's singleton
    installed claim win. ``use_installed_default=False`` means explicit disable.
    A non-null ``module`` is a registered logical JS/MJS asset name and wins over
    the installed default.
    """

    module: Optional[str]
    use_installed_default: bool


@dataclass(frozen=True, slots=True)
class LiveDemoRoleAccessV1:
    """One role-sealed browser/API access surface returned by a host."""

    role: Optional[str]
    urls: Mapping[str, str]

    @property
    def page_url(self) -> str:
        page = str(self.urls.get("page") or "").strip()
        if not page:
            raise RuntimeError(
                f"live-demo access for role {self.role!r} has no page URL"
            )
        return page

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "urls": dict(self.urls),
        }


@dataclass(frozen=True, slots=True)
class LiveDemoLaunchReceiptV1:
    """Host-neutral description of one live demo after lambda/launch."""

    launcher_name: str
    session_id: str
    base_url: str
    selected_role: Optional[str]
    accesses: tuple[LiveDemoRoleAccessV1, ...]

    @property
    def kind(self) -> str:
        return "thinkument_live_demo_launch_receipt_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "launcher_name": self.launcher_name,
            "session_id": self.session_id,
            "base_url": self.base_url,
            "selected_role": self.selected_role,
            "accesses": [row.to_dict() for row in self.accesses],
        }


class BaseLiveDemoLauncherV1(ABC):
    """Minimal exchangeable host contract for a live P / SM / C demo."""

    @property
    @abstractmethod
    def launcher_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def start_v1(
        self,
        *,
        tape: LiveRunTapeV1,
        public_view_role: Optional[str],
    ) -> LiveDemoHandleV1:
        """lambda: start one hosted P / SM / C run."""
        raise NotImplementedError

    @abstractmethod
    def receipt_v1(
        self,
        *,
        handle: LiveDemoHandleV1,
    ) -> LiveDemoLaunchReceiptV1:
        """Describe the live browser/API capabilities for the started run."""
        raise NotImplementedError

    @abstractmethod
    def serve_v1(self, *, handle: LiveDemoHandleV1) -> None:
        """Keep the concrete host alive until its serving loop is stopped."""
        raise NotImplementedError

    @abstractmethod
    def close_v1(self, *, handle: LiveDemoHandleV1) -> None:
        """omega: release the run and all host resources owned by the handle."""
        raise NotImplementedError


def live_run_tape_v1(
    *,
    program: Mapping[str, Any],
    session_metadata: Optional[Mapping[str, Any]] = None,
    initial_parameter_overrides: Optional[Mapping[str, Any]] = None,
    source: str = "",
) -> LiveRunTapeV1:
    """Validate and copy one authored P / SM / C tape."""
    if not isinstance(program, Mapping):
        raise TypeError("P/program must be a mapping")
    if session_metadata is not None and not isinstance(
        session_metadata,
        Mapping,
    ):
        raise TypeError("SM/session_metadata must be a mapping or None")
    if initial_parameter_overrides is not None and not isinstance(
        initial_parameter_overrides,
        Mapping,
    ):
        raise TypeError(
            "C/initial_parameter_overrides must be a mapping or None"
        )

    return LiveRunTapeV1(
        program=deepcopy(dict(program)),
        session_metadata=deepcopy(dict(session_metadata or {})),
        initial_parameter_overrides=deepcopy(
            dict(initial_parameter_overrides or {})
        ),
        source=str(source or ""),
    )


def materialize_joint_p_sm_c_v1(
    tape: LiveRunTapeV1,
) -> EffectiveLiveRunSurfacesV1:
    """Materialize the canonical joint-C semantics for a legacy host seam.

    C parameterizes the union of the symbol surfaces exposed by P and SM:

        C -> Param(P) union Param(SM)

    Modern/canonical service launchers should continue passing P, SM, and C to
    the run-from-here/session facade and let that facade perform the operation.
    Some local hosts predate that combined launch signature and accept only an
    already-effective program plus resolved session metadata. Those hosts call
    this helper exactly once before crossing that boundary.

    The helper intentionally delegates both routing and SM binding to the same
    canonical machinery used elsewhere; it defines no new overlay language.
    """
    if not isinstance(tape, LiveRunTapeV1):
        raise TypeError("tape must be LiveRunTapeV1")

    P = deepcopy(dict(tape.P))
    SM = deepcopy(dict(tape.SM))
    C = deepcopy(dict(tape.C))

    if C:
        routed = _route_joint_symbol_surfaces_v1(
            surfaces={
                "program": P,
                "session_metadata": SM,
            },
            initial_parameter_overrides=C,
        )
        if not isinstance(routed, Mapping):
            raise TypeError("joint P/SM puppeteering router must return a mapping")
        routed_program = routed.get("program")
        routed_sm = routed.get("session_metadata")
        if not isinstance(routed_program, Mapping):
            raise TypeError("joint P/SM router returned non-mapping program")
        if not isinstance(routed_sm, Mapping):
            raise TypeError(
                "joint P/SM router returned non-mapping session_metadata"
            )
        P = deepcopy(dict(routed_program))
        SM = deepcopy(dict(routed_sm))

    resolved_SM = _bind_session_metadata_symbols_v1(SM)
    if not isinstance(resolved_SM, Mapping):
        raise TypeError("resolved SM must be a mapping")

    return EffectiveLiveRunSurfacesV1(
        program=P,
        session_metadata=deepcopy(dict(resolved_SM)),
    )


def split_session_metadata_v1(
    session_metadata: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Split standard SM into host-neutral metadata/roles/policy partitions.

    Flask and Django both ultimately need this separation, but it is not a
    Flask or Django concern. Keeping it here prevents host adapters from
    independently reinterpreting the standard SM role surface.
    """
    if not isinstance(session_metadata, Mapping):
        raise TypeError("session_metadata must be a mapping")

    metadata = deepcopy(dict(session_metadata))
    raw_roles = metadata.pop("roles", {}) or {}
    raw_policy = metadata.pop("role_mismatch_policy", {}) or {}

    if not isinstance(raw_roles, Mapping):
        raise TypeError("session_metadata.roles must be a mapping")
    if not isinstance(raw_policy, Mapping):
        raise TypeError(
            "session_metadata.role_mismatch_policy must be a mapping"
        )

    roles: dict[str, Any] = {}
    for raw_name, value in dict(raw_roles).items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError("session role names must be non-empty")
        if name in roles:
            raise ValueError(f"duplicate normalized session role {name!r}")
        roles[name] = deepcopy(value)

    return metadata, roles, deepcopy(dict(raw_policy))


def choose_public_view_role_v1(
    *,
    roles: Mapping[str, Any],
    requested: Optional[str],
) -> Optional[str]:
    """Choose the host's selected role without changing the role surface.

    Every role still receives its own capability. ``public_view_role`` only
    selects the host's conventional/default capability when a host requires
    one. With multiple roles and no explicit request, authored insertion order
    provides a deterministic default.
    """
    normalized = None
    if requested not in (None, ""):
        normalized = str(requested).strip() or None

    role_names = list(roles)
    if not role_names:
        if normalized is not None:
            raise ValueError(
                "public_view_role cannot be supplied for a roleless SM"
            )
        return None

    if normalized is None:
        return role_names[0]
    if normalized not in roles:
        raise ValueError(
            f"public_view_role {normalized!r} is not one of {role_names!r}"
        )
    return normalized


def live_demo_opinionation_selection_v1(
    *,
    module: Optional[str],
    disable: bool,
) -> LiveDemoOpinionationSelectionV1:
    """Normalize one CLI/programmatic frontend opinionation choice."""
    normalized_module = None
    if module not in (None, ""):
        normalized_module = str(module).strip() or None

    if disable and normalized_module is not None:
        raise ValueError(
            "cannot select --opinionation-module and --no-opinionation together"
        )

    return LiveDemoOpinionationSelectionV1(
        module=normalized_module,
        use_installed_default=not bool(disable),
    )


def resolve_object_ref_v1(ref: str) -> Any:
    """Resolve one explicit ``python.module:attribute.path`` reference."""
    raw = str(ref or "").strip()
    module_name, separator, attr_path = raw.partition(":")
    if not separator or not module_name or not attr_path:
        raise ValueError(
            "object reference must be 'python.module:attribute'"
        )

    value: Any = import_module(module_name)
    for part in attr_path.split("."):
        if not part:
            raise ValueError(f"invalid empty attribute in object ref {raw!r}")
        value = getattr(value, part)
    return value


def _optional_module_attr(
    module: Any,
    name: str,
) -> Any:
    return getattr(module, name) if hasattr(module, name) else None


def live_run_tape_from_module_v1(
    module_name: str,
    *,
    program_attr: str = "PROGRAM",
    session_metadata_attr: str = "SESSION_METADATA",
    overrides_attr: str = "PUPPET",
) -> LiveRunTapeV1:
    """Load conventional P / SM / C constants from one authoring module."""
    normalized = str(module_name or "").strip()
    if not normalized:
        raise ValueError("source module must be non-empty")

    module = import_module(normalized)
    if not hasattr(module, program_attr):
        raise AttributeError(
            f"{normalized!r} has no required {program_attr!r} P/program"
        )

    return live_run_tape_v1(
        program=getattr(module, program_attr),
        session_metadata=_optional_module_attr(
            module,
            session_metadata_attr,
        ),
        initial_parameter_overrides=_optional_module_attr(
            module,
            overrides_attr,
        ),
        source=normalized,
    )


def live_run_tape_from_refs_v1(
    *,
    program_ref: str,
    session_metadata_ref: Optional[str] = None,
    overrides_ref: Optional[str] = None,
) -> LiveRunTapeV1:
    """Load P and optional SM/C from explicit object references."""
    return live_run_tape_v1(
        program=resolve_object_ref_v1(program_ref),
        session_metadata=(
            None
            if not session_metadata_ref
            else resolve_object_ref_v1(session_metadata_ref)
        ),
        initial_parameter_overrides=(
            None
            if not overrides_ref
            else resolve_object_ref_v1(overrides_ref)
        ),
        source=str(program_ref),
    )


def prepare_runtime_hooks_v1(
    hooks: Iterable[PrepareRuntimeV1],
) -> tuple[Any, ...]:
    """Run host-independent registration/composition hooks exactly once."""
    receipts: list[Any] = []
    for hook in hooks:
        if not callable(hook):
            raise TypeError(f"prepare hook is not callable: {hook!r}")
        receipts.append(hook())
    return tuple(receipts)


def prepare_runtime_refs_v1(refs: Sequence[str]) -> tuple[Any, ...]:
    """Resolve and execute repeatable ``--prepare module:callable`` hooks."""
    hooks: list[PrepareRuntimeV1] = []
    for ref in refs:
        value = resolve_object_ref_v1(ref)
        if not callable(value):
            raise TypeError(f"prepare reference {ref!r} is not callable")
        hooks.append(value)
    return prepare_runtime_hooks_v1(hooks)


def render_launch_receipt_v1(
    receipt: LiveDemoLaunchReceiptV1,
    *,
    as_json: bool,
) -> str:
    """Render one launch receipt for humans or shell automation."""
    if as_json:
        return json.dumps(
            receipt.to_dict(),
            indent=2,
            sort_keys=True,
        )

    lines = [
        f"Thinkument live demo via {receipt.launcher_name}",
        f"session: {receipt.session_id}",
        f"server:  {receipt.base_url}",
        "role pages:",
    ]
    for access in receipt.accesses:
        label = access.role if access.role is not None else "default"
        lines.append(f"  {label}: {access.page_url}")
    lines.append("Press Ctrl-C to stop the live demo.")
    return "\n".join(lines)


def run_live_demo_v1(
    *,
    tape: LiveRunTapeV1,
    launcher: BaseLiveDemoLauncherV1,
    public_view_role: Optional[str] = None,
    prepare_runtime: Sequence[PrepareRuntimeV1] = (),
    emit: Callable[[str], Any] = print,
    json_output: bool = False,
) -> LiveDemoLaunchReceiptV1:
    """Prepare, launch, announce, serve, and always close one live demo."""
    if not isinstance(launcher, BaseLiveDemoLauncherV1):
        raise TypeError("launcher must inherit BaseLiveDemoLauncherV1")
    if not isinstance(tape, LiveRunTapeV1):
        raise TypeError("tape must be LiveRunTapeV1")

    prepare_runtime_hooks_v1(prepare_runtime)
    handle: Any = None
    try:
        handle = launcher.start_v1(
            tape=tape,
            public_view_role=public_view_role,
        )
        receipt = launcher.receipt_v1(handle=handle)
        emit(render_launch_receipt_v1(receipt, as_json=json_output))
        launcher.serve_v1(handle=handle)
        return receipt
    finally:
        if handle is not None:
            launcher.close_v1(handle=handle)


def add_live_run_source_arguments_v1(
    parser: argparse.ArgumentParser,
) -> None:
    """Install the shared P / SM / C authoring-source CLI arguments."""
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--source",
        metavar="PYTHON_MODULE",
        help=(
            "Load conventional PROGRAM plus optional SESSION_METADATA and "
            "PUPPET constants from one module."
        ),
    )
    source.add_argument(
        "--program",
        metavar="MODULE:ATTRIBUTE",
        help="Explicit P/ThinkProgram object reference.",
    )
    parser.add_argument(
        "--session-metadata",
        metavar="MODULE:ATTRIBUTE",
        help="Explicit SM object reference; valid only with --program.",
    )
    parser.add_argument(
        "--overrides",
        metavar="MODULE:ATTRIBUTE",
        help="Explicit C object reference; valid only with --program.",
    )
    parser.add_argument(
        "--prepare",
        metavar="MODULE:CALLABLE",
        action="append",
        default=[],
        help=(
            "Runtime registration/composition hook. Repeat for multiple "
            "independent app packs."
        ),
    )
    parser.add_argument(
        "--public-view-role",
        default=None,
        help=(
            "Optional selected/default role. Every declared role still gets "
            "its own URL."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print the launch receipt as JSON instead of human-readable text.",
    )


def add_live_run_opinionation_arguments_v1(
    parser: argparse.ArgumentParser,
) -> None:
    """Install the shared per-launch frontend opinionation CLI grammar."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--opinionation-module",
        default=None,
        metavar="LOGICAL_JS_ASSET",
        help=(
            "Registered logical .js/.mjs opinionation asset for this launch. "
            "Omit to use the installed package default."
        ),
    )
    group.add_argument(
        "--no-opinionation",
        action="store_true",
        help=(
            "Explicitly disable opinionation for this launch instead of using "
            "the installed package default."
        ),
    )


def live_run_opinionation_from_namespace_v1(
    args: argparse.Namespace,
) -> LiveDemoOpinionationSelectionV1:
    return live_demo_opinionation_selection_v1(
        module=getattr(args, "opinionation_module", None),
        disable=bool(getattr(args, "no_opinionation", False)),
    )


def live_run_tape_from_namespace_v1(
    args: argparse.Namespace,
) -> LiveRunTapeV1:
    """Build one tape from arguments installed by the shared CLI helper."""
    if getattr(args, "source", None):
        if getattr(args, "session_metadata", None) or getattr(
            args,
            "overrides",
            None,
        ):
            raise ValueError(
                "--session-metadata/--overrides are explicit-reference "
                "options and cannot be combined with --source"
            )
        return live_run_tape_from_module_v1(str(args.source))

    return live_run_tape_from_refs_v1(
        program_ref=str(args.program),
        session_metadata_ref=getattr(args, "session_metadata", None),
        overrides_ref=getattr(args, "overrides", None),
    )


__all__ = [
    "BaseLiveDemoLauncherV1",
    "EffectiveLiveRunSurfacesV1",
    "LiveDemoHandleV1",
    "LiveDemoLaunchReceiptV1",
    "LiveDemoOpinionationSelectionV1",
    "LiveDemoRoleAccessV1",
    "LiveRunTapeV1",
    "PrepareRuntimeV1",
    "add_live_run_opinionation_arguments_v1",
    "add_live_run_source_arguments_v1",
    "choose_public_view_role_v1",
    "live_demo_opinionation_selection_v1",
    "live_run_opinionation_from_namespace_v1",
    "live_run_tape_from_module_v1",
    "live_run_tape_from_namespace_v1",
    "live_run_tape_from_refs_v1",
    "live_run_tape_v1",
    "materialize_joint_p_sm_c_v1",
    "prepare_runtime_hooks_v1",
    "prepare_runtime_refs_v1",
    "render_launch_receipt_v1",
    "resolve_object_ref_v1",
    "run_live_demo_v1",
    "split_session_metadata_v1",
]

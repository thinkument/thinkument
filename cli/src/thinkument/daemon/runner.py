"""In-process P x SM x C x W execution runner for local studio daemon."""
from __future__ import annotations

import copy
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional

from _thinksessions.run.run_from_here import (
    create_live_session_from_program,
    delete_live_session,
    dispatch_live_session_action_with_chain_reaction,
    get_live_session_events,
    get_live_session_events_since,
    get_live_session_latest_event_seq,
    render_live_session_state,
    run_funked_black_box_from_program,
)
from thinkument.daemon.interceptor import VendorInvocation, default_mock_interceptor

# Ensure default languages and runtime composition are bootstrapped
try:
    import _thinkprogram.thinkprogramTM._program_language
    from _thinkprogram.thinkprogramTM.api import LANG_THINK_PROGRAM_V1
    from _thinkprogram._thinkcontinuitykernelTM.api import register_kernel_step_fn_v1
    register_kernel_step_fn_v1()
except ImportError:
    LANG_THINK_PROGRAM_V1 = "think_program_v1"

try:
    from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
        pull_thinkwidget_class_into_kernel_v1,
    )
    from _thinksessions.example_reused_test_flow_setups.widgets.test import DEMO_WIDGET_CLASSES
    for _cls in DEMO_WIDGET_CLASSES:
        pull_thinkwidget_class_into_kernel_v1(_cls, overwrite=True)
except Exception:
    pass


class LocalSessionRunner:
    """Manages active in-memory Thinkument sessions for local studio execution."""

    def __init__(self, default_interceptor: Optional[Callable[[VendorInvocation], Dict[str, Any]]] = None) -> None:
        self._interceptor = default_interceptor or default_mock_interceptor
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def set_interceptor(self, interceptor: Callable[[VendorInvocation], Dict[str, Any]]) -> None:
        self._interceptor = interceptor

    def get_interceptor(self) -> Callable[[VendorInvocation], Dict[str, Any]]:
        return self._interceptor

    def create_session(
        self,
        *,
        P: Mapping[str, Any],
        SM: Optional[Mapping[str, Any]] = None,
        C: Optional[Mapping[str, Any]] = None,
        roles: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        public_view_role: Optional[str] = None,
        base_url: str = "http://localhost:5052",
        interceptor: Optional[Callable[[VendorInvocation], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create a local P x SM x C live session with role-sealed access handles."""
        effective_interceptor = interceptor or self._interceptor

        # Resolve launch metadata and roles
        effective_sm = copy.deepcopy(dict(SM or {}))
        if roles and "roles" not in effective_sm:
            effective_sm["roles"] = copy.deepcopy(dict(roles))

        # Create session via highest authoring run facade
        created = create_live_session_from_program(
            program=P,
            program_language=LANG_THINK_PROGRAM_V1,
            initial_parameter_overrides=C,
            session_metadata=effective_sm,
            roles=roles,
        )
        session_id = str(created["session_id"])

        # Determine roles for handle generation
        discovered_roles: List[str] = []
        if roles:
            discovered_roles = list(roles.keys())
        elif "roles" in effective_sm and isinstance(effective_sm["roles"], Mapping):
            discovered_roles = list(effective_sm["roles"].keys())
        if not discovered_roles:
            discovered_roles = ["default"]

        default_role = public_view_role or discovered_roles[0]

        # Generate role-sealed URL handles
        handles = {}
        for r in discovered_roles:
            slug = f"{session_id}_{r}"
            handles[r] = {
                "slug": slug,
                "role": r,
                "url": f"{base_url}/live/{slug}",
                "path": f"/live/{slug}",
            }

        selected_slug = f"{session_id}_{default_role}"
        launch_result = {
            "kind": "web_RESTful_launch_result_v1",
            "session_id": session_id,
            "starter_id": f"local_starter_{session_id[:8]}",
            "metadata": dict(metadata or {}),
            "public_view_role": default_role,
            "selected": {
                "slug": selected_slug,
                "role": default_role,
                "url": f"{base_url}/live/{selected_slug}",
                "path": f"/live/{selected_slug}",
            },
            "handles": handles,
            "launch_state": {
                "current_step": 0,
                "status": "mounted",
            },
            "analytics": {
                "dashboard_url": f"{base_url}/analytics/{session_id}",
                "events_url": f"{base_url}/api/v1/sessions/{session_id}/events/",
            },
        }

        self._sessions[session_id] = {
            "session_id": session_id,
            "P": P,
            "SM": effective_sm,
            "C": C,
            "launch_result": launch_result,
            "interceptor": effective_interceptor,
        }

        return launch_result

    def dispatch(
        self,
        session_id: str,
        *,
        action: str = "STEP",
        user_fill: Optional[Mapping[str, Any]] = None,
        user_signal: Optional[Mapping[str, Any]] = None,
        role: Optional[str] = None,
        cursor: Optional[int] = None,
        identity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch data and/or signals targeting widgets on the current step."""
        sid = str(session_id)
        client_id = identity_id or f"client_{sid[:8]}"

        receipt = dispatch_live_session_action_with_chain_reaction(
            session_id=sid,
            action=action,
            identity_id=client_id,
            user_fill=user_fill,
            user_signal=user_signal,
            role=role,
            my_current_event_seq_number=cursor,
        )
        return receipt

    def get_state(self, session_id: str, *, role: Optional[str] = None) -> Dict[str, Any]:
        """Render current session state for the given role."""
        try:
            return render_live_session_state(session_id=str(session_id), role=role)
        except Exception:
            sid = str(session_id)
            if sid in self._sessions:
                return {
                    "kind": "unprimed_session_state_v1",
                    "session_id": sid,
                    "status": "ATSTART",
                    "launch_state": self._sessions[sid]["launch_result"]["launch_state"],
                }
            raise

    def get_events(
        self,
        session_id: str,
        *,
        after_seq: Optional[int] = None,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch theta event window since after_seq."""
        return get_live_session_events_since(
            session_id=str(session_id),
            role=role,
            after_event_seq=after_seq,
        )

    def close_session(self, session_id: str) -> Dict[str, Any]:
        """Delete an active session."""
        sid = str(session_id)
        self._sessions.pop(sid, None)
        return delete_live_session(session_id=sid)

    def run_blackbox(
        self,
        *,
        P: Mapping[str, Any],
        C: Optional[Mapping[str, Any]] = None,
        SM: Optional[Mapping[str, Any]] = None,
        roles: Optional[Mapping[str, Any]] = None,
        timeout_seconds: int = 60,
    ) -> Dict[str, Any]:
        """Execute one complete P/SM/C black-box run to ATCOMPLETION."""
        effective_sm = copy.deepcopy(dict(SM or {}))
        # Ensure chainreactionTM is enabled for black-box execution
        if "chainreactionTM" not in effective_sm:
            effective_sm["chainreactionTM"] = {"enabled": True}

        result = run_funked_black_box_from_program(
            program=P,
            program_language="python",
            initial_parameter_overrides=C,
            session_metadata=effective_sm,
            roles=roles,
        )
        return result

    def submit_job(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        """Execute or queue a custom envelope job using the configured interceptor."""
        job_id = str(uuid.uuid4())
        channel = envelope.get("channel") or ("vibe_coder" if "goal" in envelope else "vendor_op")
        call_key = envelope.get("call_key") or f"local_{job_id[:8]}"

        chain = envelope.get("chain")
        if not chain:
            op = envelope.get("operation") or envelope.get("fn")
            if op:
                chain = [{"id": "op_0", "fn": op, "args": envelope.get("args") or {}}]
            elif channel == "vibe_coder" or "goal" in envelope:
                chain = [{"id": "vibe_step", "fn": "program.vibe_synthesize", "args": envelope}]
            else:
                chain = []

        outputs = {}
        synthesized_prog = None

        for idx, step in enumerate(chain):
            step_id = step.get("id", f"step_{idx}")
            fn = step.get("fn", "")
            args = step.get("args") or {}

            if channel == "vibe_coder" or fn == "program.vibe_synthesize":
                step_args = {**envelope, **(args or {})}
                if isinstance(envelope.get("args"), dict):
                    step_args.update(envelope["args"])
                goal = step_args.get("goal") or "Local Vibe Program"
                synthesized_prog = self._synthesize_local_program(
                    goal=goal,
                    instruction=step_args.get("instruction", ""),
                    existing_program=step_args.get("program") or step_args.get("existing_program"),
                )
                step_res = {
                    "ok": True,
                    "status": "synthesized",
                    "program": synthesized_prog,
                    "fn": fn,
                }
            else:
                inv = VendorInvocation(
                    operation=fn,
                    modality=args.get("modality", "general"),
                    args=args,
                    call_key=call_key,
                    vendor=args.get("vendor"),
                    context=envelope.get("context"),
                )
                step_res = self.get_interceptor()(inv)
            outputs[step_id] = step_res

        last_res = outputs.get(chain[-1]["id"]) if chain else {}
        job_record = {
            "job_id": job_id,
            "status": "success",
            "progress": {"percent": 100, "message": "Completed"},
            "channel": channel,
            "call_key": call_key,
            "outputs": outputs,
            "result": last_res,
            "program": synthesized_prog or last_res.get("program"),
            "error": None,
        }
        self._jobs[job_id] = job_record
        return job_record

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._jobs.get(str(job_id))

    def _synthesize_local_program(
        self,
        goal: str,
        *,
        instruction: str = "",
        existing_program: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Local zero-cost deterministic program synthesis matching canonical schema."""
        if existing_program and instruction:
            updated = copy.deepcopy(existing_program)
            flow = updated.get("run", {}).get("program", {}).get("flow", [])
            new_step_id = f"step_{len(flow) + 1}"
            widgets = updated.setdefault("run", {}).setdefault("program", {}).setdefault("widgets", {})
            widgets[f"w_{new_step_id}"] = {
                "widget": {
                    "kind": "json_widget_v1",
                    "name": f"w_{new_step_id}",
                    "declaration": {"inputs": {}, "outputs": {}},
                    "signals": {
                        "mount": {
                            "execution": "sync",
                            "returns": {
                                "reexplode": {"title": "Review Step"},
                                "outputs": {"summary": {"status": f"EVOLVED: {instruction[:40]}"}},
                            },
                        },
                        "fill": {
                            "execution": "sync",
                            "returns": {"done": True, "outputs": {"summary": {"status": "COMPLETED"}}},
                        },
                    },
                },
                "args": {"note": instruction[:60]},
                "roles": ["reviewer"],
            }
            flow.append({"id": new_step_id, "widgets": [f"w_{new_step_id}"]})
            return updated

        prog_id = f"local_prog_{uuid.uuid4().hex[:8]}"
        title = f"Local Vibe: {goal[:50].strip()}"
        return {
            "kind": "think_program_v1",
            "surface_version": "v1",
            "run": {
                "info": {"id": prog_id, "title": title},
                "program": {
                    "info": {"id": prog_id, "title": title},
                    "widgets": {
                        "main_widget": {
                            "widget": {
                                "kind": "json_widget_v1",
                                "name": "main_widget",
                                "declaration": {
                                    "inputs": {},
                                    "outputs": {"summary": {"kind": "dict", "fields": {"status": {"kind": "str"}}}},
                                    "args": {"goal": {"type": "str"}},
                                },
                                "signals": {
                                    "mount": {
                                        "execution": "sync",
                                        "returns": {"outputs": {"summary": {"status": f"INITIALIZED: {goal[:40]}"}}},
                                    },
                                    "fill": {
                                        "execution": "sync",
                                        "returns": {"done": True, "outputs": {"summary": {"status": "COMPLETED"}}},
                                    },
                                },
                            },
                            "args": {"goal": goal},
                            "roles": ["user"],
                        }
                    },
                    "flow": [{"id": "step_1", "widgets": ["main_widget"]}],
                },
            },
        }

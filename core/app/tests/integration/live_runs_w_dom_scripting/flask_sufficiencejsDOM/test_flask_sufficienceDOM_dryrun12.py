from __future__ import annotations

"""Direct DOM-scripted Program 12 integration runs through sufficience.js.

The five authored P12 scenarios are exercised as five ordinary DOMScriptr Runs
while one Chromium Browser is reused across them. No dry-run runner, funked
case catalog, strategy adapter, or A/E matcher participates.

The application-specific script knows only the sufficience DOM controls it
manipulates and the browser-visible server receipt it chooses to inspect.
"""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from playwright.async_api import expect

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program12__funked_puzzle_generation_and_completion import (  # noqa: E402
    PROGRAM12_SCENARIOS,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.registration import (  # noqa: E402
    register_dry_run_lib_widgets_flows_v1,
)
from ways_to_run.live_run_atelier._whichserver_agnostic_demo_launcher import (  # noqa: E402
    LiveDemoOpinionationSelectionV1,
    live_run_tape_v1,
)
from ways_to_run.live_run_DOMscripted_atelier._whichserver_agnostic_scripted_DOM_run_launcher import (  # noqa: E402
    ScriptedDOMAtelierV1,
)
from ways_to_run.live_run_DOMscripted_atelier.flask_scripted_DOM_run_launcher import (  # noqa: E402
    flask_role_url_key_v1,
    run_flask_scripted_dom_in_atelier_v1,
)


SUFFICIENCE_MODULE = "test_opinionations/sufficience.js"
SUFFICIENCE_ROOT = (
    '[data-thinkument-sufficience="thinkument_test_sufficience_opinionation_v1"]'
)
SUMMARY = "[data-sufficience-summary]"
ASSERT_TIMEOUT_MS = 5_000


def _launch_options() -> dict[str, object]:
    explicit = os.getenv("DOMSCRIPTR_BROWSER_EXECUTABLE")
    executable = explicit or shutil.which("chromium") or shutil.which("google-chrome")
    return {"executable_path": executable} if executable else {}


async def _booted(client) -> None:
    await expect(client.page.locator(SUFFICIENCE_ROOT)).to_have_count(1)
    await expect(
        client.page.get_by_role("heading", name="Thinkument sufficience station")
    ).to_be_visible()


async def _summary(client) -> Mapping[str, Any]:
    raw = await client.page.locator(SUMMARY).text_content()
    value = json.loads(raw or "{}")
    if not isinstance(value, Mapping):
        raise AssertionError(f"sufficience summary is not an object: {value!r}")
    return value


async def _assert_active(client, expected: list[str] | None) -> None:
    try:
        await client.wait_js(
            """(expected) => {
              const node = document.querySelector('[data-sufficience-summary]');
              if (!node) return false;
              try {
                const row = JSON.parse(node.textContent || '{}');
                return JSON.stringify(row.active_widget_ids ?? null)
                  === JSON.stringify(expected);
              } catch { return false; }
            }""",
            expected,
            timeout=ASSERT_TIMEOUT_MS,
        )
    except Exception as exc:
        actual = await _summary(client)
        raise AssertionError(
            f"active widgets did not converge: expected={expected!r}, "
            f"actual={dict(actual)!r}"
        ) from exc


async def _assert_complete(client) -> None:
    try:
        await client.wait_js(
            """() => {
              const node = document.querySelector('[data-sufficience-summary]');
              if (!node) return false;
              try {
                const row = JSON.parse(node.textContent || '{}');
                return row.runtime_kind === 'ATCOMPLETION'
                  && (row.active_widget_ids ?? null) === null;
              } catch { return false; }
            }""",
            timeout=ASSERT_TIMEOUT_MS,
        )
    except Exception as exc:
        actual = await _summary(client)
        raise AssertionError(
            f"client did not render completion: actual={dict(actual)!r}"
        ) from exc


async def _set_micro(client, datum_id: str, micro_name: str, value: Any) -> None:
    suffix = f'[data-datum-id="{datum_id}"][data-micro-name="{micro_name}"]'
    include = client.page.locator(
        f'[data-sufficience-micro-include="1"]{suffix}'
    )
    editor = client.page.locator(
        f'[data-sufficience-micro-value="1"]{suffix}'
    )
    await expect(include).to_have_count(1)
    await expect(editor).to_have_count(1)
    await include.check()
    await editor.fill(json.dumps(value, separators=(",", ":")))


async def _dispatch_funked_step(
    client,
    *,
    fill: Mapping[str, Mapping[str, Any]] | None = None,
) -> Mapping[str, Any]:
    for datum_id, micros in dict(fill or {}).items():
        for micro_name, value in dict(micros).items():
            await _set_micro(client, str(datum_id), str(micro_name), value)

    request_id = f"p12-dom-{uuid4().hex}"
    await client.page.locator("[data-sufficience-request-id]").fill(request_id)
    await client.page.locator("[data-sufficience-funked]").check()
    await client.page.locator('[data-sufficience-action="STEP"]').click()

    outcome = await client.wait_js(
        """(rid) => {
          const parse = (selector) => {
            const node = document.querySelector(selector);
            if (!node) return null;
            try { return JSON.parse(node.textContent || 'null'); } catch { return null; }
          };
          const result = parse('[data-sufficience-dispatch-result]');
          if (result && result.request_id === rid) return result;
          const local = parse('[data-sufficience-local-receipt]');
          if (local?.kind === 'thinkument_sufficience_local_error_v1') {
            throw new Error(`local sufficience dispatch error: ${JSON.stringify(local)}`);
          }
          if (
            local?.kind === 'thinkument_outbound_dispatch_validation_v1'
            && local.ok === false
          ) {
            throw new Error(`local sufficience rejection: ${JSON.stringify(local)}`);
          }
          return false;
        }""",
        request_id,
        timeout=ASSERT_TIMEOUT_MS,
    )
    if not isinstance(outcome, Mapping):
        raise AssertionError(f"funked DOM dispatch returned non-object: {outcome!r}")
    return outcome


def _after_event_seq(result: Mapping[str, Any]) -> int:
    pocket = result.get("dispatch_concurrency")
    if not isinstance(pocket, Mapping):
        raise AssertionError(f"dispatch result lacks concurrency pocket: {result!r}")
    value = pocket.get("after_event_seq")
    if type(value) is not int:
        raise AssertionError(f"after_event_seq is not an exact int: {value!r}")
    return value


async def _sync_to(client, event_seq: int) -> None:
    """Causal barrier: transport sync, then rendered sufficience cursor sync."""
    await client.page.evaluate(
        """async (wanted) => {
          const root = document.querySelector('[data-thinkument-config-id]');
          const control = root?.thinkumentClientControl;
          if (!control || typeof control.syncTo !== 'function') {
            throw new Error('Thinkument browser control syncTo is unavailable');
          }
          await control.syncTo(wanted);
        }""",
        int(event_seq),
    )
    await client.wait_js(
        """(wanted) => {
          const node = document.querySelector('[data-sufficience-summary]');
          if (!node) return false;
          try {
            const row = JSON.parse(node.textContent || '{}');
            return Number.isInteger(row.cursor) && row.cursor >= wanted;
          } catch { return false; }
        }""",
        int(event_seq),
        timeout=ASSERT_TIMEOUT_MS,
    )


async def _sync_all(clients: Mapping[str, Any], result: Mapping[str, Any]) -> int:
    high = _after_event_seq(result)
    await asyncio.gather(*(_sync_to(client, high) for client in clients.values()))
    return high


def _stopped_reason(result: Mapping[str, Any]) -> str:
    receipt = result.get("chainreactionTM_receipt")
    if not isinstance(receipt, Mapping):
        raise AssertionError(f"funked result lacks chainreaction receipt: {result!r}")
    return str(receipt.get("stopped_reason") or "")


def _roles_for(scenario: Mapping[str, Any]) -> list[str]:
    SM = scenario.get("session_metadata")
    if not isinstance(SM, Mapping):
        raise AssertionError("P12 scenario session_metadata must be a mapping")
    roles = SM.get("roles")
    if not isinstance(roles, Mapping) or not roles:
        raise AssertionError("P12 scenario must expose named roles")
    return [str(role) for role in roles]


async def _clients_for(run, roles: list[str]) -> dict[str, Any]:
    values = await asyncio.gather(
        *(
            run.client(
                run.urls[flask_role_url_key_v1(role)],
                name=role,
            )
            for role in roles
        )
    )
    clients = dict(zip(roles, values))
    await asyncio.gather(*(_booted(client) for client in values))
    return clients


async def _script_start_to_finish(run) -> Mapping[str, Any]:
    clients = await _clients_for(run, ["solver"])
    actor = clients["solver"]
    assert (await _summary(actor)).get("runtime_kind") == "ATSTART"

    result = await _dispatch_funked_step(actor)
    assert result.get("event_kind") == "ATCOMPLETION"
    assert result.get("finished") is True
    assert _stopped_reason(result) == "program_complete_or_not_manual"
    high = await _sync_all(clients, result)
    await _assert_complete(actor)
    return {"ok": True, "final_event_seq": high}


async def _script_one_widget_retry(run) -> Mapping[str, Any]:
    clients = await _clients_for(run, ["solver"])
    actor = clients["solver"]
    assert (await _summary(actor)).get("runtime_kind") == "ATSTART"

    result = await _dispatch_funked_step(actor)
    assert result.get("event_kind") == "ATCOMPLETION"
    chain = result.get("chainreactionTM_receipt")
    assert isinstance(chain, Mapping)
    assert int(chain.get("generated_dispatches_e2e") or 0) == 2
    high = await _sync_all(clients, result)
    await _assert_complete(actor)
    return {"ok": True, "final_event_seq": high}


async def _script_many_widgets_many_roles(run) -> Mapping[str, Any]:
    roles = ["generator", "solver_a", "solver_b"]
    clients = await _clients_for(run, roles)
    assert (await _summary(clients["generator"])).get("runtime_kind") == "ATSTART"

    result = await _dispatch_funked_step(clients["generator"])
    assert result.get("event_kind") == "ATCOMPLETION"
    chain = result.get("chainreactionTM_receipt")
    assert isinstance(chain, Mapping)
    assert int(chain.get("generated_dispatches_e2e") or 0) == 5
    high = await _sync_all(clients, result)
    await asyncio.gather(*(_assert_complete(client) for client in clients.values()))
    return {"ok": True, "final_event_seq": high}


async def _script_funked_and_human_collaboration(run) -> Mapping[str, Any]:
    roles = ["generator", "human_reviewer", "solver"]
    clients = await _clients_for(run, roles)
    assert (await _summary(clients["generator"])).get("runtime_kind") == "ATSTART"

    generated = await _dispatch_funked_step(clients["generator"])
    assert generated.get("event_kind") == "MANUALFILLNEEDEDSTEP"
    assert _stopped_reason(generated) == "next_pending_role_unchainreactioned"
    await _sync_all(clients, generated)
    await _assert_active(clients["human_reviewer"], ["checkpoint"])

    completed = await _dispatch_funked_step(
        clients["human_reviewer"],
        fill={"checkpoint": {"approval": "approve"}},
    )
    assert completed.get("event_kind") == "ATCOMPLETION"
    assert _stopped_reason(completed) == "program_complete_or_not_manual"
    high = await _sync_all(clients, completed)
    await asyncio.gather(*(_assert_complete(client) for client in clients.values()))
    return {"ok": True, "final_event_seq": high}


async def _script_multi_human_multi_funked_collaboration(run) -> Mapping[str, Any]:
    roles = [
        "generator",
        "human_reviewer_a",
        "solver_a",
        "human_reviewer_b",
        "solver_b",
    ]
    clients = await _clients_for(run, roles)
    assert (await _summary(clients["generator"])).get("runtime_kind") == "ATSTART"

    first = await _dispatch_funked_step(clients["generator"])
    assert first.get("event_kind") == "MANUALFILLNEEDEDSTEP"
    assert _stopped_reason(first) == "next_pending_role_unchainreactioned"
    await _sync_all(clients, first)
    await _assert_active(clients["human_reviewer_a"], ["checkpoint_a"])

    second = await _dispatch_funked_step(
        clients["human_reviewer_a"],
        fill={"checkpoint_a": {"approval": "approve"}},
    )
    assert second.get("event_kind") == "MANUALFILLNEEDEDSTEP"
    assert _stopped_reason(second) == "next_pending_role_unchainreactioned"
    await _sync_all(clients, second)
    await _assert_active(clients["human_reviewer_b"], ["checkpoint_b"])

    third = await _dispatch_funked_step(
        clients["human_reviewer_b"],
        fill={"checkpoint_b": {"approval": "approve"}},
    )
    assert third.get("event_kind") == "ATCOMPLETION"
    assert _stopped_reason(third) == "program_complete_or_not_manual"
    high = await _sync_all(clients, third)
    await asyncio.gather(*(_assert_complete(client) for client in clients.values()))
    return {"ok": True, "final_event_seq": high}


_SCRIPTS = {
    "start_to_finish": _script_start_to_finish,
    "one_widget_retry": _script_one_widget_retry,
    "many_widgets_many_roles": _script_many_widgets_many_roles,
    "funked_and_human_collaboration": _script_funked_and_human_collaboration,
    "multi_human_multi_funked_collaboration": (
        _script_multi_human_multi_funked_collaboration
    ),
}


async def _run_v1() -> None:
    register_dry_run_lib_widgets_flows_v1()
    opinionation = LiveDemoOpinionationSelectionV1(
        module=SUFFICIENCE_MODULE,
        use_installed_default=True,
    )

    # One Browser is amortized over all five independent server/session Runs.
    async with ScriptedDOMAtelierV1(
        headless=True,
        launch_options=_launch_options(),
    ) as atelier:
        for name, scenario in PROGRAM12_SCENARIOS.items():
            roles = _roles_for(scenario)
            tape = live_run_tape_v1(
                program=scenario["program"],
                session_metadata=scenario["session_metadata"],
                initial_parameter_overrides=None,
                source=f"{__name__}:{name}",
            )
            receipt = await run_flask_scripted_dom_in_atelier_v1(
                atelier=atelier,
                tape=tape,
                script=_SCRIPTS[name],
                opinionation=opinionation,
                public_view_role=roles[0],
                start_on_create=False,
            )
            assert isinstance(receipt.result, Mapping)
            assert receipt.result.get("ok") is True


def test_flask_sufficienceDOM_dryrun12() -> None:
    asyncio.run(_run_v1())


if __name__ == "__main__":
    asyncio.run(_run_v1())

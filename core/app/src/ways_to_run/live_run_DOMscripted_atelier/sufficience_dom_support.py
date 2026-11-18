from __future__ import annotations

"""Server-neutral direct-DOM helpers for Thinkument sufficience scripts.

This module is deliberately not a dry-run adapter. It knows no dry-run case
catalog, A/E matcher, or strategy grammar. It is a small convenience surface
over the public ``sufficience.js`` DOM, ThinkumentJS' public browser control /
loopback seams, and DOMScriptr clients.

Both Flask- and Django-hosted scripted live-run proofs use this same module so
only the server adapter changes between the two E2E membranes.
"""

import asyncio
import json
import os
import shutil
from copy import deepcopy
from typing import Any, Iterable, Mapping
from uuid import uuid4

from playwright.async_api import expect


SUFFICIENCE_MODULE = "test_opinionations/sufficience.js"
SUFFICIENCE_ROOT = (
    '[data-thinkument-sufficience="thinkument_test_sufficience_opinionation_v1"]'
)
SUMMARY = "[data-sufficience-summary]"
ASSERT_TIMEOUT_MS = 5_000

_LOCAL_RECEIPT_WATCH = "__domscriptrSufficienceLocalReceiptWatch"


def browser_launch_options_v1() -> dict[str, object]:
    explicit = os.getenv("DOMSCRIPTR_BROWSER_EXECUTABLE")
    executable = (
        explicit
        or shutil.which("chromium")
        or shutil.which("google-chrome")
    )
    return {"executable_path": executable} if executable else {}


async def booted_v1(client) -> None:
    await expect(client.page.locator(SUFFICIENCE_ROOT)).to_have_count(1)
    await expect(
        client.page.get_by_role(
            "heading",
            name="Thinkument sufficience station",
        )
    ).to_be_visible()


async def summary_v1(client) -> Mapping[str, Any]:
    raw = await client.page.locator(SUMMARY).text_content()
    value = json.loads(raw or "{}")
    if not isinstance(value, Mapping):
        raise AssertionError(f"sufficience summary is not an object: {value!r}")
    return value


async def assert_summary_v1(
    client,
    *,
    active: list[str] | None,
    runtime_kind: str | None = None,
) -> None:
    expected_json = json.dumps(
        {
            "active": active,
            "runtimeKind": runtime_kind,
        },
        separators=(",", ":"),
        sort_keys=True,
    )

    try:
        await client.wait_js(
            """(expectedJSON) => {
              const expected = JSON.parse(expectedJSON);
              const node = document.querySelector('[data-sufficience-summary]');
              if (!node) return false;
              let row;
              try { row = JSON.parse(node.textContent || '{}'); }
              catch { return false; }

              const actualActive = row.active_widget_ids ?? null;
              const activeOK = JSON.stringify(actualActive)
                === JSON.stringify(expected.active);
              const kindOK = expected.runtimeKind === null
                || row.runtime_kind === expected.runtimeKind;
              return activeOK && kindOK;
            }""",
            expected_json,
            timeout=ASSERT_TIMEOUT_MS,
        )
    except Exception as exc:
        actual = await summary_v1(client)
        raise AssertionError(
            "sufficience summary did not converge: "
            f"expected={json.loads(expected_json)!r}, actual={dict(actual)!r}"
        ) from exc


async def read_q_v1(client) -> Mapping[str, Any]:
    value = await client.page.evaluate(
        """() => {
          const root = document.querySelector('[data-thinkument-config-id]');
          const loopback = root?.thinkumentLoopback;
          if (!loopback || typeof loopback.readQ !== 'function') {
            throw new Error('Thinkument loopback.readQ is unavailable');
          }
          return loopback.readQ();
        }"""
    )
    if not isinstance(value, Mapping):
        raise AssertionError(f"Thinkument Q is not an object: {value!r}")
    return value


async def current_u_v1(client) -> Mapping[str, Any] | None:
    Q = await read_q_v1(client)
    value = Q.get("latest_U")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise AssertionError(f"Q.latest_U is not an object/null: {value!r}")
    return value


async def latest_trident_v1(client) -> Mapping[str, Any]:
    Q = await read_q_v1(client)
    actions = [
        row
        for row in list(Q.get("actions") or [])
        if isinstance(row, Mapping)
    ]
    if not actions:
        raise AssertionError(f"Q contains no committed action trident: {Q!r}")
    latest = dict(actions[-1])
    if not latest.get("informative_events"):
        dispatch_id = str(latest.get("dispatch_id") or "").strip()
        eps_rows = list(Q.get("eps_rows") or [])
        matching = [
            r
            for r in eps_rows
            if isinstance(r, Mapping)
            and (
                (dispatch_id and str(r.get("trident_dispatch_id") or "").strip() == dispatch_id)
                or (dispatch_id and str(r.get("request_id") or "").strip() == dispatch_id)
            )
        ]
        selected = matching
        def _to_informative(r: Mapping[str, Any]) -> Dict[str, Any]:
            payload = r.get("payload")
            base = dict(payload) if isinstance(payload, Mapping) else {"payload": payload}
            if "channel" in r and "name" not in base:
                base["name"] = r["channel"]
            if "channel" in r and "channel" not in base:
                base["channel"] = r["channel"]
            if "datum_id" in r and "datum_id" not in base:
                base["datum_id"] = r["datum_id"]
            if "event_id" in r and "event_id" not in base:
                base["event_id"] = r["event_id"]
            return base

        latest["informative_events"] = [_to_informative(r) for r in selected]
        latest["eps_rows"] = selected
    return latest


def _latest_informative_rows_from_trident_v1(
    trident: Mapping[str, Any],
    *,
    q: Optional[Mapping[str, Any]] = None,
) -> list[Mapping[str, Any]]:
    rows = [
        row
        for row in list(trident.get("informative_events") or [])
        if isinstance(row, Mapping)
    ]
    if rows:
        return rows
    if q is not None:
        dispatch_id = str(trident.get("dispatch_id") or "").strip()
        eps_rows = list(q.get("eps_rows") or [])
        if dispatch_id:
            return [
                r
                for r in eps_rows
                if isinstance(r, Mapping)
                and (
                    str(r.get("trident_dispatch_id") or "").strip() == dispatch_id
                    or str(r.get("request_id") or "").strip() == dispatch_id
                )
            ]
        return []
    return []


async def assert_latest_contains_v1(client, *needles: str) -> None:
    """Assert textual needles only against the latest informative middle.

    This intentionally does not search the entire trident. A value present only
    in controller start/end U, metadata, provenance, or another unrelated
    trident field must not satisfy an assertion intended to prove informative
    middle behavior.

    Prefer ``assert_latest_informative_events_v1`` when the expected event
    structure is known and an exact structural assertion can be expressed.
    """

    Q = await read_q_v1(client)
    trident = await latest_trident_v1(client)
    rows = _latest_informative_rows_from_trident_v1(trident, q=Q)

    texts = [
        json.dumps(row, sort_keys=True, default=str).lower()
        for row in rows
    ]

    missing = [
        str(needle)
        for needle in needles
        if not any(str(needle).lower() in text for text in texts)
    ]

    if missing:
        raise AssertionError(
            "latest informative middle is missing "
            f"{missing!r}: "
            f"{json.dumps(rows, indent=2, default=str)}"
        )


def _contains_expected_structure_v1(
    actual: Any,
    expected: Any,
) -> bool:
    """Return whether ``actual`` structurally contains ``expected``.

    Mapping expectations are recursive subsets. Non-mapping values, including
    lists, are compared exactly. This keeps event assertions explicit without
    requiring tests to repeat unrelated transport/provenance fields.
    """

    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return False
        return all(
            key in actual
            and _contains_expected_structure_v1(actual[key], wanted)
            for key, wanted in expected.items()
        )

    return actual == expected


async def assert_latest_informative_events_v1(
    client,
    *expected_events: Mapping[str, Any],
) -> None:
    """Assert structural event subsets against the latest informative middle.

    Every expected mapping must be structurally satisfied by at least one
    informative event. Different expected mappings may intentionally match
    different informative events.
    """

    Q = await read_q_v1(client)
    trident = await latest_trident_v1(client)
    rows = _latest_informative_rows_from_trident_v1(trident, q=Q)

    missing: list[Mapping[str, Any]] = []

    for expected_event in expected_events:
        if not any(
            _contains_expected_structure_v1(row, expected_event)
            or (
                isinstance(row.get("payload"), Mapping)
                and _contains_expected_structure_v1(row["payload"], expected_event)
            )
            or (
                isinstance(row.get("event"), Mapping)
                and _contains_expected_structure_v1(row["event"], expected_event)
            )
            for row in rows
        ):
            missing.append(expected_event)

    if missing:
        raise AssertionError(
            "latest informative middle is missing expected structural events: "
            f"missing={json.dumps(missing, indent=2, default=str)}, "
            f"actual={json.dumps(rows, indent=2, default=str)}"
        )


async def assert_latest_informative_empty_v1(client) -> None:
    Q = await read_q_v1(client)
    trident = await latest_trident_v1(client)
    rows = _latest_informative_rows_from_trident_v1(trident, q=Q)
    if rows:
        raise AssertionError(
            "expected exact-empty informative middle, got "
            f"{json.dumps(rows, indent=2, default=str)}"
        )


def deep_get_v1(value: Any, dotted: str) -> Any:
    current = value
    for part in str(dotted).split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise KeyError(f"missing path {dotted!r} at component {part!r}")
        current = current[part]
    return current


async def assert_u_paths_v1(client, expected: Mapping[str, Any]) -> None:
    U = await current_u_v1(client)
    if U is None:
        raise AssertionError("current U is null")
    for path, wanted in expected.items():
        actual = deep_get_v1(U, str(path))
        if actual != wanted:
            raise AssertionError(
                f"U path {path!r} mismatch: "
                f"expected={wanted!r}, actual={actual!r}"
            )


async def set_micro_v1(
    client,
    datum_id: str,
    micro_name: str,
    value: Any,
) -> None:
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


async def _set_signal_v1(client, signal: Mapping[str, Any]) -> None:
    await client.page.locator("[data-sufficience-signal-include]").check()
    await client.page.locator("[data-sufficience-signal-datum]").fill(
        str(signal.get("datum_id") or "")
    )
    await client.page.locator("[data-sufficience-signal-kind]").fill(
        str(signal.get("kind") or "")
    )
    await client.page.locator("[data-sufficience-signal-info]").fill(
        json.dumps(signal.get("info") or {}, separators=(",", ":"))
    )


async def _arm_local_receipt_watch_v1(client) -> int:
    """Return a browser-local revision for the rendered local receipt.

    The observer lives entirely in the page. It lets a subsequent action prove
    that an uncorrelated local validation/error receipt was produced *after*
    that action was armed instead of accidentally accepting a stale receipt
    left rendered by an earlier action.

    If the receipt itself carries the new request id, request-id correlation is
    stronger and is preferred by ``wait_outcome_v1``.
    """

    value = await client.page.evaluate(
        f"""() => {{
          const root = document.querySelector(
            '[data-thinkument-config-id]'
          );
          if (!root) {{
            throw new Error('Thinkument root not found');
          }}

          const key = {json.dumps(_LOCAL_RECEIPT_WATCH)};
          let watch = globalThis[key];

          if (!watch) {{
            watch = {{
              revision: 0,
              observer: null,
            }};

            const selector = '[data-sufficience-local-receipt]';

            const elementIsLocal = (node) => {{
              if (!node || node.nodeType !== Node.ELEMENT_NODE) {{
                return false;
              }}
              return node.matches?.(selector)
                || Boolean(node.querySelector?.(selector));
            }};

            const mutationTouchesLocal = (mutation) => {{
              const targetElement = (
                mutation.target?.nodeType === Node.ELEMENT_NODE
                  ? mutation.target
                  : mutation.target?.parentElement
              );

              if (
                targetElement?.matches?.(selector)
                || targetElement?.closest?.(selector)
              ) {{
                return true;
              }}

              for (const node of mutation.addedNodes || []) {{
                if (elementIsLocal(node)) return true;
              }}

              for (const node of mutation.removedNodes || []) {{
                if (elementIsLocal(node)) return true;
              }}

              return false;
            }};

            const observer = new MutationObserver((mutations) => {{
              if (mutations.some(mutationTouchesLocal)) {{
                watch.revision += 1;
              }}
            }});

            observer.observe(root, {{
              childList: true,
              subtree: true,
              characterData: true,
            }});

            watch.observer = observer;
            globalThis[key] = watch;
          }}

          return watch.revision;
        }}"""
    )

    if type(value) is not int:
        raise AssertionError(
            f"local receipt watch revision is not an exact int: {value!r}"
        )

    return value


async def wait_outcome_v1(
    client,
    request_id: str,
    *,
    local_revision: int | None = None,
) -> Mapping[str, Any]:
    """Wait for the outcome belonging to the just-issued public action.

    Server dispatch receipts must match ``request_id``.

    Local validation/error receipts are accepted only when either:

    * the receipt itself carries the matching request id; or
    * the caller armed the local-receipt observer before clicking and the
      rendered local receipt has mutated since that revision.

    This prevents a stale local rejection from an earlier action from
    satisfying a later action's expectation.
    """

    outcome = await client.wait_js(
        f"""(args) => {{
          const read = (selector) => {{
            const node = document.querySelector(selector);
            if (!node) return null;
            try {{ return JSON.parse(node.textContent || 'null'); }}
            catch {{ return null; }}
          }};

          const result = read('[data-sufficience-dispatch-result]');
          if (
            result
            && (
              result.request_id === args.rid
              || result.requestId === args.rid
            )
          ) {{
            return {{ kind: 'dispatch', value: result }};
          }}

          const local = read('[data-sufficience-local-receipt]');
          if (!local) return false;

          const localRid = (
            local.request_id
            ?? local.requestId
            ?? local.action?.request_id
            ?? local.action?.requestId
            ?? null
          );

          const watch = globalThis[
            {json.dumps(_LOCAL_RECEIPT_WATCH)}
          ];
          const currentRevision = Number(watch?.revision ?? 0);

          const locallyCorrelated = (
            localRid !== null
              ? String(localRid) === String(args.rid)
              : (
                  Number.isInteger(args.localRevision)
                  && currentRevision > args.localRevision
                )
          );

          if (!locallyCorrelated) return false;

          if (local.kind === 'thinkument_sufficience_local_error_v1') {{
            return {{ kind: 'local_error', value: local }};
          }}

          if (
            local.kind === 'thinkument_outbound_dispatch_validation_v1'
            && local.ok === false
          ) {{
            return {{ kind: 'local_rejection', value: local }};
          }}

          return false;
        }}""",
        {
            "rid": str(request_id),
            "localRevision": local_revision,
        },
        timeout=ASSERT_TIMEOUT_MS,
    )

    if not isinstance(outcome, Mapping):
        raise AssertionError(f"unexpected sufficience outcome: {outcome!r}")

    return outcome


async def step_v1(
    client,
    *,
    fill: Mapping[str, Mapping[str, Any]] | None = None,
    signal: Mapping[str, Any] | None = None,
    funked: bool = False,
    request_prefix: str = "dom-step",
) -> Mapping[str, Any]:
    for datum_id, micros in dict(fill or {}).items():
        for micro_name, value in dict(micros).items():
            await set_micro_v1(client, str(datum_id), str(micro_name), value)

    if signal is not None:
        await _set_signal_v1(client, signal)

    request_id = f"{request_prefix}-{uuid4().hex}"
    await client.page.locator("[data-sufficience-request-id]").fill(request_id)

    funked_box = client.page.locator("[data-sufficience-funked]")
    if funked:
        await funked_box.check()
    elif await funked_box.is_checked():
        await funked_box.uncheck()

    local_revision = await _arm_local_receipt_watch_v1(client)

    await client.page.locator('[data-sufficience-action="STEP"]').click()

    return await wait_outcome_v1(
        client,
        request_id,
        local_revision=local_revision,
    )


async def exact_public_step_v1(
    client,
    *,
    user_fill: Mapping[str, Any],
    user_signal: Mapping[str, Any] | None = None,
    funked: bool = False,
    request_prefix: str = "dom-exact-step",
) -> Mapping[str, Any]:
    """Dispatch an exact *public* higher-app STEP through the diagnostic DOM.

    This still cannot forge ThinkumentJS-owned identity, role, or canonical
    cursor fields. It is useful when the role correctly cannot see structured
    controls for a datum and the desired assertion is a public guard denial.
    """

    request_id = f"{request_prefix}-{uuid4().hex}"
    details = client.page.locator("[data-sufficience-exact-action-composer]")

    if not await details.evaluate("node => Boolean(node.open)"):
        await details.locator("summary").click()

    action = {
        "action": "STEP",
        "userFill": dict(user_fill),
        "userSignal": (
            None
            if user_signal is None
            else dict(user_signal)
        ),
        "funked": bool(funked),
        "requestId": request_id,
    }

    await client.page.locator("[data-sufficience-exact-action]").fill(
        json.dumps(action, separators=(",", ":"))
    )

    local_revision = await _arm_local_receipt_watch_v1(client)

    await client.page.locator(
        "[data-sufficience-exact-action-dispatch]"
    ).click()

    return await wait_outcome_v1(
        client,
        request_id,
        local_revision=local_revision,
    )


async def simple_action_v1(
    client,
    action: str,
    *,
    request_prefix: str = "dom-action",
) -> Mapping[str, Any]:
    normalized = str(action).upper()
    if normalized not in {"UNDO", "REDO"}:
        raise ValueError("simple action must be UNDO or REDO")

    request_id = f"{request_prefix}-{uuid4().hex}"
    await client.page.locator("[data-sufficience-request-id]").fill(request_id)

    local_revision = await _arm_local_receipt_watch_v1(client)

    await client.page.locator(
        f'[data-sufficience-action="{normalized}"]'
    ).click()

    return await wait_outcome_v1(
        client,
        request_id,
        local_revision=local_revision,
    )


def dispatch_value_v1(outcome: Mapping[str, Any]) -> Mapping[str, Any]:
    if outcome.get("kind") != "dispatch":
        raise AssertionError(f"expected server dispatch receipt, got {outcome!r}")

    value = outcome.get("value")
    if not isinstance(value, Mapping):
        raise AssertionError(
            f"dispatch outcome has no mapping value: {outcome!r}"
        )

    return value


def assert_write_role_rejection_v1(outcome: Mapping[str, Any]) -> None:
    if outcome.get("kind") != "local_rejection":
        raise AssertionError(
            f"expected local role rejection, got {outcome!r}"
        )

    receipt = outcome.get("value")
    if not isinstance(receipt, Mapping):
        raise AssertionError(
            f"local rejection is not a mapping: {outcome!r}"
        )

    errors = [
        row
        for row in list(receipt.get("errors") or [])
        if isinstance(row, Mapping)
    ]

    if not any(row.get("code") == "write_role_denied" for row in errors):
        raise AssertionError(
            f"expected write_role_denied, got {receipt!r}"
        )


def after_event_seq_v1(result: Mapping[str, Any]) -> int:
    pocket = result.get("dispatch_concurrency")
    if not isinstance(pocket, Mapping):
        raise AssertionError(
            f"dispatch result lacks concurrency pocket: {result!r}"
        )

    value = pocket.get("after_event_seq")
    if type(value) is not int:
        raise AssertionError(
            f"after_event_seq is not an exact int: {value!r}"
        )

    return value


async def sync_to_v1(client, event_seq: int) -> None:
    await client.page.evaluate(
        """async (wanted) => {
          const root = document.querySelector('[data-thinkument-config-id]');
          const control = root?.thinkumentClientControl;
          if (!control || typeof control.syncTo !== 'function') {
            throw new Error(
              'Thinkument browser control syncTo is unavailable'
            );
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
          } catch {
            return false;
          }
        }""",
        int(event_seq),
        timeout=ASSERT_TIMEOUT_MS,
    )


async def sync_all_v1(
    clients: Mapping[str, Any] | Iterable[Any],
    result_or_event_seq: Mapping[str, Any] | int,
) -> int:
    high = (
        after_event_seq_v1(result_or_event_seq)
        if isinstance(result_or_event_seq, Mapping)
        else int(result_or_event_seq)
    )

    values = (
        list(clients.values())
        if isinstance(clients, Mapping)
        else list(clients)
    )

    await asyncio.gather(
        *(sync_to_v1(client, high) for client in values)
    )

    return high


async def install_packet_capture_v1(client) -> None:
    await client.page.evaluate(
        """() => {
          globalThis.__domscriptrThinkumentPackets = [];
          globalThis.__domscriptrThinkumentPacketObserver?.disconnect?.();

          const root = document.querySelector('[data-thinkument-config-id]');
          if (!root) throw new Error('Thinkument root not found');

          let previous = null;

          const capture = () => {
            const node = root.querySelector('[data-sufficience-packet]');
            if (!node) return;

            const raw = String(node.textContent || '');
            if (!raw || raw === previous) return;

            previous = raw;
            globalThis.__domscriptrThinkumentPackets.push(raw);
          };

          const observer = new MutationObserver(capture);

          observer.observe(root, {
            childList: true,
            subtree: true,
            characterData: true,
          });

          globalThis.__domscriptrThinkumentPacketObserver = observer;
          capture();
        }"""
    )


async def packet_count_v1(client) -> int:
    value = await client.page.evaluate(
        "() => globalThis.__domscriptrThinkumentPackets?.length || 0"
    )
    return int(value)


async def packets_from_v1(
    client,
    index: int,
) -> list[Mapping[str, Any]]:
    rows = await client.page.evaluate(
        """(start) => (
          globalThis.__domscriptrThinkumentPackets || []
        ).slice(start)""",
        int(index),
    )

    out: list[Mapping[str, Any]] = []

    for raw in rows:
        value = json.loads(str(raw))
        if isinstance(value, Mapping):
            out.append(value)

    return out


async def wait_packet_triggers_v1(
    client,
    *,
    start_index: int,
    required: Iterable[str] = ("epsilon", "theta"),
) -> list[Mapping[str, Any]]:
    wanted = sorted({str(value) for value in required})

    await client.wait_js(
        """(args) => {
          const rows = (
            globalThis.__domscriptrThinkumentPackets || []
          ).slice(args.start);

          const seen = new Set();

          for (const raw of rows) {
            try {
              const packet = JSON.parse(raw);
              if (packet?.trigger?.kind) {
                seen.add(packet.trigger.kind);
              }
            } catch {}
          }

          return args.wanted.every((kind) => seen.has(kind));
        }""",
        {
            "start": int(start_index),
            "wanted": wanted,
        },
        timeout=ASSERT_TIMEOUT_MS,
    )

    return await packets_from_v1(client, start_index)


def _without_event_seq_v1(
    event: Mapping[str, Any],
) -> dict[str, Any]:
    out = deepcopy(dict(event))
    out.pop("event_seq", None)
    return out


def assert_epsilon_reconciled_by_theta_v1(
    packets: Iterable[Mapping[str, Any]],
) -> None:
    epsilon: list[Mapping[str, Any]] = []
    theta: list[Mapping[str, Any]] = []

    for packet in packets:
        trigger = packet.get("trigger")
        kind = (
            trigger.get("kind")
            if isinstance(trigger, Mapping)
            else None
        )

        information = packet.get("information")
        if not isinstance(information, Mapping):
            continue

        rows = list(
            information.get("newEvents")
            or information.get("newRows")
            or []
        )

        if kind == "epsilon":
            for row in rows:
                if isinstance(row, Mapping):
                    event = row.get("payload") if "payload" in row else row.get("event")
                    if isinstance(event, Mapping):
                        epsilon.append(dict(event))
                    else:
                        epsilon.append(dict(row))

        elif kind == "theta":
            theta.extend(
                dict(row)
                for row in rows
                if isinstance(row, Mapping)
            )

    if not epsilon:
        raise AssertionError(
            "dispatch produced no captured epsilon event rows"
        )

    if not theta:
        raise AssertionError(
            "dispatch produced no captured theta event rows"
        )

    for provisional in epsilon:
        if "event_seq" in provisional:
            raise AssertionError(
                f"epsilon event illegally has event_seq: {provisional!r}"
            )


async def assert_trident_continuity_v1(client) -> None:
    Q = await read_q_v1(client)

    actions = [
        row
        for row in list(Q.get("actions") or [])
        if isinstance(row, Mapping)
    ]

    for previous, current in zip(actions, actions[1:]):
        prev_end = (
            previous.get("end", {})
            .get("payload", {})
            .get("U")
            if isinstance(previous.get("end"), Mapping)
            else None
        )

        cur_start = (
            current.get("start", {})
            .get("payload", {})
            .get("U")
            if isinstance(current.get("start"), Mapping)
            else None
        )

        if prev_end != cur_start:
            raise AssertionError(
                "projected controller boundary continuity broke: "
                f"previous_end_U={prev_end!r}, "
                f"current_start_U={cur_start!r}"
            )


__all__ = [
    "ASSERT_TIMEOUT_MS",
    "SUFFICIENCE_MODULE",
    "SUFFICIENCE_ROOT",
    "SUMMARY",
    "after_event_seq_v1",
    "assert_epsilon_reconciled_by_theta_v1",
    "assert_latest_contains_v1",
    "assert_latest_informative_empty_v1",
    "assert_latest_informative_events_v1",
    "assert_summary_v1",
    "assert_trident_continuity_v1",
    "assert_u_paths_v1",
    "assert_write_role_rejection_v1",
    "booted_v1",
    "browser_launch_options_v1",
    "current_u_v1",
    "deep_get_v1",
    "dispatch_value_v1",
    "exact_public_step_v1",
    "install_packet_capture_v1",
    "latest_trident_v1",
    "packet_count_v1",
    "packets_from_v1",
    "read_q_v1",
    "set_micro_v1",
    "simple_action_v1",
    "step_v1",
    "summary_v1",
    "sync_all_v1",
    "sync_to_v1",
    "wait_outcome_v1",
    "wait_packet_triggers_v1",
]
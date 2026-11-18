import assert from "node:assert/strict";
import test from "node:test";
import http from "node:http";
import { once } from "node:events";

import {
  createPortal,
} from "../../src/live_vial/_js/thinkumentJS/platform/__web/portal.js";
import {
  createThinkumentApp,
} from "../../src/live_vial/_js/thinkumentJS/platform/app.js";

const json = (res, status, responseBody) => {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(responseBody));
};

async function body(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString() || "{}");
}

const manualU = (value) => ({
  kind: "MANUALFILLNEEDEDSTEP",
  form_id: "form",
  current_frame_id: "frame",
  current_span: "span",
  current_span_id: "span",
  datum_widgets_on_this_span: ["note"],
  datum_states_on_this_span: [{
    datum_id: "note",
    is_pending: true,
    enabled: true,
    roles: ["maker"],
    micros: [{
      name: "text",
      type: "text",
      required: true,
    }],
    fill: value,
    has_fill: value !== null,
  }],
  datum_widget_fills: {
    note: value,
  },
  role_mismatch_modulation_info: {
    role_viewing: "maker",
    assignments: {
      note: ["maker"],
    },
    mismatch_datum_ids: [],
  },
});

const controller = (
  seq,
  phase,
  id,
  U,
  { identityId, role },
) => ({
  kind: "controller_loop_event_v1",
  event_seq: seq,
  event_id: `e${seq}`,
  dispatch_id: id,
  dispatcher_identity_id: identityId,
  dispatcher_role: role,
  phase,
  action: "STEP",
  payload: {
    U,
    outcome: "success",
    result: { last_error: null },
  },
});

async function withBackend(run) {
  const state = {
    seq: 0,
    epsSeq: 0,
    events: [],
    epsRows: [],
    value: null,
    dispatches: 0,
    receipts: new Map(),
    inFlightGate: null,
  };

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://localhost");

    if (url.pathname === "/latest") {
      return json(res, 200, { latest_event_seq: state.seq });
    }

    if (url.pathname === "/events") {
      const after = Number(url.searchParams.get("after_event_seq") || 0);
      const limit = Number(url.searchParams.get("limit") || 100);
      const events = state.events
        .filter((event) => event.event_seq > after)
        .slice(0, limit);
      const next = events.length ? events.at(-1).event_seq : state.seq;
      return json(res, 200, {
        events,
        after_event_seq: after,
        next_after_event_seq: next,
        session_latest_event_seq: state.seq,
        canonical_gap_detected: false,
      });
    }

    if (url.pathname === "/eps") {
      const after = Number(url.searchParams.get("after_seq") || 0);
      const limit = Number(url.searchParams.get("limit") || 100);
      const rows = state.epsRows
        .filter((row) => row.eps_seq > after)
        .slice(0, limit);
      if (state.inFlightGate && rows.length) {
        state.inFlightGate.resolveOpenObserved?.();
      }
      return json(res, 200, {
        kind: "thinkument_eps_page_v1",
        after_seq: after,
        next_after_seq: rows.length ? rows.at(-1).eps_seq : state.epsSeq,
        eps_head: state.epsSeq,
        rows,
      });
    }

    if (url.pathname === "/dispatch" && req.method === "POST") {
      const packet = await body(req);

      if (state.receipts.has(packet.request_id)) {
        return json(res, 200, state.receipts.get(packet.request_id));
      }

      if (packet.my_current_event_seq_number !== state.seq) {
        return json(res, 409, {
          rejected: true,
          rejection_kind: "stale_conflict",
          dispatch_outcome: "stale_rejected",
          write_committed: false,
        });
      }

      const first = state.dispatches === 0;
      const id = `d${++state.dispatches}`;
      let resolveOpenObserved;
      const openObserved = new Promise((resolve) => {
        resolveOpenObserved = resolve;
      });
      state.inFlightGate = { resolveOpenObserved };

      state.epsRows.push({
        kind: "thinkument_eps_row_v1",
        eps_seq: ++state.epsSeq,
        event_id: `eps-${state.epsSeq}`,
        channel: "datum.message",
        visibility: "all-with-modulation",
        content_hash: `hash-${state.epsSeq}`,
        theta_event_seq_at_emit: state.seq,
        emitter_origin: "widget_explosion",
        request_id: packet.request_id,
        trident_dispatch_id: id,
        obfuscated: false,
        datum_id: "note",
        frame_id: "frame",
        span_id: "span",
        form_id: "form",
        payload: { message: "dispatching" },
      });

      await openObserved;
      state.inFlightGate = null;

      const actor = {
        identityId: packet.identity_id,
        role: packet.role ?? null,
      };

      state.events.push(
        controller(
          ++state.seq,
          "start",
          id,
          first ? { kind: "ATSTART" } : manualU(state.value),
          actor,
        ),
      );

      if (packet.user_fill?.note) state.value = packet.user_fill.note;

      state.events.push(
        controller(
          ++state.seq,
          "end",
          id,
          manualU(state.value),
          actor,
        ),
      );

      const receipt = {
        rejected: false,
        dispatch_outcome: "applied",
        write_committed: Boolean(packet.user_fill?.note),
      };
      state.receipts.set(packet.request_id, receipt);
      return json(res, 200, receipt);
    }

    return json(res, 404, { error: "not found" });
  });

  server.listen(0, "127.0.0.1");
  await once(server, "listening");

  try {
    await run({
      base: `http://127.0.0.1:${server.address().port}`,
      state,
    });
  } finally {
    server.close();
    await once(server, "close");
  }
}

test("two guarded loopback dispatcher-pollers converge after stale refresh and retry", async () => withBackend(
  async ({ base, state }) => {
    const endpoints = {
      latestEventSeq: `${base}/latest`,
      events: `${base}/events`,
      dispatch: `${base}/dispatch`,
      dispatchFunked: `${base}/dispatch`,
      eps: `${base}/eps`,
    };

    const observations = [];

    const make = (identity) => createThinkumentApp({
      sessionId: "s",
      identityId: identity,
      role: "maker",
      portal: createPortal({
        endpoints,
        identityId: identity,
        epsPollPeriodMs: 0,
      }),
      initialX: { epsSeen: [] },
      informationDisseminationFn: async (packet) => {
        observations.push({
          identity,
          trigger: packet.trigger.kind,
          Q: packet.context.Q.cursor,
          epsCursor: packet.context.Q.eps_cursor,
        });

        if (packet.trigger.kind === "epsilon") {
          return {
            X: {
              epsSeen: [
                ...packet.context.X.epsSeen,
                ...packet.information.newRows.map((row) => ({
                  requestId: row.request_id,
                  epsSeq: row.eps_seq,
                })),
              ],
            },
          };
        }

        return { X: packet.context.X };
      },
    });

    const a = make("a");
    const b = make("b");

    const mountA = {
      action: "STEP",
      requestId: "a0",
    };
    assert.equal(a.loopback.validateDispatch(mountA).ok, true);
    assert.equal(
      (await a.loopback.dispatch(mountA)).dispatch_outcome,
      "applied",
    );
    assert.equal(a.loopback.readQ().cursor, 2);

    await b.sync();
    assert.equal(b.loopback.readQ().cursor, 2);
    assert.equal(b.loopback.readQ().eps_cursor, 1);

    const writeA = {
      action: "STEP",
      userFill: { note: { text: "A" } },
      requestId: "a1",
    };
    assert.equal(a.loopback.validateDispatch(writeA).ok, true);
    assert.equal(
      (await a.loopback.dispatch(writeA)).dispatch_outcome,
      "applied",
    );
    assert.equal(a.loopback.readQ().cursor, 4);

    const staleB = {
      action: "STEP",
      userFill: { note: { text: "stale" } },
      requestId: "b1",
    };
    // This is valid against b's latest local Q. Remote movement is deliberately
    // left to the backend cursor check.
    assert.equal(b.loopback.validateDispatch(staleB).ok, true);
    assert.equal(
      (await b.loopback.dispatch(staleB)).dispatch_outcome,
      "stale_rejected",
    );
    assert.equal(b.loopback.readQ().cursor, 4);

    const retryB = {
      action: "STEP",
      userFill: { note: { text: "B" } },
      requestId: "b2",
    };
    assert.equal(b.loopback.validateDispatch(retryB).ok, true);
    assert.equal(
      (await b.loopback.dispatch(retryB)).dispatch_outcome,
      "applied",
    );

    await a.sync();

    assert.equal(
      a.loopback.readQ().latest_U.datum_widget_fills.note.text,
      "B",
    );
    assert.equal(b.loopback.readQ().cursor, 6);
    assert.equal(a.loopback.readQ().eps_cursor, 3);
    assert.equal(b.loopback.readQ().eps_cursor, 3);
    assert.equal(state.events.length, 6);
    assert.deepEqual(
      state.events.map((event) => event.dispatcher_identity_id),
      ["a", "a", "a", "a", "b", "b"],
    );

    assert.ok(observations.some(
      (row) => row.identity === "a" && row.trigger === "epsilon" && row.Q === 0,
    ));
    assert.ok(observations.some(
      (row) => row.identity === "a" && row.trigger === "theta" && row.Q === 2,
    ));
  },
));

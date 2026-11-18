import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import test from "node:test";

import {
  createThinkumentApp,
} from "../../src/live_vial/_js/thinkumentJS/platform/app.js";
import {
  createPortal,
} from "../../src/live_vial/_js/thinkumentJS/platform/__web/portal.js";
import {
  createWombRuntime,
} from "../../src/live_vial/_js/thinkumentJS/womb.js";

const json = (res, status, value) => {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(value));
};

const readBody = async (req) => {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString() || "{}");
};

const manualU = (span = "span") => ({
  kind: "MANUALFILLNEEDEDSTEP",
  form_id: "form",
  app_form_id: "form",
  current_frame_id: "frame",
  current_frame_name: "Frame",
  current_span: span,
  current_span_id: span,
  datum_widgets_on_this_span: [],
  datum_states_on_this_span: [],
  session_metadata: {},
  role_mismatch_modulation_info: {
    role_viewing: "solver",
    assignments: {},
    mismatch_datum_ids: [],
  },
});

const initialQ = (sessionId) => ({
  kind: "thinkument_front_state_v1",
  session_id: sessionId,
  cursor: 0,
  eps_cursor: 0,
  eps_head: 0,
  eps_rows: [],
  latest_U: manualU("span-0"),
  open_action: null,
  actions: [],
  interruptions: [],
  orphan_ends: [],
  canonical_gap_count: 0,
  bootstrap: null,
});

const nextInfo = ({
  willContinue,
  index,
  total,
  stopReason,
  finalKind,
}) => ({
  kind: "chainreactionTM_next_U_funkability_v1",
  evaluated_from: "controller.loop.end.payload.U",
  U_kind: willContinue ? "MANUALFILLNEEDEDSTEP" : finalKind,
  span_id: willContinue
    ? `span-${index + 1}`
    : (finalKind === "MANUALFILLNEEDEDSTEP" ? "human-barrier" : null),
  will_funk_next_dispatch: willContinue,
  selected_role: willContinue ? "solver" : null,
  selected_version: willContinue ? "solver.v1" : null,
  pending_roles: willContinue
    ? ["solver"]
    : (stopReason === "next_pending_role_unchainreactioned"
      ? ["human_reviewer"]
      : []),
  reason: willContinue ? "next_dispatch_funkable" : stopReason,
  writable_pending_datum_ids: willContinue
    ? [`answer-${index + 1}`]
    : (stopReason === "next_pending_role_unchainreactioned"
      ? ["checkpoint"]
      : []),
  generated_index: index,
  generated_total: total,
});

const dispatchContext = ({ index, total, stopReason, finalKind }) => {
  const willContinue = index < total;
  return {
    kind: "chainreactionTM_generated_dispatch_context_v1",
    filler_version: "solver.v1",
    generated_dispatch_index: index,
    generated_dispatches_e2e: total,
    scheduled_role: "solver",
    filler_receipt: {
      kind: "test_solver_receipt_v1",
      generated_index: index,
      next_U_funkability: nextInfo({
        willContinue,
        index,
        total,
        stopReason,
        finalKind,
      }),
    },
  };
};

const controller = ({
  seq,
  phase,
  dispatchId,
  identityId,
  role,
  U,
  context = undefined,
}) => ({
  kind: "controller_loop_event_v1",
  event_seq: seq,
  event_id: `event-${seq}`,
  dispatch_id: dispatchId,
  dispatcher_identity_id: identityId,
  dispatcher_role: role,
  source: "page_flow_controller",
  name: phase === "start" ? "controller.loop.start" : "controller.loop.end",
  phase,
  session_id: "session",
  action: "STEP",
  payload: {
    A: { fill: {}, signal: null },
    fill: {},
    signal: null,
    U,
    outcome: "success",
    ...(phase === "end"
      ? {
        result: {
          event_kind: U.kind,
          finished: U.kind === "ATCOMPLETION",
          last_error: null,
        },
      }
      : {}),
    ...(context === undefined ? {} : { dispatch_context: context }),
  },
});

async function withFunkBackend(
  generatedCount,
  run,
  {
    stopReason = "program_complete_or_not_manual",
    finalKind = "ATCOMPLETION",
  } = {},
) {
  const state = {
    seq: 0,
    epsSeq: 0,
    events: [],
    epsRows: [],
    hits: {
      ordinary: 0,
      funked: 0,
    },
    inFlightGate: null,
  };

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://localhost");

    if (url.pathname === "/latest") {
      return json(res, 200, { latest_event_seq: state.seq });
    }

    if (url.pathname === "/events") {
      const after = Number(url.searchParams.get("after_event_seq") || 0);
      const events = state.events.filter((event) => event.event_seq > after);
      return json(res, 200, {
        kind: "live_session_events_since_v1",
        events,
        after_event_seq: after,
        next_after_event_seq: state.seq,
        session_latest_event_seq: state.seq,
        scanned_through_event_seq: state.seq,
        canonical_gap_detected: false,
        visibility_receipt: {
          kind: "live_session_event_visibility_receipt_v1",
          hidden_event_count: 0,
          reason: "none",
        },
      });
    }

    if (url.pathname === "/eps") {
      const after = Number(url.searchParams.get("after_seq") || 0);
      const rows = state.epsRows.filter((row) => row.eps_seq > after);
      if (state.inFlightGate && rows.length) {
        state.inFlightGate.markObserved?.();
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
      state.hits.ordinary += 1;
      return json(res, 500, { error: "funked request hit ordinary endpoint" });
    }

    if (url.pathname === "/dispatch-funked" && req.method === "POST") {
      state.hits.funked += 1;
      const packet = await readBody(req);

      assert.equal(packet.action, "STEP");
      assert.equal(packet.my_current_event_seq_number, state.seq);
      assert.equal(Object.hasOwn(packet, "funked"), false);

      let markObserved;
      const observed = new Promise((resolve) => {
        markObserved = resolve;
      });
      state.inFlightGate = { markObserved };

      for (let index = 1; index <= generatedCount; index += 1) {
        const willContinue = index < generatedCount;
        state.epsRows.push({
          kind: "thinkument_eps_row_v1",
          eps_seq: ++state.epsSeq,
          event_id: `eps-gen-${index}`,
          channel: "datum.message",
          visibility: "all-with-modulation",
          content_hash: `hash-${state.epsSeq}`,
          theta_event_seq_at_emit: state.seq,
          emitter_origin: "widget_explosion",
          request_id: packet.request_id,
          trident_dispatch_id: `generated-${index}`,
          obfuscated: false,
          datum_id: `answer-${index}`,
          frame_id: "frame",
          span_id: `span-${index}`,
          form_id: "form",
          payload: {
            generated_index: index,
            will_funk_next_dispatch: willContinue,
            reason: willContinue ? "next_dispatch_funkable" : stopReason,
          },
        });
      }

      await observed;
      state.inFlightGate = null;

      const initialDispatchId = `outer-${packet.request_id}`;
      state.events.push(
        controller({
          seq: ++state.seq,
          phase: "start",
          dispatchId: initialDispatchId,
          identityId: packet.identity_id,
          role: packet.role,
          U: manualU("span-0"),
        }),
        controller({
          seq: ++state.seq,
          phase: "end",
          dispatchId: initialDispatchId,
          identityId: packet.identity_id,
          role: packet.role,
          U: manualU("span-0"),
        }),
      );

      for (let index = 1; index <= generatedCount; index += 1) {
        const beforeU = manualU(`span-${index - 1}`);
        const afterU = index < generatedCount
          ? manualU(`span-${index}`)
          : (finalKind === "MANUALFILLNEEDEDSTEP"
            ? manualU("human-barrier")
            : { kind: finalKind });
        const id = `generated-${index}`;
        const identity = `funkedauto-solver-${packet.identity_id}`;

        state.events.push(
          controller({
            seq: ++state.seq,
            phase: "start",
            dispatchId: id,
            identityId: identity,
            role: "solver",
            U: beforeU,
          }),
          controller({
            seq: ++state.seq,
            phase: "end",
            dispatchId: id,
            identityId: identity,
            role: "solver",
            U: afterU,
            context: dispatchContext({
              index,
              total: generatedCount,
              stopReason,
              finalKind,
            }),
          }),
        );
      }

      return json(res, 200, {
        kind: "live_session_events_only_chain_dispatch_receipt_v1",
        request_id: packet.request_id,
        rejected: false,
        dispatch_outcome: "applied",
        chainreactionTM_receipt: {
          kind: "chainreactionTM_chain_reaction_receipt_v1",
          enabled: true,
          generated_dispatches_e2e: generatedCount,
          generated_fills_e2e: generatedCount,
          dispatch_count: generatedCount,
          roles_used: Array(generatedCount).fill("solver"),
          stopped_reason: stopReason,
        },
      });
    }

    return json(res, 404, { error: "not found" });
  });

  server.listen(0, "127.0.0.1");
  await once(server, "listening");

  try {
    const base = `http://127.0.0.1:${server.address().port}`;
    await run({
      state,
      endpoints: {
        latestEventSeq: `${base}/latest`,
        events: `${base}/events`,
        dispatch: `${base}/dispatch`,
        dispatchFunked: `${base}/dispatch-funked`,
        eps: `${base}/eps`,
      },
    });
  } finally {
    server.close();
    await once(server, "close");
  }
}

for (const generatedCount of [1, 2, 5]) {
  test(
    `funked client run exposes live eps rows and ${generatedCount} canonical generated trident(s)`,
    async () => withFunkBackend(generatedCount, async ({ state, endpoints }) => {
      const epsilon = [];
      const theta = [];

      const app = createThinkumentApp({
        sessionId: "session",
        identityId: "client",
        role: "solver",
        initialQ: initialQ("session"),
        portal: createPortal({
          endpoints,
          identityId: "client",
          epsPollPeriodMs: 0,
        }),
        informationDisseminationFn: async (packet, loopback) => {
          const W = createWombRuntime(packet, loopback);

          if (W.isEpsilon()) {
            epsilon.push({
              newRows: W.epsNewRows(),
              allRows: W.epsRows(),
            });
          } else {
            theta.push({
              cursor: W.Q().cursor,
              tridents: W.tridents(),
              funkedTridents: W.funkedTridents(),
              funkSequence: W.funkSequence(),
              epsForGenerated1: W.epsRowsForTrident("generated-1"),
            });
          }

          return { X: W.X() };
        },
      });

      const A = {
        action: "STEP",
        funked: true,
        requestId: `funk-${generatedCount}`,
      };

      const validation = app.loopback.validateDispatch(A);
      assert.equal(validation.ok, true);
      assert.equal(validation.A.funked, true);

      const receipt = await app.loopback.dispatch(A);
      assert.equal(receipt.rejected, false);
      assert.equal(receipt.dispatch_outcome, "applied");
      assert.equal(
        receipt.chainreactionTM_receipt.generated_dispatches_e2e,
        generatedCount,
      );

      assert.deepEqual(state.hits, {
        ordinary: 0,
        funked: 1,
      });

      assert.ok(epsilon.length >= 1);
      const live = epsilon.find(
        (row) => row.allRows.length === generatedCount,
      );
      assert.ok(live, "epsilon should expose every live generated eps row");
      assert.deepEqual(
        live.allRows.map((row) => row.trident_dispatch_id),
        Array.from({ length: generatedCount }, (_, idx) => `generated-${idx + 1}`),
      );

      const finalTheta = theta.at(-1);
      assert.ok(finalTheta);
      assert.equal(finalTheta.tridents.length, generatedCount + 1);
      assert.equal(finalTheta.funkedTridents.length, generatedCount);
      assert.equal(finalTheta.epsForGenerated1.length, 1);
      assert.equal(
        finalTheta.tridents[0].end.payload.dispatch_context,
        undefined,
      );

      assert.deepEqual(
        finalTheta.funkSequence.map(
          (row) => row.will_funk_next_dispatch,
        ),
        [
          ...Array(Math.max(0, generatedCount - 1)).fill(true),
          false,
        ],
      );
      assert.deepEqual(
        finalTheta.funkSequence.map((row) => row.reason),
        [
          ...Array(Math.max(0, generatedCount - 1)).fill(
            "next_dispatch_funkable",
          ),
          "program_complete_or_not_manual",
        ],
      );
      assert.equal(app.loopback.readQ().latest_U.kind, "ATCOMPLETION");
    }),
  );
}


test(
  "funked client sees a generated sequence stop cleanly at a human barrier",
  async () => withFunkBackend(
    2,
    async ({ endpoints }) => {
      const thetaSequences = [];
      const epsilonRows = [];

      const app = createThinkumentApp({
        sessionId: "session",
        identityId: "client",
        role: "solver",
        initialQ: initialQ("session"),
        portal: createPortal({
          endpoints,
          identityId: "client",
          epsPollPeriodMs: 0,
        }),
        informationDisseminationFn: async (packet, loopback) => {
          const W = createWombRuntime(packet, loopback);
          if (W.isTheta()) thetaSequences.push(W.funkSequence());
          if (W.isEpsilon()) epsilonRows.push(W.epsRows());
          return { X: W.X() };
        },
      });

      const result = await app.loopback.dispatch({
        action: "STEP",
        funked: true,
        requestId: "funk-human-barrier",
      });

      assert.equal(
        result.chainreactionTM_receipt.stopped_reason,
        "next_pending_role_unchainreactioned",
      );
      assert.equal(app.loopback.readQ().latest_U.kind, "MANUALFILLNEEDEDSTEP");

      const canonical = thetaSequences.at(-1);
      assert.deepEqual(
        canonical.map((row) => row.will_funk_next_dispatch),
        [true, false],
      );
      assert.equal(
        canonical.at(-1).reason,
        "next_pending_role_unchainreactioned",
      );
      assert.ok(epsilonRows.some((rows) => (
        rows.length === 2
        && rows.at(-1).payload.reason === "next_pending_role_unchainreactioned"
      )));
    },
    {
      stopReason: "next_pending_role_unchainreactioned",
      finalKind: "MANUALFILLNEEDEDSTEP",
    },
  ),
);

test("projected clients do not infer redacted funk metadata", () => {
  const projectedTrident = {
    local_id: "projected:1",
    projected: true,
    dispatch_id: null,
    dispatcher_identity_id: null,
    dispatcher_role: null,
    action: "STEP",
    status: "success",
    start: {
      kind: "controller_loop_event_v1",
      event_seq: 1,
      dispatch_id: null,
      dispatcher_identity_id: null,
      dispatcher_role: null,
      phase: "start",
      action: "STEP",
      payload: { U: manualU("hidden") },
    },
    end: {
      kind: "controller_loop_event_v1",
      event_seq: 2,
      dispatch_id: null,
      dispatcher_identity_id: null,
      dispatcher_role: null,
      phase: "end",
      action: "STEP",
      payload: {
        U: manualU("hidden"),
        dispatch_context: null,
        outcome: "success",
        result: { last_error: null },
      },
    },
  };

  const Q = {
    ...initialQ("session"),
    cursor: 2,
    latest_U: manualU("hidden"),
    actions: [projectedTrident],
  };
  const packet = {
    kind: "thinkument_information_inbound_v1",
    trigger: {
      kind: "theta",
      canonical: true,
      provisional: false,
      reason: "backend_events",
    },
    context: {
      session_id: "session",
      identity_id: "viewer",
      role: "viewer",
      Q,
      X: {},
    },
    information: {
      kind: "thinkument_theta_information_v1",
      oldQ: initialQ("session"),
      newQ: Q,
      newEvents: [],
      pollPage: null,
      reason: "backend_events",
    },
  };

  const W = createWombRuntime(packet);
  assert.equal(W.isFunkedTrident(projectedTrident), false);
  assert.deepEqual(W.funkedTridents(), []);
  assert.equal(W.funkStatus(projectedTrident).observable_funked, false);
});

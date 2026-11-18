import assert from "node:assert/strict";
import test from "node:test";

import {
  createThinkumentApp,
  REQUEST_ID_FIELD,
} from "../../src/live_vial/_js/thinkumentJS/platform/app.js";
import {
  end,
  page,
  start,
} from "./helpers/events.js";

const idlePortal = () => ({
  identityId: "i",
  async enquire() {
    return { latest_event_seq: 0 };
  },
  async pull() {
    throw new Error("unused");
  },
  async pullEps({ afterSeq = 0 } = {}) {
    return {
      kind: "thinkument_eps_page_v1",
      after_seq: afterSeq,
      next_after_seq: afterSeq,
      eps_head: afterSeq,
      rows: [],
    };
  },
  async dispatch(packet) {
    return {
      request_id: packet.request_id,
      rejected: false,
      dispatch_outcome: "applied",
    };
  },
});

test("publishes exact request correlation field", () => {
  assert.equal(REQUEST_ID_FIELD, "request_id");
});

test("theta commits Q, X, one receipt, and omega dump", async () => {
  const portal = idlePortal();
  portal.enquire = async () => ({ latest_event_seq: 2 });
  portal.pull = async () => page(
    [start(1, "d"), end(2, "d")],
    0,
    2,
  );

  const dumps = [];
  const seen = [];
  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "i",
    portal,
    initialX: { theta: 0 },
    stateDumper: async (dump) => dumps.push(dump),
    informationDisseminationFn: async (packet) => {
      seen.push(packet);
      return {
        X: {
          theta: packet.context.X.theta + 1,
        },
        receipt: { source: packet.trigger.kind },
      };
    },
  });

  await app.sync();

  assert.equal(seen.length, 1);
  assert.equal(seen[0].trigger.kind, "theta");
  assert.equal(app.readQ().cursor, 2);
  assert.deepEqual(app.readX(), { theta: 1 });
  assert.equal(
    app.readInformationDisseminationReceipts()[0].trigger,
    "theta",
  );
  assert.equal(dumps.at(-1).kind, "thinkument_front_dump_v2");
  assert.equal(dumps.at(-1).Q.cursor, 2);
  assert.deepEqual(dumps.at(-1).X, { theta: 1 });
});

test("failed theta leaves Q retryable and commits no receipt", async () => {
  const portal = idlePortal();
  portal.enquire = async () => ({ latest_event_seq: 2 });
  portal.pull = async () => page(
    [start(1, "d"), end(2, "d")],
    0,
    2,
  );

  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "i",
    portal,
    informationDisseminationFn: async () => {
      throw new Error("render failed");
    },
  });

  await assert.rejects(() => app.sync(), /render failed/);
  assert.equal(app.readQ().cursor, 0);
  assert.deepEqual(app.readInformationDisseminationReceipts(), []);
});

test("theta fires when canonical cursor advances through a fully hidden page", async () => {
  const portal = idlePortal();
  portal.enquire = async () => ({ latest_event_seq: 2 });
  portal.pull = async () => page([], 0, 2, 2);

  const packets = [];
  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "i",
    portal,
    initialX: { thetaCount: 0 },
    informationDisseminationFn: async (packet) => {
      packets.push(packet);
      return {
        X: {
          thetaCount: packet.context.X.thetaCount + 1,
        },
      };
    },
  });

  await app.sync();

  assert.equal(packets.length, 1);
  assert.equal(packets[0].trigger.kind, "theta");
  assert.deepEqual(packets[0].information.newEvents, []);
  assert.equal(packets[0].information.oldQ.cursor, 0);
  assert.equal(packets[0].information.newQ.cursor, 2);
  assert.equal(app.readQ().cursor, 2);
  assert.deepEqual(app.readX(), { thetaCount: 1 });
});

test("epsilon updates X and Q.eps_cursor without advancing theta Q.cursor", async () => {
  const portal = idlePortal();
  portal.dispatch = async (packet, { onEpsPage }) => {
    await onEpsPage({
      kind: "thinkument_eps_page_v1",
      after_seq: 0,
      next_after_seq: 1,
      eps_head: 1,
      rows: [{
        kind: "thinkument_eps_row_v1",
        eps_seq: 1,
        event_id: "ev-1",
        channel: "datum.message",
        request_id: packet.request_id,
        payload: { message: "working" },
      }],
    });
    return {
      request_id: packet.request_id,
      rejected: false,
      dispatch_outcome: "applied",
    };
  };

  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "i",
    portal,
    initialX: { progress: [] },
    informationDisseminationFn: async (packet) => {
      assert.equal(packet.trigger.kind, "epsilon");
      return {
        X: {
          progress: [
            ...packet.context.X.progress,
            packet.information.newRows[0].payload.message,
          ],
        },
      };
    },
  });

  await app.dispatch({ action: "STEP", requestId: "r1" });

  assert.equal(app.readQ().cursor, 0);
  assert.equal(app.readQ().eps_cursor, 1);
  assert.deepEqual(app.readX(), { progress: ["working"] });
  assert.equal(
    app.readInformationDisseminationReceipts()[0].trigger,
    "epsilon",
  );
});

test("dispatches serialize and use Q cursor at execution time", async () => {
  let latest = 0;
  const events = [];
  const order = [];

  const portal = {
    identityId: "i",
    async enquire() {
      return { latest_event_seq: latest };
    },
    async pull({ afterEventSeq }) {
      return {
        events: events.filter((event) => event.event_seq > afterEventSeq),
        after_event_seq: afterEventSeq,
        next_after_event_seq: latest,
        session_latest_event_seq: latest,
      };
    },
    async pullEps({ afterSeq = 0 } = {}) {
      return {
        kind: "thinkument_eps_page_v1",
        after_seq: afterSeq,
        next_after_seq: afterSeq,
        eps_head: afterSeq,
        rows: [],
      };
    },
    async dispatch(packet) {
      order.push([
        packet.request_id,
        packet.my_current_event_seq_number,
        packet.identity_id,
      ]);
      events.push(
        start(++latest, packet.request_id),
        end(++latest, packet.request_id),
      );
      return {
        request_id: packet.request_id,
        rejected: false,
        dispatch_outcome: "applied",
      };
    },
  };

  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "sealed",
    portal,
  });

  await Promise.all([
    app.dispatch({ action: "STEP", requestId: "a" }),
    app.dispatch({ action: "STEP", requestId: "b" }),
  ]);

  assert.deepEqual(order, [
    ["a", 0, "sealed"],
    ["b", 2, "sealed"],
  ]);
  assert.equal(app.readQ().cursor, 4);
});

test("loopback writeX is serialized, persisted, and detached", async () => {
  const dumps = [];
  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "i",
    portal: idlePortal(),
    initialX: { workspace: { selected: "old" } },
    stateDumper: async (dump) => dumps.push(dump),
  });

  const first = app.loopback.readX();
  first.workspace.selected = "mutated-outside";
  assert.equal(app.loopback.readX().workspace.selected, "old");

  await app.loopback.writeX((X) => ({
    ...X,
    workspace: {
      ...X.workspace,
      selected: "new",
    },
  }));

  assert.equal(app.readX().workspace.selected, "new");
  assert.equal(dumps.at(-1).X.workspace.selected, "new");
  assert.equal(app.loopback.readQ().cursor, 0);
});

test("in-flight epsilon hands authority to theta catch-up after dispatch completes", async () => {
  let latest = 0;
  let epsHead = 0;
  const events = [];
  const epsRows = [];
  let releaseDispatch;
  const dispatchGate = new Promise((resolve) => {
    releaseDispatch = resolve;
  });
  let epsProcessed;
  const processed = new Promise((resolve) => {
    epsProcessed = resolve;
  });

  const portal = {
    identityId: "i",

    async enquire() {
      return { latest_event_seq: latest };
    },

    async pull({ afterEventSeq }) {
      return {
        events: events.filter(
          (event) => event.event_seq > afterEventSeq,
        ),
        after_event_seq: afterEventSeq,
        next_after_event_seq: latest,
        session_latest_event_seq: latest,
      };
    },

    async pullEps({ afterSeq = 0 } = {}) {
      const rows = epsRows.filter((row) => row.eps_seq > afterSeq);
      return {
        kind: "thinkument_eps_page_v1",
        after_seq: afterSeq,
        next_after_seq: epsHead,
        eps_head: epsHead,
        rows,
      };
    },

    async dispatch(packet, { onEpsPage }) {
      events.push(
        start(++latest, packet.request_id),
        end(++latest, packet.request_id),
      );
      const row = {
        kind: "thinkument_eps_row_v1",
        eps_seq: ++epsHead,
        event_id: "ev-1",
        channel: "datum.message",
        request_id: packet.request_id,
        payload: { message: "in-flight" },
      };
      epsRows.push(row);

      await onEpsPage({
        kind: "thinkument_eps_page_v1",
        after_seq: 0,
        next_after_seq: epsHead,
        eps_head: epsHead,
        rows: [row],
      });

      epsProcessed();

      await dispatchGate;

      return {
        request_id: packet.request_id,
        rejected: false,
        dispatch_outcome: "applied",
      };
    },
  };

  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "i",
    portal,
  });

  const pending = app.dispatch({
    action: "STEP",
    requestId: "r1",
  });

  await processed;

  // In-flight epsilon advances Q.eps_cursor, but never advances canonical theta Q.cursor.
  assert.equal(app.readQ().cursor, 0);
  assert.equal(app.readQ().eps_cursor, 1);

  releaseDispatch();
  await pending;

  // Once dispatch completes, theta catches up through the canonical pull path and owns Q.cursor.
  assert.equal(app.readQ().cursor, 2);
});

test("failed dispatch still catches up eps before theta catch-up", async () => {
  const order = [];
  const portal = {
    identityId: "i",
    async enquire() {
      order.push("theta_enquire");
      return { latest_event_seq: 0 };
    },
    async pull() {
      throw new Error("unused");
    },
    async pullEps({ afterSeq = 0 } = {}) {
      order.push("eps_pull");
      return {
        kind: "thinkument_eps_page_v1",
        after_seq: afterSeq,
        next_after_seq: 1,
        eps_head: 1,
        rows: [{
          kind: "thinkument_eps_row_v1",
          eps_seq: 1,
          event_id: "ev-err",
          channel: "datum.message",
          payload: { message: "emitted before boom" },
        }],
      };
    },
    async dispatch() {
      order.push("dispatch_throw");
      throw new Error("boom");
    },
  };

  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "i",
    portal,
  });

  await assert.rejects(
    () => app.dispatch({ action: "STEP", requestId: "r-fail" }),
    /boom/,
  );

  assert.deepEqual(order, ["dispatch_throw", "eps_pull", "theta_enquire"]);
  assert.equal(app.readQ().eps_cursor, 1);
});

test("malformed or cross-session omega data fails closed", async () => {
  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "i",
    portal: idlePortal(),
    initialX: { clean: true },
    stateLoader: async () => ({
      kind: "thinkument_front_dump_v2",
      session_id: "other",
      Q: { bad: true },
      X: { contaminated: true },
      informationDisseminationReceipts: [{ bad: true }],
    }),
  });

  await app.start();
  try {
    assert.equal(app.readQ().cursor, 0);
    assert.deepEqual(app.readX(), { clean: true });
    assert.deepEqual(app.readInformationDisseminationReceipts(), []);
  } finally {
    app.stop();
  }
});

test("writeX updater is synchronous so it cannot hold the X lane across async work", async () => {
  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "i",
    portal: idlePortal(),
    initialX: { n: 0 },
  });

  await assert.rejects(
    () => app.writeX(async (X) => ({ ...X, n: 1 })),
    /writeX updater must be synchronous/,
  );
  assert.deepEqual(app.readX(), { n: 0 });
});

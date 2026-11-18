import assert from "node:assert/strict";
import test from "node:test";

import {
  createThinkumentApp,
} from "../../src/live_vial/_js/thinkumentJS/platform/app.js";
import {
  emptyFrontState,
} from "../../src/live_vial/_js/thinkumentJS/platform/_backend_events/digest.js";
import {
  end,
  page,
  start,
} from "./helpers/events.js";

const exactKeys = (value, keys) => assert.deepEqual(
  Object.keys(value).sort(),
  [...keys].sort(),
);

test("the opinionation blanket is one packet family over theta and epsilon", async () => {
  let latest = 0;
  const events = [];
  const packets = [];

  const portal = {
    identityId: "identity",
    async enquire() {
      return { latest_event_seq: latest };
    },
    async pull({ afterEventSeq }) {
      return page(
        events.filter((event) => event.event_seq > afterEventSeq),
        afterEventSeq,
        latest,
        latest,
      );
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
    async dispatch(packet, { onEpsPage }) {
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
          payload: { text: "working" },
        }],
      });

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
    sessionId: "session",
    identityId: "identity",
    role: "writer",
    portal,
    initialX: {
      seen: [],
    },
    informationDisseminationFn: async (packet) => {
      exactKeys(packet, [
        "kind",
        "trigger",
        "context",
        "information",
      ]);
      exactKeys(packet.context, [
        "session_id",
        "identity_id",
        "role",
        "Q",
        "X",
      ]);
      packets.push(packet);

      return {
        X: {
          seen: [
            ...packet.context.X.seen,
            packet.trigger.kind,
          ],
        },
        receipt: {
          trigger: packet.trigger.kind,
        },
      };
    },
  });

  await app.dispatch({
    action: "STEP",
    requestId: "r1",
  });

  assert.deepEqual(
    packets.map((packet) => packet.trigger.kind),
    ["epsilon", "theta"],
  );
  assert.deepEqual(app.readX(), { seen: ["epsilon", "theta"] });
  assert.equal(app.readQ().cursor, 2);
  assert.equal(app.readQ().eps_cursor, 1);

  const epsilon = packets[0];
  assert.equal(epsilon.trigger.canonical, false);
  assert.equal(epsilon.context.Q.cursor, 0);
  assert.equal(epsilon.context.Q.eps_cursor, 1);
  assert.equal(
    Object.hasOwn(
      epsilon.information.newRows[0],
      "event_seq",
    ),
    false,
  );

  const theta = packets[1];
  assert.equal(theta.trigger.canonical, true);
  assert.equal(theta.context.Q.cursor, 2);
  assert.equal(theta.information.newEvents[0].event_seq, 1);
});

test("omega is Q + X + unified receipts and reloads exactly", async () => {
  const dumps = [];
  const Q = emptyFrontState("session");

  const app = createThinkumentApp({
    sessionId: "session",
    identityId: "identity",
    portal: {
      identityId: "identity",
      async enquire() { return { latest_event_seq: 0 }; },
      async pull() { throw new Error("unused"); },
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
    },
    initialQ: Q,
    initialX: { selected: null },
    stateDumper: async (dump) => dumps.push(dump),
  });

  await app.writeX({ selected: "a" });
  const dump = app.readDump();

  exactKeys(dump, [
    "kind",
    "session_id",
    "Q",
    "X",
    "informationDisseminationReceipts",
  ]);
  assert.equal(dump.kind, "thinkument_front_dump_v2");
  assert.deepEqual(dump.X, { selected: "a" });

  const reloaded = createThinkumentApp({
    sessionId: "session",
    identityId: "identity",
    portal: {
      identityId: "identity",
      async enquire() { return { latest_event_seq: 0 }; },
      async pull() { throw new Error("unused"); },
      async pullEps({ afterSeq = 0 } = {}) {
        return {
          kind: "thinkument_eps_page_v1",
          after_seq: afterSeq,
          next_after_seq: afterSeq,
          eps_head: afterSeq,
          rows: [],
        };
      },
      async dispatch() { throw new Error("unused"); },
    },
    stateLoader: async () => dump,
  });

  await reloaded.start();
  try {
    assert.deepEqual(reloaded.readDump(), dump);
  } finally {
    reloaded.stop();
  }

  assert.ok(dumps.length >= 1);
});

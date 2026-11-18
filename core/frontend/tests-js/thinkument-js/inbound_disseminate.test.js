import assert from "node:assert/strict";
import test from "node:test";

import {
  disseminateInformation,
  INFORMATION_TRIGGER_EPSILON,
  INFORMATION_TRIGGER_THETA,
} from "../../src/live_vial/_js/thinkumentJS/inbound.js";
import {
  emptyFrontState,
} from "../../src/live_vial/_js/thinkumentJS/platform/_backend_events/digest.js";

const clientContext = {
  session_id: "s",
  identity_id: "i",
  role: "writer",
};

test("theta and epsilon normalize to one exact outer socket", async () => {
  const oldQ = emptyFrontState("s");
  const newQ = { ...oldQ, cursor: 2 };
  const seen = [];

  const drink = async (packet) => {
    seen.push(packet);
    assert.deepEqual(
      Object.keys(packet).sort(),
      ["context", "information", "kind", "trigger"].sort(),
    );
    assert.equal(packet.kind, "thinkument_information_inbound_v1");
    assert.equal(packet.context.session_id, "s");
    assert.equal(packet.context.identity_id, "i");
    return {
      X: {
        ...packet.context.X,
        [packet.trigger.kind]: true,
      },
      receipt: { handled: packet.trigger.kind },
    };
  };

  const theta = await disseminateInformation({
    drink,
    trigger: INFORMATION_TRIGGER_THETA,
    clientContext,
    Q: newQ,
    oldX: {},
    theta: {
      oldQ,
      newQ,
      newEvents: [{ event_seq: 1 }, { event_seq: 2 }],
      reason: "backend_events",
    },
  });

  assert.equal(seen[0].trigger.kind, "theta");
  assert.equal(seen[0].trigger.canonical, true);
  assert.equal(seen[0].information.kind, "thinkument_theta_information_v1");
  assert.equal(seen[0].information.newQ.cursor, 2);
  assert.deepEqual(theta.X, { theta: true });
  assert.equal(theta.disseminationReceipt.cursor, 2);

  const epsRow = {
    kind: "thinkument_eps_row_v1",
    eps_seq: 1,
    event_id: "ev-1",
    channel: "datum.message",
    request_id: "r1",
    trident_dispatch_id: "d1",
    payload: { text: "working" },
  };
  const epsNewQ = {
    ...newQ,
    eps_cursor: 1,
    eps_head: 1,
    eps_rows: [epsRow],
  };

  const epsilon = await disseminateInformation({
    drink,
    trigger: INFORMATION_TRIGGER_EPSILON,
    clientContext,
    Q: epsNewQ,
    oldX: theta.X,
    epsilon: {
      oldQ: newQ,
      newQ: epsNewQ,
      newRows: [epsRow],
      page: {
        kind: "thinkument_eps_page_v1",
        after_seq: 0,
        next_after_seq: 1,
        eps_head: 1,
        rows: [epsRow],
      },
    },
  });

  assert.equal(seen[1].trigger.kind, "epsilon");
  assert.equal(seen[1].trigger.canonical, false);
  assert.equal(seen[1].information.kind, "thinkument_epsilon_information_v1");
  assert.equal(seen[1].information.newQ.eps_cursor, 1);
  assert.equal(seen[1].information.newRows[0].request_id, "r1");
  assert.equal(
    Object.hasOwn(seen[1].information.newRows[0], "event_seq"),
    false,
  );
  assert.deepEqual(epsilon.X, { theta: true, epsilon: true });
  assert.equal(epsilon.disseminationReceipt.eps_cursor, 1);
});

test("packets are detached and drinker outputs are dead JSON", async () => {
  const Q = emptyFrontState("s");
  const oldX = { stable: { n: 1 } };
  const events = [{ event_seq: 1, payload: { n: 1 } }];

  const out = await disseminateInformation({
    trigger: INFORMATION_TRIGGER_THETA,
    clientContext,
    Q: { ...Q, cursor: 1 },
    oldX,
    theta: {
      oldQ: Q,
      newQ: { ...Q, cursor: 1 },
      newEvents: events,
      reason: "backend_events",
    },
    drink: async (packet) => {
      packet.information.newEvents[0].payload.n = 9;
      packet.context.X.stable.n = 9;
      return { X: { done: true } };
    },
  });

  assert.equal(events[0].payload.n, 1);
  assert.equal(oldX.stable.n, 1);
  assert.deepEqual(out.X, { done: true });

  await assert.rejects(
    () => disseminateInformation({
      trigger: INFORMATION_TRIGGER_THETA,
      clientContext,
      Q,
      oldX: {},
      theta: {
        oldQ: Q,
        newQ: Q,
        newEvents: [],
        reason: "backend_events",
      },
      drink: async () => ({ X: new Map() }),
    }),
    /plain object/,
  );
});

test("missing or null drinker preserves X", async () => {
  const Q = emptyFrontState("s");
  const oldX = { preserved: true };

  for (const drink of [null, async () => null]) {
    const out = await disseminateInformation({
      drink,
      trigger: INFORMATION_TRIGGER_THETA,
      clientContext,
      Q,
      oldX,
      theta: {
        oldQ: Q,
        newQ: Q,
        newEvents: [],
        reason: "backend_events",
      },
    });
    assert.deepEqual(out.X, oldX);
  }
});

test("epsilon pages with hidden/owner-only tail advance eps_cursor and reach the drinker", async () => {
  const Q0 = emptyFrontState("s");
  const Q1 = { ...Q0, eps_cursor: 3, eps_head: 3 };
  const seen = [];

  const out = await disseminateInformation({
    trigger: INFORMATION_TRIGGER_EPSILON,
    clientContext,
    Q: Q1,
    oldX: { count: 0 },
    epsilon: {
      oldQ: Q0,
      newQ: Q1,
      newRows: [],
      page: {
        kind: "thinkument_eps_page_v1",
        after_seq: 0,
        next_after_seq: 3,
        eps_head: 3,
        rows: [],
      },
    },
    drink: async (packet) => {
      seen.push(packet.information.pollPage.next_after_seq);
      assert.deepEqual(packet.information.newRows, []);
      return {
        X: {
          count: packet.context.X.count + 1,
        },
      };
    },
  });

  assert.equal(out.X.count, 1);
  assert.equal(out.disseminationReceipt.eps_cursor, 3);
  assert.deepEqual(seen, [3]);
});

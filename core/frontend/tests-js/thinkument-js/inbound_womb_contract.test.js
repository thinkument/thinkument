import assert from "node:assert/strict";
import test from "node:test";

import {
  disseminateInformation,
  INFORMATION_TRIGGER_THETA,
} from "../../src/live_vial/_js/thinkumentJS/inbound.js";

test("theta preserves full poll page and passes loopback as second womb arg", async () => {
  const Q0 = {
    kind: "thinkument_front_state_v1",
    session_id: "s",
    cursor: 0,
    eps_cursor: 0,
    eps_head: 0,
    eps_rows: [],
    latest_U: null,
    open_action: null,
    actions: [],
    interruptions: [],
    orphan_ends: [],
    canonical_gap_count: 0,
    bootstrap: null,
  };
  const Q1 = { ...Q0, cursor: 2 };
  const loopback = Object.freeze({ kind: "thinkument_outbound_v1" });

  const out = await disseminateInformation({
    trigger: INFORMATION_TRIGGER_THETA,
    clientContext: {
      session_id: "s",
      identity_id: "i",
      role: "maker",
    },
    Q: Q1,
    oldX: { n: 0 },
    loopback,
    theta: {
      oldQ: Q0,
      newQ: Q1,
      newEvents: [],
      reason: "backend_events",
      page: {
        kind: "live_session_events_since_v1",
        events: [],
        after_event_seq: 0,
        next_after_event_seq: 2,
        session_latest_event_seq: 2,
        scanned_through_event_seq: 2,
        canonical_gap_detected: false,
        visibility_receipt: {
          hidden_event_count: 2,
        },
      },
    },
    drink: async (packet, receivedLoopback) => {
      assert.equal(receivedLoopback, loopback);
      assert.equal(packet.context.Q.cursor, 2);
      assert.equal(packet.information.newEvents.length, 0);
      assert.equal(
        packet.information.pollPage.visibility_receipt.hidden_event_count,
        2,
      );
      return {
        X: { n: packet.context.X.n + 1 },
      };
    },
  });

  assert.deepEqual(out.X, { n: 1 });
  assert.equal(out.disseminationReceipt.cursor, 2);
});

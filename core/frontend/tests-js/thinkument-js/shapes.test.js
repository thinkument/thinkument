import assert from "node:assert/strict";
import test from "node:test";
import {
  makeDispatch,
  normalizeEnquiryResult,
  normalizeEpsPage,
  normalizePullResult,
} from "../../src/live_vial/_js/thinkumentJS/platform/__web/shapes.js";

test("dispatch is exact, cloned, and dead JSON", () => {
  const fill = { d: { x: 1 } };
  const packet = makeDispatch({ action: "step", userFill: fill, identityId: "i", requestId: "r", cursor: 7 });
  fill.d.x = 2;
  assert.equal(packet.action, "STEP");
  assert.deepEqual(packet.user_fill, { d: { x: 1 } });
  assert.throws(() => makeDispatch({ action: "STEP", userFill: { d: undefined }, identityId: "i", requestId: "r", cursor: 1 }), TypeError);
  assert.throws(() => makeDispatch({ action: "STEP", identityId: "i", requestId: "r", cursor: "1" }), TypeError);
});

test("enquiry aliases, pull progress laws, and eps page normalization", () => {
  assert.equal(normalizeEnquiryResult({ event_seq: 3 }).latest_event_seq, 3);
  assert.equal(normalizeEnquiryResult({ latest_event_seq: 4 }).latest_event_seq, 4);
  assert.throws(() => normalizePullResult({ events: [], after_event_seq: 0, next_after_event_seq: 0, session_latest_event_seq: 1 }), RangeError);
  assert.throws(() => normalizePullResult({ events: [{ event_seq: 2 }, { event_seq: 1 }], after_event_seq: 0, next_after_event_seq: 2, session_latest_event_seq: 2 }), RangeError);

  const epsPage = normalizeEpsPage({
    kind: "thinkument_eps_page_v1",
    after_seq: 0,
    next_after_seq: 2,
    eps_head: 2,
    rows: [
      { eps_seq: 1, event_id: "e1", channel: "datum.message", payload: { text: "a" } },
      { eps_seq: 2, event_id: "e2", channel: "datum.message", payload: { text: "b" } },
    ],
  });
  assert.equal(epsPage.next_after_seq, 2);
  assert.equal(epsPage.eps_head, 2);
  assert.equal(epsPage.rows.length, 2);

  assert.throws(
    () => normalizeEpsPage({
      after_seq: 0,
      next_after_seq: 2,
      eps_head: 2,
      rows: [{ eps_seq: 2 }, { eps_seq: 1 }],
    }),
    RangeError,
  );
});

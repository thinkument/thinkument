import assert from "node:assert/strict";
import test from "node:test";
import {
  createEpsPollPull,
  createPollPull,
} from "../../src/live_vial/_js/thinkumentJS/platform/_backend_events/pollpull.js";

test("uses scalar enquiry then bounded pages", async () => {
  let pulls = 0;
  const seen = [];
  const portal = {
    identityId: "i",
    async enquire() { return { latest_event_seq: 3 }; },
    async pull({ afterEventSeq }) {
      pulls += 1;
      return afterEventSeq === 0
        ? { events: [{ event_seq: 1 }], after_event_seq: 0, next_after_event_seq: 1, session_latest_event_seq: 3 }
        : { events: [], after_event_seq: 1, next_after_event_seq: 3, session_latest_event_seq: 3 };
    },
  };
  const poller = createPollPull({ portal, pageSize: 1, onPage: async (page) => seen.push(page.next_after_event_seq) });
  const result = await poller.catchUp(0);
  assert.equal(result.cursor, 3);
  assert.equal(pulls, 2);
  assert.deepEqual(seen, [1, 3]);
});

test("queued catchups resolve their cursor when execution starts", async () => {
  let current = 0;
  let pulls = 0;
  const portal = {
    identityId: "i",
    async enquire() { return { latest_event_seq: 1 }; },
    async pull({ afterEventSeq }) {
      pulls += 1;
      return { events: [{ event_seq: 1 }], after_event_seq: afterEventSeq, next_after_event_seq: 1, session_latest_event_seq: 1 };
    },
  };
  const poller = createPollPull({ portal, pageSize: 1, onPage: async () => { current = 1; } });
  await Promise.all([poller.catchUp(() => current), poller.catchUp(() => current)]);
  assert.equal(pulls, 1);
});

test("synchronizing is observable", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const portal = { identityId: "i", async enquire() { await gate; return { latest_event_seq: 0 }; }, async pull() { throw new Error("unused"); } };
  const poller = createPollPull({ portal, pageSize: 1, onPage: async () => {} });
  const pending = poller.catchUp(0);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(poller.synchronizing, true);
  release();
  await pending;
  assert.equal(poller.synchronizing, false);
});

test("eps poller drains bounded pages up to eps_head and forwards cold-boot window", async () => {
  const pullCalls = [];
  const seenPages = [];
  const portal = {
    async pullEps({ afterSeq, limit, window }) {
      pullCalls.push({ afterSeq, limit, window });
      if (afterSeq === 0) {
        return {
          kind: "thinkument_eps_page_v1",
          after_seq: 0,
          next_after_seq: 2,
          eps_head: 3,
          rows: [{ eps_seq: 2, event_id: "e2", channel: "datum.message" }],
        };
      }
      return {
        kind: "thinkument_eps_page_v1",
        after_seq: 2,
        next_after_seq: 3,
        eps_head: 3,
        rows: [{ eps_seq: 3, event_id: "e3", channel: "datum.message" }],
      };
    },
  };
  let cursor = 0;
  const epsPoller = createEpsPollPull({
    portal,
    pageSize: 1,
    onPage: async (page) => {
      cursor = page.next_after_seq;
      seenPages.push(page.next_after_seq);
    },
  });
  const result = await epsPoller.catchUp(() => cursor, { window: 512 });
  assert.equal(result.cursor, 3);
  assert.deepEqual(seenPages, [2, 3]);
  assert.equal(pullCalls[0].window, 512);
  assert.equal(pullCalls[1].window, null);
});

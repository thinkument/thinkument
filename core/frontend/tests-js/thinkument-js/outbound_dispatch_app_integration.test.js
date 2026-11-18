import assert from "node:assert/strict";
import test from "node:test";

import {
  createThinkumentApp,
} from "../../src/live_vial/_js/thinkumentJS/platform/app.js";

const controller = (seq, phase, id, U) => ({
  kind: "controller_loop_event_v1",
  event_seq: seq,
  event_id: `e${seq}`,
  dispatch_id: id,
  dispatcher_identity_id: "actor",
  dispatcher_role: "maker",
  phase,
  action: "STEP",
  payload: {
    U,
    outcome: "success",
    result: { last_error: null },
  },
});

test("serialized app dispatch revalidates against execution-time Q", async () => {
  let latest = 0;
  const events = [];
  const posted = [];

  const portal = {
    identityId: "actor",
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
      posted.push(packet.request_id);
      const id = packet.request_id;
      events.push(
        controller(++latest, "start", id, { kind: "ATSTART" }),
        controller(++latest, "end", id, { kind: "ATCOMPLETION" }),
      );
      return {
        rejected: false,
        dispatch_outcome: "applied",
      };
    },
  };

  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "actor",
    role: "maker",
    portal,
  });

  const first = app.dispatch({ action: "STEP", requestId: "r1" });
  const second = app.dispatch({ action: "STEP", requestId: "r2" });

  assert.equal((await first).dispatch_outcome, "applied");
  await assert.rejects(second, /ATCOMPLETION/);
  assert.deepEqual(posted, ["r1"]);
  assert.equal(app.readQ().cursor, 2);
});

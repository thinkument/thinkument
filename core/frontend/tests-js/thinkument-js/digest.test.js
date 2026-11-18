import assert from "node:assert/strict";
import test from "node:test";

import {
  digestEpsPage,
  digestEvents,
  emptyFrontState,
  validateFrontState,
} from "../../src/live_vial/_js/thinkumentJS/platform/_backend_events/digest.js";
import {
  end,
  start,
} from "./helpers/events.js";

test(
  "modulates start and successful end without embedding eps in tridents",
  () => {
    const q = digestEvents(
      emptyFrontState("s"),
      [
        start(1, "d"),
        end(2, "d"),
      ],
    );

    assert.equal(q.cursor, 2);
    assert.equal(q.eps_cursor, 0);
    assert.deepEqual(q.eps_rows, []);
    assert.equal(
      q.actions[0].status,
      "success",
    );
    assert.equal(
      Object.hasOwn(q.actions[0], "informative_events"),
      false,
    );
  },
);

test(
  "digestEpsPage advances eps_cursor, deduplicates by eps_seq, and bounds eps_rows",
  () => {
    const q0 = emptyFrontState("s");
    const { nextState: q1, newRows: r1 } = digestEpsPage(
      q0,
      {
        kind: "thinkument_eps_page_v1",
        after_seq: 0,
        next_after_seq: 2,
        eps_head: 3,
        rows: [
          {
            kind: "thinkument_eps_row_v1",
            eps_seq: 1,
            event_id: "ev-1",
            channel: "datum.message",
            emitted_at: "2026-11-08T00:00:00Z",
            content_hash: "h1",
            visibility: "all-with-modulation",
            theta_event_seq_at_emit: 0,
            emitter_origin: "widget_explosion",
            request_id: "req-1",
            trident_dispatch_id: "d-1",
            obfuscated: false,
            datum_id: "note",
            frame_id: "frame",
            span_id: "span",
            form_id: "form",
            payload: { text: "one" },
          },
          {
            kind: "thinkument_eps_row_v1",
            eps_seq: 2,
            event_id: "ev-2",
            channel: "datum.message",
            emitted_at: "2026-11-08T00:00:01Z",
            content_hash: "h2",
            visibility: "all-with-modulation",
            theta_event_seq_at_emit: 0,
            emitter_origin: "widget_explosion",
            request_id: "req-1",
            trident_dispatch_id: "d-1",
            obfuscated: false,
            datum_id: "note",
            frame_id: "frame",
            span_id: "span",
            form_id: "form",
            payload: { text: "two" },
          },
        ],
      },
      { limits: { maxEpsRows: 2 } },
    );

    assert.equal(q1.eps_cursor, 2);
    assert.equal(r1.length, 2);
    assert.equal(q1.eps_rows.length, 2);

    const { nextState: q2 } = digestEpsPage(
      q1,
      {
        kind: "thinkument_eps_page_v1",
        after_seq: 2,
        next_after_seq: 3,
        eps_head: 3,
        rows: [
          {
            kind: "thinkument_eps_row_v1",
            eps_seq: 3,
            event_id: "ev-3",
            channel: "datum.message",
            emitted_at: "2026-11-08T00:00:02Z",
            content_hash: "h3",
            visibility: "all-with-modulation",
            theta_event_seq_at_emit: 2,
            emitter_origin: "widget_explosion",
            request_id: "req-2",
            trident_dispatch_id: "d-2",
            obfuscated: true,
            datum_id: null,
            frame_id: null,
            span_id: null,
            form_id: null,
            payload: null,
          },
        ],
      },
      { limits: { maxEpsRows: 2 } },
    );

    assert.equal(q2.eps_cursor, 3);
    assert.deepEqual(
      q2.eps_rows.map((row) => row.eps_seq),
      [2, 3],
    );
  },
);

test(
  "classifies semantic, system, interruption, orphan, and gaps",
  () => {
    const systemEnd = end(
      7,
      "z",
      {
        outcome: "system_error",
      },
    );

    const q = digestEvents(
      emptyFrontState("s"),
      [
        start(1, "a"),
        end(
          2,
          "a",
          {
            lastError: {
              d: "bad",
            },
          },
        ),
        start(3, "b"),
        start(4, "c"),
        end(5, "missing"),
        start(6, "z"),
        systemEnd,
      ],
      8,
      {
        canonicalGapDetected: true,
      },
    );

    assert.deepEqual(
      q.actions.map((x) => x.status),
      [
        "semantic_rejected",
        "interrupted",
        "interrupted",
        "system_error",
      ],
    );
    assert.equal(
      q.orphan_ends.length,
      1,
    );
    assert.equal(q.cursor, 8);
    assert.equal(
      q.canonical_gap_count,
      1,
    );
  },
);

test(
  "front state is session scoped and histories can be bounded",
  () => {
    assert.throws(
      () => validateFrontState(
        emptyFrontState("a"),
        {
          sessionId: "b",
        },
      ),
      RangeError,
    );

    const q = digestEvents(
      emptyFrontState("s"),
      [
        start(1, "a"),
        end(2, "a"),
        start(3, "b"),
        end(4, "b"),
      ],
      4,
      {
        limits: {
          maxActionEnvelopes: 1,
        },
      },
    );

    assert.equal(
      q.actions.length,
      1,
    );
    assert.equal(
      q.actions[0].dispatch_id,
      "b",
    );
  },
);

test(
  "controller event without dispatcher identity fails closed",
  () => {
    const event = start(1, "d");
    delete event.dispatcher_identity_id;

    assert.throws(
      () => digestEvents(
        emptyFrontState("s"),
        [event],
      ),
      /dispatcher_identity_id must be a non-empty/,
    );
  },
);

test(
  "fully hidden projected controller boundaries form one local trident",
  () => {
    const projectedStart = start(1, "hidden");
    projectedStart.dispatch_id = null;
    projectedStart.dispatcher_identity_id = null;
    projectedStart.dispatcher_role = null;
    projectedStart.payload.A = null;

    const projectedEnd = end(2, "hidden");
    projectedEnd.dispatch_id = null;
    projectedEnd.dispatcher_identity_id = null;
    projectedEnd.dispatcher_role = null;
    projectedEnd.payload.A = null;

    const q = digestEvents(
      emptyFrontState("s"),
      [projectedStart, projectedEnd],
    );

    assert.equal(q.actions.length, 1);
    assert.equal(q.actions[0].local_id, "projected:1");
    assert.equal(q.actions[0].projected, true);
    assert.equal(q.actions[0].dispatch_id, null);
    assert.equal(q.actions[0].dispatcher_identity_id, null);
    assert.equal(q.actions[0].dispatcher_role, null);
    assert.equal(q.actions[0].status, "success");
  },
);

test(
  "partially null controller correlation fails closed",
  () => {
    const malformed = start(1, "d");
    malformed.dispatch_id = null;

    assert.throws(
      () => digestEvents(
        emptyFrontState("s"),
        [malformed],
      ),
      /fully projected null correlation envelope/,
    );
  },
);

test(
  "controller end cannot close an envelope owned by another actor",
  () => {
    const q = digestEvents(
      emptyFrontState("s"),
      [
        start(
          1,
          "d",
          "MANUAL",
          {
            identityId: "actor-a",
            role: "writer",
          },
        ),
        end(
          2,
          "d",
          {
            identityId: "actor-b",
            role: "writer",
          },
        ),
      ],
    );

    assert.equal(
      q.open_action.dispatcher_identity_id,
      "actor-a",
    );
    assert.equal(
      q.orphan_ends.length,
      1,
    );
    assert.equal(
      q.actions.length,
      0,
    );
  },
);

test(
  "completed action preserves dispatcher actor",
  () => {
    const q = digestEvents(
      emptyFrontState("s"),
      [
        start(
          1,
          "d",
          "MANUAL",
          {
            identityId: "writer-device-9",
            role: "writer",
          },
        ),
        end(
          2,
          "d",
          {
            identityId: "writer-device-9",
            role: "writer",
          },
        ),
      ],
    );

    assert.equal(
      q.actions[0].dispatcher_identity_id,
      "writer-device-9",
    );
    assert.equal(
      q.actions[0].dispatcher_role,
      "writer",
    );
  },
);

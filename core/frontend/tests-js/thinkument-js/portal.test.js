import assert from "node:assert/strict";
import test from "node:test";

import {
  createPortal,
} from "../../src/live_vial/_js/thinkumentJS/platform/__web/portal.js";

const response = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  async json() {
    return body;
  },
});

test(
  "supports enquiry, hidden-only pull progress, and formal 409",
  async () => {
    const calls = [];

    const fetchFn = async (
      url,
      options,
    ) => {
      calls.push([
        url,
        options,
      ]);

      if (calls.length === 1) {
        return response(
          200,
          {
            latest_event_seq: 2,
          },
        );
      }

      if (calls.length === 2) {
        return response(
          200,
          {
            events: [],
            after_event_seq: 0,
            next_after_event_seq: 2,
            session_latest_event_seq: 2,
          },
        );
      }

      return response(
        409,
        {
          rejected: true,
          rejection_kind:
            "stale_conflict",
        },
      );
    };

    const portal = createPortal({
      endpoints: {
        latestEventSeq: "/latest",
        events: "/events",
        dispatch: "/d",
        dispatchFunked: "/df",
        context: "/c",
      },
      identityId: "i",
      fetchFn,
    });

    assert.equal(
      (
        await portal.enquire()
      ).latest_event_seq,
      2,
    );
    assert.equal(
      (
        await portal.pull({
          afterEventSeq: 0,
          limit: 10,
        })
      ).next_after_event_seq,
      2,
    );
    assert.match(
      calls[1][0],
      /identity_id=i/,
    );
    assert.equal(
      (
        await portal.dispatch({
          identity_id: "i",
          request_id: "r1",
        })
      ).rejected,
      true,
    );
  },
);

test(
  "reads run-level eps page with after_seq, limit, and optional window",
  async () => {
    const calls = [];

    const portal = createPortal({
      endpoints: {
        eps: "/eps",
      },
      identityId: "actor-1",
      fetchFn: async (url) => {
        calls.push(url);

        return response(
          200,
          {
            kind: "thinkument_eps_page_v1",
            after_seq: 0,
            next_after_seq: 1,
            eps_head: 1,
            rows: [
              {
                kind: "thinkument_eps_row_v1",
                eps_seq: 1,
                event_id: "ev-1",
                channel: "datum.message",
                payload: { text: "working" },
              },
            ],
          },
        );
      },
    });

    const page = await portal.pullEps({
      afterSeq: 0,
      limit: 50,
      window: 512,
    });

    assert.equal(page.next_after_seq, 1);
    assert.equal(page.eps_head, 1);
    assert.match(calls[0], /after_seq=0/);
    assert.match(calls[0], /limit=50/);
    assert.match(calls[0], /window=512/);
    assert.doesNotMatch(calls[0], /role=/);
  },
);

test(
  "dispatch pumps run-level eps pages while the dispatch request remains open",
  async () => {
    let dispatchReleased;
    const dispatchGate = new Promise(
      (resolve) => {
        dispatchReleased = resolve;
      },
    );

    let epsReads = 0;
    const seen = [];

    const portal = createPortal({
      endpoints: {
        dispatch: "/dispatch",
        dispatchFunked: "/dispatch-funked",
        eps: "/eps",
      },
      identityId: "actor",
      epsPollPeriodMs: 0,
      sleep: async () => {},
      fetchFn: async (url) => {
        if (String(url).startsWith("/eps")) {
          epsReads += 1;

          if (epsReads === 1) {
            return response(
              200,
              {
                kind: "thinkument_eps_page_v1",
                after_seq: 0,
                next_after_seq: 1,
                eps_head: 1,
                rows: [
                  {
                    eps_seq: 1,
                    event_id: "ev-1",
                    channel: "datum.message",
                    payload: { text: "working" },
                  },
                ],
              },
            );
          }

          dispatchReleased();

          return response(
            200,
            {
              kind: "thinkument_eps_page_v1",
              after_seq: 1,
              next_after_seq: 1,
              eps_head: 1,
              rows: [],
            },
          );
        }

        await dispatchGate;

        return response(
          200,
          {
            rejected: false,
            dispatch_outcome: "applied",
          },
        );
      },
    });

    const result = await portal.dispatch(
      {
        identity_id: "actor",
        request_id: "request",
      },
      {
        onEpsPage(page) {
          seen.push(page.next_after_seq);
        },
      },
    );

    assert.equal(
      result.dispatch_outcome,
      "applied",
    );
    assert.ok(seen.includes(1));
  },
);

test(
  "resolves Django 202 jobs",
  async () => {
    const bodies = [
      response(
        202,
        {
          status: "accepted",
          status_url: "/jobs/1",
        },
      ),
      response(
        200,
        {
          status: "running",
        },
      ),
      response(
        200,
        {
          status: "success",
          result_json: {
            rejected: false,
            dispatch_outcome: "applied",
          },
        },
      ),
    ];

    const portal = createPortal({
      endpoints: {
        dispatch: "/d",
        dispatchFunked: "/df",
      },
      fetchFn: async () => (
        bodies.shift()
      ),
      sleep: async () => {},
      jobPollPeriodMs: 0,
    });

    assert.equal(
      (
        await portal.dispatch({
          identity_id: "i",
          request_id: "r1",
        })
      ).dispatch_outcome,
      "applied",
    );
  },
);

test(
  "dispatch fails before fetch when identity_id is absent",
  async () => {
    let calls = 0;

    const portal = createPortal({
      endpoints: {
        dispatch: "/d",
        dispatchFunked: "/df",
      },
      fetchFn: async () => {
        calls += 1;

        return response(
          200,
          {
            rejected: false,
          },
        );
      },
    });

    await assert.rejects(
      () => portal.dispatch({
        request_id: "r1",
      }),
      /dispatch packet\.identity_id is required/,
    );
    assert.equal(
      calls,
      0,
    );
  },
);

test(
  "funked dispatch also fails before fetch without identity_id",
  async () => {
    let calls = 0;

    const portal = createPortal({
      endpoints: {
        dispatch: "/d",
        dispatchFunked: "/df",
      },
      fetchFn: async () => {
        calls += 1;

        return response(
          200,
          {
            rejected: false,
          },
        );
      },
    });

    await assert.rejects(
      () => portal.dispatch(
        {
          request_id: "r1",
        },
        {
          funked: true,
        },
      ),
      /dispatch packet\.identity_id is required/,
    );
    assert.equal(
      calls,
      0,
    );
  },
);

test(
  "dispatch completion aborts an active eps sleep",
  async () => {
    let epsReads = 0;
    let sleepAborted = false;

    const portal = createPortal({
      endpoints: {
        dispatch: "/dispatch",
        dispatchFunked: "/dispatch-funked",
        eps: "/eps",
      },
      identityId: "actor",
      epsPollPeriodMs: 10_000,
      sleep: (
        _ms,
        signal,
      ) => new Promise(
        (resolve, reject) => {
          if (signal.aborted) {
            sleepAborted = true;
            reject(signal.reason);
            return;
          }

          signal.addEventListener(
            "abort",
            () => {
              sleepAborted = true;
              reject(signal.reason);
            },
            { once: true },
          );
        },
      ),
      fetchFn: async (url) => {
        if (String(url).startsWith("/eps")) {
          epsReads += 1;

          return response(
            200,
            {
              kind: "thinkument_eps_page_v1",
              after_seq: 0,
              next_after_seq: 0,
              eps_head: 0,
              rows: [],
            },
          );
        }

        await new Promise(
          (resolve) => setImmediate(resolve),
        );

        return response(
          200,
          {
            rejected: false,
            dispatch_outcome: "applied",
          },
        );
      },
    });

    const result =
      await portal.dispatch(
        {
          identity_id: "actor",
          request_id: "request",
        },
        {
          onEpsPage() {},
        },
      );

    assert.equal(
      result.dispatch_outcome,
      "applied",
    );
    assert.equal(
      epsReads,
      1,
    );
    assert.equal(
      sleepAborted,
      true,
    );
  },
);

test(
  "default in-flight eps cadence is 250 ms",
  async () => {
    let observedSleepMs = null;
    let markSleepStarted;

    const sleepStarted =
      new Promise((resolve) => {
        markSleepStarted = resolve;
      });

    const portal = createPortal({
      endpoints: {
        dispatch: "/dispatch",
        dispatchFunked: "/dispatch-funked",
        eps: "/eps",
      },
      identityId: "actor",

      sleep: (
        ms,
        signal,
      ) => {
        observedSleepMs = ms;
        markSleepStarted();

        return new Promise(
          (resolve, reject) => {
            if (signal.aborted) {
              reject(signal.reason);
              return;
            }

            signal.addEventListener(
              "abort",
              () => reject(
                signal.reason,
              ),
              { once: true },
            );
          },
        );
      },

      fetchFn: async (url) => {
        if (String(url).startsWith("/eps")) {
          return response(
            200,
            {
              kind: "thinkument_eps_page_v1",
              after_seq: 0,
              next_after_seq: 0,
              eps_head: 0,
              rows: [],
            },
          );
        }

        await sleepStarted;

        return response(
          200,
          {
            rejected: false,
            dispatch_outcome: "applied",
          },
        );
      },
    });

    await portal.dispatch(
      {
        identity_id: "actor",
        request_id: "request",
      },
      {
        onEpsPage() {},
      },
    );

    assert.equal(
      observedSleepMs,
      250,
    );
  },
);

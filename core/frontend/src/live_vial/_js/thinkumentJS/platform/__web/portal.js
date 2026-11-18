import {
  assertDispatchIdentity,
  normalizeDispatchResult,
  normalizeEnquiryResult,
  normalizeEpsPage,
  normalizePublicState,
  normalizePullResult,
} from "./shapes.js";

const sleepDefault = (ms, signal) => new Promise((resolve, reject) => {
  if (signal?.aborted) return reject(signal.reason || new Error("aborted"));
  const onAbort = () => { clearTimeout(timer); reject(signal.reason || new Error("aborted")); };
  const timer = setTimeout(() => {
    signal?.removeEventListener("abort", onAbort);
    resolve();
  }, ms);
  signal?.addEventListener("abort", onAbort, { once: true });
});

function endpoint(endpoints, key) {
  const value = String(endpoints?.[key] || "").trim();
  if (!value) throw new TypeError(`endpoints.${key} is required`);
  return value;
}

async function readJson(response) {
  let body = {};
  try { body = await response.json(); } catch {}

  if (!response.ok && response.status !== 409) {
    const error = new Error(body.error || body.reason || `HTTP ${response.status}`);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}

function requestTarget(base, params) {
  const url = new URL(base, "http://thinkument.invalid");
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, String(value));
  }
  return /^https?:/i.test(base) ? url.toString() : `${url.pathname}${url.search}`;
}

const jobStatusRow = (body) => (
  body?.job && typeof body.job === "object" && !Array.isArray(body.job)
    ? body.job
    : body
);

export function createPortal({
  endpoints,
  identityId = null,
  fetchFn = globalThis.fetch,
  headersFn = () => ({}),
  credentials = "same-origin",
  requestTimeoutMs = 20_000,
  dispatchWaitMs = 20_000,
  jobPollPeriodMs = 250,
  epsPollPeriodMs = 250,
  epsPageSize = 100,
  sleep = sleepDefault,
}) {
  if (typeof fetchFn !== "function") throw new TypeError("fetchFn is required");
  if (!endpoints || typeof endpoints !== "object") throw new TypeError("endpoints are required");
  if (!Number.isInteger(epsPageSize) || epsPageSize < 1) {
    throw new TypeError("epsPageSize must be a positive integer");
  }
  if (!Number.isFinite(epsPollPeriodMs) || epsPollPeriodMs < 0) {
    throw new TypeError("epsPollPeriodMs must be a non-negative finite number");
  }

  const call = async (url, options = {}) => {
    const timeoutController = new AbortController();
    const onExternalAbort = () => timeoutController.abort(options.signal.reason);
    options.signal?.addEventListener("abort", onExternalAbort, { once: true });
    const timer = requestTimeoutMs > 0
      ? setTimeout(() => timeoutController.abort(new Error("request timeout")), requestTimeoutMs)
      : null;

    try {
      const response = await fetchFn(url, {
        credentials,
        ...options,
        signal: timeoutController.signal,
        headers: {
          Accept: "application/json",
          ...headersFn(url, options),
          ...(options.headers || {}),
        },
      });
      return { response, body: await readJson(response) };
    } finally {
      if (timer !== null) clearTimeout(timer);
      options.signal?.removeEventListener("abort", onExternalAbort);
    }
  };

  const resolveAcceptedJob = async (body, signal) => {
    if (body.status !== "accepted" || !body.status_url) return body;
    const deadline = Date.now() + dispatchWaitMs;

    while (true) {
      if (signal?.aborted) throw signal.reason || new Error("dispatch job polling aborted");
      if (dispatchWaitMs > 0 && Date.now() >= deadline) {
        const error = new Error("dispatch job did not complete before client deadline");
        error.code = "dispatch_job_timeout";
        error.accepted = body;
        throw error;
      }
      await sleep(jobPollPeriodMs, signal);
      const { body: statusBody } = await call(body.status_url, { signal });
      const row = jobStatusRow(statusBody);
      const status = String(row?.status || "").toLowerCase();
      if (status === "success") return row.result_json ?? row.result ?? row;
      if (["failure", "failed", "canceled", "cancelled"].includes(status)) {
        const error = new Error(row.error || `dispatch job ${status}`);
        error.body = statusBody;
        throw error;
      }
    }
  };

  const pullEps = async ({
    afterSeq = 0,
    limit = epsPageSize,
    window = null,
    signal,
  } = {}) => {
    if (!Number.isInteger(afterSeq) || afterSeq < 0) {
      throw new TypeError("afterSeq must be a non-negative integer");
    }
    if (!Number.isInteger(limit) || limit < 1) {
      throw new TypeError("eps limit must be a positive integer");
    }
    const params = {
      after_seq: afterSeq,
      limit,
    };
    if (window !== null && window !== undefined) {
      if (!Number.isInteger(window) || window < 1) {
        throw new TypeError("eps window must be a positive integer");
      }
      params.window = window;
    }

    const target = requestTarget(endpoint(endpoints, "eps"), params);
    return normalizeEpsPage((await call(target, { signal })).body, {
      requestedAfterSeq: afterSeq,
    });
  };

  const startEpsPump = ({ signal, onEpsTick, onEpsPage }) => {
    const hasTick = typeof onEpsTick === "function";
    const hasPage = typeof onEpsPage === "function";
    if (!hasTick && !hasPage) return { async stop() {} };
    if (!String(endpoints.eps || "").trim()) {
      return { async stop() {} };
    }

    const controller = new AbortController();
    const onExternalAbort = () => controller.abort(signal?.reason || new Error("eps pump aborted"));
    if (signal?.aborted) onExternalAbort();
    else signal?.addEventListener("abort", onExternalAbort, { once: true });

    let stopping = false;
    let observationalError = null;
    let afterSeq = 0;

    const pump = (async () => {
      try {
        if (epsPollPeriodMs > 0) {
          await sleep(epsPollPeriodMs, controller.signal);
        }

        while (!stopping && !controller.signal.aborted) {
          if (hasTick) {
            await onEpsTick({ signal: controller.signal });
          } else {
            const page = await pullEps({
              afterSeq,
              signal: controller.signal,
            });
            if (page.next_after_seq > afterSeq) {
              afterSeq = page.next_after_seq;
            }
            await onEpsPage(page);
          }
          if (stopping || controller.signal.aborted) return;
          await sleep(epsPollPeriodMs, controller.signal);
          if (epsPollPeriodMs === 0 && !stopping && !controller.signal.aborted) {
            await new Promise((resolve) => setTimeout(resolve, 0));
          }
        }
      } catch (error) {
        if (!stopping && !signal?.aborted && !controller.signal.aborted) observationalError = error;
      } finally {
        signal?.removeEventListener("abort", onExternalAbort);
      }
    })();

    return {
      async stop() {
        stopping = true;
        if (!controller.signal.aborted) controller.abort(new Error("eps pump stopped"));
        try { await pump; } catch {}
        if (!hasTick && hasPage && afterSeq === 0 && !signal?.aborted) {
          try {
            const finalPage = await pullEps({ afterSeq });
            afterSeq = Math.max(afterSeq, finalPage.next_after_seq);
            await onEpsPage(finalPage);
          } catch (error) {
            observationalError = observationalError || error;
          }
        }
        return observationalError;
      },
    };
  };

  return Object.freeze({
    identityId,

    async enquire({ signal } = {}) {
      return normalizeEnquiryResult((await call(endpoint(endpoints, "latestEventSeq"), { signal })).body);
    },

    async pull({ identityId: callerIdentityId, afterEventSeq, limit, signal }) {
      const identity = String(callerIdentityId || identityId || "").trim();
      if (!identity) throw new TypeError("identityId is required for pull");
      const target = requestTarget(endpoint(endpoints, "events"), {
        identity_id: identity,
        after_event_seq: afterEventSeq,
        limit,
      });
      return normalizePullResult((await call(target, { signal })).body);
    },

    pullEps,

    async dispatch(packet, { funked = false, signal, onEpsTick = null, onEpsPage = null } = {}) {
      assertDispatchIdentity(packet, "dispatch packet");
      const epsPump = startEpsPump({ signal, onEpsTick, onEpsPage });
      try {
        const body = (await call(
          endpoint(endpoints, funked ? "dispatchFunked" : "dispatch"),
          {
            method: "POST",
            signal,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(packet),
          },
        )).body;
        return normalizeDispatchResult(await resolveAcceptedJob(body, signal));
      } finally {
        await epsPump.stop();
      }
    },

    async readContext({ signal } = {}) {
      return normalizePublicState((await call(endpoint(endpoints, "context"), { signal })).body);
    },
  });
}

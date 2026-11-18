const defaultSleep = (ms, signal) => new Promise((resolve, reject) => {
  if (signal?.aborted) return reject(signal.reason || new Error("aborted"));
  const onAbort = () => { clearTimeout(timer); reject(signal.reason || new Error("aborted")); };
  const timer = setTimeout(() => { signal?.removeEventListener("abort", onAbort); resolve(); }, ms);
  signal?.addEventListener("abort", onAbort, { once: true });
});

export function createPollPull({ portal, pageSize, onPage, onError = () => {}, sleep = defaultSleep }) {
  if (!portal || typeof portal.enquire !== "function" || typeof portal.pull !== "function") throw new TypeError("portal is invalid");
  if (!Number.isInteger(pageSize) || pageSize < 1) throw new TypeError("pageSize must be a positive integer");
  if (typeof onPage !== "function") throw new TypeError("onPage is required");

  let stopped = false;
  let loopPromise = null;
  let syncTail = Promise.resolve();
  let synchronizingCount = 0;
  const controller = new AbortController();

  const normalizedCursor = (cursorOrGetter) => {
    const cursor = typeof cursorOrGetter === "function" ? cursorOrGetter() : cursorOrGetter;
    if (!Number.isInteger(cursor) || cursor < 0) throw new TypeError("cursor must be a non-negative integer");
    return cursor;
  };

  const normalizedTarget = (value) => {
    if (!Number.isInteger(value) || value < 0) throw new TypeError("latestEventSeq must be a non-negative integer");
    return value;
  };

  const oneCatchUp = async (cursorOrGetter, latestHint = null) => {
    const cursor = normalizedCursor(cursorOrGetter);
    if (stopped) throw controller.signal.reason || new Error("poller stopped");
    synchronizingCount += 1;
    try {
      let C = cursor;
      let A = latestHint === null
        ? (await portal.enquire({ signal: controller.signal })).latest_event_seq
        : normalizedTarget(latestHint);
      const pages = [];

      while (!stopped && C < A) {
        const page = await portal.pull({
          identityId: portal.identityId,
          afterEventSeq: C,
          limit: pageSize,
          signal: controller.signal,
        });
        if (page.after_event_seq !== C) throw new Error("pull response cursor does not match request cursor");
        if (page.next_after_event_seq <= C) throw new Error("pull made no cursor progress");
        await onPage(page);
        pages.push(page);
        C = page.next_after_event_seq;
        A = Math.max(A, page.session_latest_event_seq);
      }
      return { cursor: C, latest: A, pages };
    } finally {
      synchronizingCount -= 1;
    }
  };

  const enqueue = (run) => {
    const result = syncTail.then(run, run);
    syncTail = result.then(() => undefined, () => undefined);
    return result;
  };

  const catchUp = (cursorOrGetter) => enqueue(() => oneCatchUp(cursorOrGetter));

  /*
   * Synchronize to a caller-owned canonical high-water without first issuing
   * an enquiry. This is safe when the caller learned that high-water from an
   * authoritative server receipt/page. Pull responses may reveal an even newer
   * high-water; in that case the loop naturally continues through it.
   */
  const catchUpTo = (cursorOrGetter, latestEventSeq) => enqueue(
    () => oneCatchUp(cursorOrGetter, normalizedTarget(latestEventSeq)),
  );

  function runLoop({ getCursor, getDelayMs }) {
    if (typeof getCursor !== "function" || typeof getDelayMs !== "function") throw new TypeError("getCursor and getDelayMs are required");
    if (loopPromise) return loopPromise;

    loopPromise = (async () => {
      while (!stopped) {
        try {
          await sleep(getDelayMs(), controller.signal);
          if (stopped) break;
          await catchUp(getCursor);
        } catch (error) {
          if (stopped || controller.signal.aborted) break;
          try { await onError(error); } catch {}
        }
      }
    })().finally(() => { loopPromise = null; });
    return loopPromise;
  }

  return Object.freeze({
    catchUp,
    catchUpTo,
    runLoop,
    stop(reason = new Error("poller stopped")) {
      const running = loopPromise;
      if (!stopped) { stopped = true; controller.abort(reason); }
      return running ?? Promise.resolve();
    },
    get stopped() { return stopped; },
    get running() { return loopPromise !== null; },
    get synchronizing() { return synchronizingCount > 0; },
  });
}

export function createEpsPollPull({ portal, pageSize, onPage, onError = () => {}, sleep = defaultSleep }) {
  if (!portal || typeof portal !== "object") throw new TypeError("portal is invalid");
  if (!Number.isInteger(pageSize) || pageSize < 1) throw new TypeError("pageSize must be a positive integer");
  if (typeof onPage !== "function") throw new TypeError("onPage is required");

  let stopped = false;
  let loopPromise = null;
  let syncTail = Promise.resolve();
  let synchronizingCount = 0;
  const controller = new AbortController();

  const normalizedCursor = (cursorOrGetter) => {
    const cursor = typeof cursorOrGetter === "function" ? cursorOrGetter() : cursorOrGetter;
    if (!Number.isInteger(cursor) || cursor < 0) throw new TypeError("eps cursor must be a non-negative integer");
    return cursor;
  };

  const oneCatchUp = async (cursorOrGetter, { window = null } = {}) => {
    const cursor = normalizedCursor(cursorOrGetter);
    if (stopped) throw controller.signal.reason || new Error("eps poller stopped");
    if (typeof portal.pullEps !== "function") {
      return { cursor, head: cursor, pages: [] };
    }
    synchronizingCount += 1;
    try {
      let E = cursor;
      let head = cursor;
      const pages = [];
      let firstPage = true;

      while (!stopped) {
        const page = await portal.pullEps({
          afterSeq: E,
          limit: pageSize,
          window: firstPage ? window : null,
          signal: controller.signal,
        });
        firstPage = false;

        if (page.after_seq !== E) throw new Error("eps pull response cursor does not match request cursor");
        if (page.next_after_seq < E) throw new Error("eps pull cursor regressed");

        pages.push(page);
        head = Math.max(head, page.eps_head);

        if (page.rows.length > 0 || page.next_after_seq > E) {
          await onPage(page);
        }

        if (page.next_after_seq <= E) break;
        E = page.next_after_seq;
        if (E >= head) break;
      }
      return { cursor: E, head, pages };
    } finally {
      synchronizingCount -= 1;
    }
  };

  const enqueue = (run) => {
    const result = syncTail.then(run, run);
    syncTail = result.then(() => undefined, () => undefined);
    return result;
  };

  const catchUp = (cursorOrGetter, options = {}) => enqueue(() => oneCatchUp(cursorOrGetter, options));

  function runLoop({ getCursor, getDelayMs }) {
    if (typeof getCursor !== "function" || typeof getDelayMs !== "function") {
      throw new TypeError("getCursor and getDelayMs are required");
    }
    if (loopPromise) return loopPromise;

    loopPromise = (async () => {
      while (!stopped) {
        try {
          await sleep(getDelayMs(), controller.signal);
          if (stopped) break;
          await catchUp(getCursor);
        } catch (error) {
          if (stopped || controller.signal.aborted) break;
          try { await onError(error); } catch {}
        }
      }
    })().finally(() => { loopPromise = null; });
    return loopPromise;
  }

  return Object.freeze({
    catchUp,
    runLoop,
    stop(reason = new Error("eps poller stopped")) {
      const running = loopPromise;
      if (!stopped) { stopped = true; controller.abort(reason); }
      return running ?? Promise.resolve();
    },
    get stopped() { return stopped; },
    get running() { return loopPromise !== null; },
    get synchronizing() { return synchronizingCount > 0; },
  });
}

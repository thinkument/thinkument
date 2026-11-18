import { normalizeGlobals } from "./globals.js";
import { makeDispatch } from "./__web/shapes.js";
import { cloneDeadJson, plainObject } from "./_shared/dead_json.js";
import { emptyFrontState, digestEpsPage, digestEvents, validateFrontState } from "./_backend_events/digest.js";
import { createEpsPollPull, createPollPull } from "./_backend_events/pollpull.js";
import { createThinkumentLoopbackApi } from "../outbound.js";
import { assertOutboundDispatchValid, validateOutboundDispatch } from "../outbound_guard.js";
import { disseminateInformation, INFORMATION_TRIGGER_EPSILON, INFORMATION_TRIGGER_THETA } from "../inbound.js";

const randomId = () => (
  globalThis.crypto?.randomUUID?.()
  || `${Date.now()}-${Math.random().toString(36).slice(2)}`
);

const bounded = (rows, item, maximum) => [
  ...rows,
  cloneDeadJson(item),
].slice(-maximum);

export const REQUEST_ID_FIELD = "request_id";

const dispatchCanonicalHighWater = (result) => {
  const value = result?.dispatch_concurrency?.after_event_seq;
  return Number.isInteger(value) && value >= 0 ? value : null;
};

export function createThinkumentApp({
  sessionId,
  identityId,
  role = null,
  portal,
  globals = {},
  initialQ = null,
  initialX = {},
  stateLoader = null,
  stateDumper = null,
  informationDisseminationFn = null,
  clock = Date,
  sleep,
  onError = () => {},
}) {
  const sid = String(sessionId || "").trim();
  const iid = String(identityId || "").trim();

  if (!sid || !iid) throw new TypeError("sessionId and identityId are required");
  if (!portal || typeof portal.dispatch !== "function") throw new TypeError("portal is required");
  plainObject(initialX, "initialX");

  const G = normalizeGlobals(globals);
  const drink = informationDisseminationFn;

  let Q = initialQ === null
    ? emptyFrontState(sid)
    : validateFrontState(initialQ, { sessionId: sid });
  let X = cloneDeadJson(initialX, "initialX");
  let informationReceipts = [];

  let localDispatchesInFlight = 0;
  let dispatchFastUntil = 0;
  let remoteActivityUntil = 0;
  let started = false;
  let startPromise = null;

  let dispatchTail = Promise.resolve();
  let disseminationTail = Promise.resolve();
  let stateCommitTail = Promise.resolve();

  const api = {};

  const clientContext = () => ({
    session_id: sid,
    identity_id: iid,
    role,
  });

  const snapshot = () => ({
    kind: "thinkument_front_dump_v2",
    session_id: sid,
    Q: cloneDeadJson(Q),
    X: cloneDeadJson(X),
    informationDisseminationReceipts: cloneDeadJson(informationReceipts),
  });

  const dump = async () => {
    if (typeof stateDumper === "function") await stateDumper(snapshot());
  };

  const extendDeadline = (currentDeadline, durationMs) => Math.max(
    currentDeadline,
    clock.now() + durationMs,
  );

  const beginLocalDispatch = () => {
    localDispatchesInFlight += 1;
    dispatchFastUntil = extendDeadline(dispatchFastUntil, G.dispatchWindowMs);
  };

  const finishLocalDispatch = () => {
    localDispatchesInFlight = Math.max(0, localDispatchesInFlight - 1);
    dispatchFastUntil = extendDeadline(dispatchFastUntil, G.dispatchWindowMs);
  };

  const noteRemoteCanonicalActivity = () => {
    remoteActivityUntil = extendDeadline(remoteActivityUntil, G.remoteActivityWindowMs);
  };

  const pollingCadence = () => {
    const now = clock.now();
    if (localDispatchesInFlight > 0 || now < dispatchFastUntil) {
      return { mode: "dispatch_fast", periodMs: G.dispatchPeriodMs };
    }
    if (now < remoteActivityUntil) {
      return { mode: "remote_activity", periodMs: G.remoteActivityPeriodMs };
    }
    return { mode: "baseline", periodMs: G.basePeriodMs };
  };

  const delay = () => pollingCadence().periodMs;

  const commitState = (successorFactory) => {
    if (typeof successorFactory !== "function") throw new TypeError("successorFactory must be a function");

    const operation = async () => {
      const outcome = await successorFactory({
        Q: cloneDeadJson(Q, "current Q"),
        X: cloneDeadJson(X, "current X"),
      });
      plainObject(outcome, "state transition outcome");
      plainObject(outcome.Q, "state transition outcome.Q");
      plainObject(outcome.X, "state transition outcome.X");

      Q = validateFrontState(outcome.Q, { sessionId: sid });
      X = cloneDeadJson(outcome.X, "state transition outcome.X");
      return outcome;
    };

    const result = stateCommitTail.then(operation, operation);
    stateCommitTail = result.then(() => undefined, () => undefined);
    return result;
  };

  const appendInformationReceipt = (receipt) => {
    informationReceipts = bounded(
      informationReceipts,
      receipt,
      G.maxInformationDisseminationReceipts,
    );
  };

  const createDisseminationLoopback = ({ heartbeatQ, heartbeatX }) => {
    const qSnapshot = cloneDeadJson(heartbeatQ, "information heartbeat Q");
    const xSnapshot = cloneDeadJson(heartbeatX, "information heartbeat X");
    let active = true;

    const reentrantMutationError = (name) => new Error(
      `${name} cannot run reentrantly during information dissemination; `
      + "capture the loopback and invoke it from a later substrate callback",
    );

    const loopback = Object.freeze({
      kind: api.loopback.kind,
      readQ() {
        return active ? cloneDeadJson(qSnapshot, "information loopback Q") : api.loopback.readQ();
      },
      readX() {
        return active ? cloneDeadJson(xSnapshot, "information loopback X") : api.loopback.readX();
      },
      async writeX(nextOrUpdater) {
        if (active) throw reentrantMutationError("loopback.writeX");
        return api.loopback.writeX(nextOrUpdater);
      },
      validateDispatch(args) {
        if (!active) return api.loopback.validateDispatch(args);
        return validateOutboundDispatch({
          Q: cloneDeadJson(qSnapshot, "information dispatch validation Q"),
          role,
          A: args,
        });
      },
      dispatch(args) {
        if (active) throw reentrantMutationError("loopback.dispatch");
        return api.loopback.dispatch(args);
      },
    });

    return {
      loopback,
      release() { active = false; },
    };
  };

  const applyEpsPage = async (page) => {
    const operation = async () => {
      const oldQ = Q;
      const { nextState: newQ, newRows } = digestEpsPage(
        oldQ,
        page,
        { limits: G },
      );
      if (newQ.eps_cursor === oldQ.eps_cursor && !newRows.length) return;

      if (!newRows.length) {
        await commitState(async (current) => {
          if (current.Q.eps_cursor !== oldQ.eps_cursor) {
            throw new Error("eps Q changed while advancing eps cursor");
          }
          return {
            Q: {
              ...current.Q,
              eps_cursor: newQ.eps_cursor,
              eps_rows: newQ.eps_rows,
            },
            X: current.X,
          };
        });
        await dump();
        return;
      }

      let scopedLoopback = null;
      let outcome;
      try {
        outcome = await commitState(async (current) => {
          if (current.Q.eps_cursor !== oldQ.eps_cursor) {
            throw new Error("eps Q changed while applying one eps page");
          }
          const mergedQ = {
            ...current.Q,
            eps_cursor: newQ.eps_cursor,
            eps_rows: newQ.eps_rows,
          };
          scopedLoopback = createDisseminationLoopback({
            heartbeatQ: mergedQ,
            heartbeatX: current.X,
          });
          const disseminated = await disseminateInformation({
            drink,
            trigger: INFORMATION_TRIGGER_EPSILON,
            clientContext: clientContext(),
            Q: mergedQ,
            oldX: current.X,
            loopback: scopedLoopback.loopback,
            epsilon: {
              oldQ: current.Q,
              newQ: mergedQ,
              newRows,
              page,
            },
          });
          return {
            Q: mergedQ,
            X: disseminated.X,
            disseminationReceipt: disseminated.disseminationReceipt,
          };
        });
      } finally {
        scopedLoopback?.release();
      }
      appendInformationReceipt(outcome.disseminationReceipt);
      await dump();
    };

    const result = disseminationTail.then(operation, operation);
    disseminationTail = result.then(() => undefined, () => undefined);
    return result;
  };

  const enqueueDispatch = ({
    action,
    userFill = {},
    userSignal = null,
    funked = false,
    requestId = randomId(),
  }, { catchUpAfter }) => {
    const operation = async () => {
      const localA = { action, userFill, userSignal, funked, requestId };
      assertOutboundDispatchValid({ Q, role, A: localA });

      const packet = makeDispatch({
        action,
        userFill,
        userSignal,
        role,
        identityId: iid,
        requestId,
        cursor: Q.cursor,
      });

      beginLocalDispatch();
      let result;
      let dispatchError = null;
      try {
        result = await portal.dispatch(packet, {
          funked,
          onEpsPage: applyEpsPage,
          onEpsTick: async () => {
            try {
              await epsPoller.catchUp(() => Q.eps_cursor);
            } catch (error) {
              try { await onError(error); } catch {}
            }
          },
        });
      } catch (error) {
        dispatchError = error;
      } finally {
        finishLocalDispatch();
      }

      if (catchUpAfter) {
        try {
          await epsPoller.catchUp(() => Q.eps_cursor);
        } catch (error) {
          if (!dispatchError) throw error;
          try { await onError(error); } catch {}
        }
        try {
          const afterEventSeq = dispatchError ? null : dispatchCanonicalHighWater(result);
          if (afterEventSeq !== null) {
            await poller.catchUpTo(() => Q.cursor, afterEventSeq);
          } else {
            await poller.catchUp(() => Q.cursor);
          }
        } catch (error) {
          if (!dispatchError) throw error;
          try { await onError(error); } catch {}
        }
      }

      if (dispatchError) throw dispatchError;
      return result;
    };

    const result = dispatchTail.then(operation, operation);
    dispatchTail = result.then(() => undefined, () => undefined);
    return result;
  };

  const pageHasRemoteOrUnknownActivity = (page) => {
    const controllerEvents = page.events.filter(
      (event) => event.kind === "controller_loop_event_v1",
    );
    if (!controllerEvents.length) return true;
    return controllerEvents.some(
      (event) => String(event.dispatcher_identity_id ?? "").trim() !== iid,
    );
  };

  const applyPage = async (page) => {
    const operation = async () => {
      const oldQ = Q;
      const newQ = digestEvents(
        oldQ,
        page.events,
        page.next_after_event_seq,
        {
          canonicalGapDetected: Boolean(page.canonical_gap_detected),
          limits: G,
        },
      );
      if (newQ.cursor === oldQ.cursor) return;

      let scopedLoopback = null;
      let outcome;
      try {
        outcome = await commitState(async (current) => {
          if (current.Q.cursor !== oldQ.cursor) {
            throw new Error("canonical Q changed while applying one theta page");
          }
          scopedLoopback = createDisseminationLoopback({
            heartbeatQ: newQ,
            heartbeatX: current.X,
          });
          const disseminated = await disseminateInformation({
            drink,
            trigger: INFORMATION_TRIGGER_THETA,
            clientContext: clientContext(),
            Q: newQ,
            oldX: current.X,
            loopback: scopedLoopback.loopback,
            theta: {
              oldQ,
              newQ,
              newEvents: page.events,
              page,
              reason: page.canonical_gap_detected
                ? "backend_events_after_gap"
                : "backend_events",
            },
          });
          return {
            Q: newQ,
            X: disseminated.X,
            disseminationReceipt: disseminated.disseminationReceipt,
          };
        });
      } finally {
        scopedLoopback?.release();
      }

      appendInformationReceipt(outcome.disseminationReceipt);
      if (pageHasRemoteOrUnknownActivity(page)) noteRemoteCanonicalActivity();
      await dump();
    };

    const result = disseminationTail.then(operation, operation);
    disseminationTail = result.then(() => undefined, () => undefined);
    return result;
  };

  const poller = createPollPull({
    portal,
    pageSize: G.eventPageSize,
    onPage: applyPage,
    onError,
    sleep,
  });

  const epsPoller = createEpsPollPull({
    portal,
    pageSize: G.epsPageSize,
    onPage: applyEpsPage,
    onError,
    sleep,
  });

  const resetToInitial = () => {
    Q = initialQ === null
      ? emptyFrontState(sid)
      : validateFrontState(initialQ, { sessionId: sid });
    X = cloneDeadJson(initialX, "initialX");
    informationReceipts = [];
  };

  const load = async () => {
    if (typeof stateLoader !== "function") return;
    const loaded = await stateLoader(sid);
    if (!loaded) return;

    try {
      plainObject(loaded, "loaded Thinkument dump");
      if (loaded.kind !== "thinkument_front_dump_v2") throw new TypeError("invalid Thinkument dump kind");
      if (String(loaded.session_id) !== sid) throw new RangeError("Thinkument dump belongs to another session");
      Q = validateFrontState(loaded.Q, { sessionId: sid });
      plainObject(loaded.X, "loaded X");
      X = cloneDeadJson(loaded.X, "loaded X");
      informationReceipts = Array.isArray(loaded.informationDisseminationReceipts)
        ? cloneDeadJson(loaded.informationDisseminationReceipts).slice(-G.maxInformationDisseminationReceipts)
        : [];
    } catch {
      resetToInitial();
    }
  };

  Object.assign(api, {
    async start() {
      if (started) return api;
      if (startPromise) return startPromise;

      startPromise = (async () => {
        await load();
        await epsPoller.catchUp(() => Q.eps_cursor, {
          window: Q.eps_cursor === 0 ? G.maxEpsRows : null,
        });
        await poller.catchUp(() => Q.cursor);
        started = true;
        epsPoller.runLoop({
          getCursor: () => Q.eps_cursor,
          getDelayMs: delay,
        }).catch(onError);
        poller.runLoop({
          getCursor: () => Q.cursor,
          getDelayMs: delay,
        }).catch(onError);
        return api;
      })();

      try {
        return await startPromise;
      } catch (error) {
        started = false;
        throw error;
      } finally {
        startPromise = null;
      }
    },

    stop() {
      started = false;
      return Promise.all([epsPoller.stop(), poller.stop()]).then(() => undefined);
    },

    async sync() {
      await epsPoller.catchUp(() => Q.eps_cursor);
      return poller.catchUp(() => Q.cursor);
    },

    async syncTo(latestEventSeq) {
      await epsPoller.catchUp(() => Q.eps_cursor);
      return poller.catchUpTo(() => Q.cursor, latestEventSeq);
    },

    validateDispatch(args) {
      return validateOutboundDispatch({
        Q: cloneDeadJson(Q, "dispatch validation Q"),
        role,
        A: args,
      });
    },

    dispatch(args) {
      return enqueueDispatch(args, { catchUpAfter: true });
    },

    readQ() { return cloneDeadJson(Q, "Q"); },
    readX() { return cloneDeadJson(X, "X"); },

    writeX(nextOrUpdater) {
      const operation = async () => {
        const outcome = await commitState(async (current) => {
          const candidate = typeof nextOrUpdater === "function"
            ? nextOrUpdater(cloneDeadJson(current.X, "writeX current X"))
            : nextOrUpdater;
          if (candidate?.then instanceof Function) {
            throw new TypeError(
              "writeX updater must be synchronous; perform async work before writeX, then commit the dead-JSON successor",
            );
          }
          plainObject(candidate, "writeX successor");
          return {
            Q: current.Q,
            X: cloneDeadJson(candidate, "writeX successor"),
          };
        });
        await dump();
        return cloneDeadJson(outcome.X, "writeX committed X");
      };
      return operation();
    },

    readInformationDisseminationReceipts() {
      return cloneDeadJson(informationReceipts, "information dissemination receipts");
    },

    readDump() { return snapshot(); },

    readLifecycle() {
      const cadence = pollingCadence();
      return {
        started,
        stopped: poller.stopped && epsPoller.stopped,
        polling: poller.running || epsPoller.running,
        synchronizing: poller.synchronizing || epsPoller.synchronizing,
        pollingMode: cadence.mode,
        pollingPeriodMs: cadence.periodMs,
        localDispatchesInFlight,
      };
    },
  });

  api.loopback = createThinkumentLoopbackApi(api);
  return Object.freeze(api);
}

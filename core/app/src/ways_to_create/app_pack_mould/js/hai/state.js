const HAI_STATE_KEY = "app_pack_mould";
const HAI_STATE_KIND = "app_pack_mould_front_state_v1";
const MAX_TRIDENT_REFS = 512;
const MAX_LIVE_ROWS = 512;

const asObject = (value) => (
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value
    : null
);

const clone = (value) => structuredClone(value);

export const initialHaiState = () => ({
  kind: HAI_STATE_KIND,
  collected_processed_dispatch_tridents: [],
  collected_live_inexplosion_msgs: [],
  page_being_viewed: -1,
  snap_page_on_new_trident: true,
  silence_eps: false,
  silence_theta: false,
});

export const normalizeHaiState = (X) => {
  const source = asObject(X?.[HAI_STATE_KEY]);
  const base = initialHaiState();
  if (!source) return base;

  const out = {
    ...base,
    ...clone(source),
  };
  out.kind = HAI_STATE_KIND;
  if (!Array.isArray(out.collected_processed_dispatch_tridents)) {
    out.collected_processed_dispatch_tridents = [];
  }
  if (!Array.isArray(out.collected_live_inexplosion_msgs)) {
    out.collected_live_inexplosion_msgs = [];
  }
  if (!Number.isInteger(out.page_being_viewed) || out.page_being_viewed < -1) {
    out.page_being_viewed = -1;
  }
  for (const key of [
    "snap_page_on_new_trident",
    "silence_eps",
    "silence_theta",
  ]) {
    out[key] = Boolean(out[key]);
  }
  return out;
};

export const graftHaiState = (X, haiState) => ({
  ...(asObject(X) ?? {}),
  [HAI_STATE_KEY]: clone(haiState),
});

const tridentRef = (T) => ({
  local_id: T?.local_id ?? null,
  dispatch_id: T?.dispatch_id ?? null,
  action: T?.action ?? null,
  status: T?.status ?? null,
  start_event_seq: T?.start?.event_seq ?? null,
  end_event_seq: T?.end?.event_seq ?? null,
});

const liveRef = (row) => ({
  eps_seq: row?.eps_seq ?? null,
  request_id: row?.request_id ?? null,
  trident_dispatch_id: row?.trident_dispatch_id ?? null,
  channel: row?.channel ?? null,
  obfuscated: Boolean(row?.obfuscated),
  row: clone(row ?? {}),
});

const appendUniqueBounded = (rows, additions, keyFn, maximum) => {
  const out = [...rows];
  const keys = new Set(out.map(keyFn));
  for (const item of additions) {
    const key = keyFn(item);
    if (keys.has(key)) continue;
    keys.add(key);
    out.push(item);
  }
  return out.slice(-maximum);
};

export const stateAfterHeartbeat = (W) => {
  const oldX = W.X();
  const state = normalizeHaiState(oldX);

  if (W.isTheta()) {
    const oldCursor = W.thetaOldQ()?.cursor ?? -1;
    const newRefs = W.tridents()
      .filter((T) => Number.isInteger(T?.end?.event_seq) && T.end.event_seq > oldCursor)
      .map(tridentRef);
    state.collected_processed_dispatch_tridents = appendUniqueBounded(
      state.collected_processed_dispatch_tridents,
      newRefs,
      (row) => `${row.local_id}|${row.end_event_seq}`,
      MAX_TRIDENT_REFS,
    );
    if (state.snap_page_on_new_trident) state.page_being_viewed = -1;
  }

  if (W.isEpsilon()) {
    const incomingRows = W.epsNewRows()?.length ? W.epsNewRows() : W.epsRows();
    const refs = incomingRows.map((row) => liveRef(row));
    state.collected_live_inexplosion_msgs = appendUniqueBounded(
      state.collected_live_inexplosion_msgs,
      refs,
      (item) => `${item.eps_seq}`,
      MAX_LIVE_ROWS,
    );
  }

  return {
    state,
    X: graftHaiState(oldX, state),
  };
};

const stateFromLoopback = (loopback) => normalizeHaiState(loopback.readX());

const writeHaiState = async (loopback, updater) => loopback.writeX((X) => {
  const current = normalizeHaiState(X);
  const next = updater(clone(current));
  return graftHaiState(X, next);
});

const historicalValidation = () => ({
  kind: "app_pack_mould_dispatch_validation_v1",
  ok: false,
  dispatchable: false,
  errors: [{
    code: "historical_page_read_only",
    message: "dispatch is disabled while viewing a historical HAI page",
  }],
});

export function createHaiLoopbackApi({ kernelLoopback, onStateCommitted = null }) {
  if (!kernelLoopback || kernelLoopback.kind !== "thinkument_outbound_v1") {
    throw new TypeError("kernelLoopback must be thinkument_outbound_v1");
  }

  const commit = async (updater) => {
    const X = await writeHaiState(kernelLoopback, updater);
    if (typeof onStateCommitted === "function") {
      await onStateCommitted(clone(X));
    }
    return clone(X);
  };

  const viewingHistorical = () => stateFromLoopback(kernelLoopback).page_being_viewed !== -1;

  return Object.freeze({
    kind: "app_pack_mould_loopback_v1",

    readQ: () => kernelLoopback.readQ(),
    readX: () => kernelLoopback.readX(),
    writeX(nextOrUpdater) {
      return kernelLoopback.writeX((currentX) => {
        const owned = normalizeHaiState(currentX);
        const proposed = typeof nextOrUpdater === "function"
          ? nextOrUpdater(clone(currentX))
          : clone(nextOrUpdater);
        if (proposed === null || typeof proposed !== "object" || Array.isArray(proposed)) {
          throw new TypeError("HAI writeX successor must be a plain object");
        }
        return graftHaiState(proposed, owned);
      });
    },

    readHaiState: () => clone(stateFromLoopback(kernelLoopback)),
    getCollectedProcessedDispatchTridents: () => clone(
      stateFromLoopback(kernelLoopback).collected_processed_dispatch_tridents,
    ),
    getCollectedLiveInexplosionMsgs: () => clone(
      stateFromLoopback(kernelLoopback).collected_live_inexplosion_msgs,
    ),

    getPageNumber: () => stateFromLoopback(kernelLoopback).page_being_viewed,
    async setPageNumber(value) {
      if (!Number.isInteger(value) || value < -1) {
        throw new TypeError("page number must be -1 or a non-negative integer");
      }
      const cursor = kernelLoopback.readQ().cursor;
      if (value > cursor) throw new RangeError("page number cannot exceed current Q cursor");
      return commit((state) => ({ ...state, page_being_viewed: value }));
    },

    getSnapPageOnNewTrident: () => stateFromLoopback(kernelLoopback).snap_page_on_new_trident,
    setSnapPageOnNewTrident: (value) => commit((state) => ({
      ...state,
      snap_page_on_new_trident: Boolean(value),
    })),

    getSilenceEps: () => stateFromLoopback(kernelLoopback).silence_eps,
    setSilenceEps: (value) => commit((state) => ({
      ...state,
      silence_eps: Boolean(value),
    })),

    getSilenceTheta: () => stateFromLoopback(kernelLoopback).silence_theta,
    setSilenceTheta: (value) => commit((state) => ({
      ...state,
      silence_theta: Boolean(value),
    })),

    validateDispatch(A) {
      return viewingHistorical()
        ? historicalValidation()
        : kernelLoopback.validateDispatch(A);
    },

    dispatch(A) {
      if (viewingHistorical()) {
        const receipt = historicalValidation();
        const error = new TypeError(receipt.errors[0].message);
        error.code = receipt.errors[0].code;
        error.receipt = receipt;
        throw error;
      }
      return kernelLoopback.dispatch(A);
    },
  });
}

export const HAI_FRONT_STATE_KEY = HAI_STATE_KEY;
export const HAI_FRONT_STATE_KIND = HAI_STATE_KIND;

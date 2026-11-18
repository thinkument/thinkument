export const DEFAULTS = Object.freeze({
  /*
   * Canonical queue polling is intentionally adaptive, but the baseline is
   * still the discovery bound for activity caused by another client. Keep the
   * idle bound human-interactive: a continuously visible client should learn
   * about remote canonical work within about one second without requiring any
   * test-only sync hook.
   *
   * Local dispatches already use the authoritative dispatch receipt and
   * catchUpTo(), so these faster burst cadences are only the background safety
   * net around nearby activity; they are not the correctness mechanism.
   */
  basePeriodMs: 1_000,
  dispatchPeriodMs: 250,
  dispatchWindowMs: 5_000,
  remoteActivityPeriodMs: 500,
  remoteActivityWindowMs: 5_000,
  eventPageSize: 100,
  requestTimeoutMs: 20_000,
  dispatchWaitMs: 20_000,
  jobPollPeriodMs: 250,
  epsPollPeriodMs: 250,
  epsPageSize: 100,
  maxEpsRows: 512,
  maxInformationDisseminationReceipts: 256,
  maxActionEnvelopes: 2_048,
  maxInterruptions: 512,
  maxOrphanEnds: 512,
});

const plainObject = (value, name) => {
  if (
    value === null
    || typeof value !== "object"
    || Array.isArray(value)
  ) {
    throw new TypeError(`${name} must be an object`);
  }
};

const finite = (value, name) => {
  if (!Number.isFinite(value) || value < 0) {
    throw new TypeError(
      `${name} must be a non-negative finite number`,
    );
  }
};

const positiveInteger = (value, name) => {
  if (!Number.isInteger(value) || value < 1) {
    throw new TypeError(`${name} must be a positive integer`);
  }
};

export function normalizeGlobals(raw = {}) {
  plainObject(raw, "globals");

  const g = {
    ...DEFAULTS,
    ...raw,
  };

  for (const key of [
    "basePeriodMs",
    "dispatchPeriodMs",
    "dispatchWindowMs",
    "remoteActivityPeriodMs",
    "remoteActivityWindowMs",
    "requestTimeoutMs",
    "dispatchWaitMs",
    "jobPollPeriodMs",
    "epsPollPeriodMs",
  ]) {
    finite(g[key], key);
  }

  for (const key of [
    "eventPageSize",
    "epsPageSize",
    "maxEpsRows",
    "maxInformationDisseminationReceipts",
    "maxActionEnvelopes",
    "maxInterruptions",
    "maxOrphanEnds",
  ]) {
    positiveInteger(g[key], key);
  }

  if (g.dispatchPeriodMs > g.remoteActivityPeriodMs) {
    throw new RangeError(
      "dispatchPeriodMs cannot exceed remoteActivityPeriodMs",
    );
  }

  if (g.remoteActivityPeriodMs > g.basePeriodMs) {
    throw new RangeError(
      "remoteActivityPeriodMs cannot exceed basePeriodMs",
    );
  }

  return Object.freeze({ ...g });
}

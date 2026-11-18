import {
  cloneDeadJson,
  plainObject,
} from "../_shared/dead_json.js";

const CONTROLLER_KIND = "controller_loop_event_v1";

const boundedAppend = (
  rows,
  value,
  maximum,
) => [...rows, value].slice(-maximum);

const limitsWithDefaults = (limits = {}) => ({
  maxActionEnvelopes:
    limits.maxActionEnvelopes
    ?? Number.MAX_SAFE_INTEGER,
  maxEpsRows:
    limits.maxEpsRows
    ?? 512,
  maxInterruptions:
    limits.maxInterruptions
    ?? Number.MAX_SAFE_INTEGER,
  maxOrphanEnds:
    limits.maxOrphanEnds
    ?? Number.MAX_SAFE_INTEGER,
});

export function emptyFrontState(
  sessionId,
  {
    cursor = 0,
    epsCursor = 0,
    latestU = null,
    bootstrap = null,
  } = {},
) {
  if (!Number.isInteger(cursor) || cursor < 0) {
    throw new TypeError(
      "cursor must be a non-negative integer",
    );
  }
  if (!Number.isInteger(epsCursor) || epsCursor < 0) {
    throw new TypeError(
      "epsCursor must be a non-negative integer",
    );
  }

  return {
    kind: "thinkument_front_state_v1",
    session_id: String(sessionId),
    cursor,
    eps_cursor: epsCursor,
    eps_rows: [],
    latest_U: latestU === null
      ? null
      : cloneDeadJson(latestU, "latestU"),
    open_action: null,
    actions: [],
    interruptions: [],
    orphan_ends: [],
    canonical_gap_count: 0,
    bootstrap: bootstrap === null
      ? null
      : cloneDeadJson(bootstrap, "bootstrap"),
  };
}

export function validateFrontState(
  value,
  { sessionId = null } = {},
) {
  plainObject(value, "front state");

  if (value.kind !== "thinkument_front_state_v1") {
    throw new TypeError("invalid front state kind");
  }
  if (
    !Number.isInteger(value.cursor)
    || value.cursor < 0
  ) {
    throw new TypeError(
      "front state cursor must be a non-negative integer",
    );
  }
  if (
    !Number.isInteger(value.eps_cursor)
    || value.eps_cursor < 0
  ) {
    throw new TypeError(
      "front state eps_cursor must be a non-negative integer",
    );
  }
  if (
    sessionId !== null
    && String(value.session_id) !== String(sessionId)
  ) {
    throw new RangeError(
      "front state belongs to another session",
    );
  }

  for (
    const key of [
      "actions",
      "eps_rows",
      "interruptions",
      "orphan_ends",
    ]
  ) {
    if (!Array.isArray(value[key])) {
      throw new TypeError(
        `front state ${key} must be an array`,
      );
    }
  }

  if (value.open_action !== null) {
    plainObject(
      value.open_action,
      "front state open_action",
    );
  }
  if (
    !Number.isInteger(value.canonical_gap_count)
    || value.canonical_gap_count < 0
  ) {
    throw new TypeError(
      "canonical_gap_count must be a non-negative integer",
    );
  }

  return cloneDeadJson(value, "front state");
}

function classifyEnd(event) {
  if (event.payload?.outcome === "system_error") {
    return "system_error";
  }

  const lastError = event.payload?.result?.last_error;
  return (
    lastError
    && typeof lastError === "object"
    && !Array.isArray(lastError)
    && Object.keys(lastError).length
  )
    ? "semantic_rejected"
    : "success";
}

function controllerCorrelation(event) {
  const dispatchId = event.dispatch_id;
  const identityId = event.dispatcher_identity_id;
  const role = event.dispatcher_role;

  const fullyProjected = (
    dispatchId === null
    && identityId === null
    && role === null
  );
  if (fullyProjected) {
    return {
      projected: true,
      dispatchId: null,
      identityId: null,
      role: null,
    };
  }

  if (
    typeof dispatchId !== "string"
    || !dispatchId.trim()
  ) {
    throw new TypeError(
      "controller event dispatch_id must be a non-empty string "
      + "or part of a fully projected null correlation envelope",
    );
  }
  if (
    typeof identityId !== "string"
    || !identityId.trim()
  ) {
    throw new TypeError(
      "controller event dispatcher_identity_id must be a non-empty "
      + "string or part of a fully projected null correlation envelope",
    );
  }
  if (
    role !== null
    && typeof role !== "string"
  ) {
    throw new TypeError(
      "controller event dispatcher_role must be string or null",
    );
  }

  return {
    projected: false,
    dispatchId: dispatchId.trim(),
    identityId: identityId.trim(),
    role,
  };
}

function localTridentId(correlation, event) {
  return correlation.projected
    ? `projected:${event.event_seq}`
    : `dispatch:${correlation.dispatchId}`;
}

function endMatchesOpen(open, correlation) {
  if (open.projected !== correlation.projected) {
    return false;
  }
  if (correlation.projected) {
    return true;
  }
  return (
    open.dispatch_id === correlation.dispatchId
    && open.dispatcher_identity_id === correlation.identityId
    && open.dispatcher_role === correlation.role
  );
}

export function applyEvent(
  state,
  rawEvent,
  limits = {},
) {
  const caps = limitsWithDefaults(limits);
  const event = cloneDeadJson(rawEvent, "event");

  if (
    !Number.isInteger(event.event_seq)
    || event.event_seq <= state.cursor
  ) {
    throw new RangeError(
      `event_seq must increase: cursor=${state.cursor}, `
      + `received=${event.event_seq}`,
    );
  }

  const next = {
    ...state,
    cursor: event.event_seq,
  };

  if (event.kind !== CONTROLLER_KIND) {
    return next;
  }

  plainObject(
    event.payload,
    "controller event payload",
  );
  plainObject(
    event.payload.U,
    "controller event payload.U",
  );

  const correlation = controllerCorrelation(event);

  next.latest_U = cloneDeadJson(
    event.payload.U,
    "controller event payload.U",
  );

  if (event.phase === "start") {
    if (next.open_action) {
      const interrupted = {
        ...next.open_action,
        status: "interrupted",
      };
      next.actions = boundedAppend(
        next.actions,
        interrupted,
        caps.maxActionEnvelopes,
      );
      next.interruptions = boundedAppend(
        next.interruptions,
        interrupted.dispatch_id,
        caps.maxInterruptions,
      );
    }

    next.open_action = {
      local_id: localTridentId(correlation, event),
      projected: correlation.projected,
      dispatch_id: correlation.dispatchId,
      dispatcher_identity_id: correlation.identityId,
      dispatcher_role: correlation.role,
      action: String(event.action || ""),
      start: event,
      end: null,
      status: "open",
    };
    return next;
  }

  if (event.phase !== "end") {
    throw new TypeError(
      `unknown controller phase ${event.phase}`,
    );
  }

  if (
    !next.open_action
    || !endMatchesOpen(next.open_action, correlation)
  ) {
    next.orphan_ends = boundedAppend(
      next.orphan_ends,
      event,
      caps.maxOrphanEnds,
    );
    return next;
  }

  next.actions = boundedAppend(
    next.actions,
    {
      ...next.open_action,
      end: event,
      status: classifyEnd(event),
    },
    caps.maxActionEnvelopes,
  );
  next.open_action = null;
  return next;
}

export function digestEvents(
  state,
  events,
  scannedThrough = null,
  {
    canonicalGapDetected = false,
    limits = {},
  } = {},
) {
  if (!Array.isArray(events)) {
    throw new TypeError("events must be an array");
  }

  let next = validateFrontState(state);
  for (const event of events) {
    next = applyEvent(next, event, limits);
  }

  if (scannedThrough !== null) {
    if (
      !Number.isInteger(scannedThrough)
      || scannedThrough < next.cursor
    ) {
      throw new RangeError(
        "scannedThrough cannot precede visible cursor",
      );
    }
    next = {
      ...next,
      cursor: scannedThrough,
    };
  }

  if (canonicalGapDetected) {
    next = {
      ...next,
      canonical_gap_count:
        next.canonical_gap_count + 1,
    };
  }

  return next;
}

export function digestEpsPage(
  state,
  epsPage,
  {
    limits = {},
  } = {},
) {
  const validated = validateFrontState(state);
  plainObject(epsPage, "epsPage");
  if (!Array.isArray(epsPage.rows)) {
    throw new TypeError("epsPage.rows must be an array");
  }

  const caps = limitsWithDefaults(limits);
  let cursor = validated.eps_cursor;
  let rows = [...validated.eps_rows];
  const newRows = [];

  for (const rawRow of epsPage.rows) {
    const row = cloneDeadJson(rawRow, "eps row");
    if (
      !Number.isInteger(row.eps_seq)
      || row.eps_seq <= cursor
    ) {
      throw new RangeError(
        `eps_seq must increase: eps_cursor=${cursor}, `
        + `received=${row.eps_seq}`,
      );
    }
    cursor = row.eps_seq;
    rows.push(row);
    newRows.push(row);
  }

  if (
    epsPage.next_after_seq !== null
    && epsPage.next_after_seq !== undefined
  ) {
    if (
      !Number.isInteger(epsPage.next_after_seq)
      || epsPage.next_after_seq < cursor
    ) {
      throw new RangeError(
        "next_after_seq cannot precede visible eps_cursor",
      );
    }
    cursor = epsPage.next_after_seq;
  }

  rows = rows.slice(-caps.maxEpsRows);

  return {
    nextState: {
      ...validated,
      eps_cursor: cursor,
      eps_rows: rows,
    },
    newRows,
  };
}
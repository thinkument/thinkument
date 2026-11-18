import {
  cloneDeadJson,
  plainObject,
} from "../_shared/dead_json.js";

const text = (value, name) => {
  const out = String(value ?? "").trim();
  if (!out) throw new TypeError(`${name} is required`);
  return out;
};

const integer = (value, name, minimum = 0) => {
  if (!Number.isInteger(value) || value < minimum) {
    throw new TypeError(
      `${name} must be an integer >= ${minimum}`,
    );
  }
  return value;
};

export function makeEnquiry({
  sessionId,
  identityId,
  role = null,
}) {
  return Object.freeze({
    kind: "thinkument_enquiry_v1",
    session_id: text(sessionId, "sessionId"),
    identity_id: text(identityId, "identityId"),
    role: role === null ? null : String(role),
  });
}

export function normalizeEnquiryResult(value) {
  plainObject(value, "Enquiry'");
  return Object.freeze({
    ...cloneDeadJson(value, "Enquiry'"),
    latest_event_seq: integer(
      value.latest_event_seq ?? value.event_seq,
      "latest_event_seq",
    ),
  });
}

export function makePull({
  sessionId,
  identityId,
  role = null,
  afterEventSeq,
  limit,
}) {
  return Object.freeze({
    kind: "thinkument_pull_v1",
    session_id: text(sessionId, "sessionId"),
    identity_id: text(identityId, "identityId"),
    role: role === null ? null : String(role),
    after_event_seq: integer(
      afterEventSeq,
      "afterEventSeq",
    ),
    limit: integer(limit, "limit", 1),
  });
}

export function normalizePullResult(value) {
  plainObject(value, "Pull'");
  if (!Array.isArray(value.events)) {
    throw new TypeError("Pull' must contain events[]");
  }

  const after = integer(
    value.after_event_seq ?? 0,
    "after_event_seq",
  );
  const next = integer(
    value.next_after_event_seq,
    "next_after_event_seq",
  );
  const latest = integer(
    value.session_latest_event_seq,
    "session_latest_event_seq",
  );

  if (next < after) {
    throw new RangeError(
      "next_after_event_seq cannot precede after_event_seq",
    );
  }
  if (next > latest) {
    throw new RangeError(
      "next_after_event_seq cannot exceed session_latest_event_seq",
    );
  }
  if (latest > after && next === after) {
    throw new RangeError(
      "Pull' made no canonical cursor progress",
    );
  }

  let previous = after;
  for (const event of value.events) {
    plainObject(event, "Pull'.events[]");
    if (
      !Number.isInteger(event.event_seq)
      || event.event_seq <= previous
      || event.event_seq > next
    ) {
      throw new RangeError(
        "Pull' visible events must be strictly ordered "
        + "inside the scanned range",
      );
    }
    previous = event.event_seq;
  }

  return Object.freeze({
    ...cloneDeadJson(value, "Pull'"),
    after_event_seq: after,
    next_after_event_seq: next,
    session_latest_event_seq: latest,
  });
}

export function makeDispatch({
  action,
  userFill = {},
  userSignal = null,
  role = null,
  identityId,
  requestId,
  cursor,
}) {
  plainObject(userFill, "userFill");
  if (userSignal !== null) {
    plainObject(userSignal, "userSignal");
  }

  const actionName = text(action, "action").toUpperCase();
  if (
    actionName !== "STEP"
    && (Object.keys(userFill).length || userSignal !== null)
  ) {
    throw new RangeError(
      `${actionName} does not accept STEP fill or signal payloads`,
    );
  }

  const actionFields = { action: actionName };
  if (actionName === "STEP") {
    actionFields.user_fill = cloneDeadJson(userFill, "userFill");
    actionFields.user_signal = userSignal === null
      ? null
      : cloneDeadJson(userSignal, "userSignal");
  }

  return Object.freeze({
    ...actionFields,
    role: role === null ? null : String(role),
    identity_id: text(identityId, "identityId"),
    request_id: text(requestId, "requestId"),
    my_current_event_seq_number: integer(
      cursor,
      "cursor",
    ),
  });
}

export function assertDispatchIdentity(
  value,
  name = "dispatch",
) {
  plainObject(value, name);
  text(value.identity_id, `${name}.identity_id`);
  return value;
}

export function normalizeDispatchResult(value) {
  plainObject(value, "C'");
  if (typeof value.rejected !== "boolean") {
    throw new TypeError("C'.rejected must be boolean");
  }
  if (
    value.dispatch_outcome !== undefined
    && typeof value.dispatch_outcome !== "string"
  ) {
    throw new TypeError(
      "C'.dispatch_outcome must be a string when present",
    );
  }
  return Object.freeze(cloneDeadJson(value, "C'"));
}

export function normalizeEpsPage(
  value,
  { requestedAfterSeq = null } = {},
) {
  plainObject(value, "EpsPage'");

  if (
    value.kind !== undefined
    && value.kind !== "thinkument_eps_page_v1"
  ) {
    throw new TypeError("unknown eps page kind");
  }

  if (!Array.isArray(value.rows)) {
    throw new TypeError("EpsPage' must contain rows[]");
  }

  const after = integer(
    value.after_seq ?? requestedAfterSeq ?? 0,
    "after_seq",
  );
  const next = integer(
    value.next_after_seq,
    "next_after_seq",
  );
  const head = integer(
    value.eps_head,
    "eps_head",
  );

  if (
    requestedAfterSeq !== null
    && after !== integer(requestedAfterSeq, "requestedAfterSeq")
  ) {
    throw new RangeError(
      "after_seq does not match requestedAfterSeq",
    );
  }
  if (next < after) {
    throw new RangeError(
      "next_after_seq cannot precede after_seq",
    );
  }
  if (next > head) {
    throw new RangeError(
      "next_after_seq cannot exceed eps_head",
    );
  }

  let previous = after;
  for (const row of value.rows) {
    plainObject(row, "EpsPage'.rows[]");

    if (
      row.kind !== undefined
      && row.kind !== "thinkument_eps_row_v1"
    ) {
      throw new TypeError("unknown eps row kind");
    }

    const seq = integer(
      row.eps_seq,
      "eps_seq",
      1,
    );

    if (seq <= previous || seq > next) {
      throw new RangeError(
        "eps rows must be strictly ordered "
        + "inside the scanned range",
      );
    }
    previous = seq;

    if (row.event_id !== undefined) {
      text(row.event_id, "EpsPage'.rows[].event_id");
    }
    if (row.channel !== undefined) {
      text(row.channel, "EpsPage'.rows[].channel");
    }
    if (row.emitted_at !== undefined) {
      text(row.emitted_at, "EpsPage'.rows[].emitted_at");
    }
    if (row.content_hash !== undefined) {
      text(row.content_hash, "EpsPage'.rows[].content_hash");
    }
    if (row.visibility !== undefined) {
      const visibility = text(
        row.visibility,
        "EpsPage'.rows[].visibility",
      );
      if (visibility === "owner-only") {
        throw new RangeError(
          "frontend EpsPage' must never contain owner-only rows",
        );
      }
    }
    if (row.emitter_origin !== undefined) {
      text(row.emitter_origin, "EpsPage'.rows[].emitter_origin");
    }

    if (Object.hasOwn(row, "event_seq")) {
      throw new RangeError(
        "eps rows must not carry canonical event_seq",
      );
    }

    if (row.obfuscated !== undefined && typeof row.obfuscated !== "boolean") {
      throw new TypeError(
        "EpsPage'.rows[].obfuscated must be boolean",
      );
    }

    if (row.obfuscated === true) {
      if (
        row.datum_id !== null
        || row.frame_id !== null
        || row.span_id !== null
        || row.payload !== null
      ) {
        throw new RangeError(
          "obfuscated eps row must null out datum_id, "
          + "frame_id, span_id, and payload",
        );
      }
    } else if (row.payload !== undefined) {
      plainObject(
        row.payload,
        "EpsPage'.rows[].payload",
      );
    }
  }

  return Object.freeze({
    ...cloneDeadJson(value, "EpsPage'"),
    after_seq: after,
    next_after_seq: next,
    eps_head: head,
  });
}

export function normalizePublicState(value) {
  plainObject(value, "public state");
  plainObject(value.ctx, "public state.ctx");
  return Object.freeze(
    cloneDeadJson(value, "public state"),
  );
}
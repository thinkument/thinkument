import {
  cloneDeadJson,
  plainObject,
} from "./platform/_shared/dead_json.js";

export const INFORMATION_TRIGGER_THETA = "theta";
export const INFORMATION_TRIGGER_EPSILON = "epsilon";

const normalizedResult = (
  value,
  oldX,
) => {
  if (value == null) {
    return {
      receipt: null,
      X: cloneDeadJson(oldX, "old X"),
    };
  }

  plainObject(value, "drinker result");
  plainObject(value.X, "drinker result.X");

  return {
    receipt: value.receipt === undefined
      ? null
      : cloneDeadJson(value.receipt, "drinker receipt"),
    X: cloneDeadJson(value.X, "drinker result.X"),
  };
};

const thetaInformation = ({
  oldQ,
  newQ,
  newEvents,
  reason,
  page = null,
}) => {
  plainObject(oldQ, "theta.oldQ");
  plainObject(newQ, "theta.newQ");
  if (!Array.isArray(newEvents)) {
    throw new TypeError("theta.newEvents must be an array");
  }
  if (page !== null) {
    plainObject(page, "theta.page");
  }

  return {
    trigger: Object.freeze({
      kind: INFORMATION_TRIGGER_THETA,
      canonical: true,
      provisional: false,
      reason: String(reason),
    }),
    information: {
      kind: "thinkument_theta_information_v1",
      oldQ: cloneDeadJson(oldQ, "theta.oldQ"),
      newQ: cloneDeadJson(newQ, "theta.newQ"),
      newEvents: cloneDeadJson(newEvents, "theta.newEvents"),
      pollPage: page === null
        ? null
        : cloneDeadJson(page, "theta.page"),
      reason: String(reason),
    },
    receiptContext: {
      cursor: newQ.cursor,
      new_event_count: newEvents.length,
      reason: String(reason),
    },
  };
};

const epsilonInformation = ({
  oldQ,
  newQ,
  newRows,
  page = null,
}) => {
  plainObject(oldQ, "epsilon.oldQ");
  plainObject(newQ, "epsilon.newQ");
  if (!Array.isArray(newRows)) {
    throw new TypeError("epsilon.newRows must be an array");
  }
  if (page !== null) {
    plainObject(page, "epsilon.page");
  }

  return {
    trigger: Object.freeze({
      kind: INFORMATION_TRIGGER_EPSILON,
      canonical: false,
      provisional: false,
      reason: "eps_rows",
    }),
    information: {
      kind: "thinkument_epsilon_information_v1",
      oldQ: cloneDeadJson(oldQ, "epsilon.oldQ"),
      newQ: cloneDeadJson(newQ, "epsilon.newQ"),
      newRows: cloneDeadJson(newRows, "epsilon.newRows"),
      pollPage: page === null
        ? null
        : cloneDeadJson(page, "epsilon.page"),
      reason: "eps_rows",
    },
    receiptContext: {
      eps_cursor: newQ.eps_cursor,
      eps_head: page?.eps_head ?? newQ.eps_cursor,
      new_row_count: newRows.length,
      reason: "eps_rows",
    },
  };
};

/**
 * Normalize either canonical theta or provisional epsilon into the one
 * downstream information-drinker packet.
 *
 * Input socket:
 *   drink(packet, loopback)
 *
 * `packet` is detached dead JSON. `loopback`, when supplied by
 * createThinkumentApp, is the frozen thinkument_outbound_v1 capability seam.
 *
 * Output socket:
 *   null/undefined => preserve X
 *   { X: <dead JSON object>, receipt?: <dead JSON> }
 */
export async function disseminateInformation({
  drink,
  trigger,
  clientContext,
  Q,
  oldX,
  theta = null,
  epsilon = null,
  loopback = null,
}) {
  plainObject(clientContext, "clientContext");
  plainObject(Q, "Q");
  plainObject(oldX, "oldX");

  let normalized;
  if (trigger === INFORMATION_TRIGGER_THETA) {
    normalized = thetaInformation(theta || {});
  } else if (trigger === INFORMATION_TRIGGER_EPSILON) {
    normalized = epsilonInformation(epsilon || {});
  } else {
    throw new RangeError(`unknown information trigger ${trigger}`);
  }

  if (typeof drink !== "function") {
    return {
      X: cloneDeadJson(oldX, "oldX"),
      disseminationReceipt: {
        kind: "thinkument_inbound_receipt_v1",
        trigger: normalized.trigger.kind,
        skipped: true,
        reason: "no_drinker",
        ...cloneDeadJson(normalized.receiptContext),
        receipt: null,
      },
    };
  }

  const packet = Object.freeze({
    kind: "thinkument_information_inbound_v1",
    trigger: normalized.trigger,
    context: Object.freeze({
      session_id: String(clientContext.session_id),
      identity_id: String(clientContext.identity_id),
      role: clientContext.role === null
        ? null
        : String(clientContext.role),
      Q: cloneDeadJson(Q, "context.Q"),
      X: cloneDeadJson(oldX, "context.X"),
    }),
    information: Object.freeze(
      cloneDeadJson(normalized.information, "information"),
    ),
  });

  const out = normalizedResult(
    await drink(packet, loopback),
    oldX,
  );

  return {
    X: out.X,
    disseminationReceipt: {
      kind: "thinkument_inbound_receipt_v1",
      trigger: normalized.trigger.kind,
      skipped: false,
      ...cloneDeadJson(normalized.receiptContext),
      receipt: out.receipt,
    },
  };
}

export const disseminate = disseminateInformation;

import {
  cloneDeadJson,
  plainObject,
} from "./platform/_shared/dead_json.js";

const INBOUND_KIND = "thinkument_information_inbound_v1";
const THETA = "theta";
const EPSILON = "epsilon";
const OBFUSCATED_DATUM_KIND = "role_mismatch_obfuscated_datum_v1";

const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

const text = (value) => String(value ?? "").trim();

const clone = (value, label = "womb value") => cloneDeadJson(value, label);

const asObject = (value) => (
  value !== null
  && typeof value === "object"
  && !Array.isArray(value)
    ? value
    : null
);

const datumIdOf = (row) => text(row?.datum_id ?? row?.id);

const currentUOf = (packet) => (
  asObject(packet?.context?.Q?.latest_U)
);

const datumRowsOf = (U) => (
  Array.isArray(U?.datum_states_on_this_span)
    ? U.datum_states_on_this_span.filter((row) => asObject(row))
    : []
);

const datumIndexOf = (U) => {
  const out = new Map();
  for (const row of datumRowsOf(U)) {
    const datumId = datumIdOf(row);
    if (!datumId) continue;
    if (out.has(datumId)) {
      throw new Error(
        `duplicate datum_id in datum_states_on_this_span: ${datumId}`,
      );
    }
    out.set(datumId, row);
  }
  return out;
};

const activeIdsOf = (U) => {
  if (!U || !own(U, "datum_widgets_on_this_span")) {
    return null;
  }
  if (!Array.isArray(U.datum_widgets_on_this_span)) {
    throw new TypeError(
      "U.datum_widgets_on_this_span must be an array when present",
    );
  }
  return U.datum_widgets_on_this_span
    .map(text)
    .filter(Boolean);
};

const isObfuscated = (row) => (
  row?.kind === OBFUSCATED_DATUM_KIND
  || row?.role_mismatch_obfuscated === true
);

const uniqueDatumIds = (values) => [
  ...new Set(
    values
      .map(text)
      .filter(Boolean),
  ),
];

const scopeOf = (U) => {
  if (!U) return null;

  return {
    form_id: U.form_id ?? null,
    app_form_id: U.app_form_id ?? null,
    frame_id: U.current_frame_id ?? null,
    frame_name: U.current_frame_name ?? null,
    span_id: U.current_span_id ?? U.current_span ?? null,
  };
};

const semanticContextOf = (U) => {
  if (!U) return null;

  return {
    kind: U.kind ?? null,
    scope: scopeOf(U),
    step: asObject(U.step) ?? {},
    globals: asObject(U.globals) ?? {},
    state: asObject(U.state) ?? {},
    tags: Array.isArray(U.tags) ? U.tags : [],
    session_metadata: asObject(U.session_metadata) ?? {},
    provenance: asObject(U.session_metadata?.provenance) ?? {},
    multiframespec: asObject(U.multiframespec) ?? {},
    role_modulation:
      asObject(U.role_mismatch_modulation_info) ?? null,
  };
};

const roleReadProjectionOf = (U, viewerRole) => {
  const info = asObject(
    U?.role_mismatch_modulation_info,
  );

  const rows = datumRowsOf(U);

  const mismatchIds = Array.isArray(
    info?.mismatch_datum_ids,
  )
    ? uniqueDatumIds(info.mismatch_datum_ids)
    : [];

  const obfuscatedIds = uniqueDatumIds([
    ...mismatchIds,
    ...rows
      .filter(isObfuscated)
      .map(datumIdOf),
  ]);

  const readableIds = uniqueDatumIds(
    rows
      .filter((row) => !isObfuscated(row))
      .map(datumIdOf),
  );

  return {
    kind: "thinkument_womb_role_read_projection_v1",
    viewer_role: viewerRole === null
      ? null
      : String(viewerRole),
    modulated: info !== null,
    readable_widget_ids: readableIds,
    obfuscated_widget_ids: obfuscatedIds,
    mismatch_datum_ids: mismatchIds,
    assignments: (
      info !== null
      && own(info, "assignments")
    )
      ? info.assignments
      : null,
    receipt: asObject(info?.receipt),
  };
};

const deadJsonEqual = (left, right) => {
  if (left === right) return true;

  const leftArray = Array.isArray(left);
  const rightArray = Array.isArray(right);

  if (leftArray || rightArray) {
    if (!leftArray || !rightArray) return false;
    if (left.length !== right.length) return false;

    return left.every(
      (value, index) => deadJsonEqual(
        value,
        right[index],
      ),
    );
  }

  const leftObject = asObject(left);
  const rightObject = asObject(right);

  if (leftObject === null || rightObject === null) {
    return false;
  }

  const leftKeys = Object.keys(leftObject);
  const rightKeys = Object.keys(rightObject);

  if (leftKeys.length !== rightKeys.length) {
    return false;
  }

  return leftKeys.every(
    (key) => (
      own(rightObject, key)
      && deadJsonEqual(
        leftObject[key],
        rightObject[key],
      )
    ),
  );
};

const boundaryPositionOf = (U) => {
  if (!U) return null;

  return {
    kind: U.kind ?? null,
    scope: scopeOf(U),
    step: asObject(U.step) ?? {},
  };
};

const authoredArgsOf = (row) => {
  const raw = asObject(row?.args)
    ?? asObject(row?.shell?.args)
    ?? {};
  const out = { ...raw };
  delete out.__kernel;
  return out;
};

const microsOf = (row) => {
  for (const candidate of [
    row?.micros,
    row?.shell?.micros,
  ]) {
    if (Array.isArray(candidate)) {
      return candidate;
    }
  }
  return [];
};

const runtimeStateOf = (row) => (
  asObject(row?.lifecycle?.runtime?.state) ?? {}
);

const assignmentFor = (U, datumId) => {
  const containers = [
    U?.role_assignments,
    U?.role_mismatch_modulation_info?.assignments,
  ];

  for (const container of containers) {
    if (Array.isArray(container)) {
      const row = container.find(
        (item) => datumIdOf(item) === datumId,
      );
      if (row) return clone(row, "role assignment");
    }

    if (asObject(container) && own(container, datumId)) {
      return clone(container[datumId], "role assignment");
    }
  }

  return null;
};

const tridentA = (trident) => {
  const endA = trident?.end?.payload?.A;
  if (endA !== undefined) return endA;
  const startA = trident?.start?.payload?.A;
  return startA === undefined ? null : startA;
};

const dispatchSummaryOf = (trident) => ({
  local_id: trident?.local_id ?? null,
  projected: Boolean(trident?.projected),
  dispatch_id: trident?.dispatch_id ?? null,
  dispatcher_identity_id:
    trident?.dispatcher_identity_id ?? null,
  dispatcher_role:
    trident?.dispatcher_role ?? null,
  action: trident?.action ?? null,
  A: tridentA(trident),
  status: trident?.status ?? null,
  start_event_seq:
    trident?.start?.event_seq ?? null,
  end_event_seq:
    trident?.end?.event_seq ?? null,
});

const timelineTridentsOf = (Q) => [
  ...(Array.isArray(Q?.actions) ? Q.actions : []),
  ...(asObject(Q?.open_action)
    ? [Q.open_action]
    : []),
];

const dispatchTimelineOf = (Q) => {
  const tridents = timelineTridentsOf(Q);

  return tridents.map((trident, index) => {
    const startU = asObject(
      trident?.start?.payload?.U,
    );
    const endU = asObject(
      trident?.end?.payload?.U,
    );

    let continuousFromPrevious = null;

    if (index > 0) {
      const previousEndU = asObject(
        tridents[index - 1]
          ?.end
          ?.payload
          ?.U,
      );

      if (
        previousEndU !== null
        && startU !== null
      ) {
        continuousFromPrevious =
          deadJsonEqual(
            previousEndU,
            startU,
          );
      }
    }

    return {
      ...dispatchSummaryOf(trident),
      source: boundaryPositionOf(startU),
      destination: boundaryPositionOf(endU),
      complete: endU !== null,
      continuous_from_previous:
        continuousFromPrevious,
    };
  });
};

const funkContextOf = (trident) => (
  asObject(trident?.end?.payload?.dispatch_context)
);

const funkContextOfEvent = (event) => (
  event?.kind === "controller_loop_event_v1"
  && event?.phase === "end"
    ? asObject(event?.payload?.dispatch_context)
    : null
);

const funkReceiptOfContext = (context) => (
  asObject(context?.filler_receipt)
);

const nextFunkabilityOfReceipt = (receipt) => (
  asObject(receipt?.next_U_funkability)
);

const funkStatusFrom = ({
  context,
  dispatchId = null,
  localId = null,
  eventSeq = null,
}) => {
  if (context === null) {
    return {
      kind: "thinkument_funk_status_v1",
      observable_funked: false,
      dispatch_id: dispatchId,
      local_id: localId,
      end_event_seq: eventSeq,
      dispatch_context: null,
      filler_receipt: null,
      next_U_funkability: null,
      will_funk_next_dispatch: null,
      reason: null,
    };
  }

  const receipt = funkReceiptOfContext(context);
  const next = nextFunkabilityOfReceipt(receipt);

  return {
    kind: "thinkument_funk_status_v1",
    observable_funked: true,
    dispatch_id: dispatchId,
    local_id: localId,
    end_event_seq: eventSeq,
    dispatch_context: clone(context, "womb funk status context"),
    filler_receipt: receipt === null
      ? null
      : clone(receipt, "womb funk status receipt"),
    next_U_funkability: next === null
      ? null
      : clone(next, "womb funk status next funkability"),
    will_funk_next_dispatch: next?.will_funk_next_dispatch ?? null,
    reason: next?.reason ?? null,
  };
};

const accessProbe = (loopback, datumId) => {
  if (!loopback || typeof loopback.validateDispatch !== "function") {
    return null;
  }

  return loopback.validateDispatch({
    action: "STEP",
    userSignal: {
      datum_id: datumId,
      kind: "__thinkument_womb_access_probe__",
      info: {},
    },
  });
};

const assertInboundPacket = (packet) => {
  plainObject(packet, "womb packet");
  if (packet.kind !== INBOUND_KIND) {
    throw new TypeError(
      `womb expects ${INBOUND_KIND}; got ${String(packet.kind)}`,
    );
  }
  plainObject(packet.trigger, "womb packet.trigger");
  plainObject(packet.context, "womb packet.context");
  plainObject(packet.context.Q, "womb packet.context.Q");
  plainObject(packet.context.X, "womb packet.context.X");
  plainObject(packet.information, "womb packet.information");

  if (![THETA, EPSILON].includes(packet.trigger.kind)) {
    throw new RangeError(
      `unknown womb heartbeat ${String(packet.trigger.kind)}`,
    );
  }

  return packet;
};

const assertLoopback = (loopback) => {
  if (loopback == null) return null;
  if (
    loopback.kind !== "thinkument_outbound_v1"
    || typeof loopback.readQ !== "function"
    || typeof loopback.readX !== "function"
    || typeof loopback.writeX !== "function"
    || typeof loopback.validateDispatch !== "function"
    || typeof loopback.dispatch !== "function"
  ) {
    throw new TypeError(
      "womb loopback must be the thinkument_outbound_v1 surface",
    );
  }
  return loopback;
};

/**
 * Build the high-app read surface for one dissemination heartbeat.
 *
 * Everything read here is detached dead JSON. Q remains ThinkumentJS-owned;
 * X is the heartbeat's input snapshot. Use the drinker return value to commit
 * the next X for this heartbeat.
 */
export function createWombRuntime(packet, loopback = null) {
  assertInboundPacket(packet);
  const outbound = assertLoopback(loopback);

  const Q = packet.context.Q;
  const X = packet.context.X;
  const U = currentUOf(packet);
  const rows = datumRowsOf(U);
  const byId = datumIndexOf(U);

  const requireDatum = (datumId) => {
    const id = text(datumId);
    const row = byId.get(id);
    if (!row) {
      throw new KeyErrorForWombDatum(id);
    }
    return row;
  };

  const requireReadableDatum = (datumId) => {
    const row = requireDatum(datumId);
    if (isObfuscated(row)) {
      throw new ObfuscatedWombDatumError(text(datumId));
    }
    return row;
  };

  const runtime = {
    kind: "thinkument_womb_runtime_v1",
    loopback: outbound,

    rawPacket() {
      return clone(packet, "womb raw packet");
    },

    information() {
      return clone(packet.information, "womb information");
    },

    heartbeat() {
      return packet.trigger.kind;
    },

    isTheta() {
      return packet.trigger.kind === THETA;
    },

    isEpsilon() {
      return packet.trigger.kind === EPSILON;
    },

    trigger() {
      return clone(packet.trigger, "womb trigger");
    },

    session() {
      return {
        session_id: String(packet.context.session_id),
        identity_id: String(packet.context.identity_id),
        role: packet.context.role === null
          ? null
          : String(packet.context.role),
      };
    },

    Q() {
      return clone(Q, "womb Q");
    },

    X() {
      return clone(X, "womb X");
    },

    U() {
      return U === null ? null : clone(U, "womb U");
    },

    runtimeKind() {
      return U?.kind ?? null;
    },

    currentScope() {
      const scope = scopeOf(U);
      return scope === null
        ? null
        : clone(scope, "womb current scope");
    },

    currentStep() {
      const step = asObject(U?.step);
      return step === null
        ? null
        : clone(step, "womb current step");
    },

    semanticContext() {
      const context = semanticContextOf(U);
      return context === null
        ? null
        : clone(
          context,
          "womb semantic context",
        );
    },

    widgetsOnSpan() {
      return clone(rows, "womb widgets on span");
    },

    readableWidgetsOnSpan() {
      return clone(
        rows.filter((row) => !isObfuscated(row)),
        "womb readable widgets on span",
      );
    },

    widget(datumId) {
      return clone(requireDatum(datumId), `womb widget ${datumId}`);
    },

    hasWidget(datumId) {
      return byId.has(text(datumId));
    },

    widgetArgs(datumId) {
      return clone(
        authoredArgsOf(requireReadableDatum(datumId)),
        `womb widget args ${datumId}`,
      );
    },

    widgetShell(datumId) {
      const row = requireReadableDatum(datumId);
      const shell = asObject(row.shell);
      return shell === null
        ? null
        : clone(shell, `womb widget shell ${datumId}`);
    },

    widgetMicros(datumId) {
      return clone(
        microsOf(requireReadableDatum(datumId)),
        `womb widget micros ${datumId}`,
      );
    },

    widgetRuntimeState(datumId) {
      return clone(
        runtimeStateOf(requireReadableDatum(datumId)),
        `womb widget runtime state ${datumId}`,
      );
    },

    widgetFill(datumId) {
      const row = requireReadableDatum(datumId);
      return own(row, "fill")
        ? clone(row.fill, `womb widget fill ${datumId}`)
        : null;
    },

    widgetSemanticValidation(datumId) {
      const row = requireReadableDatum(datumId);
      const semantic = asObject(row.semantic_validation);
      return semantic === null
        ? null
        : clone(
          semantic,
          `womb widget semantic validation ${datumId}`,
        );
    },

    activeWidgetIds() {
      const ids = activeIdsOf(U);
      return ids === null
        ? null
        : clone(ids, "womb active widget ids");
    },

    activeWidgets() {
      const ids = activeIdsOf(U);
      if (ids === null) return null;
      return clone(
        ids.map((id) => byId.get(id)).filter(Boolean),
        "womb active widgets",
      );
    },

    sessionMetadata() {
      return clone(
        asObject(U?.session_metadata) ?? {},
        "womb session metadata",
      );
    },

    provenance() {
      return clone(
        asObject(U?.session_metadata?.provenance) ?? {},
        "womb provenance",
      );
    },

    multiframespec() {
      return clone(
        asObject(U?.multiframespec) ?? {},
        "womb multiframespec",
      );
    },

    lastError() {
      const value = U?.last_error;
      return value == null
        ? null
        : clone(value, "womb last error");
    },

    roleModulationInfo() {
      const value = asObject(U?.role_mismatch_modulation_info);
      return value === null
        ? null
        : clone(value, "womb role modulation info");
    },

    roleModulationReceipt() {
      const value = asObject(
        U?.role_mismatch_modulation_info?.receipt,
      );
      return value === null
        ? null
        : clone(value, "womb role modulation receipt");
    },

    roleReadProjection() {
      return clone(
        roleReadProjectionOf(
          U,
          packet.context.role,
        ),
        "womb role read projection",
      );
    },

    accessForWidget(datumId) {
      const id = text(datumId);
      const row = byId.get(id);
      const activeIds = activeIdsOf(U);
      const probe = accessProbe(outbound, id);

      return {
        datum_id: id,
        present_on_span: Boolean(row),
        readable: Boolean(row && !isObfuscated(row)),
        pending: row?.is_pending === true,
        enabled: row?.enabled !== false,
        editable_membership: (
          activeIds === null
            ? false
            : activeIds.includes(id)
        ),
        role_assignment: assignmentFor(U, id),
        write: probe === null ? null : probe.ok,
        write_validation: probe === null
          ? null
          : clone(probe, `womb access validation ${id}`),
      };
    },

    accessTable() {
      return clone(
        rows.map((row) => runtime.accessForWidget(datumIdOf(row))),
        "womb access table",
      );
    },

    tridents() {
      return clone(
        Array.isArray(Q.actions) ? Q.actions : [],
        "womb tridents",
      );
    },

    openTrident() {
      return Q.open_action == null
        ? null
        : clone(Q.open_action, "womb open trident");
    },

    latestTrident() {
      const actions = Array.isArray(Q.actions) ? Q.actions : [];
      return actions.length
        ? clone(actions.at(-1), "womb latest trident")
        : null;
    },

    tridentByDispatchId(dispatchId) {
      const id = text(dispatchId);
      const found = (Array.isArray(Q.actions) ? Q.actions : [])
        .find((row) => row?.dispatch_id === id);
      return found
        ? clone(found, `womb trident ${id}`)
        : null;
    },

    UForTrident(trident, boundary = "end") {
      if (!trident) return null;
      if (!["start", "end"].includes(boundary)) {
        throw new RangeError("trident boundary must be start or end");
      }
      const value = asObject(trident?.[boundary]?.payload?.U);
      return value === null
        ? null
        : clone(value, `womb trident ${boundary} U`);
    },

    semanticContextForTrident(
      trident,
      boundary = "end",
    ) {
      const boundaryU =
        runtime.UForTrident(
          trident,
          boundary,
        );

      const context =
        semanticContextOf(boundaryU);

      return context === null
        ? null
        : clone(
          context,
          `womb trident ${boundary} semantic context`,
        );
    },

    roleModulationForTrident(trident, boundary = "end") {
      const boundaryU = runtime.UForTrident(trident, boundary);
      const value = asObject(
        boundaryU?.role_mismatch_modulation_info,
      );
      return value === null
        ? null
        : clone(value, `womb trident ${boundary} role modulation`);
    },

    roleReceiptForTrident(trident, boundary = "end") {
      const modulation = runtime.roleModulationForTrident(
        trident,
        boundary,
      );
      const value = asObject(modulation?.receipt);
      return value === null
        ? null
        : clone(value, `womb trident ${boundary} role receipt`);
    },

    semanticErrorsForTrident(trident) {
      const value = trident?.end?.payload?.result?.last_error
        ?? trident?.end?.payload?.U?.last_error
        ?? null;
      return value === null
        ? null
        : clone(value, "womb trident semantic errors");
    },

    dispatchForTrident(trident) {
      if (!trident) return null;
      return clone(
        dispatchSummaryOf(trident),
        "womb trident dispatch",
      );
    },

    dispatchTimeline() {
      return clone(
        dispatchTimelineOf(Q),
        "womb dispatch timeline",
      );
    },

    actionPackets() {
      return clone(
        dispatchTimelineOf(Q)
          .map((row) => row.A),
        "womb action packets",
      );
    },

    isFunkedTrident(trident = null) {
      const target = trident ?? runtime.latestTrident();
      return funkContextOf(target) !== null;
    },

    funkedTridents() {
      return clone(
        (Array.isArray(Q.actions) ? Q.actions : [])
          .filter((row) => funkContextOf(row) !== null),
        "womb funked tridents",
      );
    },

    funkContext(trident = null) {
      const target = trident ?? runtime.latestTrident();
      const value = funkContextOf(target);
      return value === null
        ? null
        : clone(value, "womb funk context");
    },

    funkReceipt(trident = null) {
      const context = runtime.funkContext(trident);
      const receipt = funkReceiptOfContext(context);
      return receipt === null
        ? null
        : clone(receipt, "womb funk receipt");
    },

    nextFunkability(trident = null) {
      const receipt = runtime.funkReceipt(trident);
      const next = nextFunkabilityOfReceipt(receipt);
      return next === null
        ? null
        : clone(next, "womb next funkability");
    },

    funkStatus(trident = null) {
      const target = trident ?? runtime.latestTrident();
      return clone(funkStatusFrom({
        context: funkContextOf(target),
        dispatchId: target?.dispatch_id ?? null,
        localId: target?.local_id ?? null,
        eventSeq: target?.end?.event_seq ?? null,
      }), "womb funk status");
    },

    funkSequence() {
      return clone(
        (Array.isArray(Q.actions) ? Q.actions : [])
          .filter((row) => funkContextOf(row) !== null)
          .map((row) => funkStatusFrom({
            context: funkContextOf(row),
            dispatchId: row?.dispatch_id ?? null,
            localId: row?.local_id ?? null,
            eventSeq: row?.end?.event_seq ?? null,
          })),
        "womb funk sequence",
      );
    },

    thetaOldQ() {
      if (!runtime.isTheta()) return null;
      return clone(
        packet.information.oldQ,
        "womb theta old Q",
      );
    },

    thetaNewQ() {
      if (!runtime.isTheta()) return null;
      return clone(
        packet.information.newQ,
        "womb theta new Q",
      );
    },

    newCanonicalEvents() {
      if (!runtime.isTheta()) return [];
      return clone(
        packet.information.newEvents ?? [],
        "womb theta events",
      );
    },

    thetaPollPage() {
      if (!runtime.isTheta()) return null;
      const page = asObject(packet.information.pollPage);
      return page === null
        ? null
        : clone(page, "womb theta poll page");
    },

    isFunkedControllerEndEvent(event) {
      return funkContextOfEvent(event) !== null;
    },

    funkStatusForEvent(event) {
      const context = funkContextOfEvent(event);
      return clone(funkStatusFrom({
        context,
        dispatchId: event?.dispatch_id ?? null,
        localId: null,
        eventSeq: event?.event_seq ?? null,
      }), "womb funk event status");
    },

    epsOldQ() {
      if (!runtime.isEpsilon()) return null;
      return clone(
        packet.information.oldQ,
        "womb eps old Q",
      );
    },

    epsNewQ() {
      if (!runtime.isEpsilon()) return null;
      return clone(
        packet.information.newQ,
        "womb eps new Q",
      );
    },

    epsPollPage() {
      if (!runtime.isEpsilon()) return null;
      const page = asObject(packet.information.pollPage);
      return page === null
        ? null
        : clone(page, "womb eps poll page");
    },

    epsPage() {
      return runtime.epsPollPage();
    },

    epsRows() {
      return clone(
        Array.isArray(Q.eps_rows) ? Q.eps_rows : [],
        "womb eps rows",
      );
    },

    epsNewRows() {
      if (!runtime.isEpsilon()) return [];
      return clone(
        packet.information.newRows ?? [],
        "womb eps new rows",
      );
    },

    epsCursor() {
      return Number.isInteger(Q.eps_cursor) ? Q.eps_cursor : 0;
    },

    epsHead() {
      if (
        runtime.isEpsilon()
        && Number.isInteger(packet.information.pollPage?.eps_head)
      ) {
        return packet.information.pollPage.eps_head;
      }
      return runtime.epsCursor();
    },

    epsRowsForRequest(requestId) {
      const id = text(requestId);
      if (!id) return [];
      return clone(
        (Array.isArray(Q.eps_rows) ? Q.eps_rows : [])
          .filter((row) => text(row?.request_id) === id),
        `womb eps rows for request ${id}`,
      );
    },

    epsRowsForTrident(tridentDispatchId) {
      const id = text(tridentDispatchId);
      if (!id) return [];
      return clone(
        (Array.isArray(Q.eps_rows) ? Q.eps_rows : [])
          .filter((row) => text(row?.trident_dispatch_id) === id),
        `womb eps rows for trident ${id}`,
      );
    },

    epsRowsForLatestTrident() {
      const target = runtime.openTrident() ?? runtime.latestTrident();
      const id = text(target?.dispatch_id);
      if (!id) return [];
      return runtime.epsRowsForTrident(id);
    },

    epsRowsForDatum(datumId) {
      const id = text(datumId);
      if (!id) return [];
      return clone(
        (Array.isArray(Q.eps_rows) ? Q.eps_rows : [])
          .filter((row) => !row?.obfuscated && text(row?.datum_id) === id),
        `womb eps rows for datum ${id}`,
      );
    },
  };

  return Object.freeze(runtime);
}

export class KeyErrorForWombDatum extends RangeError {
  constructor(datumId) {
    super(`datum is not present on the current projected span: ${datumId}`);
    this.name = "KeyErrorForWombDatum";
    this.datum_id = datumId;
  }
}

export class ObfuscatedWombDatumError extends RangeError {
  constructor(datumId) {
    super(`datum is role-obfuscated in the current projection: ${datumId}`);
    this.name = "ObfuscatedWombDatumError";
    this.datum_id = datumId;
  }
}

/**
 * Copy/paste opinionation womb.
 *
 * The returned X is the only state mutation this heartbeat performs.
 * Substrate callbacks installed here may capture `W.loopback` and use its
 * guarded API later when the user/device acts.
 */
export async function womb(packet, loopback) {
  const W = createWombRuntime(packet, loopback);

  // Example:
  // if (W.isTheta()) renderCurrentSubstrate(W);
  // if (W.isEpsilon()) renderProgressSubstrate(W);
  //
  // A DOM/native event handler installed by the render function may later call:
  //   W.loopback.validateDispatch(A)
  //   await W.loopback.dispatch(A)
  //   await W.loopback.writeX(...)
  //
  // During this drink invocation, commit X by returning it below rather than
  // awaiting loopback.writeX(), because this callback itself is the active
  // ThinkumentJS Q/X commit.

  return {
    X: W.X(),
  };
}

export const opinionation = Object.freeze({
  kind: "thinkument_front_opinionation_v2",
  initialX: {},
  drink: womb,
});

export default opinionation;

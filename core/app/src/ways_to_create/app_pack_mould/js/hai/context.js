const asObject = (value) => (
  value !== null
  && typeof value === "object"
  && !Array.isArray(value)
    ? value
    : null
);

const clone = (value) => structuredClone(value);
const own = (value, key) => (
  Object.prototype.hasOwnProperty.call(value, key)
);
const text = (value) => String(value ?? "").trim();

const isObfuscated = (row) => (
  row?.kind === "role_mismatch_obfuscated_datum_v1"
  || row?.role_mismatch_obfuscated === true
);

const scopeOf = (U) => U ? {
  form_id: U.form_id ?? null,
  app_form_id: U.app_form_id ?? null,
  frame_id: U.current_frame_id ?? null,
  frame_name: U.current_frame_name ?? null,
  span_id:
    U.current_span_id
    ?? U.current_span
    ?? null,
} : null;

const sameScope = (left, right) => (
  JSON.stringify(scopeOf(left))
  === JSON.stringify(scopeOf(right))
);

const rowsOf = (U) => (
  Array.isArray(U?.datum_states_on_this_span)
    ? U.datum_states_on_this_span.filter(
      (row) => asObject(row),
    )
    : []
);

const activeIdsOf = (U) => {
  if (
    !U
    || !own(U, "datum_widgets_on_this_span")
  ) {
    return null;
  }

  return Array.isArray(
    U.datum_widgets_on_this_span,
  )
    ? U.datum_widgets_on_this_span
      .map(text)
      .filter(Boolean)
    : [];
};

const boundaryRows = (Q) => {
  const rows = [];

  for (
    const T
    of Array.isArray(Q?.actions)
      ? Q.actions
      : []
  ) {
    const startU = asObject(
      T?.start?.payload?.U,
    );
    const endU = asObject(
      T?.end?.payload?.U,
    );

    if (
      startU
      && Number.isInteger(
        T?.start?.event_seq,
      )
    ) {
      rows.push({
        cursor: T.start.event_seq,
        boundary: "start",
        U: startU,
        T,
      });
    }

    if (
      endU
      && Number.isInteger(
        T?.end?.event_seq,
      )
    ) {
      rows.push({
        cursor: T.end.event_seq,
        boundary: "end",
        U: endU,
        T,
      });
    }
  }

  const open = asObject(Q?.open_action);
  const openU = asObject(
    open?.start?.payload?.U,
  );

  if (
    openU
    && Number.isInteger(
      open?.start?.event_seq,
    )
  ) {
    rows.push({
      cursor: open.start.event_seq,
      boundary: "start",
      U: openU,
      T: open,
    });
  }

  return rows.sort(
    (a, b) => a.cursor - b.cursor,
  );
};

const historicalView = (Q, requested) => {
  if (requested === -1) {
    return {
      U: asObject(Q?.latest_U),
      requested_cursor: -1,
      resolved_cursor: Q?.cursor ?? 0,
      viewing_latest: true,
      retention_limited: false,
      boundary: "latest",
    };
  }

  const boundaries = boundaryRows(Q);
  let selected = null;

  for (const row of boundaries) {
    if (row.cursor <= requested) {
      selected = row;
    } else {
      break;
    }
  }

  if (
    selected === null
    && boundaries.length
  ) {
    selected = boundaries[0];
  }

  return {
    U: selected?.U ?? asObject(Q?.latest_U),
    requested_cursor: requested,
    resolved_cursor:
      selected?.cursor
      ?? Q?.cursor
      ?? 0,
    viewing_latest: false,
    retention_limited: Boolean(
      selected
      && selected.cursor > requested
    ),
    boundary:
      selected?.boundary
      ?? "latest_fallback",
  };
};

const authoredArgs = (row) => {
  const source = (
    asObject(row?.args)
    ?? asObject(row?.shell?.args)
    ?? {}
  );
  const out = { ...source };
  delete out.__kernel;
  return out;
};

const microsOf = (row) => {
  for (
    const candidate
    of [
      row?.micros,
      row?.shell?.micros,
    ]
  ) {
    if (Array.isArray(candidate)) {
      return candidate;
    }
  }
  return [];
};

const runtimeStateOf = (row) => (
  asObject(
    row?.lifecycle?.runtime?.state,
  ) ?? {}
);

const staticAccess = (
  row,
  activeIds,
) => ({
  datum_id: text(
    row?.datum_id ?? row?.id,
  ),
  present_on_span: true,
  readable: !isObfuscated(row),
  pending:
    row?.is_pending === true,
  enabled:
    row?.enabled !== false,
  editable_membership:
    Array.isArray(activeIds)
      ? activeIds.includes(
        text(
          row?.datum_id ?? row?.id,
        ),
      )
      : false,
  role_assignment: null,
  write: false,
  write_validation: null,
  historical_read_only: true,
});

const widgetModel = ({
  row,
  activeIds,
  latest,
  W,
}) => {
  const datumId = text(
    row?.datum_id ?? row?.id,
  );
  const readable = !isObfuscated(row);
  const args = readable
    ? authoredArgs(row)
    : {};

  const access = (
    latest
    && datumId
  )
    ? W.accessForWidget(datumId)
    : staticAccess(
      row,
      activeIds,
    );

  return {
    datum_id: datumId,
    readable,
    active:
      Array.isArray(activeIds)
        ? activeIds.includes(datumId)
        : false,
    authoritative:
      row?.is_authoritative === true,
    pending:
      row?.is_pending === true,
    enabled:
      row?.enabled !== false,
    // Registered implementation identity from the projected lifecycle, independent of render keys.
    widget_type: readable ? text(row?.lifecycle?.widget ?? row?.shell?.lifecycle?.widget) || null : null,
    renderer_key:
      readable
        ? text(
          args.hai_renderer,
        ) || null
        : null,
    args: clone(args),
    shell:
      readable
        ? clone(
          asObject(row?.shell)
          ?? null,
        )
        : null,
    micros:
      readable
        ? clone(microsOf(row))
        : [],
    runtime_state:
      readable
        ? clone(
          runtimeStateOf(row),
        )
        : {},
    fill:
      readable
      && own(row, "fill")
        ? clone(row.fill)
        : null,
    has_fill:
      readable
        ? Boolean(row?.has_fill)
        : false,
    semantic_validation:
      readable
        ? clone(
          asObject(
            row?.semantic_validation,
          ) ?? null,
        )
        : null,
    access: clone(access),
    raw: clone(row),
  };
};

const appPackSelectionFromMetadata = (
  sessionMetadata,
) => {
  const pocket = asObject(
    sessionMetadata?.app_pack_mould,
  );

  return {
    id:
      text(pocket?.app_pack)
      || null,
    args: clone(
      asObject(
        pocket?.app_args,
      ) ?? {},
    ),
  };
};

const appPackSelection = ({
  launchSessionMetadata,
  runtimeSessionMetadata,
  defaultAppPackId,
}) => {
  const launch = (
    appPackSelectionFromMetadata(
      asObject(
        launchSessionMetadata,
      ) ?? {},
    )
  );

  const runtime = (
    appPackSelectionFromMetadata(
      asObject(
        runtimeSessionMetadata,
      ) ?? {},
    )
  );

  if (
    launch.id !== null
    && runtime.id !== null
    && launch.id !== runtime.id
  ) {
    throw new Error(
      "HAI app-pack selection disagrees between "
      + "launch session metadata "
      + `(${launch.id}) and runtime session metadata `
      + `(${runtime.id})`,
    );
  }

  return launch.id !== null
    ? launch
    : runtime.id !== null
      ? runtime
      : { id: defaultAppPackId, args: {} };
};

const thetaContext = (W) => (
  W.isTheta()
    ? {
      old_Q: W.thetaOldQ(),
      new_Q: W.thetaNewQ(),
      new_events:
        W.newCanonicalEvents(),
      poll_page:
        W.thetaPollPage(),
    }
    : null
);

const epsilonContext = (W) => {
  if (!W.isEpsilon()) return null;
  const page = typeof W.epsPage === "function"
    ? W.epsPage()
    : typeof W.epsPollPage === "function"
      ? W.epsPollPage()
      : null;
  return {
    rows:
      W.epsRows(),
    new_rows:
      W.epsNewRows(),
    page,
    cursor:
      W.epsCursor(),
    head:
      W.epsHead(),
    next_after_seq:
      page?.next_after_seq
      ?? W.epsCursor(),
  };
};

/*
 * The stable, deliberately redundant higher-app data blanket.
 *
 * `view` below may point at a historical boundary. `womb` always describes
 * latest ThinkumentJS/Womb truth for this heartbeat. The expensive queue
 * projections are computed once in buildHaiRenderContext and shared between
 * `queue` and `womb`; app packs therefore get the same public contract without
 * paying to rebuild timelines/action packets twice per heartbeat.
 */
const wombBlanket = (
  W,
  derived,
) => ({
  information:
    W.information(),
  current_U:
    W.U(),
  runtime_kind:
    W.runtimeKind(),
  scope:
    W.currentScope(),
  step:
    W.currentStep(),
  semantic_context:
    W.semanticContext(),
  session_metadata:
    W.sessionMetadata(),
  provenance:
    W.provenance(),
  multiframespec:
    W.multiframespec(),
  last_error:
    W.lastError(),
  access_table:
    W.accessTable(),
  role_modulation_info:
    W.roleModulationInfo(),
  role_modulation_receipt:
    W.roleModulationReceipt(),
  role_read_projection:
    derived.role_projection,
  tridents:
    derived.tridents,
  open_trident:
    derived.open_trident,
  latest_trident:
    derived.latest_trident,
  dispatch_timeline:
    derived.dispatch_timeline,
  action_packets:
    derived.action_packets,
  latest_semantic_errors:
    derived.latest_trident === null
      ? null
      : W.semanticErrorsForTrident(
        derived.latest_trident,
      ),
  latest_role_receipt:
    derived.latest_trident === null
      ? null
      : W.roleReceiptForTrident(
        derived.latest_trident,
      ),
  funk_context:
    W.funkContext(),
  funk_receipt:
    W.funkReceipt(),
  next_funkability:
    W.nextFunkability(),
  funk_status:
    derived.funk_status,
  funk_sequence:
    W.funkSequence(),
});

// Lazily requested history projection: ordinary packs pay no appearance-history cost.
const widgetAppearances = (Q, view, currentWidgets) => {
  const spans = new Map();
  const currentKey = JSON.stringify(scopeOf(view.U));
  const candidates = boundaryRows(Q).filter(row => row.cursor <= view.resolved_cursor);
  if (view.U) candidates.push({ U:view.U, cursor:view.resolved_cursor });
  for (const {U, cursor} of candidates) {
    if (!rowsOf(U).length) continue;
    const scope = scopeOf(U);
    const id = JSON.stringify(scope);
    const current = id === currentKey;
    spans.set(id, Object.freeze({
      id, scope:clone(scope), step:clone(asObject(U.step)), cursor, current,
      widgets:current ? currentWidgets : Object.freeze(rowsOf(U).map(row => widgetModel({
        row, activeIds:activeIdsOf(U), latest:false, W:null,
      }))),
    }));
  }
  return Object.freeze([...spans.values()]);
};

export function buildHaiRenderContext({
  W,
  haiState,
  sessionMetadata = null,
  defaultAppPackId = "example_notes",
}) {
  const Q = W.Q();
  const view = historicalView(
    Q,
    haiState.page_being_viewed,
  );
  const U = view.U;
  const activeIds = activeIdsOf(U);
  const latest = view.viewing_latest;

  const runtimeSessionMetadata =
    W.sessionMetadata();

  const widgets = rowsOf(U).map(
    (row) => widgetModel({
      row,
      activeIds,
      latest,
      W,
    }),
  );

  let appearances = null;

  const derived = Object.freeze({
    tridents:
      W.tridents(),
    open_trident:
      W.openTrident(),
    latest_trident:
      W.latestTrident(),
    dispatch_timeline:
      W.dispatchTimeline(),
    action_packets:
      W.actionPackets(),
    role_projection:
      W.roleReadProjection(),
    funk_status:
      W.funkStatus(),
  });

  const womb = Object.freeze(
    wombBlanket(
      W,
      derived,
    ),
  );

  return Object.freeze({
    kind:
      "app_pack_mould_render_context_v1",

    heartbeat: Object.freeze({
      kind:
        W.heartbeat(),
      trigger:
        W.trigger(),
      canonical_cursor:
        Q.cursor,
      eps_cursor:
        Q.eps_cursor ?? 0,
      eps_head:
        Q.eps_head ?? 0,
    }),

    session:
      Object.freeze(
        W.session(),
      ),

    app_pack:
      Object.freeze(
        appPackSelection({
          launchSessionMetadata:
            sessionMetadata,
          runtimeSessionMetadata,
          defaultAppPackId,
        }),
      ),

    state:
      Object.freeze(
        clone(haiState),
      ),

    view: Object.freeze({
      get widget_appearances() {
        appearances ??= widgetAppearances(Q, view, widgets);
        return appearances;
      },
      requested_cursor:
        view.requested_cursor,
      resolved_cursor:
        view.resolved_cursor,
      viewing_latest:
        view.viewing_latest,
      retention_limited:
        view.retention_limited,
      boundary:
        view.boundary,
      runtime_kind:
        U?.kind ?? null,
      scope:
        scopeOf(U),
      step:
        clone(
          asObject(U?.step)
          ?? null,
        ),
      U:
        U === null
          ? null
          : clone(U),
      active_widget_ids:
        clone(activeIds),
      widgets:
        Object.freeze(
          widgets,
        ),
      last_error:
        U?.last_error == null
          ? null
          : clone(
            U.last_error,
          ),
      role_modulation:
        clone(
          asObject(
            U?.role_mismatch_modulation_info,
          ) ?? null,
        ),
    }),

    queue: Object.freeze({
      Q,
      timeline:
        derived.dispatch_timeline,
      action_packets:
        derived.action_packets,
      latest_trident:
        derived.latest_trident,
      open_trident:
        derived.open_trident,
      funk_status:
        derived.funk_status,
      role_projection:
        derived.role_projection,
    }),

    womb,
    theta:
      thetaContext(W),
    epsilon:
      epsilonContext(W),
  });
}

const idsOfRows = (U) => (
  rowsOf(U).map(
    (row) => text(
      row?.datum_id ?? row?.id,
    ),
  )
);

const rowMap = (U) => (
  new Map(
    rowsOf(U).map(
      (row) => [
        text(
          row?.datum_id ?? row?.id,
        ),
        row,
      ],
    ),
  )
);

export function planThetaRefresh(ctx) {
  if (!ctx.theta) return null;

  if (!ctx.view.viewing_latest) {
    return {
      kind: "none",
      changed_widget_ids: [],
    };
  }

  const oldU = asObject(
    ctx.theta.old_Q?.latest_U,
  );
  const newU = asObject(
    ctx.theta.new_Q?.latest_U,
  );

  if (
    !oldU
    || !newU
    || !sameScope(oldU, newU)
  ) {
    return {
      kind: "stage",
      changed_widget_ids:
        ctx.view.widgets.map(
          (row) => row.datum_id,
        ),
    };
  }

  const oldIds = idsOfRows(oldU);
  const newIds = idsOfRows(newU);

  if (
    JSON.stringify(oldIds)
    !== JSON.stringify(newIds)
  ) {
    return {
      kind: "stage",
      changed_widget_ids: newIds,
    };
  }

  if (
    JSON.stringify(
      activeIdsOf(oldU),
    )
    !== JSON.stringify(
      activeIdsOf(newU),
    )
  ) {
    return {
      kind: "stage",
      changed_widget_ids: newIds,
    };
  }

  const oldById = rowMap(oldU);
  const newById = rowMap(newU);

  const changed = newIds.filter(
    (id) => (
      JSON.stringify(
        oldById.get(id),
      )
      !== JSON.stringify(
        newById.get(id),
      )
    ),
  );

  return {
    kind:
      changed.length
        ? "widgets"
        : "none",
    changed_widget_ids:
      changed,
  };
}

export const epsChannelOf = (
  row,
) => (
  text(row?.channel)
  || "unknown"
);
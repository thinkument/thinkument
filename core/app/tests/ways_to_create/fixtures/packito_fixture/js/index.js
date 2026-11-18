const asObject = (value) => (
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value
    : null
);

const text = (value) => String(value ?? "");
const pretty = (value) => JSON.stringify(value, null, 2);
const MAX_RENDERED_NOTIFICATIONS = 32;
export const PACKITO_INSPECTOR_CONTEXT_PROPERTY = "__thinkumentPackitoContextV1";

/*
 * Packito is the pedagogical pack, so it deliberately leaves durable DOM
 * evidence that every overridable HAI callable really ran. These markers are
 * Packito-only teaching/test hooks, not part of the generic HAI contract.
 */
export const PACKITO_CALLABLE_PROOF_ATTRIBUTES = Object.freeze({
  notification: "data-packito-callable-notification-count",
  widget: "data-packito-callable-widget",
  widgetNotification: "data-packito-callable-widget-notification-count",
  widgetsContainer: "data-packito-callable-widgets-container",
  outers: "data-packito-callable-outers-count",
  page: "data-packito-callable-page-count",
  noReadWidget: "data-packito-callable-no-read",
  noWriteWidget: "data-packito-callable-no-write",
});

const element = (documentRef, tag, attrs = {}, textContent = null) => {
  const node = documentRef.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    node.setAttribute(name, String(value));
  }
  if (textContent !== null) node.textContent = String(textContent);
  return node;
};

const integerAttribute = (node, name) => {
  const raw = node?.getAttribute?.(name);
  const parsed = Number.parseInt(String(raw ?? "0"), 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
};

const bumpAttribute = (node, name) => {
  if (!node?.setAttribute) return 0;
  const next = integerAttribute(node, name) + 1;
  node.setAttribute(name, String(next));
  return next;
};

const findHaiShell = (node) => {
  let current = node ?? null;
  while (current) {
    if (current.getAttribute?.("data-thinkument-hai") !== null) return current;
    current = current.parentElement ?? current.parentNode ?? null;
  }
  return null;
};

const markShellCallable = (node, callableName) => {
  const attribute = PACKITO_CALLABLE_PROOF_ATTRIBUTES[callableName];
  if (!attribute) return 0;
  const shell = findHaiShell(node);
  return shell ? bumpAttribute(shell, attribute) : 0;
};

const microNameOf = (micro) => String(micro?.name ?? micro?.id ?? "").trim();

const editorFor = ({ documentRef, widget, micro }) => {
  const name = microNameOf(micro);
  const row = element(documentRef, "label", {
    class: "packito-micro",
    "data-packito-micro": `${widget.datum_id}.${name}`,
  });
  const include = element(documentRef, "input", {
    type: "checkbox",
    "data-hai-micro-include": "1",
    "data-datum-id": widget.datum_id,
    "data-micro-name": name,
    "aria-label": `include ${widget.datum_id}.${name}`,
  });
  include.type = "checkbox";

  const title = element(
    documentRef,
    "span",
    { class: "packito-micro-label" },
    micro?.label || name,
  );
  const editor = element(documentRef, "textarea", {
    "data-hai-micro-value": "1",
    "data-datum-id": widget.datum_id,
    "data-micro-name": name,
    "aria-label": `${widget.datum_id}.${name} JSON literal`,
  });
  const fill = asObject(widget.fill) ?? {};
  editor.value = Object.prototype.hasOwnProperty.call(fill, name)
    ? pretty(fill[name])
    : "null";
  editor.disabled = !widget.access.write;
  include.disabled = !widget.access.write;

  const meta = element(
    documentRef,
    "small",
    { class: "packito-micro-meta" },
    `${micro?.type || "unknown"}${micro?.required ? " / required" : ""}`,
  );
  row.append(include, title, editor, meta);
  return row;
};

const cardShell = ({ documentRef, widget, renderer }) => {
  const card = element(documentRef, "article", {
    class: "hai-widget packito-widget",
    "data-hai-widget-card": "1",
    "data-hai-widget-id": widget.datum_id,
    "data-hai-renderer": renderer,
    "data-packito-widget": renderer,
  });
  const heading = element(
    documentRef,
    "h3",
    { class: "packito-widget-title" },
    widget.args?.prompt || widget.args?.label || widget.shell?.title || widget.datum_id,
  );
  const badges = element(documentRef, "div", { class: "packito-badges" });
  for (const [label, value] of [
    ["active", widget.active],
    ["authoritative", widget.authoritative],
    ["write", widget.access?.write],
  ]) {
    badges.append(element(documentRef, "span", {
      class: "packito-badge",
      "data-packito-badge": label,
    }, `${label}:${String(value)}`));
  }
  card.append(heading, badges);
  return card;
};

const appendMicroEditors = ({ documentRef, card, widget }) => {
  for (const micro of widget.micros ?? []) {
    const name = microNameOf(micro);
    if (!name) continue;
    card.append(editorFor({ documentRef, widget, micro }));
  }
};

const appendRuntime = ({ documentRef, card, widget }) => {
  const details = element(documentRef, "details", {
    "data-packito-widget-runtime": widget.datum_id,
  });
  details.append(
    element(documentRef, "summary", {}, "Backend runtime state"),
    element(documentRef, "pre", {}, pretty({
      args: widget.args,
      runtime_state: widget.runtime_state,
      fill: widget.fill,
      semantic_validation: widget.semantic_validation,
      access: widget.access,
    })),
  );
  card.append(details);
};

/* Shared implementation used by dedicated Packito renderers. This is not the
 * HAI `callables.widget` fallback by itself. */
const genericRenderer = ({ documentRef, widget }) => {
  const card = cardShell({
    documentRef,
    widget,
    renderer: widget.renderer_key || "packito.generic.v1",
  });
  appendMicroEditors({ documentRef, card, widget });
  appendRuntime({ documentRef, card, widget });
  return card;
};

/* The actual overridable HAI `widget` callable. It is exercised only when a
 * readable+writable widget has no renderer claimed by widgetRenderers. */
const renderWidgetFallback = ({ documentRef, widget }) => {
  const card = genericRenderer({ documentRef, widget });
  card.setAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.widget, "1");
  return card;
};

const renderChoice = ({ documentRef, widget, api }) => {
  const card = genericRenderer({ documentRef, widget });
  card.setAttribute("data-packito-choice", "1");

  if (widget.access.write) {
    const refresh = element(documentRef, "button", {
      type: "button",
      "data-packito-refresh": widget.datum_id,
    }, "Signal: refresh");
    refresh.addEventListener("click", async () => {
      const A = {
        action: "STEP",
        userFill: {},
        userSignal: {
          datum_id: widget.datum_id,
          kind: "refresh",
          info: { source: "packito renderer" },
        },
      };
      const receipt = api.validateDispatch(A);
      api.presentLocalReceipt(receipt);
      if (!receipt.ok) return;
      api.presentDispatchResult(await api.dispatch(A));
    });
    card.append(refresh);
  }
  return card;
};

const renderBoard = ({ documentRef, widget }) => {
  const card = genericRenderer({ documentRef, widget });
  card.setAttribute("data-packito-board", "1");
  card.prepend(element(
    documentRef,
    "p",
    { "data-packito-board-total": "1" },
    `total=${widget.runtime_state?.total ?? 0} ticks=${widget.runtime_state?.ticks ?? 0}`,
  ));
  return card;
};

const renderHistory = ({ documentRef, widget }) => {
  const card = genericRenderer({ documentRef, widget });
  card.setAttribute("data-packito-history-widget", "1");
  card.prepend(element(
    documentRef,
    "pre",
    { "data-packito-wire-index": "1" },
    pretty(widget.runtime_state?.wire_index ?? {}),
  ));
  return card;
};

const renderRoleGate = ({ documentRef, widget }) => {
  const card = genericRenderer({ documentRef, widget });
  card.setAttribute("data-packito-role-gate", "1");
  return card;
};

const renderPuzzleSeed = ({ documentRef, widget }) => {
  const card = genericRenderer({ documentRef, widget });
  card.setAttribute("data-packito-puzzle-seed", "1");
  return card;
};

const renderPuzzleAnswer = ({ documentRef, widget }) => {
  const card = genericRenderer({ documentRef, widget });
  card.setAttribute("data-packito-puzzle-answer", "1");
  return card;
};

const trimNotifications = (container) => {
  const nodes = Array.from(
    container?.querySelectorAll?.("[data-packito-notification-entry]") ?? [],
  );
  for (const node of nodes.slice(0, Math.max(0, nodes.length - MAX_RENDERED_NOTIFICATIONS))) {
    node.remove();
  }
};

const appendNotification = (container, node) => {
  node.setAttribute("data-packito-notification-entry", "1");
  container.append(node);
  trimNotifications(container);
};

const renderGlobalNotification = ({ documentRef, container, row, channel }) => {
  markShellCallable(container, "notification");
  appendNotification(container, element(
    documentRef,
    "div",
    {
      class: "packito-notification packito-notification-global",
      "data-hai-notification": channel,
      "data-packito-global-notice": channel,
    },
    `${channel}: ${row?.payload?.message?.text ?? row?.payload?.phase ?? "event"}`,
  ));
};

const renderWidgetNotification = ({ documentRef, container, row, channel }) => {
  markShellCallable(container, "widgetNotification");
  appendNotification(container, element(
    documentRef,
    "div",
    {
      class: "packito-notification packito-notification-widget",
      "data-hai-widget-notification": channel,
      "data-packito-widget-notice": channel,
    },
    `${channel}: ${row?.payload?.phase ?? row?.payload?.message?.text ?? "event"}`,
  ));
};

const customMessageRoute = ({ documentRef, shell, row, channel }) => {
  bumpAttribute(shell, "data-packito-custom-route-count");
  const host = shell.querySelector("[data-hai-global-notifications]");
  if (!host) return;
  appendNotification(host, element(
    documentRef,
    "div",
    {
      class: "packito-notification packito-notification-custom",
      "data-packito-custom-notice": channel,
    },
    `${channel}: ${pretty(row?.payload ?? {})}`,
  ));
};

const renderNoRead = ({ documentRef, widget, ctx }) => {
  const card = element(documentRef, "article", {
    class: "hai-widget packito-widget packito-obfuscated",
    "data-hai-widget-card": "1",
    "data-hai-widget-id": widget.datum_id,
    "data-hai-no-read": "1",
    "data-packito-no-read": widget.datum_id,
    [PACKITO_CALLABLE_PROOF_ATTRIBUTES.noReadWidget]: "1",
  });
  card.append(
    element(documentRef, "h3", {}, widget.datum_id),
    element(documentRef, "p", {}, `Hidden from role ${ctx.session.role ?? "roleless"}`),
  );
  return card;
};

const renderNoWrite = ({ documentRef, widget, ctx }) => {
  const card = element(documentRef, "article", {
    class: "hai-widget packito-widget packito-readonly",
    "data-hai-widget-card": "1",
    "data-hai-widget-id": widget.datum_id,
    "data-hai-no-write": "1",
    "data-packito-no-write": widget.datum_id,
    [PACKITO_CALLABLE_PROOF_ATTRIBUTES.noWriteWidget]: "1",
  });
  card.append(
    element(documentRef, "h3", {}, widget.args?.prompt || widget.shell?.title || widget.datum_id),
    element(documentRef, "p", {}, ctx.view.viewing_latest
      ? "Readable here, but this role cannot write it."
      : "Historical pages are intentionally read-only."),
    element(documentRef, "pre", { "data-packito-readonly-state": "1" }, pretty({
      fill: widget.fill,
      runtime_state: widget.runtime_state,
      access: widget.access,
    })),
  );
  return card;
};

const renderWidgetsContainer = ({ documentRef, container, widgets, renderWidgetCard, ctx }) => {
  container.setAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.widgetsContainer, "1");
  container.append(element(
    documentRef,
    "header",
    { class: "packito-stage-heading", "data-packito-stage-heading": "1" },
    `${ctx.view.step?.title ?? "Current span"} / ${widgets.length} projected widget(s)`,
  ));
  for (const widget of widgets) container.append(renderWidgetCard(widget));
};

const renderPage = ({ shell, ctx, renderDefaultPage }) => {
  bumpAttribute(shell, PACKITO_CALLABLE_PROOF_ATTRIBUTES.page);
  shell.setAttribute("data-packito-heartbeat", ctx.heartbeat.kind);
  shell.setAttribute("data-packito-runtime-kind", ctx.view.runtime_kind || "none");
  return renderDefaultPage();
};

const renderOuters = ({ shell, ctx, renderDefaultOuters }) => {
  bumpAttribute(shell, PACKITO_CALLABLE_PROOF_ATTRIBUTES.outers);
  shell.setAttribute("data-packito-viewing-latest", String(ctx.view.viewing_latest));
  return renderDefaultOuters();
};

const controlButton = (documentRef, label, attrs, handler) => {
  const button = element(documentRef, "button", { type: "button", ...attrs }, label);
  button.addEventListener("click", handler);
  return button;
};

const renderControls = ({ documentRef, container, api, reason }) => {
  bumpAttribute(container, "data-packito-outer-controls-count");
  if (reason?.epsilon) bumpAttribute(container, "data-packito-outer-controls-epsilon-count");
  if (reason?.new_page) bumpAttribute(container, "data-packito-outer-controls-new-page-count");
  if (reason?.widget_refresh) bumpAttribute(container, "data-packito-outer-controls-widget-refresh-count");

  const state = api.readHaiState();
  const wrap = element(documentRef, "section", {
    class: "packito-controls",
    "data-packito-controls": "1",
  });
  wrap.append(
    element(documentRef, "strong", {}, "HAI lifecycle controls"),
    element(documentRef, "span", {
      "data-packito-state-summary": "1",
    }, `page=${state.page_being_viewed} snap=${state.snap_page_on_new_trident} eps=${state.silence_eps} theta=${state.silence_theta}`),
    controlButton(
      documentRef,
      "Latest page",
      { "data-packito-control": "latest" },
      () => api.setPageNumber(-1),
    ),
    controlButton(
      documentRef,
      "Oldest retained page",
      { "data-packito-control": "history" },
      () => api.setPageNumber(0),
    ),
    controlButton(
      documentRef,
      `Snap: ${state.snap_page_on_new_trident ? "on" : "off"}`,
      { "data-packito-control": "snap" },
      () => api.setSnapPageOnNewTrident(!api.getSnapPageOnNewTrident()),
    ),
    controlButton(
      documentRef,
      `Epsilon: ${state.silence_eps ? "silent" : "live"}`,
      { "data-packito-control": "epsilon" },
      () => api.setSilenceEps(!api.getSilenceEps()),
    ),
    controlButton(
      documentRef,
      `Theta: ${state.silence_theta ? "silent" : "live"}`,
      { "data-packito-control": "theta" },
      () => api.setSilenceTheta(!api.getSilenceTheta()),
    ),
  );
  container.replaceChildren(wrap);
};

const inspectorPayload = (ctx) => ({
  contract: "app_pack_mould_render_context_v1",
  heartbeat: ctx.heartbeat,
  session: ctx.session,
  app_pack: ctx.app_pack,
  hai_state: ctx.state,
  historical_or_latest_view: {
    requested_cursor: ctx.view.requested_cursor,
    resolved_cursor: ctx.view.resolved_cursor,
    viewing_latest: ctx.view.viewing_latest,
    retention_limited: ctx.view.retention_limited,
    runtime_kind: ctx.view.runtime_kind,
    scope: ctx.view.scope,
    step: ctx.view.step,
    active_widget_ids: ctx.view.active_widget_ids,
    widgets: ctx.view.widgets.map((widget) => ({
      datum_id: widget.datum_id,
      readable: widget.readable,
      active: widget.active,
      authoritative: widget.authoritative,
      pending: widget.pending,
      renderer_key: widget.renderer_key,
      args: widget.args,
      shell: widget.shell,
      micros: widget.micros,
      runtime_state: widget.runtime_state,
      fill: widget.fill,
      semantic_validation: widget.semantic_validation,
      access: widget.access,
    })),
  },
  queue: ctx.queue,
  womb: ctx.womb,
  theta: ctx.theta,
  epsilon: ctx.epsilon,
});

const inspectorSummary = (ctx) => ({
  contract: ctx.kind,
  heartbeat: ctx.heartbeat.kind,
  cursor: ctx.heartbeat.canonical_cursor,
  role: ctx.session.role,
  app_pack: ctx.app_pack.id,
  runtime_kind: ctx.view.runtime_kind,
  viewing_latest: ctx.view.viewing_latest,
  active_widget_ids: ctx.view.active_widget_ids,
  widget_count: ctx.view.widgets.length,
  action_count: ctx.queue.action_packets.length,
  open_trident: ctx.queue.open_trident !== null,
  role_receipt_kind: ctx.womb.role_modulation_receipt?.kind ?? null,
  latest_semantic_errors_present: ctx.womb.latest_semantic_errors !== null,
  funk_receipt_kind: ctx.womb.funk_receipt?.kind ?? null,
  next_funkability: ctx.womb.next_funkability ?? null,
});

const materializeInspector = (container) => {
  const ctx = container?.[PACKITO_INSPECTOR_CONTEXT_PROPERTY];
  const pre = container?.querySelector?.("[data-packito-inspector-json]");
  if (!ctx || !pre) return;
  pre.textContent = pretty(inspectorPayload(ctx));
  pre.setAttribute(
    "data-packito-materialized-cursor",
    String(ctx.heartbeat.canonical_cursor ?? ""),
  );
};

const renderInspector = ({ documentRef, container, ctx, reason }) => {
  bumpAttribute(container, "data-packito-outer-inspector-count");
  if (reason?.epsilon) bumpAttribute(container, "data-packito-outer-inspector-epsilon-count");
  if (reason?.new_page) bumpAttribute(container, "data-packito-outer-inspector-new-page-count");
  if (reason?.widget_refresh) bumpAttribute(container, "data-packito-outer-inspector-widget-refresh-count");

  if (ctx.app_pack.args?.show_inspector === false) {
    delete container[PACKITO_INSPECTOR_CONTEXT_PROPERTY];
    container.replaceChildren();
    return;
  }

  // Keep the complete current context live in-browser. This is the pedagogical
  // data blanket and the programmatic inspection seam. Do not stringify it on
  // every theta/epsilon heartbeat: queue/history growth would make the visual
  // inspector quadratic in work while teaching nothing new.
  container[PACKITO_INSPECTOR_CONTEXT_PROPERTY] = ctx;

  let details = container.querySelector("[data-packito-inspector]");
  if (!details) {
    details = element(documentRef, "details", {
      class: "packito-inspector",
      "data-packito-inspector": "1",
    });
    const summary = element(documentRef, "summary", {}, "Complete HAI / Womb data blanket");
    const compact = element(documentRef, "pre", {
      "data-packito-inspector-summary": "1",
    });
    const full = element(documentRef, "pre", {
      "data-packito-inspector-json": "1",
    }, "Open this inspector to materialize the full current blanket.");
    details.append(summary, compact, full);
    details.addEventListener("toggle", () => {
      if (details.open) materializeInspector(container);
    });
    container.replaceChildren(details);
  }

  const compact = details.querySelector("[data-packito-inspector-summary]");
  if (compact) compact.textContent = pretty(inspectorSummary(ctx));

  // If a human deliberately left the expensive inspector open, keep it live.
  // Closed inspectors remain cheap on both theta and epsilon.
  if (details.open) materializeInspector(container);
};

export const appPack = Object.freeze({
  kind: "app_pack_mould_app_pack_v1",
  id: "packito",
  styleUrls: Object.freeze([
    new URL("./style.css", import.meta.url).href,
  ]),
  callables: Object.freeze({
    notification: renderGlobalNotification,
    widget: renderWidgetFallback,
    widgetNotification: renderWidgetNotification,
    widgetsContainer: renderWidgetsContainer,
    outers: renderOuters,
    page: renderPage,
    noReadWidget: renderNoRead,
    noWriteWidget: renderNoWrite,
  }),
  widgetRenderers: Object.freeze({
    "packito.choice.v1": renderChoice,
    "packito.board.v1": renderBoard,
    "packito.history.v1": renderHistory,
    "packito.role_gate.v1": renderRoleGate,
    "packito.puzzle_seed.v1": renderPuzzleSeed,
    "packito.puzzle_answer.v1": renderPuzzleAnswer,
  }),
  epsRoutes: Object.freeze({
    "packito.widget_notice": "widget",
    "packito.global_notice": "global",
    "packito.silent_metric": "silence",
    "packito.custom_notice": Object.freeze({
      mode: "custom",
      handler: customMessageRoute,
    }),
  }),
  defaultEpsRoute: "global",
  outers: Object.freeze({
    packito_controls: Object.freeze({
      render: renderControls,
      powder: Object.freeze({
        new_page: true,
        widget_refresh: true,
        epsilon: false,
      }),
    }),
    packito_inspector: Object.freeze({
      render: renderInspector,
      powder: Object.freeze({
        new_page: true,
        widget_refresh: true,
        // Epsilon still updates the retained context pointer, but closed
        // inspectors no longer stringify/replace the complete blanket.
        epsilon: true,
      }),
    }),
  }),
});

export default appPack;

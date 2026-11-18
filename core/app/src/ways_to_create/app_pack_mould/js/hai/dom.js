import {
  epsChannelOf,
  planThetaRefresh,
} from "./context.js";

const asObject = (value) => (
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value
    : null
);

const json = (value) => JSON.stringify(value, null, 2);
const text = (value) => String(value ?? "").trim();

const element = (documentRef, tag, attrs = {}, textContent = null) => {
  const node = documentRef.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    node.setAttribute(name, String(value));
  }
  if (textContent !== null) node.textContent = String(textContent);
  return node;
};

const query = (root, selector) => root.querySelector(selector);

const cssEscape = (value) => {
  const raw = String(value ?? "");
  if (globalThis.CSS && typeof globalThis.CSS.escape === "function") {
    return globalThis.CSS.escape(raw);
  }
  return raw.replace(/[^A-Za-z0-9_-]/g, (char) => `\\${char}`);
};

const ensureStyle = (documentRef, href, marker) => {
  if (!documentRef?.head || !href) return;
  if (documentRef.head.querySelector(`link[data-${marker}="${href}"]`)) return;
  const link = documentRef.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  link.setAttribute(`data-${marker}`, href);
  documentRef.head.append(link);
};

export const ensureHaiStyles = ({ documentRef, baseUrl, appPack }) => {
  ensureStyle(
    documentRef,
    new URL("./hai/hai.css", baseUrl).href,
    "thinkument-hai-style",
  );
  for (const href of appPack.styleUrls ?? []) {
    ensureStyle(documentRef, href, "thinkument-hai-pack-style");
  }
};

const shellFor = (root, ctx) => {
  let shell = query(root, "[data-thinkument-hai]");
  if (shell) return shell;
  const documentRef = root.ownerDocument;
  shell = element(documentRef, "section", {
    "data-thinkument-hai": "app_pack_mould_opinionation_v1",
    "data-hai-app-pack": ctx.app_pack.id,
  });

  for (const name of ["brand", "status", "history", "latest_trident"]) {
    shell.append(element(documentRef, "div", {
      "data-hai-outer": name,
    }));
  }

  shell.append(
    element(documentRef, "div", {
      "data-hai-global-notifications": "1",
      "aria-live": "polite",
    }),
    element(documentRef, "main", { "data-hai-stage": "1" }),
    element(documentRef, "pre", { "data-hai-local-receipt": "1" }, "null"),
    element(documentRef, "pre", { "data-hai-dispatch-result": "1" }, "null"),
  );
  root.replaceChildren(shell);
  return shell;
};

const renderJsonSlot = (shell, selector, value) => {
  const node = query(shell, selector);
  if (node) node.textContent = json(value);
};

const domApi = (api, shell) => {
  let rendering = true;
  const mutation = (name, fn) => (...args) => {
    if (rendering) {
      throw new Error(
        `${name} cannot run during a HAI render callable; install a later substrate callback`,
      );
    }
    return fn(...args);
  };

  const guarded = Object.freeze({
    ...api,
    writeX: mutation("writeX", (...args) => api.writeX(...args)),
    dispatch: mutation("dispatch", (...args) => api.dispatch(...args)),
    setPageNumber: mutation(
      "setPageNumber",
      (...args) => api.setPageNumber(...args),
    ),
    setSnapPageOnNewTrident: mutation(
      "setSnapPageOnNewTrident",
      (...args) => api.setSnapPageOnNewTrident(...args),
    ),
    setSilenceEps: mutation(
      "setSilenceEps",
      (...args) => api.setSilenceEps(...args),
    ),
    setSilenceTheta: mutation(
      "setSilenceTheta",
      (...args) => api.setSilenceTheta(...args),
    ),
    presentLocalReceipt(value) {
      renderJsonSlot(shell, "[data-hai-local-receipt]", value);
    },
    presentDispatchResult(value) {
      renderJsonSlot(shell, "[data-hai-dispatch-result]", value);
    },
  });

  return {
    api: guarded,
    release() {
      rendering = false;
    },
  };
};

const microRows = (widget) => Array.isArray(widget.micros) ? widget.micros : [];
const currentFill = (widget) => asObject(widget.fill) ?? {};

const baseWidget = ({ documentRef, widget }) => {
  const card = element(documentRef, "article", {
    class: "hai-widget",
    "data-hai-widget-card": "1",
    "data-hai-widget-id": widget.datum_id,
    "data-hai-renderer": widget.renderer_key || "generic",
  });
  card.append(
    element(
      documentRef,
      "h3",
      { class: "hai-widget-title" },
      widget.args.title || widget.shell?.title || widget.datum_id,
    ),
  );

  const fill = currentFill(widget);
  for (const micro of microRows(widget)) {
    const microName = text(micro?.name ?? micro?.id);
    if (!microName) continue;
    const row = element(documentRef, "div", {
      class: "hai-micro",
      "data-hai-micro": `${widget.datum_id}.${microName}`,
    });
    const include = element(documentRef, "input", {
      type: "checkbox",
      "data-hai-micro-include": "1",
      "data-datum-id": widget.datum_id,
      "data-micro-name": microName,
      "aria-label": `include ${widget.datum_id}.${microName}`,
    });
    include.type = "checkbox";
    include.checked = false;

    const editor = element(documentRef, "textarea", {
      "data-hai-micro-value": "1",
      "data-datum-id": widget.datum_id,
      "data-micro-name": microName,
      "aria-label": `${widget.datum_id}.${microName} JSON literal`,
    });
    editor.value = Object.prototype.hasOwnProperty.call(fill, microName)
      ? json(fill[microName])
      : "null";

    row.append(
      include,
      editor,
      element(documentRef, "pre", { "data-hai-micro-meta": "1" }, json(micro)),
    );
    card.append(row);
  }
  return card;
};

const baseNoReadWidget = ({ documentRef, widget }) => element(
  documentRef,
  "article",
  {
    class: "hai-widget hai-widget-obfuscated",
    "data-hai-widget-card": "1",
    "data-hai-widget-id": widget.datum_id,
    "data-hai-no-read": "1",
  },
  `${widget.datum_id}: hidden by role projection`,
);

const baseNoWriteWidget = ({ documentRef, widget }) => {
  const card = element(documentRef, "article", {
    class: "hai-widget hai-widget-readonly",
    "data-hai-widget-card": "1",
    "data-hai-widget-id": widget.datum_id,
    "data-hai-no-write": "1",
  });
  card.append(
    element(documentRef, "h3", {}, widget.args.title || widget.datum_id),
    element(documentRef, "pre", { "data-hai-readonly-fill": "1" }, json(widget.fill)),
  );
  return card;
};

const baseNotification = ({ documentRef, container, row, channel }) => {
  container.append(element(
    documentRef,
    "div",
    {
      class: "hai-notification",
      "data-hai-notification": channel,
    },
    row?.payload?.message?.text
      ?? row?.payload?.text
      ?? json(row),
  ));
};

const baseWidgetNotification = ({ documentRef, container, row, channel }) => {
  container.append(element(
    documentRef,
    "div",
    {
      class: "hai-widget-notification",
      "data-hai-widget-notification": channel,
    },
    row?.payload?.message?.text
      ?? row?.payload?.text
      ?? json(row),
  ));
};

const baseNoReadEpsNotification = ({ documentRef, container, row, channel }) => {
  container.append(element(
    documentRef,
    "div",
    {
      class: "hai-notification hai-eps-obfuscated",
      "data-hai-eps-obfuscated": channel,
      "data-hai-eps-seq": row?.eps_seq ?? "",
    },
    `eps#${row?.eps_seq ?? "?"} (${channel}): hidden by role projection`,
  ));
};

const actionFromComposer = (shell) => {
  const userFill = {};
  for (const include of shell.querySelectorAll("[data-hai-micro-include]")) {
    if (!include.checked) continue;
    const datumId = text(include.getAttribute("data-datum-id"));
    const microName = text(include.getAttribute("data-micro-name"));
    const editor = shell.querySelector(
      `[data-hai-micro-value][data-datum-id="${cssEscape(datumId)}"][data-micro-name="${cssEscape(microName)}"]`,
    );
    userFill[datumId] ??= {};
    userFill[datumId][microName] = JSON.parse(editor?.value ?? "null");
  }

  let userSignal = null;
  const includeSignal = query(shell, "[data-hai-signal-include]");
  if (includeSignal?.checked) {
    userSignal = {
      datum_id: text(query(shell, "[data-hai-signal-datum]")?.value),
      kind: text(query(shell, "[data-hai-signal-kind]")?.value),
      info: JSON.parse(query(shell, "[data-hai-signal-info]")?.value || "{}"),
    };
  }

  const A = {
    action: "STEP",
    userFill,
    userSignal,
    funked: Boolean(query(shell, "[data-hai-funked]")?.checked),
  };
  const requestId = text(query(shell, "[data-hai-request-id]")?.value);
  if (requestId) A.requestId = requestId;
  return A;
};

const installAction = ({ button, shell, api, actionFactory }) => {
  button.addEventListener("click", async () => {
    try {
      renderJsonSlot(shell, "[data-hai-dispatch-result]", null);
      const A = actionFactory();
      const validation = api.validateDispatch(A);
      renderJsonSlot(shell, "[data-hai-local-receipt]", validation);
      if (!validation.ok) return;
      renderJsonSlot(
        shell,
        "[data-hai-dispatch-result]",
        await api.dispatch(A),
      );
    } catch (error) {
      renderJsonSlot(shell, "[data-hai-local-receipt]", {
        kind: "app_pack_mould_local_error_v1",
        name: error?.name ?? "Error",
        message: error?.message ?? String(error),
        code: error?.code ?? null,
        receipt: error?.receipt ?? null,
      });
    }
  });
};

const renderComposer = ({ documentRef, shell, container, api, ctx }) => {
  const composer = element(documentRef, "section", {
    "data-hai-composer": "1",
  });
  composer.append(element(documentRef, "h2", {}, "Dispatch"));

  const signalInclude = element(documentRef, "input", {
    type: "checkbox",
    "data-hai-signal-include": "1",
  });
  signalInclude.type = "checkbox";
  const signalDatum = element(documentRef, "input", {
    type: "text",
    "data-hai-signal-datum": "1",
  });
  signalDatum.value = ctx.view.active_widget_ids?.[0] ?? "";
  const signalKind = element(documentRef, "input", {
    type: "text",
    "data-hai-signal-kind": "1",
  });
  const signalInfo = element(documentRef, "textarea", {
    "data-hai-signal-info": "1",
  });
  signalInfo.value = "{}";
  const funked = element(documentRef, "input", {
    type: "checkbox",
    "data-hai-funked": "1",
  });
  funked.type = "checkbox";
  const requestId = element(documentRef, "input", {
    type: "text",
    "data-hai-request-id": "1",
  });

  composer.append(signalInclude, signalDatum, signalKind, signalInfo, funked, requestId);

  const actionRow = element(documentRef, "div", { "data-hai-actions": "1" });
  const step = element(documentRef, "button", { type: "button", "data-hai-action": "STEP" }, "STEP");
  const undo = element(documentRef, "button", { type: "button", "data-hai-action": "UNDO" }, "UNDO");
  const redo = element(documentRef, "button", { type: "button", "data-hai-action": "REDO" }, "REDO");
  actionRow.append(step, undo, redo);
  composer.append(actionRow);

  const exact = element(documentRef, "details", { "data-hai-exact-action-composer": "1" });
  exact.append(element(documentRef, "summary", {}, "Advanced exact public A"));
  const exactEditor = element(documentRef, "textarea", { "data-hai-exact-action": "1" });
  exactEditor.value = json({ action: "STEP", userFill: {}, userSignal: null });
  const exactButton = element(documentRef, "button", { type: "button", "data-hai-exact-action-dispatch": "1" }, "Dispatch exact A");
  exact.append(exactEditor, exactButton);
  composer.append(exact);

  const disabled = !ctx.view.viewing_latest;
  for (const node of [step, undo, redo, exactButton, signalInclude, signalDatum, signalKind, signalInfo, funked, requestId, exactEditor]) {
    node.disabled = disabled;
  }

  installAction({ button: step, shell, api, actionFactory: () => actionFromComposer(shell) });
  installAction({ button: undo, shell, api, actionFactory: () => ({ action: "UNDO" }) });
  installAction({ button: redo, shell, api, actionFactory: () => ({ action: "REDO" }) });
  installAction({
    button: exactButton,
    shell,
    api,
    actionFactory: () => JSON.parse(exactEditor.value),
  });
  container.append(composer);
};

const baseWidgetsContainer = ({ container, widgets, renderWidgetCard }) => {
  for (const widget of widgets) container.append(renderWidgetCard(widget));
};

const baseOutersCallable = ({ renderDefaultOuters }) => renderDefaultOuters();
const basePageCallable = ({ renderDefaultPage }) => renderDefaultPage();

const BASE_CALLABLES = Object.freeze({
  notification: baseNotification,
  widget: baseWidget,
  widgetNotification: baseWidgetNotification,
  noReadEpsNotification: baseNoReadEpsNotification,
  widgetsContainer: baseWidgetsContainer,
  outers: baseOutersCallable,
  page: basePageCallable,
  noReadWidget: baseNoReadWidget,
  noWriteWidget: baseNoWriteWidget,
});

const renderWidget = ({ documentRef, widget, ctx, api, appPack, callables }) => {
  if (!widget.readable) {
    return callables.noReadWidget({ documentRef, widget, ctx, api });
  }
  if (!widget.access.write || !ctx.view.viewing_latest) {
    return callables.noWriteWidget({ documentRef, widget, ctx, api });
  }
  const renderer = widget.renderer_key
    ? appPack.widgetRenderers?.[widget.renderer_key]
    : null;
  return (renderer ?? callables.widget)({ documentRef, widget, ctx, api });
};

const renderStage = ({ root, shell, ctx, api, appPack, callables }) => {
  const documentRef = root.ownerDocument;
  const stage = query(shell, "[data-hai-stage]");
  const widgets = element(documentRef, "section", { "data-hai-widgets": "1" });
  callables.widgetsContainer({
    documentRef,
    container: widgets,
    widgets: ctx.view.widgets,
    ctx,
    api,
    renderWidgetCard: (widget) => renderWidget({
      documentRef,
      widget,
      ctx,
      api,
      appPack,
      callables,
    }),
  });
  stage.replaceChildren(widgets);
  renderComposer({ documentRef, shell, container: stage, api, ctx });
};

const patchWidgets = ({ root, shell, ctx, api, appPack, callables, ids }) => {
  const documentRef = root.ownerDocument;
  const container = query(shell, "[data-hai-widgets]");
  if (!container) return renderStage({ root, shell, ctx, api, appPack, callables });

  for (const datumId of ids) {
    const widget = ctx.view.widgets.find((row) => row.datum_id === datumId);
    const old = container.querySelector(`[data-hai-widget-card][data-hai-widget-id="${cssEscape(datumId)}"]`);
    if (!widget || !old) return renderStage({ root, shell, ctx, api, appPack, callables });
    old.replaceWith(renderWidget({ documentRef, widget, ctx, api, appPack, callables }));
  }
};

const BASE_OUTERS = Object.freeze({
  brand: Object.freeze({
    powder: Object.freeze({ new_page: true, widget_refresh: false, epsilon: false }),
    render({ documentRef, container, appPack }) {
      container.replaceChildren(element(
        documentRef,
        "strong",
        { "data-hai-brand": "1" },
        `Thinkument HAI / ${appPack.id}`,
      ));
    },
  }),
  status: Object.freeze({
    powder: Object.freeze({ new_page: true, widget_refresh: true, epsilon: true }),
    render({ documentRef, container, ctx, appPack }) {
      container.replaceChildren(element(
        documentRef,
        "pre",
        { "data-hai-summary": "1" },
        json({
          trigger: ctx.heartbeat.kind,
          cursor: ctx.heartbeat.canonical_cursor,
          page: ctx.state.page_being_viewed,
          resolved_cursor: ctx.view.resolved_cursor,
          viewing_latest: ctx.view.viewing_latest,
          runtime_kind: ctx.view.runtime_kind,
          active_widget_ids: ctx.view.active_widget_ids,
          role: ctx.session.role,
          app_pack: appPack.id,
        }),
      ));
    },
  }),
  history: Object.freeze({
    powder: Object.freeze({ new_page: true, widget_refresh: false, epsilon: false }),
    render({ documentRef, container, ctx, api }) {
      const nav = element(documentRef, "nav", { "data-hai-history": "1" });
      const latest = element(documentRef, "button", { type: "button", "data-hai-history-page": "-1" }, "Latest");
      latest.addEventListener("click", () => api.setPageNumber(-1));
      nav.append(latest);
      for (const T of ctx.queue.timeline) {
        if (!Number.isInteger(T.end_event_seq)) continue;
        const button = element(
          documentRef,
          "button",
          { type: "button", "data-hai-history-page": T.end_event_seq },
          `${T.action || "A"}@${T.end_event_seq}`,
        );
        button.addEventListener("click", () => api.setPageNumber(T.end_event_seq));
        nav.append(button);
      }
      container.replaceChildren(nav);
    },
  }),
  latest_trident: Object.freeze({
    powder: Object.freeze({ new_page: true, widget_refresh: false, epsilon: false }),
    render({ documentRef, container, ctx }) {
      container.replaceChildren(element(
        documentRef,
        "pre",
        { "data-hai-latest-trident": "1" },
        json(ctx.queue.latest_trident),
      ));
    },
  }),
});

const powderMatches = (powder, reason) => (
  (reason.new_page && powder?.new_page)
  || (reason.widget_refresh && powder?.widget_refresh)
  || (reason.epsilon && powder?.epsilon)
);

const renderOuterSpecs = ({ root, shell, ctx, api, appPack, reason }) => {
  const documentRef = root.ownerDocument;
  const merged = { ...BASE_OUTERS, ...(appPack.outers ?? {}) };
  for (const [name, spec] of Object.entries(merged)) {
    if (!powderMatches(spec.powder ?? {}, reason)) continue;
    let container = query(shell, `[data-hai-outer="${cssEscape(name)}"]`);
    if (!container) {
      container = element(documentRef, "div", { "data-hai-outer": name });
      shell.prepend(container);
    }
    spec.render({ documentRef, container, ctx, api, appPack, reason });
  }
};

const routeForRow = (appPack, row) => {
  const channel = epsChannelOf(row);
  const configured = appPack.epsRoutes?.[channel]
    ?? appPack.defaultEpsRoute;
  if (configured !== null && configured !== undefined) {
    return { channel, route: configured };
  }
  return {
    channel,
    route: text(row?.datum_id) ? "widget" : "global",
  };
};

export const renderEpsilon = ({ root, shell, ctx, api, appPack, callables }) => {
  const documentRef = root.ownerDocument;
  const rows = ctx.epsilon?.new_rows?.length
    ? ctx.epsilon.new_rows
    : (ctx.epsilon?.rows ?? []);
  for (const row of rows) {
    const { channel, route } = routeForRow(appPack, row);
    if (route !== "silence") {
      if (row?.obfuscated === true && (route === "global" || route === "widget")) {
        callables.noReadEpsNotification({
          documentRef,
          container: query(shell, "[data-hai-global-notifications]"),
          ctx,
          api,
          row,
          channel,
        });
      } else if (route === "global") {
        callables.notification({
          documentRef,
          container: query(shell, "[data-hai-global-notifications]"),
          ctx,
          api,
          row,
          channel,
        });
      } else if (route === "widget") {
        const datumId = text(row?.datum_id);
        const widget = datumId
          ? ctx.view.widgets.find((item) => item.datum_id === datumId) ?? null
          : null;
        const card = datumId
          ? query(shell, `[data-hai-widget-card][data-hai-widget-id="${cssEscape(datumId)}"]`)
          : null;
        const container = card ?? query(shell, "[data-hai-global-notifications]");
        callables.widgetNotification({
          documentRef,
          container,
          widget,
          ctx,
          api,
          row,
          channel,
        });
      } else if (asObject(route)?.mode === "custom" && typeof route.handler === "function") {
        route.handler({ documentRef, root, shell, ctx, api, row, channel });
      } else if (typeof route === "function") {
        route({ documentRef, root, shell, ctx, api, row, channel });
      }
    }
    if (typeof callables.onEpsRow === "function") {
      callables.onEpsRow({
        documentRef,
        root,
        shell,
        ctx,
        api,
        row,
        channel,
        routeResult: route,
      });
    }
  }
};

const invokeOuters = ({ root, shell, ctx, api, appPack, callables, reason }) => (
  callables.outers({
    root,
    shell,
    ctx,
    api,
    appPack,
    reason,
    renderDefaultOuters: () => renderOuterSpecs({
      root,
      shell,
      ctx,
      api,
      appPack,
      reason,
    }),
  })
);

export const renderDefaultHeartbeat = ({ root, shell, ctx, api, appPack, callables }) => {
  if (ctx.heartbeat.kind === "epsilon") {
    renderEpsilon({ root, shell, ctx, api, appPack, callables });
    invokeOuters({
      root,
      shell,
      ctx,
      api,
      appPack,
      callables,
      reason: { new_page: false, widget_refresh: false, epsilon: true },
    });
    return;
  }

  const plan = planThetaRefresh(ctx) ?? { kind: "stage", changed_widget_ids: [] };
  if (plan.kind === "stage") {
    renderStage({ root, shell, ctx, api, appPack, callables });
  } else if (plan.kind === "widgets") {
    patchWidgets({
      root,
      shell,
      ctx,
      api,
      appPack,
      callables,
      ids: plan.changed_widget_ids,
    });
  }

  invokeOuters({
    root,
    shell,
    ctx,
    api,
    appPack,
    callables,
    reason: {
      new_page: true,
      widget_refresh: plan.kind === "stage" || plan.kind === "widgets",
      epsilon: false,
    },
  });
};

export function renderHaiHeartbeat({ root, ctx, api, appPack }) {
  if (!root?.ownerDocument) throw new TypeError("framework-4-services opinionation requires a DOM root");
  const shell = shellFor(root, ctx);
  shell.setAttribute("data-hai-app-pack", appPack.id);
  const guarded = domApi(api, shell);
  const presentedApi = guarded.api;
  const callables = Object.freeze({ ...BASE_CALLABLES, ...(appPack.callables ?? {}) });

  try {
    return callables.page({
      root,
      shell,
      ctx,
      api: presentedApi,
      appPack,
      callables,
      renderDefaultPage: () => renderDefaultHeartbeat({
        root,
        shell,
        ctx,
        api: presentedApi,
        appPack,
        callables,
      }),
    });
  } finally {
    guarded.release();
  }
}

export function rerenderHaiSnapshot({ root, ctx, api, appPack }) {
  const shell = shellFor(root, ctx);
  shell.setAttribute("data-hai-app-pack", appPack.id);
  const guarded = domApi(api, shell);
  const presentedApi = guarded.api;
  const callables = Object.freeze({ ...BASE_CALLABLES, ...(appPack.callables ?? {}) });

  const renderDefaultPage = () => {
    renderStage({ root, shell, ctx, api: presentedApi, appPack, callables });
    invokeOuters({
      root,
      shell,
      ctx,
      api: presentedApi,
      appPack,
      callables,
      reason: { new_page: true, widget_refresh: true, epsilon: false },
    });
  };

  try {
    return callables.page({
      root,
      shell,
      ctx,
      api: presentedApi,
      appPack,
      callables,
      renderDefaultPage,
    });
  } finally {
    guarded.release();
  }
}

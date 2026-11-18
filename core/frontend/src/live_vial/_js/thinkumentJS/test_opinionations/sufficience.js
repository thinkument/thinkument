/*
 * ThinkumentJS test opinionation — minimal sufficience reference.
 *
 * This is intentionally a diagnostic/test station, not production HAI UX.
 * It proves that one opinionation can observe the public station and construct
 * every public higher-app user action shape used here: STEP(F, S, funked,
 * requestId?), UNDO, and REDO. All actions still cross validateDispatch()
 * before dispatch().
 *
 * The ordinary structured controls model what a human-facing opinionation
 * would render. The exact-A diagnostic control is deliberately secondary: it
 * accepts only the same public higher-app A object that loopback.dispatch()
 * accepts. It exists so browser dry-run proofs can submit an exact A even when
 * the current role correctly cannot see a datum editor. It does not expose
 * transport-owned identity, role, or canonical cursor fields and therefore
 * cannot forge the lower ThinkumentJS wire packet.
 */

export const SUFFICIENCE_OPINIONATION_ID =
  "thinkument_test_sufficience_opinionation_v1";

// Backward-compatible spelling used by the first probe version of this fixture.
export const SUFFICIENT_OPINIONATION_ID = SUFFICIENCE_OPINIONATION_ID;

/*
 * The opinionation source always lives immediately below the public
 * ThinkumentJS root:
 *
 *   source tree:
 *     .../thinkumentJS/test_opinionations/sufficience.js
 *       -> ../womb.js
 *
 *   aggregate browser static tree:
 *     /think/static/test_opinionations/sufficience.js
 *       -> /think/static/womb.js
 *
 * The same relative specifier is therefore correct in Node source-tree E2E and
 * in a real browser. Keeping both named exports makes the module-graph contract
 * explicit without maintaining two paths that can drift.
 */
export const SUFFICIENCE_BROWSER_WOMB_SPECIFIER = "../womb.js";
export const SUFFICIENCE_NODE_WOMB_SPECIFIER = "../womb.js";

const wombModuleSpecifier = String(import.meta.url).startsWith("file:")
  ? SUFFICIENCE_NODE_WOMB_SPECIFIER
  : SUFFICIENCE_BROWSER_WOMB_SPECIFIER;

let wombModulePromise = null;
const loadWombModule = () => {
  wombModulePromise ??= import(wombModuleSpecifier);
  return wombModulePromise;
};

const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

const asObject = (value) => (
  value !== null
  && typeof value === "object"
  && !Array.isArray(value)
    ? value
    : null
);

const text = (value) => String(value ?? "").trim();
const json = (value) => JSON.stringify(value, null, 2);

const element = (
  documentRef,
  tag,
  { attrs = {}, textContent = null } = {},
) => {
  const node = documentRef.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    node.setAttribute(name, String(value));
  }
  if (textContent !== null) node.textContent = String(textContent);
  return node;
};

const appendLabeledControl = ({
  documentRef,
  parent,
  labelText,
  control,
}) => {
  const label = element(documentRef, "label", {
    attrs: { "data-sufficience-field": "1" },
  });
  label.append(
    element(documentRef, "span", { textContent: labelText }),
    control,
  );
  parent.append(label);
};

const parseDeadJsonLiteral = (raw, label) => {
  try {
    return JSON.parse(String(raw ?? ""));
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new SyntaxError(`${label} must be a JSON literal: ${reason}`);
  }
};

const parsePublicAction = (raw) => {
  const value = parseDeadJsonLiteral(raw, "public A");
  if (asObject(value) === null) {
    throw new TypeError("public A must be a JSON object");
  }
  return value;
};

const fillFor = (row) => asObject(row?.fill) ?? {};

const initialLiteralForMicro = (row, microName) => {
  const fill = fillFor(row);
  return own(fill, microName) ? json(fill[microName]) : "null";
};

const renderJsonInto = (root, selector, value) => {
  const node = root.querySelector(selector);
  if (node) node.textContent = json(value);
};

const errorValue = (error) => {
  const out = {
    kind: "thinkument_sufficience_local_error_v1",
    name: error?.name ?? "Error",
    message: error?.message ?? String(error),
  };
  for (const key of ["code", "status", "body", "receipt"]) {
    const value = error?.[key];
    if (value !== undefined) out[key] = value;
  }
  return out;
};

const renderErrorInto = (root, error) => {
  renderJsonInto(
    root,
    "[data-sufficience-local-receipt]",
    errorValue(error),
  );
};

const activeReadableRows = ({ U, activeIds }) => {
  if (!Array.isArray(activeIds)) return [];
  const wanted = new Set(activeIds);
  const rows = Array.isArray(U?.datum_states_on_this_span)
    ? U.datum_states_on_this_span
    : [];

  return rows.filter((row) => (
    asObject(row)
    && wanted.has(text(row.datum_id ?? row.id))
    && row.kind !== "role_mismatch_obfuscated_datum_v1"
    && row.role_mismatch_obfuscated !== true
  ));
};

const microsFor = (row) => {
  for (const candidate of [row?.micros, row?.shell?.micros]) {
    if (Array.isArray(candidate)) return candidate;
  }
  return [];
};

/* Construct the complete public STEP shape from only rendered controls. */
const buildStepAction = ({
  microBindings,
  signalControls,
  funkedControl,
  requestIdControl,
}) => {
  const userFill = {};

  for (const binding of microBindings) {
    if (!binding.include.checked) continue;
    userFill[binding.datumId] ??= {};
    userFill[binding.datumId][binding.microName] = parseDeadJsonLiteral(
      binding.editor.value,
      `${binding.datumId}.${binding.microName}`,
    );
  }

  let userSignal = null;
  if (signalControls.include.checked) {
    const datumId = text(signalControls.datumId.value);
    const kind = text(signalControls.kind.value);
    const info = parseDeadJsonLiteral(
      signalControls.info.value,
      "signal.info",
    );

    if (!datumId) throw new TypeError("signal.datum_id must be non-empty");
    if (!kind) throw new TypeError("signal.kind must be non-empty");
    if (asObject(info) === null) {
      throw new TypeError("signal.info must be a JSON object");
    }

    userSignal = { datum_id: datumId, kind, info };
  }

  const A = {
    action: "STEP",
    userFill,
    userSignal,
    funked: Boolean(funkedControl.checked),
  };

  const requestId = text(requestIdControl.value);
  if (requestId) A.requestId = requestId;
  return A;
};

const buildSimpleAction = ({ action, requestIdControl }) => {
  const A = { action: String(action).toUpperCase() };
  const requestId = text(requestIdControl.value);
  if (requestId) A.requestId = requestId;
  return A;
};

const installDispatchButton = ({
  button,
  root,
  loopback,
  actionFactory,
}) => {
  button.addEventListener("click", async () => {
    try {
      // Every click owns a fresh result slot. This prevents a local preflight
      // rejection from leaving the previous dispatch result looking current.
      renderJsonInto(
        root,
        "[data-sufficience-dispatch-result]",
        null,
      );

      const A = actionFactory();
      const validation = loopback.validateDispatch(A);
      renderJsonInto(
        root,
        "[data-sufficience-local-receipt]",
        validation,
      );
      if (!validation.ok) return;

      const result = await loopback.dispatch(A);
      renderJsonInto(
        root,
        "[data-sufficience-dispatch-result]",
        result,
      );
    } catch (error) {
      renderErrorInto(root, error);
    }
  });
};

const renderStation = ({
  root,
  loopback,
  role,
  Q,
  packet = null,
  trigger = "boot",
}) => {
  const documentRef = root?.ownerDocument;
  if (!root || !documentRef?.createElement) {
    throw new TypeError(
      "sufficience opinionation requires a DOM root with ownerDocument",
    );
  }

  const U = asObject(Q?.latest_U);
  const activeIds = U && own(U, "datum_widgets_on_this_span")
    ? (
      Array.isArray(U.datum_widgets_on_this_span)
        ? U.datum_widgets_on_this_span.map(text).filter(Boolean)
        : []
    )
    : null;
  const rows = activeReadableRows({ U, activeIds });

  const shell = element(documentRef, "section", {
    attrs: {
      "data-thinkument-sufficience": SUFFICIENCE_OPINIONATION_ID,
    },
  });

  shell.append(
    element(documentRef, "h1", {
      textContent: "Thinkument sufficience station",
    }),
    element(documentRef, "pre", {
      attrs: { "data-sufficience-summary": "1" },
      textContent: json({
        trigger,
        cursor: Q?.cursor ?? null,
        role: role ?? null,
        runtime_kind: U?.kind ?? null,
        active_widget_ids: activeIds,
      }),
    }),
  );

  const blanket = element(documentRef, "details", {
    attrs: { "data-sufficience-blanket": "1" },
  });
  blanket.append(
    element(documentRef, "summary", {
      textContent: "Lossless current inbound blanket",
    }),
    element(documentRef, "pre", {
      attrs: { "data-sufficience-packet": "1" },
      textContent: json(
        packet ?? {
          kind: "thinkument_sufficience_boot_blanket_v1",
          trigger: "boot",
          Q,
          X: loopback.readX(),
        },
      ),
    }),
  );
  shell.append(blanket);

  const composer = element(documentRef, "section", {
    attrs: { "data-sufficience-step-composer": "1" },
  });
  composer.append(
    element(documentRef, "h2", { textContent: "STEP composer" }),
  );

  const microBindings = [];
  for (const row of rows) {
    const datumId = text(row.datum_id ?? row.id);
    const fieldset = element(documentRef, "fieldset", {
      attrs: { "data-sufficience-datum": datumId },
    });
    fieldset.append(
      element(documentRef, "legend", { textContent: datumId }),
    );

    for (const micro of microsFor(row)) {
      const microName = text(micro?.name ?? micro?.id);
      if (!microName) continue;

      const rowNode = element(documentRef, "div", {
        attrs: {
          "data-sufficience-micro": `${datumId}.${microName}`,
        },
      });
      const include = element(documentRef, "input", {
        attrs: {
          type: "checkbox",
          "data-sufficience-micro-include": "1",
          "data-datum-id": datumId,
          "data-micro-name": microName,
        },
      });
      include.type = "checkbox";
      include.checked = false;

      const editor = element(documentRef, "textarea", {
        attrs: {
          "data-sufficience-micro-value": "1",
          "data-datum-id": datumId,
          "data-micro-name": microName,
          "aria-label": `${datumId}.${microName} JSON literal`,
        },
      });
      editor.value = initialLiteralForMicro(row, microName);

      appendLabeledControl({
        documentRef,
        parent: rowNode,
        labelText: `include ${datumId}.${microName}`,
        control: include,
      });
      appendLabeledControl({
        documentRef,
        parent: rowNode,
        labelText: "dead-JSON value",
        control: editor,
      });
      rowNode.append(
        element(documentRef, "pre", {
          attrs: { "data-sufficience-micro-meta": "1" },
          textContent: json(micro),
        }),
      );
      fieldset.append(rowNode);
      microBindings.push({ datumId, microName, include, editor });
    }
    composer.append(fieldset);
  }

  const signalBox = element(documentRef, "fieldset", {
    attrs: { "data-sufficience-signal": "1" },
  });
  signalBox.append(
    element(documentRef, "legend", { textContent: "Optional signal" }),
  );

  const signalInclude = element(documentRef, "input", {
    attrs: { type: "checkbox", "data-sufficience-signal-include": "1" },
  });
  signalInclude.type = "checkbox";
  signalInclude.checked = false;

  const signalDatum = element(documentRef, "input", {
    attrs: { type: "text", "data-sufficience-signal-datum": "1" },
  });
  signalDatum.type = "text";
  signalDatum.value = activeIds?.[0] ?? "";

  const signalKind = element(documentRef, "input", {
    attrs: { type: "text", "data-sufficience-signal-kind": "1" },
  });
  signalKind.type = "text";
  signalKind.value = "";

  const signalInfo = element(documentRef, "textarea", {
    attrs: { "data-sufficience-signal-info": "1" },
  });
  signalInfo.value = "{}";

  for (const [labelText, control] of [
    ["include signal", signalInclude],
    ["signal datum_id", signalDatum],
    ["signal kind", signalKind],
    ["signal info JSON object", signalInfo],
  ]) {
    appendLabeledControl({ documentRef, parent: signalBox, labelText, control });
  }
  composer.append(signalBox);

  const funked = element(documentRef, "input", {
    attrs: { type: "checkbox", "data-sufficience-funked": "1" },
  });
  funked.type = "checkbox";
  funked.checked = false;
  appendLabeledControl({
    documentRef,
    parent: composer,
    labelText: "funked chain reaction",
    control: funked,
  });

  const requestId = element(documentRef, "input", {
    attrs: { type: "text", "data-sufficience-request-id": "1" },
  });
  requestId.type = "text";
  requestId.value = "";
  appendLabeledControl({
    documentRef,
    parent: composer,
    labelText: "optional requestId",
    control: requestId,
  });

  const actionRow = element(documentRef, "div", {
    attrs: { "data-sufficience-actions": "1" },
  });
  const stepButton = element(documentRef, "button", {
    attrs: { type: "button", "data-sufficience-action": "STEP" },
    textContent: "Dispatch STEP",
  });
  const undoButton = element(documentRef, "button", {
    attrs: { type: "button", "data-sufficience-action": "UNDO" },
    textContent: "Dispatch UNDO",
  });
  const redoButton = element(documentRef, "button", {
    attrs: { type: "button", "data-sufficience-action": "REDO" },
    textContent: "Dispatch REDO",
  });
  actionRow.append(stepButton, undoButton, redoButton);
  composer.append(actionRow);
  shell.append(composer);

  const exactA = element(documentRef, "details", {
    attrs: { "data-sufficience-exact-action-composer": "1" },
  });
  exactA.append(
    element(documentRef, "summary", {
      textContent: "Diagnostic exact public A",
    }),
  );
  const exactAEditor = element(documentRef, "textarea", {
    attrs: {
      "data-sufficience-exact-action": "1",
      "aria-label": "exact public higher-app A JSON object",
    },
  });
  exactAEditor.value = json({ action: "STEP", userFill: {}, userSignal: null });
  const exactAButton = element(documentRef, "button", {
    attrs: {
      type: "button",
      "data-sufficience-exact-action-dispatch": "1",
    },
    textContent: "Dispatch exact public A",
  });
  appendLabeledControl({
    documentRef,
    parent: exactA,
    labelText: "public A JSON",
    control: exactAEditor,
  });
  exactA.append(exactAButton);
  shell.append(exactA);

  shell.append(
    element(documentRef, "pre", {
      attrs: { "data-sufficience-local-receipt": "1" },
      textContent: "null",
    }),
    element(documentRef, "pre", {
      attrs: { "data-sufficience-dispatch-result": "1" },
      textContent: "null",
    }),
  );

  root.replaceChildren(shell);

  const signalControls = {
    include: signalInclude,
    datumId: signalDatum,
    kind: signalKind,
    info: signalInfo,
  };

  installDispatchButton({
    button: stepButton,
    root,
    loopback,
    actionFactory: () => buildStepAction({
      microBindings,
      signalControls,
      funkedControl: funked,
      requestIdControl: requestId,
    }),
  });
  installDispatchButton({
    button: undoButton,
    root,
    loopback,
    actionFactory: () => buildSimpleAction({
      action: "UNDO",
      requestIdControl: requestId,
    }),
  });
  installDispatchButton({
    button: redoButton,
    root,
    loopback,
    actionFactory: () => buildSimpleAction({
      action: "REDO",
      requestIdControl: requestId,
    }),
  });
  installDispatchButton({
    button: exactAButton,
    root,
    loopback,
    actionFactory: () => parsePublicAction(exactAEditor.value),
  });
};

export function createOpinionation({ root, config }) {
  if (!root) throw new TypeError("sufficience opinionation requires root");

  return Object.freeze({
    kind: "thinkument_front_opinionation_v2",
    initialX: {},

    async drink(packet, loopback) {
      const { createWombRuntime } = await loadWombModule();
      const W = createWombRuntime(packet, loopback);
      renderStation({
        root,
        loopback,
        role: W.session().role,
        Q: W.Q(),
        packet: W.rawPacket(),
        trigger: W.heartbeat(),
      });
      return {
        X: W.X(),
        receipt: {
          kind: "thinkument_sufficience_render_receipt_v1",
          opinionation: SUFFICIENCE_OPINIONATION_ID,
          trigger: W.heartbeat(),
          cursor: W.Q().cursor,
          module: String(config?.modules?.opinionation || ""),
        },
      };
    },

    async onBoot({ loopback }) {
      renderStation({
        root,
        loopback,
        role: config?.role ?? null,
        Q: loopback.readQ(),
        packet: null,
        trigger: "boot",
      });
    },

    async dispose() {
      root.replaceChildren();
    },
  });
}

export default createOpinionation;

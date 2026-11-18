import assert from "node:assert/strict";
import test from "node:test";

import { validateAppPack } from "../src/ways_to_create/app_pack_mould/js/hai/app_packs.js";
import packito, {
  PACKITO_CALLABLE_PROOF_ATTRIBUTES,
  PACKITO_INSPECTOR_CONTEXT_PROPERTY,
} from "../tests/ways_to_create/fixtures/packito_fixture/js/index.js";

const EXPECTED_RENDERERS = [
  "packito.board.v1",
  "packito.choice.v1",
  "packito.history.v1",
  "packito.puzzle_answer.v1",
  "packito.puzzle_seed.v1",
  "packito.role_gate.v1",
];

const EXPECTED_CALLABLES = [
  "noReadWidget",
  "noWriteWidget",
  "notification",
  "outers",
  "page",
  "widget",
  "widgetNotification",
  "widgetsContainer",
];

test("packito exercises the complete HAI app-pack contract", () => {
  const checked = validateAppPack(packito, "packito");
  assert.deepEqual(
    Object.keys(checked.callables).sort(),
    EXPECTED_CALLABLES.toSorted(),
  );
  assert.deepEqual(
    Object.keys(PACKITO_CALLABLE_PROOF_ATTRIBUTES).sort(),
    EXPECTED_CALLABLES.toSorted(),
  );
  assert.deepEqual(
    Object.keys(checked.widgetRenderers).sort(),
    EXPECTED_RENDERERS,
  );
  for (const rendererId of EXPECTED_RENDERERS) {
    assert.equal(typeof checked.widgetRenderers[rendererId], "function");
  }
  assert.equal(checked.epsRoutes["packito.widget_notice"], "widget");
  assert.equal(checked.epsRoutes["packito.global_notice"], "global");
  assert.equal(checked.epsRoutes["packito.silent_metric"], "silence");
  assert.equal(checked.epsRoutes["packito.custom_notice"].mode, "custom");
  assert.equal(
    typeof checked.epsRoutes["packito.custom_notice"].handler,
    "function",
  );
  assert.equal(typeof checked.outers.packito_controls.render, "function");
  assert.equal(typeof checked.outers.packito_inspector.render, "function");
});

const parseAttributeSelector = (selector) => {
  const match = /^\[([^=\]]+)(?:="([^"]*)")?\]$/.exec(selector);
  if (!match) return null;
  return { name: match[1], value: match[2] ?? null };
};

class FakeNode {
  constructor(tag, documentRef) {
    this.tagName = String(tag).toUpperCase();
    this.ownerDocument = documentRef;
    this.children = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this.textContent = "";
    this.value = "";
    this.disabled = false;
    this.open = false;
    this.parentNode = null;
  }

  setAttribute(name, value) {
    this.attributes.set(String(name), String(value));
  }

  getAttribute(name) {
    return this.attributes.get(String(name)) ?? null;
  }

  append(...nodes) {
    for (const node of nodes) {
      node.parentNode = this;
      this.children.push(node);
    }
  }

  prepend(...nodes) {
    for (const node of nodes.reverse()) {
      node.parentNode = this;
      this.children.unshift(node);
    }
  }

  replaceChildren(...nodes) {
    this.children = [];
    this.append(...nodes);
  }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter((row) => row !== this);
    this.parentNode = null;
  }

  addEventListener(name, callback) {
    this.listeners.set(String(name), callback);
  }

  async click() {
    const callback = this.listeners.get("click");
    if (callback) await callback({ target: this, currentTarget: this });
  }

  async fire(name) {
    const callback = this.listeners.get(String(name));
    if (callback) await callback({ target: this, currentTarget: this });
  }

  _matches(selector) {
    const parsed = parseAttributeSelector(selector);
    if (!parsed) return false;
    if (!this.attributes.has(parsed.name)) return false;
    return parsed.value === null || this.attributes.get(parsed.name) === parsed.value;
  }

  querySelector(selector) {
    for (const child of this.children) {
      if (child._matches(selector)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }

  querySelectorAll(selector) {
    const out = [];
    for (const child of this.children) {
      if (child._matches(selector)) out.push(child);
      out.push(...child.querySelectorAll(selector));
    }
    return out;
  }
}

class FakeDocument {
  createElement(tag) {
    return new FakeNode(tag, this);
  }
}

const writableWidget = (overrides = {}) => ({
  datum_id: "a",
  args: { prompt: "A" },
  shell: { title: "A" },
  micros: [{ name: "choice", type: "text", required: true }],
  fill: {},
  runtime_state: {},
  semantic_validation: null,
  active: true,
  authoritative: true,
  access: { write: true },
  ...overrides,
});

test("every Packito callable leaves deterministic proof when invoked", () => {
  const checked = validateAppPack(packito, "packito");
  const documentRef = new FakeDocument();
  const shell = new FakeNode("section", documentRef);
  shell.setAttribute("data-thinkument-hai", "app_pack_mould_opinionation_v1");

  const notifications = new FakeNode("div", documentRef);
  shell.append(notifications);
  checked.callables.notification({
    documentRef,
    container: notifications,
    row: { eps_seq: 1, channel: "packito.global_notice", payload: { phase: "global" } },
    channel: "packito.global_notice",
  });
  checked.callables.widgetNotification({
    documentRef,
    container: notifications,
    row: { eps_seq: 2, channel: "packito.widget_notice", payload: { phase: "widget" } },
    channel: "packito.widget_notice",
  });
  assert.equal(
    shell.getAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.notification),
    "1",
  );
  assert.equal(
    shell.getAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.widgetNotification),
    "1",
  );

  let pageDefaultCalled = 0;
  checked.callables.page({
    shell,
    ctx: { heartbeat: { kind: "theta" }, view: { runtime_kind: "MANUALFILLNEEDEDSTEP" } },
    renderDefaultPage: () => { pageDefaultCalled += 1; },
  });
  assert.equal(pageDefaultCalled, 1);
  assert.equal(shell.getAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.page), "1");

  let outersDefaultCalled = 0;
  checked.callables.outers({
    shell,
    ctx: { view: { viewing_latest: true } },
    renderDefaultOuters: () => { outersDefaultCalled += 1; },
  });
  assert.equal(outersDefaultCalled, 1);
  assert.equal(shell.getAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.outers), "1");

  const widget = writableWidget({ renderer_key: "packito.unclaimed.fallback.v1" });
  const fallbackCard = checked.callables.widget({ documentRef, widget });
  assert.equal(
    fallbackCard.getAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.widget),
    "1",
  );

  const dedicatedCard = checked.widgetRenderers["packito.choice.v1"]({
    documentRef,
    widget: writableWidget({ renderer_key: "packito.choice.v1" }),
    api: {
      validateDispatch: () => ({ ok: true }),
      dispatch: async () => ({ ok: true }),
      presentLocalReceipt: () => {},
      presentDispatchResult: () => {},
    },
  });
  assert.equal(
    dedicatedCard.getAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.widget),
    null,
    "dedicated renderer must not masquerade as the generic widget callable",
  );

  const widgetsContainer = new FakeNode("section", documentRef);
  checked.callables.widgetsContainer({
    documentRef,
    container: widgetsContainer,
    widgets: [widget],
    ctx: { view: { step: { title: "Step" } } },
    renderWidgetCard: () => fallbackCard,
  });
  assert.equal(
    widgetsContainer.getAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.widgetsContainer),
    "1",
  );

  const noRead = checked.callables.noReadWidget({
    documentRef,
    widget,
    ctx: { session: { role: "auditor" } },
  });
  assert.equal(
    noRead.getAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.noReadWidget),
    "1",
  );

  const noWrite = checked.callables.noWriteWidget({
    documentRef,
    widget,
    ctx: { view: { viewing_latest: true } },
  });
  assert.equal(
    noWrite.getAttribute(PACKITO_CALLABLE_PROOF_ATTRIBUTES.noWriteWidget),
    "1",
  );
});

test("packito inspector retains the complete context but materializes full JSON lazily", async () => {
  const documentRef = new FakeDocument();
  const container = new FakeNode("div", documentRef);
  const ctx = {
    kind: "app_pack_mould_render_context_v1",
    heartbeat: { kind: "epsilon", canonical_cursor: 12 },
    session: { role: "maker" },
    app_pack: { id: "packito", args: { show_inspector: true } },
    state: { page_being_viewed: -1 },
    view: {
      requested_cursor: -1,
      resolved_cursor: 12,
      viewing_latest: true,
      retention_limited: false,
      runtime_kind: "MANUALFILLNEEDEDSTEP",
      scope: { span_id: "s" },
      step: { id: "step" },
      active_widget_ids: ["a"],
      widgets: [],
    },
    queue: {
      action_packets: [{ action: "STEP" }],
      open_trident: null,
    },
    womb: {
      access_table: [{ datum_id: "a", write: true }],
      role_modulation_receipt: null,
      latest_semantic_errors: null,
      funk_receipt: null,
      next_funkability: null,
      dispatch_timeline: [{ action: "STEP" }],
      session_metadata: { app_pack_mould: { app_pack: "packito" } },
    },
    theta: null,
    epsilon: { rows: [{ eps_seq: 1, channel: "datum.message" }] },
  };

  packito.outers.packito_inspector.render({
    documentRef,
    container,
    ctx,
    reason: { epsilon: true },
  });

  assert.equal(container[PACKITO_INSPECTOR_CONTEXT_PROPERTY], ctx);
  assert.equal(container.getAttribute("data-packito-outer-inspector-count"), "1");
  assert.equal(container.getAttribute("data-packito-outer-inspector-epsilon-count"), "1");
  const full = container.querySelector("[data-packito-inspector-json]");
  const compact = container.querySelector("[data-packito-inspector-summary]");
  const details = container.querySelector("[data-packito-inspector]");
  assert.ok(full);
  assert.ok(compact);
  assert.ok(details);
  assert.match(full.textContent, /Open this inspector to materialize/);
  assert.doesNotMatch(full.textContent, /dispatch_timeline/);
  assert.match(compact.textContent, /MANUALFILLNEEDEDSTEP/);

  details.open = true;
  await details.fire("toggle");
  assert.match(full.textContent, /dispatch_timeline/);
  assert.match(full.textContent, /session_metadata/);
  assert.equal(full.getAttribute("data-packito-materialized-cursor"), "12");
});


test("packito controls expose explicit historical navigation through the HAI state API", async () => {
  const documentRef = new FakeDocument();
  const container = new FakeNode("div", documentRef);
  const pageSelections = [];
  const api = {
    readHaiState: () => ({
      page_being_viewed: -1,
      snap_page_on_new_trident: true,
      silence_eps: false,
      silence_theta: false,
    }),
    setPageNumber: (value) => pageSelections.push(value),
    getSnapPageOnNewTrident: () => true,
    setSnapPageOnNewTrident: () => {},
    getSilenceEps: () => false,
    setSilenceEps: () => {},
    getSilenceTheta: () => false,
    setSilenceTheta: () => {},
  };

  packito.outers.packito_controls.render({
    documentRef,
    container,
    api,
    reason: { new_page: true, widget_refresh: true, epsilon: false },
  });

  assert.equal(container.getAttribute("data-packito-outer-controls-count"), "1");
  assert.equal(container.getAttribute("data-packito-outer-controls-new-page-count"), "1");
  assert.equal(container.getAttribute("data-packito-outer-controls-widget-refresh-count"), "1");
  assert.equal(container.getAttribute("data-packito-outer-controls-epsilon-count"), null);

  const history = container.querySelector('[data-packito-control="history"]');
  assert.ok(history);
  await history.click();
  assert.deepEqual(pageSelections, [0]);
});

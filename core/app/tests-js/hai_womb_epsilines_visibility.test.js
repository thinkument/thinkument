import assert from "node:assert/strict";
import test from "node:test";

import {
  renderDefaultHeartbeat,
} from "../src/ways_to_create/app_pack_mould/js/hai/dom.js";

class FakeNode {
  constructor(tag, documentRef) {
    this.tagName = String(tag).toUpperCase();
    this.ownerDocument = documentRef;
    this.children = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this.textContent = "";
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

  querySelector(selector) {
    // Basic attribute selector matching e.g. [data-hai-global-notifications] or [data-hai-widget-card][data-hai-widget-id="w_1"]
    const queue = [this];
    while (queue.length > 0) {
      const current = queue.shift();
      if (matchesSelector(current, selector)) return current;
      queue.push(...current.children);
    }
    return null;
  }
}

const matchesSelector = (node, selector) => {
  if (selector.includes("[data-hai-global-notifications]")) {
    return node.attributes.has("data-hai-global-notifications");
  }
  if (selector.includes("[data-hai-widget-card]")) {
    if (!node.attributes.has("data-hai-widget-card")) return false;
    const match = /data-hai-widget-id="([^"]+)"/.exec(selector);
    if (match) {
      return node.attributes.get("data-hai-widget-id") === match[1];
    }
    return true;
  }
  return false;
};

class FakeDocument {
  createElement(tag) {
    return new FakeNode(tag, this);
  }
}

test("HAI womb app fn routes inbound epsilon stream to appPack palette callables and mutates DOM in real-time", () => {
  const documentRef = new FakeDocument();
  const root = new FakeNode("div", documentRef);
  const shell = new FakeNode("main", documentRef);
  root.append(shell);

  // Setup DOM containers
  const globalNotifs = new FakeNode("div", documentRef);
  globalNotifs.setAttribute("data-hai-global-notifications", "true");
  shell.append(globalNotifs);

  const widgetCard1 = new FakeNode("article", documentRef);
  widgetCard1.setAttribute("data-hai-widget-card", "true");
  widgetCard1.setAttribute("data-hai-widget-id", "widget_alpha");
  shell.append(widgetCard1);

  // Track palette callable executions
  const recorded = {
    notifications: [],
    widgetNotifications: [],
    noReadEpsNotifications: [],
    onEpsRows: [],
    outersReasons: [],
  };

  const callables = {
    notification: ({ documentRef, container, row, channel }) => {
      recorded.notifications.push({ row, channel });
      const el = documentRef.createElement("div");
      el.textContent = `[GLOBAL ${channel}] ${row.payload?.message || "alert"}`;
      container.append(el);
    },
    widgetNotification: ({ documentRef, container, widget, row, channel }) => {
      recorded.widgetNotifications.push({ row, channel, widget });
      const el = documentRef.createElement("p");
      el.textContent = `[WIDGET ${row.datum_id}] ${channel}: ${row.payload?.percent}% (${row.payload?.step_name})`;
      container.append(el);
    },
    noReadEpsNotification: ({ documentRef, container, row, channel }) => {
      recorded.noReadEpsNotifications.push({ row, channel });
      const el = documentRef.createElement("span");
      el.textContent = `[OBFUSCATED ${channel}]`;
      container.append(el);
    },
    onEpsRow: ({ row, channel, routeResult }) => {
      recorded.onEpsRows.push({ row, channel, routeResult });
    },
    outers: ({ reason, renderDefaultOuters }) => {
      recorded.outersReasons.push(reason);
    },
  };

  const appPack = {
    id: "test.palette.v1",
    epsRoutes: {
      "asyncwork.announce": "global",
      "asyncwork.progress": "widget",
      "asyncwork.done": "widget",
    },
  };

  // Inbound epsilon packet simulated from live poll response
  const ctx = {
    heartbeat: { kind: "epsilon" },
    epsilon: {
      new_rows: [
        {
          channel: "asyncwork.announce",
          event_id: "eps_001",
          payload: { message: "Task async/01 scheduled on QUEUE_ASYNCWORK" },
          obfuscated: false,
        },
        {
          channel: "asyncwork.progress",
          datum_id: "widget_alpha",
          event_id: "eps_002",
          parent_ref: "async/01",
          payload: { percent: 50.0, step_name: "extract_features" },
          obfuscated: false,
        },
        {
          channel: "analytics.confidential_trace",
          datum_id: "widget_alpha",
          event_id: "eps_003",
          payload: { internal_counter: 99 },
          obfuscated: true,
        },
      ],
    },
    view: {
      widgets: [{ datum_id: "widget_alpha" }],
    },
  };

  // Execute heartbeat dispatch
  renderDefaultHeartbeat({ root, shell, ctx, api: {}, appPack, callables });

  // 1. Verify Global Notification
  assert.equal(recorded.notifications.length, 1);
  assert.equal(recorded.notifications[0].channel, "asyncwork.announce");
  assert.equal(globalNotifs.children.length, 2); // 1 global notification + 1 obfuscated notification
  assert.equal(
    globalNotifs.children[0].textContent,
    "[GLOBAL asyncwork.announce] Task async/01 scheduled on QUEUE_ASYNCWORK"
  );

  // 2. Verify Widget Notification
  assert.equal(recorded.widgetNotifications.length, 1);
  assert.equal(recorded.widgetNotifications[0].channel, "asyncwork.progress");
  assert.equal(recorded.widgetNotifications[0].widget?.datum_id, "widget_alpha");
  assert.equal(widgetCard1.children.length, 1);
  assert.equal(
    widgetCard1.children[0].textContent,
    "[WIDGET widget_alpha] asyncwork.progress: 50% (extract_features)"
  );

  // 3. Verify Obfuscated Notification
  assert.equal(recorded.noReadEpsNotifications.length, 1);
  assert.equal(recorded.noReadEpsNotifications[0].channel, "analytics.confidential_trace");
  assert.equal(globalNotifs.children[1].textContent, "[OBFUSCATED analytics.confidential_trace]");

  // 4. Verify Universal Audit Dispatch (onEpsRow receives all 3 events)
  assert.equal(recorded.onEpsRows.length, 3);
  assert.deepEqual(
    recorded.onEpsRows.map((item) => item.channel),
    ["asyncwork.announce", "asyncwork.progress", "analytics.confidential_trace"]
  );

  // 5. Verify Outers Lifecycle Notification
  assert.equal(recorded.outersReasons.length, 1);
  assert.deepEqual(recorded.outersReasons[0], {
    new_page: false,
    widget_refresh: false,
    epsilon: true,
  });
});

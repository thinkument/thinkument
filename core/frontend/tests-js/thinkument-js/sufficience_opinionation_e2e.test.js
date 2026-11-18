import assert from "node:assert/strict";
import test from "node:test";

import {
  createThinkumentApp,
} from "../../src/live_vial/_js/thinkumentJS/platform/app.js";
import {
  emptyFrontState,
} from "../../src/live_vial/_js/thinkumentJS/platform/_backend_events/digest.js";
import {
  createOpinionation,
} from "../../src/live_vial/_js/thinkumentJS/test_opinionations/sufficience.js";

const selectorAttributes = (selector) => {
  const matches = [...String(selector).matchAll(
    /\[([^\]=]+)(?:="([^"]*)")?\]/g,
  )];
  if (!matches.length) {
    throw new Error(`fake DOM only supports attribute selectors: ${selector}`);
  }
  return matches.map((match) => ({
    name: match[1],
    value: match[2] ?? null,
  }));
};

class FakeElement {
  constructor(tagName, ownerDocument) {
    this.tagName = String(tagName).toUpperCase();
    this.ownerDocument = ownerDocument;
    this.parentNode = null;
    this.children = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this._text = "";
    this.value = "";
    this.checked = false;
    this.disabled = false;
    this.type = "";
  }

  setAttribute(name, value) {
    this.attributes.set(String(name), String(value));
  }

  getAttribute(name) {
    return this.attributes.has(String(name))
      ? this.attributes.get(String(name))
      : null;
  }

  append(...nodes) {
    for (const node of nodes) {
      if (!node) continue;
      node.parentNode = this;
      this.children.push(node);
    }
  }

  appendChild(node) {
    this.append(node);
    return node;
  }

  replaceChildren(...nodes) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this._text = "";
    this.append(...nodes);
  }

  set textContent(value) {
    this.children = [];
    this._text = String(value ?? "");
  }

  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join("");
  }

  addEventListener(kind, listener) {
    const key = String(kind);
    const rows = this.listeners.get(key) ?? [];
    rows.push(listener);
    this.listeners.set(key, rows);
  }

  async click() {
    for (const listener of this.listeners.get("click") ?? []) {
      await listener({
        type: "click",
        target: this,
        currentTarget: this,
        preventDefault() {},
      });
    }
  }

  _matches(selector) {
    return selectorAttributes(selector).every(({ name, value }) => {
      if (!this.attributes.has(name)) return false;
      return value === null || this.attributes.get(name) === value;
    });
  }

  querySelectorAll(selector) {
    const out = [];
    const visit = (node) => {
      for (const child of node.children) {
        if (child._matches(selector)) out.push(child);
        visit(child);
      }
    };
    visit(this);
    return out;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] ?? null;
  }
}

class FakeDocument {
  createElement(tagName) {
    return new FakeElement(tagName, this);
  }
}

const activeU = ({
  note = null,
  score = null,
} = {}) => ({
  kind: "MANUALFILLNEEDEDSTEP",
  form_id: "form",
  app_form_id: "form",
  current_frame_id: "frame",
  current_frame_name: "Frame",
  current_span: "span",
  current_span_id: "span",
  step: {
    public_step_name: "compose",
  },
  datum_widgets_on_this_span: ["note", "score"],
  datum_states_on_this_span: [
    {
      kind: "universal_ui_datum_state_v1",
      datum_id: "note",
      is_authoritative: true,
      is_pending: true,
      enabled: true,
      roles: ["maker"],
      args: {
        placeholder: "note",
      },
      shell: {
        id: "note",
        micros: [{
          name: "text",
          type: "text",
          required: true,
          validators: [{
            kind: "semantic-validator",
          }],
        }],
      },
      micros: [{
        name: "text",
        type: "text",
        required: true,
        validators: [{
          kind: "semantic-validator",
        }],
      }],
      fill: {
        text: note,
      },
      has_fill: note !== null,
      lifecycle: {
        runtime: {
          state: {
            backend_counter: note === null ? 0 : 1,
          },
        },
      },
    },
    {
      kind: "universal_ui_datum_state_v1",
      datum_id: "score",
      is_authoritative: true,
      is_pending: true,
      enabled: true,
      roles: ["maker"],
      shell: {
        id: "score",
        micros: [{
          name: "value",
          type: "integer",
          required: true,
        }],
      },
      micros: [{
        name: "value",
        type: "integer",
        required: true,
      }],
      fill: {
        value: score,
      },
      has_fill: score !== null,
      lifecycle: {
        runtime: {
          state: {
            backend_counter: score === null ? 0 : 1,
          },
        },
      },
    },
    {
      kind: "role_mismatch_obfuscated_datum_v1",
      datum_id: "secret",
      role_mismatch_obfuscated: true,
      is_pending: true,
      enabled: true,
    },
  ],
  session_metadata: {
    roles: {
      maker: {
        read_roles: [],
      },
      reviewer: {
        read_roles: [],
      },
    },
  },
  role_mismatch_modulation_info: {
    kind: "role_mismatch_modulation_info_v1",
    role_viewing: "maker",
    assignments: {
      note: ["maker"],
      score: ["maker"],
      secret: ["reviewer"],
    },
    mismatch_datum_ids: ["secret"],
  },
});

const controller = ({
  seq,
  phase,
  dispatchId,
  action,
  U,
  A,
}) => ({
  kind: "controller_loop_event_v1",
  event_seq: seq,
  event_id: `e${seq}`,
  dispatch_id: dispatchId,
  dispatcher_identity_id: "device",
  dispatcher_role: "maker",
  phase,
  action,
  payload: {
    U,
    A,
    fill: A.fill,
    signal: A.signal,
    outcome: "success",
    ...(phase === "end"
      ? {
        result: {
          event_kind: U.kind,
          ui_mode: "FORM_FILL",
          finished: false,
          last_error: null,
        },
      }
      : {}),
  },
});

const byAttrs = (root, attrs) => root.querySelector(
  Object.entries(attrs)
    .map(([name, value]) => `[${name}="${value}"]`)
    .join(""),
);

const buildHarness = async ({ initialU = activeU() } = {}) => {
  const documentRef = new FakeDocument();
  const root = new FakeElement("div", documentRef);
  const sent = [];
  const epsilonSnapshots = [];
  const events = [];
  let latest = 0;
  let stateU = structuredClone(initialU);

  const portal = {
    identityId: "device",

    async enquire() {
      return {
        latest_event_seq: latest,
      };
    },

    async pull({ afterEventSeq }) {
      const visible = events.filter(
        (event) => event.event_seq > afterEventSeq,
      );
      return {
        kind: "live_session_events_since_v1",
        events: visible,
        after_event_seq: afterEventSeq,
        next_after_event_seq: latest,
        session_latest_event_seq: latest,
        scanned_through_event_seq: latest,
        canonical_gap_detected: false,
        visibility_receipt: {
          kind: "live_session_event_visibility_receipt_v1",
          hidden_event_count: 0,
          reason: "none",
        },
      };
    },

    async pullEps({ afterSeq = 0 } = {}) {
      return {
        kind: "thinkument_eps_page_v1",
        after_seq: afterSeq,
        next_after_seq: afterSeq,
        eps_head: afterSeq,
        rows: [],
      };
    },

    async dispatch(packet, { funked, onEpsPage }) {
      sent.push({
        packet: structuredClone(packet),
        funked,
      });

      const epsNext = (app.readQ().eps_cursor || 0) + 1;
      await onEpsPage({
        kind: "thinkument_eps_page_v1",
        after_seq: epsNext - 1,
        next_after_seq: epsNext,
        eps_head: epsNext,
        rows: [{
          kind: "thinkument_eps_row_v1",
          eps_seq: epsNext,
          event_id: `ev-${epsNext}`,
          channel: "datum.message",
          request_id: packet.request_id,
          datum_id: "note",
          payload: {
            message: {
              level: "info",
              text: "working",
            },
          },
        }],
      });
      epsilonSnapshots.push(root.textContent);

      const A = {
        fill: packet.user_fill ?? {},
        signal: packet.user_signal ?? null,
      };
      const before = structuredClone(stateU);
      const dispatchId = packet.request_id;

      events.push(controller({
        seq: ++latest,
        phase: "start",
        dispatchId,
        action: packet.action,
        U: before,
        A,
      }));

      if (packet.action === "STEP") {
        const next = structuredClone(stateU);
        for (const row of next.datum_states_on_this_span ?? []) {
          const fill = packet.user_fill?.[row.datum_id];
          if (fill && typeof fill === "object") {
            row.fill = {
              ...(row.fill ?? {}),
              ...fill,
            };
            row.has_fill = true;
            if (row.lifecycle?.runtime?.state) {
              row.lifecycle.runtime.state.backend_counter += 1;
            }
          }
        }
        stateU = next;
      }

      events.push(controller({
        seq: ++latest,
        phase: "end",
        dispatchId,
        action: packet.action,
        U: structuredClone(stateU),
        A,
      }));

      return {
        request_id: packet.request_id,
        rejected: false,
        dispatch_outcome: "applied",
        write_committed: packet.action === "STEP",
        dispatch_concurrency: {
          after_event_seq: latest,
        },
      };
    },
  };

  const opinionation = createOpinionation({
    root,
    config: {
      role: "maker",
    },
  });

  const app = createThinkumentApp({
    sessionId: "s",
    identityId: "device",
    role: "maker",
    portal,
    initialQ: emptyFrontState("s", {
      cursor: 0,
      latestU: initialU,
    }),
    initialX: opinionation.initialX,
    informationDisseminationFn: opinionation.drink,
  });

  await app.start();
  await opinionation.onBoot({
    root,
    loopback: app.loopback,
    config: {
      role: "maker",
    },
  });

  return {
    app,
    root,
    sent,
    epsilonSnapshots,
    close: async () => {
      app.stop();
      await opinionation.dispose();
    },
  };
};

test(
  "sufficience opinionation reaches the normalized STEP/UNDO/REDO action space",
  async () => {
    const harness = await buildHarness();
    const {
      app,
      root,
      sent,
      epsilonSnapshots,
    } = harness;

    try {
      assert.match(
        root.querySelector("[data-sufficience-packet]").textContent,
        /thinkument_sufficience_boot_blanket_v1/,
      );
      assert.equal(
        root.querySelectorAll("[data-sufficience-datum]").length,
        2,
      );
      assert.equal(
        byAttrs(root, {
          "data-sufficience-datum": "secret",
        }),
        null,
      );

      const noteInclude = byAttrs(root, {
        "data-sufficience-micro-include": "1",
        "data-datum-id": "note",
        "data-micro-name": "text",
      });
      const noteEditor = byAttrs(root, {
        "data-sufficience-micro-value": "1",
        "data-datum-id": "note",
        "data-micro-name": "text",
      });
      const scoreInclude = byAttrs(root, {
        "data-sufficience-micro-include": "1",
        "data-datum-id": "score",
        "data-micro-name": "value",
      });
      const scoreEditor = byAttrs(root, {
        "data-sufficience-micro-value": "1",
        "data-datum-id": "score",
        "data-micro-name": "value",
      });

      noteInclude.checked = true;
      noteEditor.value = '"hello"';
      scoreInclude.checked = true;
      scoreEditor.value = "7";

      root.querySelector(
        "[data-sufficience-signal-include]",
      ).checked = true;
      root.querySelector(
        "[data-sufficience-signal-datum]",
      ).value = "note";
      root.querySelector(
        "[data-sufficience-signal-kind]",
      ).value = "explain";
      root.querySelector(
        "[data-sufficience-signal-info]",
      ).value = '{"why":"test"}';
      root.querySelector(
        "[data-sufficience-funked]",
      ).checked = true;
      root.querySelector(
        "[data-sufficience-request-id]",
      ).value = "r-step";

      await byAttrs(root, {
        "data-sufficience-action": "STEP",
      }).click();

      assert.equal(sent.length, 1);
      assert.equal(sent[0].funked, true);
      assert.equal(sent[0].packet.action, "STEP");
      assert.equal(sent[0].packet.request_id, "r-step");
      assert.deepEqual(
        sent[0].packet.user_fill,
        {
          note: { text: "hello" },
          score: { value: 7 },
        },
      );
      assert.deepEqual(
        sent[0].packet.user_signal,
        {
          datum_id: "note",
          kind: "explain",
          info: { why: "test" },
        },
      );

      assert.ok(
        epsilonSnapshots.some((snapshot) => snapshot.includes("working")),
      );
      assert.match(
        root.querySelector("[data-sufficience-packet]").textContent,
        /"kind": "theta"/,
      );
      assert.equal(
        app.readQ()
          .latest_U
          .datum_states_on_this_span[0]
          .lifecycle
          .runtime
          .state
          .backend_counter,
        1,
      );

      await byAttrs(root, {
        "data-sufficience-action": "UNDO",
      }).click();
      await byAttrs(root, {
        "data-sufficience-action": "REDO",
      }).click();

      assert.deepEqual(
        sent.slice(1).map((row) => row.packet.action),
        ["UNDO", "REDO"],
      );
      for (const row of sent.slice(1)) {
        assert.equal(
          Object.hasOwn(row.packet, "user_fill"),
          false,
        );
        assert.equal(
          Object.hasOwn(row.packet, "user_signal"),
          false,
        );
      }
    } finally {
      await harness.close();
    }
  },
);

test(
  "sufficience exact-A diagnostic control reaches the same public loopback guard",
  async () => {
    const harness = await buildHarness();
    const { root, sent } = harness;

    try {
      const exactA = root.querySelector(
        "[data-sufficience-exact-action]",
      );
      const dispatchExact = root.querySelector(
        "[data-sufficience-exact-action-dispatch]",
      );

      exactA.value = JSON.stringify({
        action: "STEP",
        userFill: {
          secret: {
            text: "not visible to maker",
          },
        },
        userSignal: null,
        requestId: "hidden-target",
      });

      await dispatchExact.click();

      assert.equal(sent.length, 0);
      const receipt = JSON.parse(
        root.querySelector(
          "[data-sufficience-local-receipt]",
        ).textContent,
      );
      assert.equal(
        receipt.kind,
        "thinkument_outbound_dispatch_validation_v1",
      );
      assert.equal(receipt.ok, false);
      assert.ok(
        receipt.errors.some((row) => row.code === "write_role_denied"),
      );
    } finally {
      await harness.close();
    }
  },
);

test(
  "sufficience opinionation preserves the empty mount STEP and rejects malformed JSON locally",
  async () => {
    const harness = await buildHarness({
      initialU: {
        kind: "ATSTART",
      },
    });
    const { root, sent } = harness;

    try {
      await byAttrs(root, {
        "data-sufficience-action": "STEP",
      }).click();

      assert.equal(sent.length, 1);
      assert.equal(sent[0].packet.action, "STEP");
      assert.deepEqual(sent[0].packet.user_fill, {});
      assert.equal(sent[0].packet.user_signal, null);

      // Rebuild a normal active station to prove malformed dead-JSON never
      // reaches transport. This uses a fresh harness because canonical truth,
      // not test DOM mutation, owns the active shell.
    } finally {
      await harness.close();
    }

    const activeHarness = await buildHarness();
    try {
      const include = byAttrs(activeHarness.root, {
        "data-sufficience-micro-include": "1",
        "data-datum-id": "score",
        "data-micro-name": "value",
      });
      const editor = byAttrs(activeHarness.root, {
        "data-sufficience-micro-value": "1",
        "data-datum-id": "score",
        "data-micro-name": "value",
      });
      include.checked = true;
      editor.value = "not-json";

      await byAttrs(activeHarness.root, {
        "data-sufficience-action": "STEP",
      }).click();

      assert.equal(activeHarness.sent.length, 0);
      assert.match(
        activeHarness.root.querySelector(
          "[data-sufficience-local-receipt]",
        ).textContent,
        /must be a JSON literal/,
      );
    } finally {
      await activeHarness.close();
    }
  },
);

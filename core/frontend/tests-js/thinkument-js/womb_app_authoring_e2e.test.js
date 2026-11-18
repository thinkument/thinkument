import assert from "node:assert/strict";
import test from "node:test";

import {
  createThinkumentApp,
} from "../../src/live_vial/_js/thinkumentJS/platform/app.js";
import {
  createWombRuntime,
} from "../../src/live_vial/_js/thinkumentJS/womb.js";
import {
  defaultPluginFactory,
} from "../../src/live_vial/_js/thinkumentJS/wrapper_shim.js";

const activeU = (value = null) => ({
  kind: "MANUALFILLNEEDEDSTEP",
  form_id: "form",
  app_form_id: "form",
  current_frame_id: "frame",
  current_frame_name: "Frame",
  current_span: "span",
  current_span_id: "span",
  step: {
    public_step_name: "note_step",
  },
  datum_widgets_on_this_span: ["note"],
  datum_states_on_this_span: [{
    kind: "universal_ui_datum_state_v1",
    datum_id: "note",
    is_authoritative: true,
    is_pending: true,
    enabled: true,
    roles: ["maker"],
    args: {
      placeholder: "Write a note",
    },
    shell: {
      id: "note",
      micros: [{
        name: "text",
        type: "text",
        required: true,
      }],
    },
    micros: [{
      name: "text",
      type: "text",
      required: true,
    }],
    fill: value,
    has_fill: value !== null,
    semantic_validation: {
      datum_validator_fields: {},
      micros: [],
    },
    lifecycle: {
      runtime: {
        state: {
          renders: value === null ? 0 : 1,
        },
      },
    },
  }],
  datum_widget_fills: {
    note: value,
  },
  session_metadata: {
    roles: {
      maker: {
        read_roles: [],
      },
    },
  },
  role_mismatch_modulation_info: {
    kind: "role_mismatch_modulation_info_v1",
    role_viewing: "maker",
    assignments: {
      note: ["maker"],
    },
    mismatch_datum_ids: [],
  },
});

const controller = (seq, phase, dispatchId, U, A) => ({
  kind: "controller_loop_event_v1",
  event_seq: seq,
  event_id: `e${seq}`,
  dispatch_id: dispatchId,
  dispatcher_identity_id: "device",
  dispatcher_role: "maker",
  phase,
  action: "STEP",
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

test(
  "one custom womb can render theta/epsilon, retain X, validate dispatch, "
  + "and install later substrate loopbacks",
  async () => {
    let latest = 0;
    let epsSeq = 0;
    let value = null;
    const events = [];
    const epsRows = [];
    const substrate = {
      renders: [],
      progress: [],
      onSubmit: null,
    };

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
        const rows = epsRows.filter((row) => row.eps_seq > afterSeq);
        return {
          kind: "thinkument_eps_page_v1",
          after_seq: afterSeq,
          next_after_seq: epsSeq,
          eps_head: epsSeq,
          rows,
        };
      },

      async dispatch(packet, { onEpsPage }) {
        const row = {
          kind: "thinkument_eps_row_v1",
          eps_seq: ++epsSeq,
          event_id: `live-${epsSeq}`,
          emitted_at: "2026-09-04T00:00:00Z",
          channel: "datum.message",
          visibility: "all-with-modulation",
          content_hash: `hash-${epsSeq}`,
          theta_event_seq_at_emit: latest,
          emitter_origin: "widget_explosion",
          request_id: packet.request_id,
          trident_dispatch_id: packet.request_id,
          obfuscated: false,
          form_id: "form",
          frame_id: "frame",
          span_id: "span",
          datum_id: "note",
          payload: {
            message: {
              level: "info",
              text: "working",
            },
          },
        };
        epsRows.push(row);

        await onEpsPage({
          kind: "thinkument_eps_page_v1",
          after_seq: epsSeq - 1,
          next_after_seq: epsSeq,
          eps_head: epsSeq,
          rows: [row],
        });

        const A = {
          fill: packet.user_fill ?? {},
          signal: packet.user_signal ?? null,
        };
        const before = latest === 0
          ? { kind: "ATSTART" }
          : activeU(value);

        events.push(
          controller(++latest, "start", packet.request_id, before, A),
        );

        if (packet.user_fill?.note) {
          value = packet.user_fill.note;
        }

        events.push(
          controller(
            ++latest,
            "end",
            packet.request_id,
            activeU(value),
            A,
          ),
        );

        return {
          request_id: packet.request_id,
          rejected: false,
          dispatch_outcome: "applied",
          write_committed: Boolean(packet.user_fill?.note),
        };
      },
    };

    const heartbeats = [];

    const app = createThinkumentApp({
      sessionId: "s",
      identityId: "device",
      role: "maker",
      portal,
      initialX: {
        theta: 0,
        epsilon: 0,
        selected: null,
      },

      informationDisseminationFn: async (packet, loopback) => {
        const W = createWombRuntime(packet, loopback);
        heartbeats.push(W.heartbeat());

        if (W.isEpsilon()) {
          substrate.progress.push(
            ...W.epsNewRows().map(
              (row) => row.payload?.message?.text,
            ),
          );
          return {
            X: {
              ...W.X(),
              epsilon: W.X().epsilon + 1,
            },
          };
        }

        substrate.renders.push({
          cursor: W.Q().cursor,
          active: W.activeWidgetIds(),
          step:
            W.currentStep()?.public_step_name
            ?? null,
          dispatchCount:
            W.dispatchTimeline().length,
          placeholder: W.hasWidget("note")
            ? W.widgetArgs("note").placeholder
            : null,
          pollHidden:
            W.thetaPollPage()?.visibility_receipt
              ?.hidden_event_count ?? null,
        });

        const candidate = {
          action: "STEP",
          userFill: {
            note: {
              text: "from substrate",
            },
          },
          requestId: "from-substrate",
        };

        if (W.runtimeKind() === "MANUALFILLNEEDEDSTEP") {
          assert.equal(
            loopback.validateDispatch(candidate).ok,
            true,
          );

          substrate.onSubmit = async () => {
            await loopback.writeX((X) => ({
              ...X,
              selected: "note",
            }));
            return loopback.dispatch(candidate);
          };
        }

        return {
          X: {
            ...W.X(),
            theta: W.X().theta + 1,
          },
          receipt: {
            kind: "example_womb_theta_receipt_v1",
            cursor: W.Q().cursor,
          },
        };
      },
    });

    await app.loopback.dispatch({
      action: "STEP",
      requestId: "mount",
    });

    assert.ok(heartbeats.includes("epsilon"));
    assert.ok(heartbeats.includes("theta"));
    assert.equal(
      substrate.renders.at(-1).active[0],
      "note",
    );
    assert.equal(
      substrate.renders.at(-1).placeholder,
      "Write a note",
    );
    assert.equal(
      substrate.renders.at(-1).step,
      "note_step",
    );
    assert.equal(
      substrate.renders.at(-1).dispatchCount,
      1,
    );
    assert.equal(
      substrate.renders.at(-1).pollHidden,
      0,
    );
    assert.ok(substrate.progress.includes("working"));
    assert.equal(typeof substrate.onSubmit, "function");

    const result = await substrate.onSubmit();
    assert.equal(result.dispatch_outcome, "applied");

    assert.deepEqual(
      app.loopback.readQ().latest_U.datum_widget_fills.note,
      { text: "from substrate" },
    );
    assert.equal(app.loopback.readX().selected, "note");
    assert.ok(app.loopback.readX().theta >= 2);
    assert.ok(app.loopback.readX().epsilon >= 2);
    assert.equal(
      substrate.renders.at(-1).dispatchCount,
      2,
    );
  },
);

class _TestDomNode {
  constructor(documentRef, tag = "div") {
    this.ownerDocument = documentRef;
    this.tag = tag;
    this.attributes = {};
    this.children = [];
    this.textContent = "";
    this.value = "";
    this.checked = false;
    this.type = "";
    this.listeners = new Map();
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  append(...nodes) {
    this.children.push(...nodes);
  }

  replaceChildren(...nodes) {
    this.children = [...nodes];
  }

  addEventListener(name, callback) {
    this.listeners.set(name, callback);
  }

  querySelector() {
    return null;
  }
}

const createTestDomRoot = () => {
  const documentRef = {
    createElement(tag) {
      return new _TestDomNode(documentRef, tag);
    },
  };
  return new _TestDomNode(documentRef, "root");
};

test(
  "wrapper shim imports and constructs the launch-selected sufficience opinionation",
  async () => {
    const moduleUrl = new URL(
      "../../src/live_vial/_js/thinkumentJS/test_opinionations/sufficience.js",
      import.meta.url,
    ).href;
    const root = createTestDomRoot();
    const config = {
      role: "maker",
      modules: {
        opinionation: moduleUrl,
      },
    };

    const plugins = await defaultPluginFactory({
      root,
      config,
    });

    assert.equal(plugins.root, root);
    assert.equal(
      plugins.opinionation.kind,
      "thinkument_front_opinionation_v2",
    );
    assert.deepEqual(plugins.opinionation.initialX, {});

    const Q = {
      kind: "thinkument_front_queue_v1",
      cursor: 0,
      latest_U: activeU(null),
    };
    const loopback = {
      readQ: () => Q,
      readX: () => ({}),
      validateDispatch: () => ({ ok: true }),
      dispatch: async (A) => ({ ok: true, action: A.action }),
    };

    await plugins.opinionation.onBoot({ loopback });

    assert.equal(root.children.length, 1);
    assert.equal(
      root.children[0].attributes["data-thinkument-sufficience"],
      "thinkument_test_sufficience_opinionation_v1",
    );
  },
);

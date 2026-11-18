import assert from "node:assert/strict";
import test from "node:test";

import {
  createWombRuntime,
  KeyErrorForWombDatum,
  ObfuscatedWombDatumError,
} from "../../src/live_vial/_js/thinkumentJS/womb.js";

const U = {
  kind: "MANUALFILLNEEDEDSTEP",
  form_id: "form",
  app_form_id: "app",
  current_frame_id: "frame",
  current_frame_name: "Frame",
  current_span: "span",
  current_span_id: "span",
  step: {
    public_step_name: "one",
    source_step_fn: "step_one",
  },
  globals: {
    application_mode: "test",
  },
  state: {
    forms_emitted_order: ["one"],
  },
  tags: [
    "frontend-data-blanket",
  ],
  datum_widgets_on_this_span: ["note"],
  datum_states_on_this_span: [
    {
      kind: "universal_ui_datum_state_v1",
      datum_id: "note",
      is_authoritative: true,
      is_pending: true,
      enabled: true,
      args: {
        placeholder: "Say something",
        __kernel: { private_to_widget_authors: true },
      },
      shell: {
        id: "note",
        micros: [
          {
            name: "text",
            type: "text",
            required: true,
          },
        ],
      },
      micros: [
        {
          name: "text",
          type: "text",
          required: true,
        },
      ],
      fill: { text: null },
      semantic_validation: {
        datum_validator_fields: {},
        micros: [],
      },
      lifecycle: {
        runtime: {
          state: {
            phase: "draft",
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
      maker: { read_roles: [] },
    },
    provenance: {
      app_table_manifest: {
        steps: [
          { public_step_name: "one" },
        ],
      },
    },
  },
  role_mismatch_modulation_info: {
    role_viewing: "maker",
    assignments: {
      note: ["maker"],
      secret: ["reviewer"],
    },
    mismatch_datum_ids: ["secret"],
    receipt: {
      kind: "role_mismatch_activity_receipt_v1",
    },
  },
  multiframespec: {
    app_form_id: "app",
  },
  last_error: null,
};

const trident = {
  local_id: "dispatch:d1",
  projected: false,
  dispatch_id: "d1",
  dispatcher_identity_id: "maker-1",
  dispatcher_role: "maker",
  action: "STEP",
  status: "success",
  start: {
    event_seq: 1,
    payload: {
      U: structuredClone(U),
      A: {
        fill: {},
        signal: null,
      },
    },
  },
  end: {
    event_seq: 2,
    payload: {
      U: structuredClone(U),
      A: {
        fill: {
          note: { text: "hello" },
        },
        signal: null,
      },
      dispatch_context: {
        filler_receipt: {
          kind: "chainreactionTM_filler_receipt_v1",
          next_U_funkability: {
            kind: "chainreactionTM_next_U_funkability_v1",
            will_funk_next_dispatch: false,
            reason: "program_complete_or_not_manual",
          },
        },
      },
    },
  },
};

const sampleEpsRow = {
  kind: "thinkument_eps_row_v1",
  eps_seq: 1,
  event_id: "ev-1",
  channel: "datum.message",
  emitted_at: "2026-11-08T00:00:00Z",
  content_hash: "hash-1",
  visibility: "all-with-modulation",
  theta_event_seq_at_emit: 0,
  emitter_origin: "widget_explosion",
  request_id: "r1",
  trident_dispatch_id: "d1",
  obfuscated: false,
  datum_id: "note",
  frame_id: "frame",
  span_id: "span",
  form_id: "form",
  payload: {
    message: {
      text: "working",
    },
  },
};

const Q = {
  kind: "thinkument_front_state_v1",
  session_id: "s",
  cursor: 2,
  eps_cursor: 1,
  eps_head: 1,
  eps_rows: [sampleEpsRow],
  latest_U: U,
  open_action: null,
  actions: [trident],
  interruptions: [],
  orphan_ends: [],
  canonical_gap_count: 0,
  bootstrap: null,
};

const packet = {
  kind: "thinkument_information_inbound_v1",
  trigger: {
    kind: "theta",
    canonical: true,
    provisional: false,
    reason: "backend_events",
  },
  context: {
    session_id: "s",
    identity_id: "maker-1",
    role: "maker",
    Q,
    X: {
      selected: "note",
    },
  },
  information: {
    kind: "thinkument_theta_information_v1",
    oldQ: {
      ...Q,
      cursor: 0,
      actions: [],
    },
    newQ: Q,
    newEvents: [
      { event_seq: 1 },
      { event_seq: 2 },
    ],
    pollPage: {
      events: [
        { event_seq: 1 },
        { event_seq: 2 },
      ],
      after_event_seq: 0,
      next_after_event_seq: 2,
      session_latest_event_seq: 2,
      canonical_gap_detected: false,
      visibility_receipt: {
        hidden_event_count: 0,
      },
    },
    reason: "backend_events",
  },
};

const loopback = Object.freeze({
  kind: "thinkument_outbound_v1",
  readQ: () => Q,
  readX: () => ({ selected: "note" }),
  writeX: async (X) => X,
  validateDispatch: (A) => ({
    kind: "thinkument_outbound_dispatch_validation_v1",
    ok: A.userSignal?.datum_id === "note",
    errors: A.userSignal?.datum_id === "note"
      ? []
      : [{ code: "write_role_denied" }],
  }),
  dispatch: async () => ({ dispatch_outcome: "applied" }),
});

test("womb sugars cover the complete current semantic blanket", () => {
  const W = createWombRuntime(packet, loopback);

  assert.equal(W.heartbeat(), "theta");
  assert.equal(W.rawPacket().kind, "thinkument_information_inbound_v1");
  assert.equal(W.information().kind, "thinkument_theta_information_v1");
  assert.equal(W.thetaOldQ().cursor, 0);
  assert.equal(W.thetaNewQ().cursor, 2);
  assert.equal(W.runtimeKind(), "MANUALFILLNEEDEDSTEP");
  assert.equal(
    W.currentStep().public_step_name,
    "one",
  );
  assert.equal(
    W.semanticContext().step.public_step_name,
    "one",
  );
  assert.equal(
    W.semanticContext()
      .session_metadata
      .roles
      .maker
      .read_roles
      .length,
    0,
  );
  assert.equal(
    W.semanticContext().scope.span_id,
    "span",
  );
  assert.deepEqual(W.activeWidgetIds(), ["note"]);
  assert.equal(W.widgetsOnSpan().length, 2);
  assert.equal(W.readableWidgetsOnSpan().length, 1);

  assert.deepEqual(
    W.widgetArgs("note"),
    { placeholder: "Say something" },
  );
  assert.deepEqual(
    W.widgetRuntimeState("note"),
    { phase: "draft" },
  );
  assert.equal(W.widgetMicros("note")[0].name, "text");
  assert.equal(
    W.roleModulationReceipt().kind,
    "role_mismatch_activity_receipt_v1",
  );

  assert.deepEqual(
    W.roleReadProjection().obfuscated_widget_ids,
    ["secret"],
  );
  assert.deepEqual(
    W.roleReadProjection().mismatch_datum_ids,
    ["secret"],
  );
  assert.deepEqual(
    W.roleReadProjection().readable_widget_ids,
    ["note"],
  );

  assert.equal(W.accessForWidget("note").readable, true);
  assert.equal(W.accessForWidget("note").write, true);
  assert.equal(W.accessForWidget("secret").readable, false);
  assert.equal(W.accessForWidget("secret").write, false);

  assert.equal(W.tridents().length, 1);
  assert.equal(W.dispatchTimeline().length, 1);
  assert.equal(
    W.dispatchTimeline()[0]
      .source
      .step
      .public_step_name,
    "one",
  );
  assert.equal(
    W.dispatchTimeline()[0]
      .continuous_from_previous,
    null,
  );
  assert.deepEqual(
    W.actionPackets()[0].fill,
    { note: { text: "hello" } },
  );
  assert.deepEqual(
    W.dispatchForTrident(W.latestTrident()).A.fill,
    { note: { text: "hello" } },
  );
  assert.equal(
    W.nextFunkability().will_funk_next_dispatch,
    false,
  );

  assert.equal(
    W.thetaPollPage().visibility_receipt.hidden_event_count,
    0,
  );
  assert.equal(W.newCanonicalEvents().length, 2);

  // Eps correlation sugars work on both theta and epsilon heartbeats!
  assert.equal(W.epsCursor(), 1);
  assert.equal(W.epsHead(), 1);
  assert.equal(W.epsRows().length, 1);
  assert.equal(W.epsRowsForRequest("r1").length, 1);
  assert.equal(W.epsRowsForTrident("d1").length, 1);
  assert.equal(W.epsRowsForLatestTrident().length, 1);
  assert.equal(W.epsRowsForDatum("note").length, 1);

  assert.throws(
    () => W.widget("missing"),
    KeyErrorForWombDatum,
  );
  assert.throws(
    () => W.widgetArgs("secret"),
    ObfuscatedWombDatumError,
  );
});

test("active membership preserves absent versus empty", () => {
  const completionPacket = structuredClone(packet);
  completionPacket.context.Q.latest_U = {
    kind: "ATCOMPLETION",
  };
  completionPacket.information.newQ =
    completionPacket.context.Q;

  const completion = createWombRuntime(
    completionPacket,
    loopback,
  );
  assert.equal(completion.activeWidgetIds(), null);

  const redactedPacket = structuredClone(packet);
  redactedPacket.context.Q.latest_U.datum_widgets_on_this_span = [];
  redactedPacket.information.newQ =
    redactedPacket.context.Q;

  const redacted = createWombRuntime(
    redactedPacket,
    loopback,
  );
  assert.deepEqual(redacted.activeWidgetIds(), []);
});

test(
  "dispatch timeline exposes every retained A and proves adjacent U continuity",
  () => {
    const first = structuredClone(trident);
    first.local_id = "dispatch:d1";
    first.dispatch_id = "d1";
    first.start.event_seq = 1;
    first.end.event_seq = 2;

    const sharedBoundaryU = structuredClone(U);
    sharedBoundaryU.step = {
      public_step_name: "two",
    };
    sharedBoundaryU.current_span = "span-two";
    sharedBoundaryU.current_span_id = "span-two";

    first.end.payload.U =
      structuredClone(sharedBoundaryU);

    const second = structuredClone(trident);
    second.local_id = "dispatch:d2";
    second.dispatch_id = "d2";
    second.start.event_seq = 3;
    second.end.event_seq = 4;
    second.start.payload.U =
      structuredClone(sharedBoundaryU);
    second.start.payload.A = {
      fill: {
        note: {
          text: "second",
        },
      },
      signal: null,
    };
    second.end.payload.A =
      structuredClone(second.start.payload.A);

    const finalU = structuredClone(sharedBoundaryU);
    finalU.step = {
      public_step_name: "three",
    };
    second.end.payload.U = finalU;

    const timelinePacket =
      structuredClone(packet);

    timelinePacket.context.Q.actions = [
      first,
      second,
    ];
    timelinePacket.context.Q.cursor = 4;
    timelinePacket.context.Q.latest_U =
      structuredClone(finalU);
    timelinePacket.information.newQ =
      timelinePacket.context.Q;

    const W = createWombRuntime(
      timelinePacket,
      loopback,
    );

    const timeline = W.dispatchTimeline();

    assert.equal(timeline.length, 2);
    assert.equal(
      timeline[1].continuous_from_previous,
      true,
    );
    assert.equal(
      timeline[0].destination.step.public_step_name,
      "two",
    );
    assert.equal(
      timeline[1].source.step.public_step_name,
      "two",
    );

    assert.deepEqual(
      W.actionPackets(),
      [
        first.end.payload.A,
        second.end.payload.A,
      ],
    );

    assert.equal(
      W.semanticContextForTrident(
        second,
        "start",
      ).step.public_step_name,
      "two",
    );
    assert.equal(
      W.semanticContextForTrident(
        second,
        "end",
      ).step.public_step_name,
      "three",
    );

    const discontinuousPacket =
      structuredClone(timelinePacket);

    discontinuousPacket
      .context
      .Q
      .actions[1]
      .start
      .payload
      .U
      .current_span_id = "unexpected-span";

    discontinuousPacket.information.newQ =
      discontinuousPacket.context.Q;

    const discontinuous =
      createWombRuntime(
        discontinuousPacket,
        loopback,
      );

    assert.equal(
      discontinuous
        .dispatchTimeline()[1]
        .continuous_from_previous,
      false,
    );
  },
);

test("epsilon keeps canonical theta Q.cursor fixed and exposes eps rows and correlation sugars", () => {
  const oldQ = {
    ...Q,
    eps_cursor: 0,
    eps_head: 0,
    eps_rows: [],
  };
  const epsPage = {
    kind: "thinkument_eps_page_v1",
    after_seq: 0,
    next_after_seq: 1,
    eps_head: 1,
    rows: [sampleEpsRow],
  };
  const epsilonPacket = {
    kind: "thinkument_information_inbound_v1",
    trigger: {
      kind: "epsilon",
      canonical: false,
      provisional: true,
      reason: "eps_poll",
    },
    context: {
      session_id: "s",
      identity_id: "maker-1",
      role: "maker",
      Q,
      X: {},
    },
    information: {
      kind: "thinkument_epsilon_information_v1",
      oldQ,
      newQ: Q,
      newRows: [sampleEpsRow],
      pollPage: epsPage,
      reason: "eps_poll",
    },
  };

  const W = createWombRuntime(
    epsilonPacket,
    loopback,
  );

  assert.equal(W.isEpsilon(), true);
  assert.equal(W.Q().cursor, 2);
  assert.equal(W.epsOldQ().eps_cursor, 0);
  assert.equal(W.epsNewQ().eps_cursor, 1);
  assert.equal(
    W.epsNewRows()[0].payload.message.text,
    "working",
  );
  assert.equal(
    Object.hasOwn(W.epsNewRows()[0], "event_seq"),
    false,
  );
  assert.equal(W.epsPollPage().eps_head, 1);
  assert.equal(W.epsRowsForRequest("r1")[0].eps_seq, 1);
  assert.equal(W.epsRowsForTrident("d1")[0].eps_seq, 1);
  assert.equal(W.epsRowsForLatestTrident()[0].eps_seq, 1);
  assert.equal(W.epsRowsForDatum("note")[0].eps_seq, 1);
  assert.equal(W.thetaPollPage(), null);
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildHaiRenderContext,
} from "../src/ways_to_create/app_pack_mould/js/hai/context.js";

const U = {
  kind: "MANUALFILLNEEDEDSTEP",
  current_frame_id: "frame",
  current_span_id: "span",
  step: { id: "step" },
  session_metadata: {
    app_pack_mould: {
      app_pack: "packito",
      app_args: {},
    },
  },
  datum_widgets_on_this_span: ["a"],
  datum_states_on_this_span: [{
    datum_id: "a",
    is_pending: true,
    enabled: true,
    args: {
      hai_renderer: "packito.choice.v1",
      prompt: "A",
    },
    micros: [{
      name: "choice",
      type: "text",
    }],
    lifecycle: {
      runtime: {
        state: {
          revision: 1,
        },
      },
    },
  }],
};

const Q = {
  kind: "thinkument_front_state_v1",
  cursor: 2,
  latest_U: U,
  actions: [],
  open_action: null,
};

const value = (
  name,
  fallback,
) => () => (
  structuredClone(
    fallback ?? { name },
  )
);

const buildW = () => {
  const calls = new Map();

  const once = (
    name,
    result,
  ) => () => {
    calls.set(
      name,
      (calls.get(name) ?? 0) + 1,
    );
    return structuredClone(result);
  };

  return {
    calls,
    W: {
      Q: () => structuredClone(Q),
      U: () => structuredClone(U),
      X: () => ({}),

      heartbeat: () => "theta",

      trigger: () => ({
        kind: "theta",
      }),

      session: () => ({
        session_id: "s",
        identity_id: "i",
        role: null,
      }),

      isTheta: () => true,
      isEpsilon: () => false,

      thetaOldQ: () => ({
        ...Q,
        cursor: 0,
      }),

      thetaNewQ: () => (
        structuredClone(Q)
      ),

      newCanonicalEvents: () => [],
      thetaPollPage: () => null,
      epsRows: () => [],
      epsNewRows: () => [],
      epsPage: () => null,
      epsCursor: () => 0,
      epsHead: () => 0,

      accessForWidget: () => ({
        datum_id: "a",
        write: true,
      }),

      information:
        value("information"),

      runtimeKind:
        () => U.kind,

      currentScope:
        value(
          "scope",
          { span_id: "span" },
        ),

      currentStep:
        value(
          "step",
          U.step,
        ),

      semanticContext:
        value(
          "semantic_context",
        ),

      sessionMetadata:
        value(
          "session_metadata",
          U.session_metadata,
        ),

      provenance:
        value("provenance"),

      multiframespec:
        value("multiframespec"),

      lastError:
        () => null,

      accessTable:
        value(
          "access_table",
          [{
            datum_id: "a",
            write: true,
          }],
        ),

      roleModulationInfo:
        () => null,

      roleModulationReceipt:
        () => null,

      roleReadProjection:
        once(
          "roleReadProjection",
          { name: "role_projection" },
        ),

      tridents:
        once(
          "tridents",
          [],
        ),

      openTrident:
        once(
          "openTrident",
          null,
        ),

      latestTrident:
        once(
          "latestTrident",
          null,
        ),

      dispatchTimeline:
        once(
          "dispatchTimeline",
          [],
        ),

      actionPackets:
        once(
          "actionPackets",
          [],
        ),

      semanticErrorsForTrident:
        () => null,

      roleReceiptForTrident:
        () => null,

      funkContext:
        () => null,

      funkReceipt:
        () => null,

      nextFunkability:
        () => null,

      funkStatus:
        once(
          "funkStatus",
          { name: "funk_status" },
        ),

      funkSequence:
        () => [],
    },
  };
};

const haiState = () => ({
  page_being_viewed: -1,
  snap_page_on_new_trident: true,
  silence_eps: false,
  silence_theta: false,
  collected_processed_dispatch_tridents: [],
  collected_live_inexplosion_msgs: [],
});

test(
  "HAI context exposes the explicit latest-Womb blanket to every app pack",
  () => {
    const { W, calls } = buildW();

    const ctx = buildHaiRenderContext({
      W,
      haiState: haiState(),
      sessionMetadata: {
        app_pack_mould: {
          app_pack: "packito",
          app_args: {},
        },
      },
    });

    assert.equal(
      ctx.kind,
      "app_pack_mould_render_context_v1",
    );
    assert.equal(
      ctx.app_pack.id,
      "packito",
    );
    assert.equal(
      ctx.womb.runtime_kind,
      "MANUALFILLNEEDEDSTEP",
    );
    assert.deepEqual(
      ctx.womb.access_table,
      [{
        datum_id: "a",
        write: true,
      }],
    );
    assert.ok(
      "role_modulation_receipt"
      in ctx.womb,
    );
    assert.ok(
      "latest_semantic_errors"
      in ctx.womb,
    );
    assert.ok(
      "funk_receipt"
      in ctx.womb,
    );
    assert.ok(
      "next_funkability"
      in ctx.womb,
    );
    assert.ok(
      "action_packets"
      in ctx.womb,
    );
    assert.ok(
      "dispatch_timeline"
      in ctx.womb,
    );

    // Queue-derived blankets are shared between ctx.queue and ctx.womb
    // instead of being rebuilt twice on every theta/epsilon heartbeat.
    for (
      const name
      of [
        "tridents",
        "openTrident",
        "latestTrident",
        "dispatchTimeline",
        "actionPackets",
        "roleReadProjection",
        "funkStatus",
      ]
    ) {
      assert.equal(
        calls.get(name),
        1,
        `${name} should be computed once`,
      );
    }
  },
);

test(
  "HAI selects the launch app pack when runtime metadata lacks selection",
  () => {
    const { W } = buildW();

    W.U = () => ({
      ...structuredClone(U),
      session_metadata: {},
    });
    W.sessionMetadata = () => ({});

    const ctx = buildHaiRenderContext({
      W,
      haiState: haiState(),
      sessionMetadata: {
        app_pack_mould: {
          app_pack: "packito",
          app_args: {
            proof: "launch-authority",
          },
        },
      },
    });

    assert.equal(
      ctx.app_pack.id,
      "packito",
    );
    assert.deepEqual(
      ctx.app_pack.args,
      {
        proof: "launch-authority",
      },
    );
  },
);

test(
  "HAI falls back to runtime app-pack selection when launch metadata is unavailable",
  () => {
    const { W } = buildW();

    const ctx = buildHaiRenderContext({
      W,
      haiState: haiState(),
    });

    assert.equal(
      ctx.app_pack.id,
      "packito",
    );
    assert.deepEqual(
      ctx.app_pack.args,
      {},
    );
  },
);

test(
  "HAI uses the installed boot default when neither launch nor runtime selects one",
  () => {
    const { W } = buildW();

    W.U = () => ({
      ...structuredClone(U),
      session_metadata: {},
    });
    W.sessionMetadata = () => ({});

    const ctx = buildHaiRenderContext({
      W,
      haiState: haiState(),
      sessionMetadata: {},
      defaultAppPackId: "second_pack",
    });

    assert.equal(
      ctx.app_pack.id,
      "second_pack",
    );
    assert.deepEqual(
      ctx.app_pack.args,
      {},
    );
  },
);

test(
  "HAI rejects conflicting launch and runtime app-pack selections",
  () => {
    const { W } = buildW();

    assert.throws(
      () => buildHaiRenderContext({
        W,
        haiState: haiState(),
        sessionMetadata: {
          app_pack_mould: {
            app_pack: "example_notes",
            app_args: {},
          },
        },
      }),
      /app-pack selection disagrees/,
    );
  },
);
test('lazy appearance history deduplicates span snapshots, isolates repeated widgets, and respects the viewed cursor',()=>{
  const { W }=buildW();
  const first={...structuredClone(U),form_id:'first',step:{id:'p.first'}};
  first.datum_states_on_this_span[0].fill={choice:'earlier'};
  const second={...structuredClone(U),form_id:'second',step:{id:'p.second'}};
  W.Q=()=>({cursor:4,latest_U:second,actions:[
    {start:{event_seq:1,payload:{U:first}},end:{event_seq:2,payload:{U:first}}},
    {start:{event_seq:3,payload:{U:second}},end:{event_seq:4,payload:{U:second}}},
  ]});
  const ctx=buildHaiRenderContext({W,haiState:haiState()});
  const rows=ctx.view.widget_appearances;
  assert.equal(rows,ctx.view.widget_appearances);
  assert.equal(rows.length,2);
  assert.equal(rows[0].step.id,'p.first');
  assert.equal(rows[0].widgets[0].access.write,false);
  assert.deepEqual(rows[0].widgets[0].fill,{choice:'earlier'});
  assert.equal(rows[1].widgets[0],ctx.view.widgets[0]);
  assert.equal(rows[0].widgets[0].datum_id,rows[1].widgets[0].datum_id);
  const historical=buildHaiRenderContext({W,haiState:{...haiState(),page_being_viewed:2}});
  assert.equal(historical.view.widget_appearances.length,1);
  assert.equal(historical.view.widget_appearances[0].widgets[0].access.write,false);
});

test('appearance history preserves role-obfuscated rows without exposing their micro descriptors',()=>{
  const { W }=buildW();
  const hidden={...structuredClone(U),form_id:'hidden',step:{id:'p.hidden'},
    datum_states_on_this_span:[{datum_id:'secret',role_mismatch_obfuscated:true,
      lifecycle:{widget:'hidden.widget.v1'},args:{secret:'do not expose'},micros:[{name:'secret',type:'text'}],fill:{secret:'hidden'}}]};
  W.Q=()=>({cursor:4,latest_U:U,actions:[
    {start:{event_seq:1,payload:{U:hidden}},end:{event_seq:2,payload:{U:hidden}}},
  ]});
  const ctx=buildHaiRenderContext({W,haiState:haiState()});
  const row=ctx.view.widget_appearances[0].widgets[0];
  assert.equal(row.readable,false);assert.deepEqual(row.micros,[]);
  assert.deepEqual(row.args,{});assert.equal(row.fill,null);assert.equal(row.widget_type,null);
});


test('registered widget identity comes from projected lifecycle metadata, independently of renderer keys',()=>{
  const { W }=buildW();
  const snapshot=structuredClone(U);
  snapshot.datum_states_on_this_span[0].lifecycle={widget:'metal.bounded'};
  snapshot.datum_states_on_this_span[0].args={hai_renderer:'unrelated-renderer'};
  W.Q=()=>({cursor:4,latest_U:snapshot,actions:[]});
  const ctx=buildHaiRenderContext({W,haiState:haiState()});
  assert.equal(ctx.view.widgets[0].widget_type,'metal.bounded');
  assert.equal(ctx.view.widgets[0].renderer_key,'unrelated-renderer');
});

test('appearance history cannot recreate snapshots outside the retained framework boundaries',()=>{
  const { W }=buildW();
  const retained={...structuredClone(U),form_id:'retained',step:{public_step_name:'library.retained'}};
  W.Q=()=>({cursor:12,latest_U:retained,actions:[
    {start:{event_seq:10,payload:{U:retained}},end:{event_seq:12,payload:{U:retained}}},
  ]});
  const ctx=buildHaiRenderContext({W,haiState:{...haiState(),page_being_viewed:2}});
  assert.equal(ctx.view.retention_limited,true);
  assert.equal(ctx.view.widget_appearances.length,1);
  assert.equal(ctx.view.widget_appearances[0].step.public_step_name,'library.retained');
});

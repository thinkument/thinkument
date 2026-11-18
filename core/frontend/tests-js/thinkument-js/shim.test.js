import assert from "node:assert/strict";
import test from "node:test";

import {
  bootThinkument,
  defaultPluginFactory,
  readThinkumentConfig,
} from "../../src/live_vial/_js/thinkumentJS/wrapper_shim.js";

test("reads one isolated JSON config node", () => {
  const node = {
    textContent: JSON.stringify({
      kind: "thinkument_web_client_config_v1",
      rootId: "r",
    }),
  };

  const root = {
    dataset: { thinkumentConfigId: "cfg" },
    ownerDocument: {
      getElementById(id) {
        return id === "cfg" ? node : null;
      },
    },
  };

  assert.equal(readThinkumentConfig(root).rootId, "r");
});

test("configured higher-package opinionation is the one imported app policy", async () => {
  const source = `
    export function createOpinionation({ root, config }) {
      return {
        kind: "thinkument_front_opinionation_v2",
        initialX: { owner: config.owner },
        async drink(packet) {
          return {
            X: {
              ...packet.context.X,
              trigger: packet.trigger.kind,
            },
          };
        },
      };
    }
  `;
  const moduleUrl = `data:text/javascript,${encodeURIComponent(source)}`;

  const plugins = await defaultPluginFactory({
    root: { id: "root" },
    config: {
      owner: "higher-package",
      modules: {
        opinionation: moduleUrl,
      },
    },
  });

  assert.equal(
    plugins.opinionation.kind,
    "thinkument_front_opinionation_v2",
  );
  assert.deepEqual(
    plugins.opinionation.initialX,
    { owner: "higher-package" },
  );
});

test("aggregate opinionation receives guarded loopback with public validation", async () => {
  const seen = [];
  const portal = {
    identityId: "i",
    async enquire() {
      return { latest_event_seq: 0 };
    },
    async pull() {
      throw new Error("unused");
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
    async dispatch(packet, { onEpsPage }) {
      await onEpsPage({
        kind: "thinkument_eps_page_v1",
        after_seq: 0,
        next_after_seq: 1,
        eps_head: 1,
        rows: [{
          kind: "thinkument_eps_row_v1",
          eps_seq: 1,
          event_id: "ev-1",
          channel: "datum.message",
          request_id: packet.request_id,
          payload: { text: "working" },
        }],
      });
      return {
        request_id: packet.request_id,
        rejected: false,
        dispatch_outcome: "applied",
      };
    },
  };

  const app = await bootThinkument(
    {
      kind: "thinkument_web_client_config_v1",
      sessionId: "s",
      identityId: "i",
      role: null,
      initialEventSeq: 0,
      initialState: { ctx: null },
      polling: {},
      endpoints: {},
    },
    {
      opinionation: {
        kind: "thinkument_front_opinionation_v2",
        initialX: { progress: 0 },
        drink: async (packet) => {
          seen.push(packet.trigger.kind);
          return {
            X: {
              ...packet.context.X,
              progress: packet.context.X.progress + 1,
            },
          };
        },
      },
    },
    { portalInstance: portal },
  );

  assert.equal(typeof app.loopback.validateDispatch, "function");
  assert.equal(
    app.loopback.validateDispatch({ action: "STEP" }).ok,
    true,
  );
  assert.equal(
    app.loopback.validateDispatch({
      action: "STEP",
      role: "smuggled",
    }).ok,
    false,
  );

  await app.loopback.dispatch({
    action: "STEP",
    requestId: "r1",
  });

  assert.deepEqual(seen, ["epsilon"]);
  assert.deepEqual(app.loopback.readX(), { progress: 1 });
  assert.equal(app.loopback.kind, "thinkument_outbound_v1");

  app.stop();
});

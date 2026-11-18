import assert from "node:assert/strict";
import test from "node:test";

import {
  createHaiLoopbackApi,
  graftHaiState,
  initialHaiState,
} from "../src/ways_to_create/app_pack_mould/js/hai/state.js";

const kernel = (initialX) => {
  let X = structuredClone(initialX);
  const Q = {
    kind: "thinkument_front_state_v1",
    session_id: "s",
    cursor: 8,
    latest_U: { kind: "MANUALFILLNEEDEDSTEP" },
    open_action: null,
    actions: [],
    orphan_informative_events: [],
    interruptions: [],
    orphan_ends: [],
    canonical_gap_count: 0,
    bootstrap: null,
  };
  return {
    kind: "thinkument_outbound_v1",
    readQ: () => structuredClone(Q),
    readX: () => structuredClone(X),
    async writeX(nextOrUpdater) {
      X = typeof nextOrUpdater === "function"
        ? nextOrUpdater(structuredClone(X))
        : structuredClone(nextOrUpdater);
      return structuredClone(X);
    },
    validateDispatch: (A) => ({ ok: true, A }),
    dispatch: async (A) => ({ ok: true, A }),
  };
};

test("HAI state setters preserve arbitrary higher X", async () => {
  const k = kernel(graftHaiState({ app_local: 7 }, initialHaiState()));
  const api = createHaiLoopbackApi({ kernelLoopback: k });

  await api.setSilenceEps(true);
  await api.setSnapPageOnNewTrident(false);

  const X = api.readX();
  assert.equal(X.app_local, 7);
  assert.equal(api.getSilenceEps(), true);
  assert.equal(api.getSnapPageOnNewTrident(), false);

  await api.writeX((X) => ({
    ...X,
    app_local: 9,
    app_pack_mould: { malicious_overwrite: true },
  }));
  assert.equal(api.readX().app_local, 9);
  assert.equal(api.getSilenceEps(), true);
  assert.equal(api.readX().app_pack_mould.malicious_overwrite, undefined);
});

test("historical pages are deliberately read-only for dispatch", async () => {
  const k = kernel(graftHaiState({}, initialHaiState()));
  const api = createHaiLoopbackApi({ kernelLoopback: k });

  await api.setPageNumber(4);
  const receipt = api.validateDispatch({ action: "STEP" });
  assert.equal(receipt.ok, false);
  assert.equal(receipt.errors[0].code, "historical_page_read_only");
  assert.throws(() => api.dispatch({ action: "STEP" }), /historical/);

  await api.setPageNumber(-1);
  assert.equal(api.validateDispatch({ action: "STEP" }).ok, true);
});

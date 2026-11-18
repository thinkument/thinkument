import assert from "node:assert/strict";
import test from "node:test";

import {
  createThinkumentLoopbackApi,
} from "../../src/live_vial/_js/thinkumentJS/outbound.js";

test("loopback exposes Q/X/write/validate/dispatch and detaches reads", async () => {
  const calls = [];
  let X = { nested: { n: 1 } };

  const loopback = createThinkumentLoopbackApi({
    readQ: () => ({ cursor: 3 }),
    readX: () => X,
    writeX: async (nextOrUpdater) => {
      X = typeof nextOrUpdater === "function"
        ? await nextOrUpdater(structuredClone(X))
        : nextOrUpdater;
      return X;
    },
    validateDispatch: (packet) => ({
      kind: "thinkument_outbound_dispatch_validation_v1",
      ok: packet.action === "STEP",
      errors: packet.action === "STEP"
        ? []
        : [{ code: "bad", message: "bad action" }],
    }),
    dispatch: async (packet) => {
      calls.push(packet);
      return { dispatch_outcome: "applied" };
    },
  });

  assert.deepEqual(
    Object.keys(loopback).sort(),
    ["dispatch", "kind", "readQ", "readX", "validateDispatch", "writeX"].sort(),
  );

  const read = loopback.readX();
  read.nested.n = 9;
  assert.equal(loopback.readX().nested.n, 1);

  await loopback.writeX((current) => ({
    ...current,
    selected: "a",
  }));
  assert.equal(loopback.readX().selected, "a");

  assert.equal(loopback.validateDispatch({ action: "STEP" }).ok, true);

  await loopback.dispatch({ action: "STEP" });
  assert.deepEqual(calls, [{ action: "STEP" }]);

  assert.throws(
    () => loopback.dispatch({ action: "UNDO" }),
    /bad action/,
  );
  assert.deepEqual(calls, [{ action: "STEP" }]);
});

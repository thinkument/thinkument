import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeGlobals,
} from "../../src/live_vial/_js/thinkumentJS/platform/globals.js";

test("normalizes polling, eps window, and unified receipt-cap invariants", () => {
  const defaults = normalizeGlobals();

  for (const key of [
    "basePeriodMs",
    "dispatchPeriodMs",
    "remoteActivityPeriodMs",
    "epsPollPeriodMs",
    "epsPageSize",
    "maxEpsRows",
    "maxInformationDisseminationReceipts",
  ]) {
    assert.ok(Number.isInteger(defaults[key]), `${key} must be an integer`);
    assert.ok(defaults[key] > 0, `${key} must be positive`);
  }

  assert.equal(defaults.maxEpsRows, 512);

  assert.ok(
    defaults.dispatchPeriodMs <= defaults.remoteActivityPeriodMs,
    "dispatch polling must be at least as fast as remote-activity polling",
  );
  assert.ok(
    defaults.remoteActivityPeriodMs <= defaults.basePeriodMs,
    "remote-activity polling must be at least as fast as baseline polling",
  );

  const configured = normalizeGlobals({
    basePeriodMs: 1_200,
    dispatchPeriodMs: 200,
    remoteActivityPeriodMs: 600,
    epsPollPeriodMs: 100,
    epsPageSize: 50,
    maxEpsRows: 256,
    maxInformationDisseminationReceipts: 17,
  });

  assert.equal(configured.basePeriodMs, 1_200);
  assert.equal(configured.dispatchPeriodMs, 200);
  assert.equal(configured.remoteActivityPeriodMs, 600);
  assert.equal(configured.epsPollPeriodMs, 100);
  assert.equal(configured.epsPageSize, 50);
  assert.equal(configured.maxEpsRows, 256);
  assert.equal(configured.maxInformationDisseminationReceipts, 17);

  assert.throws(
    () => normalizeGlobals({
      dispatchPeriodMs: 20_000,
      remoteActivityPeriodMs: 15_000,
    }),
    RangeError,
  );

  assert.throws(
    () => normalizeGlobals({
      maxInformationDisseminationReceipts: 0,
    }),
    TypeError,
  );
});

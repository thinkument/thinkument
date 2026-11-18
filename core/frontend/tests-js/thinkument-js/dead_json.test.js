import assert from "node:assert/strict";
import test from "node:test";
import { assertDeadJson, cloneDeadJson } from "../../src/live_vial/_js/thinkumentJS/platform/_shared/dead_json.js";

test("accepts and isolates dead JSON", () => {
  const source = { a: [1, true, null, "x"] };
  const copy = cloneDeadJson(source);
  copy.a[0] = 9;
  assert.equal(source.a[0], 1);
});

test("rejects non JSON runtime objects and non-finite numbers", () => {
  assert.throws(() => assertDeadJson(new Map()), /plain objects/);
  assert.throws(() => assertDeadJson({ x: Infinity }), /finite/);
  assert.throws(() => assertDeadJson({ x: undefined }), /dead JSON/);
});

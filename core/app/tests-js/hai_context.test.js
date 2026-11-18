import assert from "node:assert/strict";
import test from "node:test";

import {
  planThetaRefresh,
} from "../src/ways_to_create/app_pack_mould/js/hai/context.js";

const U = ({ span = "s", active = ["a"], value = 1 } = {}) => ({
  kind: "MANUALFILLNEEDEDSTEP",
  current_frame_id: "f",
  current_span_id: span,
  datum_widgets_on_this_span: active,
  datum_states_on_this_span: [{
    datum_id: "a",
    is_pending: active.includes("a"),
    fill: { value },
  }],
});

const ctx = (oldU, newU) => ({
  view: {
    viewing_latest: true,
    widgets: [{ datum_id: "a" }],
  },
  theta: {
    old_Q: { latest_U: oldU },
    new_Q: { latest_U: newU },
  },
});

test("theta patching uses projected U diffs rather than action guesses", () => {
  assert.deepEqual(
    planThetaRefresh(ctx(U({ value: 1 }), U({ value: 2 }))),
    { kind: "widgets", changed_widget_ids: ["a"] },
  );

  assert.equal(
    planThetaRefresh(ctx(U(), U({ span: "next" }))).kind,
    "stage",
  );

  assert.equal(
    planThetaRefresh(ctx(U({ active: ["a"] }), U({ active: [] }))).kind,
    "stage",
  );
});

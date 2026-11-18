import assert from "node:assert/strict";
import test from "node:test";

import {
  assertOutboundDispatchValid,
  ThinkumentOutboundDispatchValidationError,
  validateOutboundDispatch,
} from "../../src/live_vial/_js/thinkumentJS/outbound_guard.js";

const datum = (
  datumId,
  {
    roles = [],
    pending = true,
    enabled = true,
    micros = [{ name: "text", type: "text", required: true }],
  } = {},
) => ({
  datum_id: datumId,
  is_pending: pending,
  enabled,
  roles,
  micros,
  fill: {},
  has_fill: false,
});

const manualU = ({ role = "maker" } = {}) => ({
  kind: "MANUALFILLNEEDEDSTEP",
  form_id: "form",
  current_frame_id: "frame",
  current_span: "span",
  current_span_id: "span",
  datum_widgets_on_this_span: [
    "note",
    "public",
    "maker_readable",
    "done",
    "disabled",
    "count",
    "validated",
  ],
  datum_states_on_this_span: [
    datum("note", { roles: ["maker"] }),
    datum("public"),
    datum("maker_readable", { roles: ["maker"] }),
    datum("done", { roles: ["maker"], pending: false }),
    datum("disabled", { roles: ["maker"], enabled: false }),
    datum("count", {
      roles: ["maker"],
      micros: [{ name: "n", type: "integer", required: true }],
    }),
    datum("validated", {
      roles: ["maker"],
      micros: [{
        name: "n",
        type: "integer",
        required: true,
        validators: [{ path: "validators:min", args: { min: 10 } }],
      }],
    }),
  ],
  role_mismatch_modulation_info: {
    role_viewing: role,
    assignments: {
      note: ["maker"],
      public: [],
      maker_readable: ["maker"],
      done: ["maker"],
      disabled: ["maker"],
      count: ["maker"],
      validated: ["maker"],
    },
  },
});

const Q = (U = manualU(), extra = {}) => ({
  kind: "thinkument_front_state_v1",
  session_id: "s",
  cursor: U === null ? 0 : 12,
  latest_U: U,
  open_action: null,
  actions: [],
  orphan_informative_events: [],
  interruptions: [],
  orphan_ends: [],
  canonical_gap_count: 0,
  bootstrap: null,
  ...extra,
});

const valid = (A, options = {}) => validateOutboundDispatch({
  Q: options.Q ?? Q(),
  role: Object.hasOwn(options, "role") ? options.role : "maker",
  A,
});

const codes = (receipt) => receipt.errors.map((row) => row.code);

test("initial empty STEP is the only STEP allowed before a U exists", () => {
  assert.equal(valid({ action: "STEP" }, { Q: Q(null) }).ok, true);

  const targeted = valid({
    action: "STEP",
    userFill: { note: { text: "x" } },
  }, { Q: Q(null) });
  assert.equal(targeted.ok, false);
  assert.ok(codes(targeted).includes("no_effective_U"));
});

test("ATSTART permits mount but not widget targeting; ATCOMPLETION blocks STEP", () => {
  const startQ = Q({ kind: "ATSTART" }, { cursor: 0 });
  assert.equal(valid({ action: "STEP" }, { Q: startQ }).ok, true);
  assert.ok(codes(valid({
    action: "STEP",
    userFill: { note: { text: "x" } },
  }, { Q: startQ })).includes("targets_before_mount"));

  const completion = valid({ action: "STEP" }, {
    Q: Q({ kind: "ATCOMPLETION" }),
  });
  assert.ok(codes(completion).includes("program_complete"));
});

test("valid macro, dotted, multi-target, signal-only, and funked STEP patterns pass", () => {
  assert.equal(valid({
    action: "STEP",
    userFill: { note: { text: "hello" } },
  }).ok, true);

  assert.equal(valid({
    action: "STEP",
    userFill: { "note.text": "hello", public: "world" },
    userSignal: { datum_id: "note", kind: "touch", info: {} },
  }).ok, true);

  assert.equal(valid({
    action: "STEP",
    userSignal: { datum_id: "note", kind: "explain", info: { why: "help" } },
  }).ok, true);

  assert.equal(valid({ action: "STEP", funked: true }).ok, true);
});

test("read visibility never becomes write authority", () => {
  const receipt = valid({
    action: "STEP",
    userFill: { maker_readable: { text: "no" } },
  }, { role: "reviewer", Q: Q(manualU({ role: "reviewer" })) });

  assert.equal(receipt.ok, false);
  assert.ok(codes(receipt).includes("write_role_denied"));
});

test("roleless callers may write only unguarded datums", () => {
  assert.equal(valid({
    action: "STEP",
    userFill: { public: { text: "ok" } },
  }, { role: null }).ok, true);

  const guarded = valid({
    action: "STEP",
    userFill: { note: { text: "no" } },
  }, { role: null });
  assert.ok(codes(guarded).includes("write_role_denied"));
});

test("done, disabled, absent, and non-editable datums are rejected", () => {
  assert.ok(codes(valid({
    action: "STEP",
    userFill: { done: { text: "x" } },
  })).includes("datum_not_pending"));

  assert.ok(codes(valid({
    action: "STEP",
    userFill: { disabled: { text: "x" } },
  })).includes("datum_disabled"));

  assert.ok(codes(valid({
    action: "STEP",
    userFill: { missing: { text: "x" } },
  })).includes("datum_not_on_current_span"));

  const U = manualU();
  U.datum_widgets_on_this_span = U.datum_widgets_on_this_span.filter((id) => id !== "note");
  assert.ok(codes(valid({
    action: "STEP",
    userFill: { note: { text: "x" } },
  }, { Q: Q(U) })).includes("datum_not_editable_membership"));
});

test("fill must fit current micro names and known micro types", () => {
  assert.ok(codes(valid({
    action: "STEP",
    userFill: { note: { unknown: "x" } },
  })).includes("micro_not_in_current_shell"));

  assert.ok(codes(valid({
    action: "STEP",
    userFill: { count: { n: "7" } },
  })).includes("micro_type_mismatch"));

  assert.equal(valid({
    action: "STEP",
    userFill: { count: 7 },
  }).ok, true);
});

test("macro plus dotted duplicate assignment is rejected", () => {
  const receipt = valid({
    action: "STEP",
    userFill: {
      note: { text: "a" },
      "note.text": "b",
    },
  });
  assert.ok(codes(receipt).includes("duplicate_micro_assignment"));
});

test("signal grammar is exact and signal-only does not require required micros", () => {
  assert.equal(valid({
    action: "STEP",
    userSignal: { datum_id: "note", kind: "explain", info: {} },
  }).ok, true);

  for (const signal of [
    { datum_id: "note", kind: "", info: {} },
    { datum_id: "note", kind: "x" },
    { datum_id: "note", kind: "x", info: {}, extra: true },
  ]) {
    assert.equal(valid({ action: "STEP", userSignal: signal }).ok, false);
  }
});

test("UNDO/REDO are payload-free; funked is intentionally STEP-only", () => {
  assert.equal(valid({ action: "UNDO" }).ok, true);
  assert.equal(valid({ action: "REDO" }).ok, true);
  assert.ok(codes(valid({
    action: "UNDO",
    userFill: { note: { text: "x" } },
  })).includes("non_step_payload"));
  assert.ok(codes(valid({ action: "UNDO", funked: true })).includes("funked_requires_step"));
});

test("transport-owned identity/role/cursor cannot be smuggled through loopback A", () => {
  for (const key of ["role", "identity_id", "my_current_event_seq_number"]) {
    const receipt = valid({ action: "STEP", [key]: key === "my_current_event_seq_number" ? 1 : "x" });
    assert.ok(codes(receipt).includes("transport_field_or_unknown_A_key"));
  }
});

test("an open canonical envelope blocks a new outbound action", () => {
  const receipt = valid({ action: "STEP" }, {
    Q: Q(manualU(), { open_action: { local_id: "dispatch:x" } }),
  });
  assert.ok(codes(receipt).includes("canonical_envelope_open"));
});

test("semantic validators remain backend-owned but are disclosed in the receipt", () => {
  const receipt = valid({
    action: "STEP",
    userFill: { validated: { n: 5 } },
  });
  assert.equal(receipt.ok, true);
  assert.equal(receipt.backend_semantic_validation_required, true);
  assert.deepEqual(receipt.semantic_validator_micros, ["validated.n"]);
});

test("assert helper throws a typed error carrying the full receipt", () => {
  assert.throws(
    () => assertOutboundDispatchValid({
      Q: Q(),
      role: "maker",
      A: { action: "STEP", userFill: { done: { text: "x" } } },
    }),
    (error) => (
      error instanceof ThinkumentOutboundDispatchValidationError
      && error.receipt.ok === false
      && error.receipt.errors.some((row) => row.code === "datum_not_pending")
    ),
  );
});

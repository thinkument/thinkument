import assert from "node:assert/strict";
import test from "node:test";

import {
  appPackModuleUrl,
  defineAppPackV1,
  validateAppPack,
} from "../src/ways_to_create/app_pack_mould/js/hai/app_packs.js";

import notes from "../src/ways_to_create/app_packs_examples/example_notes/js/index.js";


test("example app packs satisfy the same browser contract", () => {

  const checked = validateAppPack(notes, "example_notes");
  assert.equal(checked.id, "example_notes");
  assert.equal(typeof checked.widgetRenderers["example_notes.note.v1"], "function");
  assert.equal(typeof checked.outers.brand.render, "function");
});

test("defineAppPackV1 delegates normalization and supports optional HAI slots", () => {
  const widget = () => null;
  const pack = defineAppPackV1({
    id: "checked_example",
    callables: { widget },
    widgetRenderers: { "example.widget": widget },
    epsRoutes: { ping: "global" },
  });

  assert.equal(pack.kind, "app_pack_mould_app_pack_v1");
  assert.equal(pack.id, "checked_example");
  assert.equal(pack.callables.widget, widget);
  assert.equal(pack.widgetRenderers["example.widget"], widget);
  assert.equal(pack.epsRoutes.ping, "global");
  assert.deepEqual(pack.styleUrls, []);
  assert.deepEqual(Object.keys(pack.outers), []);
  assert.equal(Object.isFrozen(pack), true);
  assert.equal(Object.isFrozen(pack.callables), true);
  assert.equal(validateAppPack(pack).id, "checked_example");
});

test("defineAppPackV1 preserves the validator's id, route, and sync checks", () => {
  assert.throws(() => defineAppPackV1({ id: "../escape" }), /must match/);
  assert.throws(
    () => defineAppPackV1({ id: "bad_route", defaultEpsRoute: "unknown" }),
    /must be widget, global, silence, or custom/,
  );
  assert.throws(
    () => defineAppPackV1({ id: "legacy_routes", messageRoutes: { ping: "global" } }),
    /use appPack\.epsRoutes/,
  );
  assert.throws(
    () => defineAppPackV1({ id: "async_slot", callables: { widget: async () => null } }),
    /must be synchronous/,
  );
});


test("app-pack validation fails closed on mismatched id", () => {
  assert.throws(
    () => validateAppPack(notes, "wrong"),
    /does not match/,
  );
});


test("browser loading keeps the stable installed-pack URL convention", () => {
  const baseUrl = "https://example.invalid/think/static/bootstrap_higher_app/thinkumentJS_app_heartbeat.js";

  assert.equal(
    appPackModuleUrl({ baseUrl, appPackId: "example_notes" }),
    "https://example.invalid/think/static/bootstrap_higher_app/app_packs_examples/example_notes/index.js",
  );
});


test("browser URL construction rejects unsafe app-pack ids before import", () => {
  const baseUrl = "https://example.invalid/think/static/bootstrap_higher_app/thinkumentJS_app_heartbeat.js";

  assert.throws(
    () => appPackModuleUrl({ baseUrl, appPackId: "../escape" }),
    /must match/,
  );
});


class FakeNode {
  constructor(tag, documentRef) {
    this.tagName = String(tag).toUpperCase();
    this.ownerDocument = documentRef;
    this.children = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this.textContent = "";
    this.value = "";
    this.disabled = false;
  }

  setAttribute(name, value) {
    this.attributes.set(String(name), String(value));
  }

  append(...nodes) {
    this.children.push(...nodes);
  }

  addEventListener(name, callback) {
    this.listeners.set(String(name), callback);
  }

  async click() {
    const callback = this.listeners.get("click");
    if (callback) await callback({ target: this, currentTarget: this });
  }
}


class FakeDocument {
  createElement(tag) {
    return new FakeNode(tag, this);
  }
}


test("example_notes renderer dispatches only from its later Save callback", async () => {
  const documentRef = new FakeDocument();
  const sent = [];
  const receipts = [];
  const renderer = notes.widgetRenderers["example_notes.note.v1"];
  const card = renderer({
    documentRef,
    widget: {
      datum_id: "note",
      args: { title: "Research note", placeholder: "Write" },
      fill: { text: "old" },
      runtime_state: { last_text: "old" },
      access: { write: true },
    },
    api: {
      validateDispatch: (A) => ({ ok: true, A }),
      dispatch: async (A) => {
        sent.push(A);
        return { dispatch_outcome: "applied" };
      },
      presentLocalReceipt: (value) => receipts.push(value),
      presentDispatchResult: (value) => receipts.push(value),
    },
  });

  const editor = card.children.find((node) => node.tagName === "TEXTAREA");
  const save = card.children.find((node) => node.tagName === "BUTTON");
  assert.equal(sent.length, 0);
  editor.value = "new note";
  await save.click();
  assert.deepEqual(sent, [{
    action: "STEP",
    userFill: { note: { text: "new note" } },
    userSignal: null,
  }]);
  assert.equal(receipts.at(-1).dispatch_outcome, "applied");
});

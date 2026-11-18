import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

import {
  appPackModuleUrl,
  loadAppPack,
  resetAppPackCachesForTests,
} from "../src/ways_to_create/app_pack_mould/js/hai/app_packs.js";


test("an external installed browser pack loads by the same immutable ID convention", async () => {
  const workspace = await mkdtemp(path.join(tmpdir(), "thinkument-pack-"));
  resetAppPackCachesForTests();
  try {
    const runtime = path.join(workspace, "bootstrap_higher_app");
    const packRoot = path.join(runtime, "app_packs_examples", "vendor_think");
    await mkdir(packRoot, { recursive: true });
    const browserModule = path.join(packRoot, "index.js");
    await writeFile(browserModule, `
      export const appPack = Object.freeze({
        kind: "app_pack_mould_app_pack_v1",
        id: "vendor_think",
        styleUrls: [],
        callables: {},
        widgetRenderers: { "vendor_think.card.v1": () => null },
        epsRoutes: {},
        outers: {},
      });
      export default appPack;
    `);

    const baseUrl = pathToFileURL(path.join(runtime, "thinkumentJS_app_heartbeat.js")).href;
    assert.equal(appPackModuleUrl({ baseUrl, appPackId: "vendor_think" }),
      pathToFileURL(browserModule).href);

    const first = await loadAppPack({ baseUrl, appPackId: "vendor_think" });
    const second = await loadAppPack({ baseUrl, appPackId: "vendor_think" });
    assert.strictEqual(first, second);
    assert.equal(first.id, "vendor_think");
    assert.equal(typeof first.widgetRenderers["vendor_think.card.v1"], "function");

    await assert.rejects(
      () => loadAppPack({ baseUrl, appPackId: "not_installed" }),
      (error) => {
        assert.match(error.message, /could not load installed HAI app pack/);
        assert.ok(error.cause);
        return true;
      },
    );
    assert.throws(
      () => appPackModuleUrl({ baseUrl, appPackId: "../escape" }),
      /must match/,
    );
  } finally {
    resetAppPackCachesForTests();
    await rm(workspace, { recursive: true, force: true });
  }
});


test("an installed browser pack with the wrong exported identity is rejected", async () => {
  const workspace = await mkdtemp(path.join(tmpdir(), "thinkument-pack-bad-"));
  resetAppPackCachesForTests();
  try {
    const runtime = path.join(workspace, "bootstrap_higher_app");
    const packRoot = path.join(runtime, "app_packs_examples", "vendor_think");
    await mkdir(packRoot, { recursive: true });
    await writeFile(path.join(packRoot, "index.js"), `
      export default {
        kind: "app_pack_mould_app_pack_v1",
        id: "another_pack",
      };
    `);
    const baseUrl = pathToFileURL(path.join(runtime, "thinkumentJS_app_heartbeat.js")).href;
    await assert.rejects(
      () => loadAppPack({ baseUrl, appPackId: "vendor_think" }),
      (error) => {
        assert.match(error.cause?.message ?? "", /does not match/);
        return true;
      },
    );
  } finally {
    resetAppPackCachesForTests();
    await rm(workspace, { recursive: true, force: true });
  }
});

const PACK_KIND = "app_pack_mould_app_pack_v1";
const DEFAULT_APP_PACK_ID = "example_notes";
const APP_PACK_ID_RE = /^[a-z][a-z0-9_-]*$/;

const packCache = new Map();
const CALLABLE_KEYS = new Set([
  "notification",
  "widget",
  "widgetNotification",
  "noReadEpsNotification",
  "onEpsRow",
  "widgetsContainer",
  "outers",
  "page",
  "noReadWidget",
  "noWriteWidget",
]);
const ROUTE_NAMES = new Set(["widget", "global", "silence"]);

const asObject = (value) => (
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value
    : null
);

const isAsyncFunction = (value) => (
  typeof value === "function"
  && value.constructor?.name === "AsyncFunction"
);

const nonempty = (value, label) => {
  const out = String(value ?? "").trim();
  if (!out) throw new TypeError(`${label} must be non-empty`);
  return out;
};

const appPackId = (value) => {
  const id = nonempty(value ?? DEFAULT_APP_PACK_ID, "appPackId");
  if (!APP_PACK_ID_RE.test(id)) {
    throw new TypeError(
      "appPackId must match ^[a-z][a-z0-9_-]*$",
    );
  }
  return id;
};

const functionMap = (value, label, allowedKeys = null) => {
  const source = asObject(value) ?? {};
  for (const [key, item] of Object.entries(source)) {
    if (allowedKeys !== null && !allowedKeys.has(key)) {
      throw new TypeError(`${label}.${key} is not a supported override`);
    }
    if (typeof item !== "function") {
      throw new TypeError(`${label}.${key} must be a function`);
    }
    if (isAsyncFunction(item)) {
      throw new TypeError(`${label}.${key} must be synchronous`);
    }
  }
  return Object.freeze({ ...source });
};

const validateRoute = (route, label) => {
  if (route == null) return null;
  if (typeof route === "string") {
    if (!ROUTE_NAMES.has(route)) {
      throw new TypeError(`${label} must be widget, global, silence, or custom`);
    }
    return route;
  }
  if (typeof route === "function") {
    if (isAsyncFunction(route)) throw new TypeError(`${label} must be synchronous`);
    return route;
  }
  const custom = asObject(route);
  if (custom?.mode === "custom" && typeof custom.handler === "function") {
    if (isAsyncFunction(custom.handler)) {
      throw new TypeError(`${label}.handler must be synchronous`);
    }
    return route;
  }
  throw new TypeError(`${label} must be widget, global, silence, or a custom handler`);
};

export const validateAppPack = (raw, expectedId = null) => {
  const value = asObject(raw);
  if (!value || value.kind !== PACK_KIND) {
    throw new TypeError("invalid framework-4-services app-pack module export");
  }
  if (
    value.messageRoutes !== undefined
    || value.defaultMessageRoute !== undefined
  ) {
    throw new TypeError(
      "appPack.messageRoutes and appPack.defaultMessageRoute are removed; use appPack.epsRoutes and appPack.defaultEpsRoute",
    );
  }
  const id = appPackId(value.id);
  if (expectedId !== null && id !== expectedId) {
    throw new TypeError(`app-pack module id ${id} does not match ${expectedId}`);
  }

  const styleUrls = Array.isArray(value.styleUrls)
    ? value.styleUrls.map((url) => nonempty(url, "appPack.styleUrls[]"))
    : [];
  const epsRoutes = asObject(value.epsRoutes) ?? {};
  const outers = asObject(value.outers) ?? {};
  for (const [channel, route] of Object.entries(epsRoutes)) {
    validateRoute(route, `appPack.epsRoutes.${channel}`);
  }
  validateRoute(value.defaultEpsRoute ?? null, "appPack.defaultEpsRoute");

  for (const [name, spec] of Object.entries(outers)) {
    const outer = asObject(spec);
    if (!outer || typeof outer.render !== "function") {
      throw new TypeError(`appPack.outers.${name}.render must be a function`);
    }
    if (isAsyncFunction(outer.render)) {
      throw new TypeError(`appPack.outers.${name}.render must be synchronous`);
    }
    const powder = asObject(outer.powder) ?? {};
    for (const key of ["new_page", "widget_refresh", "epsilon"]) {
      if (powder[key] !== undefined && typeof powder[key] !== "boolean") {
        throw new TypeError(`appPack.outers.${name}.powder.${key} must be boolean`);
      }
    }
  }

  return Object.freeze({
    kind: PACK_KIND,
    id,
    styleUrls: Object.freeze(styleUrls),
    callables: functionMap(
      value.callables,
      "appPack.callables",
      CALLABLE_KEYS,
    ),
    widgetRenderers: functionMap(
      value.widgetRenderers,
      "appPack.widgetRenderers",
    ),
    epsRoutes: Object.freeze({ ...epsRoutes }),
    defaultEpsRoute: value.defaultEpsRoute ?? null,
    outers: Object.freeze({ ...outers }),
  });
};

/**
 * Build a checked HAI appPack v1 value.
 *
 * `kind` and `id` identify the public contract and selected pack. Remaining
 * properties are optional overrides for HAI's slots: `styleUrls`,
 * `callables`, `widgetRenderers`, `epsRoutes`, `defaultEpsRoute`, and
 * `outers`. Validation and normalization stay centralized in
 * `validateAppPack`; this helper adds no rendering or dispatch behavior.
 * All callbacks must be synchronous.
 *
 * @param {{kind?: string, id: string, styleUrls?: string[], callables?: object,
 * widgetRenderers?: object, epsRoutes?: object, defaultEpsRoute?: *,
 * outers?: object}} definition
 * @returns {Readonly<object>} normalized, frozen HAI appPack
 */
export const defineAppPackV1 = ({ kind = PACK_KIND, id, ...slots } = {}) => (
  validateAppPack({ kind, id, ...slots })
);

export const appPackModuleUrl = ({ baseUrl, appPackId: requestedId = null }) => {
  const base = nonempty(baseUrl, "baseUrl");
  const selected = appPackId(requestedId);
  return new URL(`./app_packs_examples/${selected}/index.js`, base).href;
};

export async function loadAppPack({ baseUrl, appPackId: requestedId = null }) {
  const selected = appPackId(requestedId);
  const moduleUrl = appPackModuleUrl({ baseUrl, appPackId: selected });

  if (!packCache.has(moduleUrl)) {
    packCache.set(moduleUrl, import(moduleUrl).then((module) => (
      validateAppPack(module.appPack ?? module.default, selected)
    )).catch((error) => {
      packCache.delete(moduleUrl);
      const wrapped = new Error(
        `could not load installed HAI app pack ${selected} from ${moduleUrl}; `
        + "verify its thinkument.app_packs_examples.v1 manifest and static_root",
      );
      wrapped.cause = error;
      throw wrapped;
    }));
  }
  return packCache.get(moduleUrl);
}

export const resetAppPackCachesForTests = () => {
  packCache.clear();
};

export const app_packs_examples_CORE_APP_PACK_KIND = PACK_KIND;
export const app_packs_examples_CORE_DEFAULT_APP_PACK_ID = DEFAULT_APP_PACK_ID;

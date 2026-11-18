import { createPortal } from "./platform/__web/portal.js";
import { createThinkumentApp } from "./platform/app.js";
import { normalizeGlobals } from "./platform/globals.js";
import { emptyFrontState } from "./platform/_backend_events/digest.js";

export const THINKUMENT_BROWSER_CONTROL_KIND =
  "thinkument_browser_control_v1";

export function readThinkumentConfig(root) {
  const configId = root?.dataset?.thinkumentConfigId;
  if (!configId) {
    throw new Error(
      "Thinkument root lacks data-thinkument-config-id",
    );
  }

  const node = root.ownerDocument.getElementById(configId);
  if (!node) {
    throw new Error(
      `Thinkument config node ${configId} was not found`,
    );
  }

  const config = JSON.parse(node.textContent || "{}");
  if (config.kind !== "thinkument_web_client_config_v1") {
    throw new Error("unknown Thinkument client config kind");
  }
  return config;
}

const importOptional = async (url) => (
  String(url || "").trim()
    ? import(String(url).trim())
    : null
);

const sessionIdFor = (config) => String(
  config.sessionId
  || config.initialState?.session_id
  || config.initialState?.access_id
  || config.rootId,
);

const plainObjectOrEmpty = (value) => (
  value !== null
  && typeof value === "object"
  && !Array.isArray(value)
    ? value
    : {}
);

const resolvedOpinionation = (plugins) => (
  plainObjectOrEmpty(plugins.opinionation)
);

const assertOutboundLoopbackSurface = (loopback) => {
  if (
    !loopback
    || loopback.kind !== "thinkument_outbound_v1"
    || typeof loopback.validateDispatch !== "function"
    || typeof loopback.dispatch !== "function"
  ) {
    throw new TypeError(
      "Thinkument loopback must expose validateDispatch() and dispatch()",
    );
  }
  return loopback;
};

const assertOpinionationSurface = (value) => {
  if (value == null) return null;
  if (typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError("Thinkument opinionation must be an object");
  }
  if (
    value.kind !== undefined
    && value.kind !== "thinkument_front_opinionation_v2"
  ) {
    throw new TypeError(
      `unknown Thinkument opinionation kind ${value.kind}`,
    );
  }
  if (value.drink !== undefined && typeof value.drink !== "function") {
    throw new TypeError("Thinkument opinionation.drink must be a function");
  }
  if (value.onBoot !== undefined && typeof value.onBoot !== "function") {
    throw new TypeError("Thinkument opinionation.onBoot must be a function");
  }
  if (value.dispose !== undefined && typeof value.dispose !== "function") {
    throw new TypeError("Thinkument opinionation.dispose must be a function");
  }
  return value;
};

const browserControlFor = (app) => Object.freeze({
  kind: THINKUMENT_BROWSER_CONTROL_KIND,

  sync() {
    return app.sync();
  },

  syncTo(latestEventSeq) {
    return app.syncTo(latestEventSeq);
  },

  readLifecycle() {
    return app.readLifecycle();
  },
});

const installBrowserControl = (root, app) => {
  if (!root) return null;
  const control = browserControlFor(app);
  Object.defineProperty(root, "thinkumentClientControl", {
    configurable: true,
    enumerable: false,
    writable: false,
    value: control,
  });
  return control;
};

const uninstallBrowserControl = (root) => {
  if (!root) return;
  try {
    delete root.thinkumentClientControl;
  } catch {}
};

export async function bootThinkument(
  config,
  plugins = {},
  dependencies = {},
) {
  const selected = resolvedOpinionation(plugins);

  const pollingGlobals = normalizeGlobals({
    ...plainObjectOrEmpty(config.polling),
    ...plainObjectOrEmpty(selected.globals),
  });

  const portal = dependencies.portalInstance || createPortal({
    endpoints: config.endpoints,
    identityId: config.identityId,
    requestTimeoutMs: pollingGlobals.requestTimeoutMs,
    dispatchWaitMs: pollingGlobals.dispatchWaitMs,
    jobPollPeriodMs: pollingGlobals.jobPollPeriodMs,
    epsPollPeriodMs: pollingGlobals.epsPollPeriodMs,
    epsPageSize: pollingGlobals.epsPageSize,
    ...dependencies.portal,
  });

  const sessionId = sessionIdFor(config);
  const initialEventSeq = Number.isInteger(config.initialEventSeq)
    ? config.initialEventSeq
    : 0;

  const seededQ = emptyFrontState(sessionId, {
    cursor: initialEventSeq,
    latestU: config.initialState?.ctx ?? null,
    bootstrap: {
      kind: "thinkument_server_snapshot_bootstrap_v1",
      initial_event_seq: initialEventSeq,
    },
  });

  const app = createThinkumentApp({
    sessionId,
    identityId: config.identityId,
    role: config.role,
    portal,
    globals: pollingGlobals,
    initialQ: seededQ,
    initialX: selected.initialX ?? {},
    informationDisseminationFn: selected.drink,
    stateLoader:
      dependencies.app?.stateLoader ?? selected.stateLoader,
    stateDumper:
      dependencies.app?.stateDumper ?? selected.stateDumper,
    ...dependencies.app,
  });

  const loopback = assertOutboundLoopbackSurface(app.loopback);
  const root = plugins.root ?? null;

  await app.start();
  installBrowserControl(root, app);

  try {
    if (typeof selected.onBoot === "function") {
      await selected.onBoot({
        root,
        loopback,
        config,
      });
    }
  } catch (error) {
    try {
      await app.stop();
    } finally {
      uninstallBrowserControl(root);
    }
    throw error;
  }

  return app;
}

async function constructOpinionation({
  opinionationModule,
  root,
  config,
}) {
  const direct = opinionationModule?.opinionation
    || (
      opinionationModule?.default
      && typeof opinionationModule.default !== "function"
        ? opinionationModule.default
        : null
    );

  if (direct) return assertOpinionationSurface(direct);

  const factory = opinionationModule?.createOpinionation
    || (
      typeof opinionationModule?.default === "function"
        ? opinionationModule.default
        : null
    );

  const value = typeof factory === "function"
    ? await factory({ root, config })
    : null;

  return assertOpinionationSurface(value);
}

export async function defaultPluginFactory({ root, config }) {
  const opinionationModule = await importOptional(
    config.modules?.opinionation,
  );

  const opinionation = await constructOpinionation({
    opinionationModule,
    root,
    config,
  });

  return {
    root,
    opinionation,
  };
}

export async function bootAllThinkumentRoots(
  documentRef = globalThis.document,
  pluginFactory = defaultPluginFactory,
  dependencies = {},
) {
  if (!documentRef) return [];
  const apps = [];

  for (
    const root
    of [...documentRef.querySelectorAll("[data-thinkument-config-id]")]
  ) {
    if (root.dataset.thinkumentBooted === "1") {
      continue;
    }

    root.dataset.thinkumentBooted = "1";

    try {
      const config = readThinkumentConfig(root);
      const plugins = typeof pluginFactory === "function"
        ? await pluginFactory({ root, config })
        : {};

      const app = await bootThinkument(
        config,
        plugins,
        dependencies,
      );

      root.thinkumentLoopback = assertOutboundLoopbackSurface(
        app.loopback,
      );

      root.disposeThinkument = async () => {
        try {
          await app.stop();
        } finally {
          try {
            await plugins.opinionation?.dispose?.();
          } finally {
            uninstallBrowserControl(root);
            try { delete root.thinkumentLoopback; } catch {}
          }
        }
      };

      apps.push(app);
    } catch (error) {
      root.dataset.thinkumentBooted = "error";
      uninstallBrowserControl(root);
      (dependencies.onError || console.error)(
        "[platform]",
        error,
      );
    }
  }

  return apps;
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      () => { void bootAllThinkumentRoots(); },
      { once: true },
    );
  } else {
    void bootAllThinkumentRoots();
  }
}

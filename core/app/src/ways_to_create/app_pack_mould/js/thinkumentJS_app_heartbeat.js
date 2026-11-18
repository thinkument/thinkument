import {
  createWombRuntime,
} from "../womb.js";

import {
  loadAppPack,
} from "./hai/app_packs.js";
import {
  buildHaiRenderContext,
} from "./hai/context.js";
import {
  ensureHaiStyles,
  renderHaiHeartbeat,
  rerenderHaiSnapshot,
} from "./hai/dom.js";
import {
  createHaiLoopbackApi,
  graftHaiState,
  initialHaiState,
  normalizeHaiState,
  stateAfterHeartbeat,
} from "./hai/state.js";

/**
 * Final framework-4-services opinionation.
 *
 * ThinkumentJS remains the transport/queue/concurrency/state kernel. This
 * module owns the stable HAI browser lifecycle above it. App packs can replace
 * render callables and add renderer/message/outer portfolios without changing
 * the kernel or this heartbeat.
 */
export const app_packs_examples_CORE_OPINIONATION_ID =
  "app_pack_mould_opinionation_v1";

const OPINIONATION_BASE_URL = import.meta.url;

const asObject = (value) => (
  value !== null
  && typeof value === "object"
  && !Array.isArray(value)
    ? value
    : null
);

const launchSessionMetadataOf = (config) => (
  asObject(config?.initialState?.ctx?.session_metadata) ?? null
);

const syntheticPacket = ({ config, loopback, X, reason }) => {
  const Q = loopback.readQ();
  return {
    kind: "thinkument_information_inbound_v1",
    trigger: {
      kind: "theta",
      canonical: true,
      provisional: false,
      reason,
    },
    context: {
      session_id: String(
        config?.sessionId
        || Q.session_id
        || config?.rootId
        || "session"
      ),
      identity_id: String(
        config?.identityId || "browser"
      ),
      role: config?.role ?? null,
      Q,
      X,
    },
    information: {
      kind: "thinkument_theta_information_v1",
      oldQ: Q,
      newQ: Q,
      newEvents: [],
      pollPage: null,
      reason,
    },
  };
};

export function createOpinionation({ root, config }) {
  if (!root) {
    throw new TypeError(
      "framework-4-services opinionation requires root"
    );
  }

  const launchSessionMetadata =
    launchSessionMetadataOf(config);

  let kernelLoopback = null;
  let haiLoopback = null;

  const appPackFor = async (ctx) => {
    const pack = await loadAppPack({
      baseUrl: OPINIONATION_BASE_URL,
      appPackId: ctx.app_pack.id,
    });
    ensureHaiStyles({
      documentRef: root.ownerDocument,
      baseUrl: OPINIONATION_BASE_URL,
      appPack: pack,
    });
    return pack;
  };

  const rerenderCommittedX = async (X) => {
    if (!kernelLoopback || !haiLoopback) return;

    const packet = syntheticPacket({
      config,
      loopback: kernelLoopback,
      X,
      reason: "hai_state_change",
    });
    const W = createWombRuntime(
      packet,
      kernelLoopback,
    );
    const ctx = buildHaiRenderContext({
      W,
      haiState: normalizeHaiState(X),
      sessionMetadata: launchSessionMetadata,
      defaultAppPackId: config?.appPackDefault || "example_notes",
    });
    const appPack = await appPackFor(ctx);

    rerenderHaiSnapshot({
      root,
      ctx,
      api: haiLoopback,
      appPack,
    });
  };

  const ensureApi = (loopback) => {
    if (haiLoopback) return haiLoopback;

    kernelLoopback = loopback;
    haiLoopback = createHaiLoopbackApi({
      kernelLoopback: loopback,
      onStateCommitted: rerenderCommittedX,
    });

    Object.defineProperty(
      root,
      "thinkumentHaiLoopback",
      {
        configurable: true,
        enumerable: false,
        writable: false,
        value: haiLoopback,
      },
    );

    return haiLoopback;
  };

  return Object.freeze({
    kind: "thinkument_front_opinionation_v2",

    initialX: graftHaiState(
      {},
      initialHaiState(),
    ),

    async drink(packet, loopback) {
      const W = createWombRuntime(
        packet,
        loopback,
      );
      const api = ensureApi(loopback);
      const next = stateAfterHeartbeat(W);
      const state = next.state;

      if (
        W.isEpsilon()
        && state.silence_eps
      ) {
        return { X: next.X };
      }

      if (
        W.isTheta()
        && state.silence_theta
      ) {
        return { X: next.X };
      }

      if (
        W.isTheta()
        && state.page_being_viewed !== -1
        && !state.snap_page_on_new_trident
      ) {
        return { X: next.X };
      }

      const ctx = buildHaiRenderContext({
        W,
        haiState: state,
        sessionMetadata: launchSessionMetadata,
        defaultAppPackId: config?.appPackDefault || "example_notes",
      });
      const appPack = await appPackFor(ctx);

      renderHaiHeartbeat({
        root,
        ctx,
        api,
        appPack,
      });

      return {
        X: next.X,
        receipt: {
          kind: "app_pack_mould_heartbeat_receipt_v1",
          opinionation:
            app_packs_examples_CORE_OPINIONATION_ID,
          trigger: W.heartbeat(),
          cursor: W.Q().cursor,
          app_pack: appPack.id,
          page_being_viewed:
            state.page_being_viewed,
          module: String(
            config?.modules?.opinionation || ""
          ),
        },
      };
    },

    async onBoot({ loopback }) {
      const api = ensureApi(loopback);
      const X = loopback.readX();

      const packet = syntheticPacket({
        config,
        loopback,
        X,
        reason: "boot",
      });
      const W = createWombRuntime(
        packet,
        loopback,
      );
      const ctx = buildHaiRenderContext({
        W,
        haiState: normalizeHaiState(X),
        sessionMetadata: launchSessionMetadata,
        defaultAppPackId: config?.appPackDefault || "example_notes",
      });
      const appPack = await appPackFor(ctx);

      rerenderHaiSnapshot({
        root,
        ctx,
        api,
        appPack,
      });
    },

    async dispose() {
      try {
        delete root.thinkumentHaiLoopback;
      } catch {}

      root.replaceChildren();
      kernelLoopback = null;
      haiLoopback = null;
    },
  });
}

export default createOpinionation;
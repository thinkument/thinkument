import {
  cloneDeadJson,
  plainObject,
} from "./platform/_shared/dead_json.js";

import {
  ThinkumentOutboundDispatchValidationError,
} from "./outbound_guard.js";

const requiredFunction = (value, name) => {
  if (typeof value !== "function") {
    throw new TypeError(`${name} must be a function`);
  }
  return value;
};

/**
 * The complete DOM/higher-JS capability seam into ThinkumentJS.
 *
 * Q is canonical client state and is read-only to downstream code.
 * X is downstream/opinionated state and is written through ThinkumentJS so
 * persistence (omega) and serialization remain centralized.
 * Dispatch uses ThinkumentJS' sealed identity/role/current-Q cursor path and
 * is screened against the latest local Q before it reaches transport.
 */
export function createThinkumentLoopbackApi(app) {
  plainObject(app, "Thinkument app");

  const readQ = requiredFunction(app.readQ, "app.readQ");
  const readX = requiredFunction(app.readX, "app.readX");
  const writeX = requiredFunction(app.writeX, "app.writeX");
  const validateDispatch = requiredFunction(
    app.validateDispatch,
    "app.validateDispatch",
  );
  const dispatch = requiredFunction(app.dispatch, "app.dispatch");

  const publicValidateDispatch = (args) => cloneDeadJson(
    validateDispatch(args),
    "loopback dispatch validation receipt",
  );

  return Object.freeze({
    kind: "thinkument_outbound_v1",

    readQ() {
      return cloneDeadJson(readQ(), "loopback Q");
    },

    readX() {
      return cloneDeadJson(readX(), "loopback X");
    },

    async writeX(nextOrUpdater) {
      const committed = await writeX(nextOrUpdater);
      return cloneDeadJson(committed, "loopback committed X");
    },

    validateDispatch(args) {
      return publicValidateDispatch(args);
    },

    dispatch(args) {
      const receipt = publicValidateDispatch(args);
      if (!receipt.ok) {
        throw new ThinkumentOutboundDispatchValidationError(receipt);
      }

      // createThinkumentApp performs the same validation again when this
      // serialized dispatch actually begins, closing the local queueing TOCTOU.
      return dispatch(args);
    },
  });
}

export default createThinkumentLoopbackApi;

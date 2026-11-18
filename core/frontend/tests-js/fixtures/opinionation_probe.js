export const PROBE_OPINIONATION_ID =
  "thinkument_test_opinionation_probe_v1";

export function createOpinionation({ root, config }) {
  if (root) {
    root.thinkumentOpinionationProbe = PROBE_OPINIONATION_ID;
  }

  return Object.freeze({
    kind: "thinkument_front_opinionation_v2",
    initialX: {
      probe: PROBE_OPINIONATION_ID,
    },

    async drink(packet) {
      return {
        X: packet.context.X,
        receipt: {
          kind: "thinkument_test_opinionation_probe_receipt_v1",
          module: String(config?.modules?.opinionation || ""),
        },
      };
    },
  });
}

export default createOpinionation;

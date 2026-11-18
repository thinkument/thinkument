import {
  assertDeadJson,
  cloneDeadJson,
  plainObject,
} from "./platform/_shared/dead_json.js";

export const OUTBOUND_DISPATCH_VALIDATION_KIND =
  "thinkument_outbound_dispatch_validation_v1";

const ACTIONS = new Set(["STEP", "UNDO", "REDO"]);
const ACTION_KEYS = new Set([
  "action",
  "userFill",
  "userSignal",
  "funked",
  "requestId",
]);
const SIGNAL_KEYS = new Set(["datum_id", "kind", "info"]);

const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

const text = (value) => String(value ?? "").trim();

const addError = (errors, code, message, extra = {}) => {
  errors.push({ code, message, ...extra });
};

const asRoleList = (value) => {
  if (value == null) return [];
  if (typeof value === "string") {
    const role = text(value);
    return role ? [role] : [];
  }
  if (Array.isArray(value)) {
    return [...new Set(value.map(text).filter(Boolean))];
  }
  if (typeof value === "object") {
    for (const key of [
      "write_roles",
      "write_role_names",
      "required_roles",
      "required_role_names",
      "assigned_roles",
      "assigned_role_names",
      "owner_roles",
      "owner_role_names",
      "role_names",
      "owners",
      "roles",
    ]) {
      if (own(value, key)) return asRoleList(value[key]);
    }
    for (const key of ["role", "write_role", "required_role", "assigned_role", "owner_role"]) {
      if (own(value, key)) return asRoleList(value[key]);
    }
  }
  return null;
};

const datumIdOf = (row, fallback = null) => {
  if (!row || typeof row !== "object") return fallback;
  return text(row.datum_id ?? row.id ?? fallback) || fallback;
};

const datumStatesById = (U) => {
  const source = U.datum_states_on_this_span;
  const out = new Map();

  if (Array.isArray(source)) {
    for (const row of source) {
      if (!row || typeof row !== "object" || Array.isArray(row)) continue;
      const id = datumIdOf(row);
      if (id) out.set(id, row);
    }
    return out;
  }

  if (source && typeof source === "object") {
    for (const [key, row] of Object.entries(source)) {
      if (!row || typeof row !== "object" || Array.isArray(row)) continue;
      const id = datumIdOf(row, key);
      if (id) out.set(id, row);
    }
  }
  return out;
};

const datumDecl = (U, datumId) => {
  const decls = U.datum_widget_decls;
  if (!decls || typeof decls !== "object" || Array.isArray(decls)) return null;
  const row = decls[datumId];
  return row && typeof row === "object" && !Array.isArray(row) ? row : null;
};

const rolesFromAssignmentContainer = (container, datumId) => {
  if (container == null) return { found: false, roles: [] };

  if (Array.isArray(container)) {
    const row = container.find((item) => (
      item && typeof item === "object" && datumIdOf(item) === datumId
    ));
    if (!row) return { found: false, roles: [] };
    const roles = asRoleList(row);
    return roles === null
      ? { found: false, roles: [] }
      : { found: true, roles };
  }

  if (typeof container !== "object") return { found: false, roles: [] };

  if (own(container, datumId)) {
    const roles = asRoleList(container[datumId]);
    return roles === null
      ? { found: false, roles: [] }
      : { found: true, roles };
  }

  return { found: false, roles: [] };
};

const findRolesInSpec = (value, datumId, depth = 0) => {
  if (depth > 12 || value == null) return { found: false, roles: [] };
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findRolesInSpec(item, datumId, depth + 1);
      if (found.found) return found;
    }
    return { found: false, roles: [] };
  }
  if (typeof value !== "object") return { found: false, roles: [] };

  if (datumIdOf(value) === datumId && (own(value, "roles") || own(value, "role"))) {
    const roles = asRoleList(own(value, "roles") ? value.roles : value.role);
    if (roles !== null) return { found: true, roles };
  }

  for (const child of Object.values(value)) {
    const found = findRolesInSpec(child, datumId, depth + 1);
    if (found.found) return found;
  }
  return { found: false, roles: [] };
};

const writeRolesFor = (U, row, datumId) => {
  for (const candidate of [row, row?.shell, datumDecl(U, datumId)]) {
    if (!candidate || typeof candidate !== "object") continue;
    if (own(candidate, "roles") || own(candidate, "role")) {
      const roles = asRoleList(
        own(candidate, "roles") ? candidate.roles : candidate.role,
      );
      if (roles !== null) return { found: true, roles, source: "datum" };
    }
  }

  for (const [container, source] of [
    [U.role_assignments, "U.role_assignments"],
    [U.role_mismatch_modulation_info?.assignments, "U.role_mismatch_modulation_info.assignments"],
  ]) {
    const result = rolesFromAssignmentContainer(container, datumId);
    if (result.found) return { ...result, source };
  }

  const fromSpec = findRolesInSpec(U.multiframespec, datumId);
  if (fromSpec.found) return { ...fromSpec, source: "U.multiframespec" };

  // Current program law: an absent effective role set means unguarded.
  return { found: true, roles: [], source: "unguarded_default" };
};

const microsFor = (U, row, datumId) => {
  const decl = datumDecl(U, datumId);
  const candidates = [
    row?.micros,
    row?.shell?.micros,
    decl?.micros,
    decl?.shell?.micros,
  ];

  for (const candidate of candidates) {
    if (!Array.isArray(candidate)) continue;
    const micros = candidate
      .filter((item) => item && typeof item === "object" && !Array.isArray(item))
      .map((item) => ({ ...item, name: text(item.name ?? item.id) }))
      .filter((item) => item.name);
    if (micros.length || candidate.length === 0) return micros;
  }
  return null;
};

const isPlainObject = (value) => (
  value !== null
  && typeof value === "object"
  && !Array.isArray(value)
  && Object.prototype.toString.call(value) === "[object Object]"
);

const knownTypeMatches = (micro, value) => {
  if (value === null) return true; // blank semantics remain backend-owned.
  const type = text(micro.type).toLowerCase();
  if (!type) return true;

  if (["text", "string", "str"].includes(type)) return typeof value === "string";
  if (["integer", "int"].includes(type)) return Number.isInteger(value);
  if (["number", "float", "decimal"].includes(type)) {
    return typeof value === "number" && Number.isFinite(value);
  }
  if (["boolean", "bool"].includes(type)) return typeof value === "boolean";
  if (["object", "mapping", "dict", "json_object"].includes(type)) return isPlainObject(value);
  if (["array", "list"].includes(type)) return Array.isArray(value);

  // Micro types are extensible. Unknown types remain backend-semantic territory.
  return true;
};

const microHasSemanticValidators = (micro) => (
  Array.isArray(micro.validators) && micro.validators.length > 0
);

const normalizeAction = (rawA, errors) => {
  if (!isPlainObject(rawA)) {
    addError(errors, "invalid_A", "A must be a plain object", { path: "A" });
    return null;
  }

  try {
    assertDeadJson(rawA, "A");
  } catch (error) {
    addError(errors, "A_not_dead_json", error.message, { path: "A" });
    return null;
  }

  for (const key of Object.keys(rawA)) {
    if (!ACTION_KEYS.has(key)) {
      addError(
        errors,
        "transport_field_or_unknown_A_key",
        `loopback A does not accept ${key}; identity, role, and cursor are ThinkumentJS-owned`,
        { path: `A.${key}` },
      );
    }
  }

  const action = text(rawA.action).toUpperCase();
  if (!ACTIONS.has(action)) {
    addError(errors, "unknown_action", "action must be STEP, UNDO, or REDO", { path: "A.action" });
  }

  const userFill = rawA.userFill === undefined ? {} : rawA.userFill;
  if (!isPlainObject(userFill)) {
    addError(errors, "invalid_user_fill", "userFill must be a plain object", { path: "A.userFill" });
  }

  const userSignal = rawA.userSignal === undefined ? null : rawA.userSignal;
  if (userSignal !== null && !isPlainObject(userSignal)) {
    addError(errors, "invalid_user_signal", "userSignal must be null or a plain object", { path: "A.userSignal" });
  }

  const funked = rawA.funked === undefined ? false : rawA.funked;
  if (typeof funked !== "boolean") {
    addError(errors, "invalid_funked", "funked must be boolean", { path: "A.funked" });
  }

  let requestId = null;
  if (rawA.requestId !== undefined) {
    requestId = text(rawA.requestId);
    if (!requestId) {
      addError(errors, "invalid_request_id", "requestId must be non-empty when supplied", { path: "A.requestId" });
    }
  }

  return {
    action,
    userFill: isPlainObject(userFill) ? userFill : {},
    userSignal: isPlainObject(userSignal) ? userSignal : null,
    funked: typeof funked === "boolean" ? funked : false,
    requestId,
  };
};

const parseSignal = (signal, errors) => {
  if (signal === null) return null;

  for (const key of Object.keys(signal)) {
    if (!SIGNAL_KEYS.has(key)) {
      addError(errors, "unknown_signal_key", `userSignal does not accept ${key}`, { path: `A.userSignal.${key}` });
    }
  }

  const datumId = text(signal.datum_id);
  const kind = text(signal.kind);
  if (!datumId) addError(errors, "signal_datum_required", "userSignal.datum_id is required", { path: "A.userSignal.datum_id" });
  if (!kind) addError(errors, "signal_kind_required", "userSignal.kind is required", { path: "A.userSignal.kind" });
  if (!isPlainObject(signal.info)) {
    addError(errors, "signal_info_required", "userSignal.info must be a plain object", { path: "A.userSignal.info" });
  }

  return { datumId, kind };
};

const splitFillKey = (key) => {
  const textKey = text(key);
  const dot = textKey.indexOf(".");
  if (dot < 0) return { datumId: textKey, microName: null };
  return {
    datumId: textKey.slice(0, dot).trim(),
    microName: textKey.slice(dot + 1).trim(),
  };
};

const activeMembership = (U) => (
  Array.isArray(U.datum_widgets_on_this_span)
    ? new Set(U.datum_widgets_on_this_span.map(text).filter(Boolean))
    : null
);

const collectTarget = (targets, datumId, channel) => {
  if (!targets.has(datumId)) {
    targets.set(datumId, { datum_id: datumId, channels: new Set(), micros: new Set() });
  }
  targets.get(datumId).channels.add(channel);
  return targets.get(datumId);
};

const validateFillForDatum = ({
  U,
  row,
  datumId,
  fillKey,
  fillValue,
  explicitMicro,
  target,
  errors,
  semanticFlags,
}) => {
  const micros = microsFor(U, row, datumId);
  if (micros === null) {
    addError(errors, "shell_not_visible", `cannot prove the current shell for ${datumId}`, { datum_id: datumId, path: `A.userFill.${fillKey}` });
    return;
  }

  const byName = new Map(micros.map((micro) => [micro.name, micro]));
  const assignments = [];

  if (explicitMicro !== null) {
    if (!explicitMicro) {
      addError(errors, "invalid_dotted_fill", `dotted fill key ${fillKey} lacks a micro name`, { datum_id: datumId, path: `A.userFill.${fillKey}` });
      return;
    }
    assignments.push([explicitMicro, fillValue]);
  } else if (isPlainObject(fillValue)) {
    for (const [microName, value] of Object.entries(fillValue)) {
      assignments.push([text(microName), value]);
    }
  } else if (micros.length === 1) {
    assignments.push([micros[0].name, fillValue]);
  } else {
    addError(
      errors,
      "macro_fill_requires_micro_object",
      `${datumId} has ${micros.length} micros; fill it with a micro-name object or dotted keys`,
      { datum_id: datumId, path: `A.userFill.${fillKey}` },
    );
    return;
  }

  for (const [microName, value] of assignments) {
    if (!microName || !byName.has(microName)) {
      addError(errors, "micro_not_in_current_shell", `${datumId}.${microName || "<blank>"} is not in the current shell`, { datum_id: datumId, micro: microName || null, path: `A.userFill.${fillKey}` });
      continue;
    }
    if (target.micros.has(microName)) {
      addError(errors, "duplicate_micro_assignment", `${datumId}.${microName} is assigned more than once`, { datum_id: datumId, micro: microName, path: `A.userFill.${fillKey}` });
      continue;
    }
    target.micros.add(microName);

    const micro = byName.get(microName);
    if (!knownTypeMatches(micro, value)) {
      addError(errors, "micro_type_mismatch", `${datumId}.${microName} does not match shell type ${micro.type}`, { datum_id: datumId, micro: microName, expected_type: micro.type, path: `A.userFill.${fillKey}` });
    }
    if (microHasSemanticValidators(micro)) semanticFlags.add(`${datumId}.${microName}`);
  }
};

const ensureTargetDispatchable = ({ U, row, datumId, role, membership, errors }) => {
  if (!row) {
    addError(errors, "datum_not_on_current_span", `${datumId} is not a datum on the current U`, { datum_id: datumId });
    return null;
  }

  if (row.is_pending !== true) {
    addError(errors, "datum_not_pending", `${datumId} is not pending in the current U`, { datum_id: datumId });
  }
  if (row.enabled === false) {
    addError(errors, "datum_disabled", `${datumId} is disabled in the current U`, { datum_id: datumId });
  }
  if (membership !== null && !membership.has(datumId)) {
    addError(errors, "datum_not_editable_membership", `${datumId} is not in datum_widgets_on_this_span`, { datum_id: datumId });
  }

  const assignment = writeRolesFor(U, row, datumId);
  const callerRole = role === null ? null : text(role);
  if (assignment.roles.length && (!callerRole || !assignment.roles.includes(callerRole))) {
    addError(
      errors,
      "write_role_denied",
      `${datumId} requires one of [${assignment.roles.join(", ")}]; caller role is ${callerRole ?? "roleless"}`,
      { datum_id: datumId, required_roles: assignment.roles, caller_role: callerRole },
    );
  }

  return {
    required_roles: assignment.roles,
    role_source: assignment.source,
  };
};

export function validateOutboundDispatch({ Q, role = null, A }) {
  const errors = [];
  const semanticFlags = new Set();
  let cursor = null;
  let U = null;

  if (!isPlainObject(Q)) {
    addError(errors, "invalid_Q", "Q must be a plain object", { path: "Q" });
  } else {
    try {
      assertDeadJson(Q, "Q");
    } catch (error) {
      addError(errors, "Q_not_dead_json", error.message, { path: "Q" });
    }

    if (Q.kind !== "thinkument_front_state_v1") {
      addError(errors, "invalid_Q_kind", "Q.kind must be thinkument_front_state_v1", { path: "Q.kind" });
    }
    if (!Number.isInteger(Q.cursor) || Q.cursor < 0) {
      addError(errors, "invalid_Q_cursor", "Q.cursor must be a non-negative integer", { path: "Q.cursor" });
    } else {
      cursor = Q.cursor;
    }
    if (Q.open_action !== null) {
      addError(errors, "canonical_envelope_open", "dispatch is blocked while Q has an open controller envelope", { path: "Q.open_action" });
    }
    if (Q.latest_U !== null && !isPlainObject(Q.latest_U)) {
      addError(errors, "invalid_latest_U", "Q.latest_U must be null or a plain object", { path: "Q.latest_U" });
    } else {
      U = Q.latest_U;
    }
  }

  const normalizedA = normalizeAction(A, errors);
  if (normalizedA === null) {
    return Object.freeze({
      kind: OUTBOUND_DISPATCH_VALIDATION_KIND,
      ok: false,
      dispatchable: false,
      strict_station_guard: true,
      cursor,
      U_kind: U?.kind ?? null,
      A: null,
      targets: [],
      backend_semantic_validation_required: false,
      semantic_validator_micros: [],
      errors: cloneDeadJson(errors),
    });
  }

  const { action, userFill, userSignal, funked } = normalizedA;
  const signal = parseSignal(userSignal, errors);
  const fillHasTargets = Object.keys(userFill).length > 0;
  const hasTargets = fillHasTargets || signal !== null;

  if (action !== "STEP" && hasTargets) {
    addError(errors, "non_step_payload", `${action} cannot carry userFill or userSignal`, { path: "A" });
  }
  if (funked && action !== "STEP") {
    addError(errors, "funked_requires_step", "funked dispatch is only admitted for STEP at the station", { path: "A.funked" });
  }

  if (action === "STEP") {
    const kind = text(U?.kind);
    if (U === null) {
      if (hasTargets || cursor !== 0) {
        addError(errors, "no_effective_U", "targeted STEP requires a current Q.latest_U; only the initial empty mount STEP is allowed without U", { path: "Q.latest_U" });
      }
    } else if (kind === "ATCOMPLETION") {
      addError(errors, "program_complete", "STEP is not dispatchable from ATCOMPLETION", { path: "Q.latest_U.kind" });
    } else if (kind === "ATSTART" && hasTargets) {
      addError(errors, "targets_before_mount", "ATSTART accepts the mount STEP but exposes no widget target shell yet", { path: "A" });
    }
  }

  const targets = new Map();
  const targetRoles = new Map();

  if (action === "STEP" && hasTargets && U !== null) {
    const rows = datumStatesById(U);
    const membership = activeMembership(U);

    for (const [fillKey, fillValue] of Object.entries(userFill)) {
      const { datumId, microName } = splitFillKey(fillKey);
      if (!datumId) {
        addError(errors, "blank_datum_id", "userFill keys must identify a datum", { path: `A.userFill.${fillKey}` });
        continue;
      }
      const target = collectTarget(targets, datumId, "fill");
      if (!targetRoles.has(datumId)) {
        targetRoles.set(datumId, ensureTargetDispatchable({ U, row: rows.get(datumId), datumId, role, membership, errors }));
      }
      validateFillForDatum({
        U,
        row: rows.get(datumId),
        datumId,
        fillKey,
        fillValue,
        explicitMicro: microName,
        target,
        errors,
        semanticFlags,
      });
    }

    if (signal !== null && signal.datumId) {
      const target = collectTarget(targets, signal.datumId, "signal");
      if (!targetRoles.has(signal.datumId)) {
        targetRoles.set(signal.datumId, ensureTargetDispatchable({ U, row: rows.get(signal.datumId), datumId: signal.datumId, role, membership, errors }));
      }
    }
  }

  const targetRows = [...targets.values()].map((target) => ({
    datum_id: target.datum_id,
    channels: [...target.channels].sort(),
    micros: [...target.micros].sort(),
    required_roles: targetRoles.get(target.datum_id)?.required_roles ?? [],
  }));

  const receipt = {
    kind: OUTBOUND_DISPATCH_VALIDATION_KIND,
    ok: errors.length === 0,
    dispatchable: errors.length === 0,
    strict_station_guard: true,
    cursor,
    U_kind: U?.kind ?? null,
    scope: U === null ? null : {
      form_id: U.form_id ?? null,
      frame_id: U.current_frame_id ?? null,
      span_id: U.current_span_id ?? U.current_span ?? null,
    },
    A: {
      action,
      userFill: cloneDeadJson(userFill, "A.userFill"),
      userSignal: userSignal === null ? null : cloneDeadJson(userSignal, "A.userSignal"),
      funked,
      requestId: normalizedA.requestId,
    },
    targets: targetRows,
    backend_semantic_validation_required: semanticFlags.size > 0,
    semantic_validator_micros: [...semanticFlags].sort(),
    errors,
  };

  return Object.freeze(cloneDeadJson(receipt, "dispatch validation receipt"));
}

export class ThinkumentOutboundDispatchValidationError extends TypeError {
  constructor(receipt) {
    const first = receipt?.errors?.[0];
    super(first?.message || "outbound dispatch rejected by ThinkumentJS station guard");
    this.name = "ThinkumentOutboundDispatchValidationError";
    this.code = first?.code || "outbound_dispatch_invalid";
    this.receipt = cloneDeadJson(receipt, "dispatch validation receipt");
  }
}

export function assertOutboundDispatchValid(input) {
  const receipt = validateOutboundDispatch(input);
  if (!receipt.ok) {
    throw new ThinkumentOutboundDispatchValidationError(receipt);
  }
  return receipt;
}

export default validateOutboundDispatch;

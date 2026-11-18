import readline from "node:readline";
import { pathToFileURL } from "node:url";
import path from "node:path";

const NONE_ROLE_KEY = "__thinkument_role_none__";
const NO_CURSOR_OVERRIDE = Symbol("no_cursor_override");
const SERVER_BOUNDARY_SIGNAL_FIXTURE_GUARD_CODES = new Set([
  "invalid_user_signal",
  "unknown_signal_key",
  "signal_datum_required",
  "signal_kind_required",
  "signal_info_required",
]);

const clone = (value) => structuredClone(value);
const normalizedRole = (role) => (
  role === null || role === undefined || String(role).trim() === ""
    ? null
    : String(role).trim()
);
const roleKey = (role) => (
  normalizedRole(role) === null ? NONE_ROLE_KEY : `role:${normalizedRole(role)}`
);

const assertPlainObject = (value, name) => {
  if (
    value === null
    || typeof value !== "object"
    || Array.isArray(value)
    || Object.prototype.toString.call(value) !== "[object Object]"
  ) throw new TypeError(`${name} must be a plain object`);
  return value;
};

const normalizeEndpoints = (value) => {
  assertPlainObject(value, "client endpoints");
  const required = [
    "context",
    "latestEventSeq",
    "events",
    "dispatch",
    "dispatchFunked",
  ];
  const epsKey = value.eps ? "eps" : (value.dispatchProgress ? "dispatchProgress" : "eps");
  required.push(epsKey);
  for (const key of required) {
    if (!String(value[key] ?? "").trim()) {
      throw new TypeError(`client endpoints.${key} is required`);
    }
  }
  const result = Object.fromEntries(required.map((key) => [key, String(value[key]).trim()]));
  if (value.eps && !result.dispatchProgress) {
    result.dispatchProgress = String(value.eps).trim();
  }
  if (value.dispatchProgress && !result.eps) {
    result.eps = String(value.dispatchProgress).trim();
  }
  return result;
};

const serializeError = (error) => ({
  name: String(error?.name || "Error"),
  message: String(error?.message || error || "unknown error"),
  code: error?.code ?? null,
  status: Number.isInteger(error?.status) ? error.status : null,
  body: error?.body && typeof error.body === "object" ? clone(error.body) : null,
  receipt: error?.receipt && typeof error.receipt === "object" ? clone(error.receipt) : null,
});

const mergeRanges = (rows) => {
  const pairs = rows
    .map((row) => ({ start: Number(row?.from_event_seq), end: Number(row?.to_event_seq) }))
    .filter((row) => Number.isInteger(row.start) && Number.isInteger(row.end) && row.start <= row.end)
    .sort((a, b) => a.start - b.start || a.end - b.end);
  const merged = [];
  for (const row of pairs) {
    const previous = merged.at(-1);
    if (!previous || row.start > previous.end + 1) merged.push({ ...row });
    else previous.end = Math.max(previous.end, row.end);
  }
  return merged.map(({ start, end }) => ({ from_event_seq: start, to_event_seq: end }));
};

const intersectRanges = (rows, startExclusive, endInclusive) => mergeRanges(
  rows
    .map((row) => ({
      from_event_seq: Math.max(Number(row.from_event_seq), Number(startExclusive) + 1),
      to_event_seq: Math.min(Number(row.to_event_seq), Number(endInclusive)),
    }))
    .filter((row) => row.from_event_seq <= row.to_event_seq),
);

const guardErrorCodes = (validation) => (
  Array.isArray(validation?.errors)
    ? validation.errors.map((row) => String(row?.code || "").trim()).filter(Boolean)
    : []
);

const isServerBoundarySignalFixture = (validation) => {
  if (validation?.ok === true) return false;
  const codes = guardErrorCodes(validation);
  return codes.length > 0 && codes.every((code) => SERVER_BOUNDARY_SIGNAL_FIXTURE_GUARD_CODES.has(code));
};

const createOpinionlessProbe = ({ createWombRuntime, expectedIdentityId, expectedRole }) => {
  const records = [];
  let loopback = null;
  let latestCanonicalObservation = null;

  const opinionation = Object.freeze({
    kind: "thinkument_front_opinionation_v2",
    initialX: {},

    async drink(packet, activeLoopback) {
      const W = createWombRuntime(packet, activeLoopback);
      const session = W.session();
      if (session.identity_id !== expectedIdentityId) {
        throw new Error(`womb identity diverged: expected=${expectedIdentityId}, actual=${session.identity_id}`);
      }
      if (session.role !== expectedRole) {
        throw new Error(`womb role diverged: expected=${String(expectedRole)}, actual=${String(session.role)}`);
      }

      /*
       * Keep only distinct public proof facts. The previous harness archived
       * full Q plus several overlapping derivatives on every heartbeat. Q
       * contains growing action history, so that turned proof history into
       * repeated structured-clone work even though Python never consumed most
       * of those copies.
       *
       * `packet.context.Q.cursor` is part of the public drink packet itself;
       * reading this scalar avoids cloning the whole Q merely to learn the
       * canonical position. All semantic data used by the proof still comes
       * through the real womb runtime.
       */
      const cursor = Number(packet?.context?.Q?.cursor);
      if (!Number.isInteger(cursor) || cursor < 0) {
        throw new TypeError("womb packet Q cursor must be a non-negative integer");
      }

      if (W.isTheta()) {
        const U = W.U();
        latestCanonicalObservation = {
          cursor,
          U,
          role_read_projection: W.roleReadProjection(),
        };
        records.push({
          kind: "thinkument_dry_run_womb_observation_v2",
          heartbeat: "theta",
          session,
          cursor,
          theta_poll_page: W.thetaPollPage(),
        });
      } else {
        records.push({
          kind: "thinkument_dry_run_womb_observation_v2",
          heartbeat: "epsilon",
          session,
          cursor,
          dispatch_request: W.dispatchRequest(),
          provisional_events: typeof W.epsRows === "function" ? W.epsRows() : (typeof W.provisionalEvents === "function" ? W.provisionalEvents() : []),
        });
      }

      return {
        X: W.X(),
        receipt: {
          kind: "thinkument_dry_run_opinionless_womb_receipt_v1",
          heartbeat: W.heartbeat(),
          cursor,
        },
      };
    },

    async onBoot({ loopback: bootLoopback }) { loopback = bootLoopback; },
    async dispose() {},
  });

  return {
    opinionation,
    records,
    loopback() {
      if (!loopback) throw new Error("ThinkumentJS loopback was not delivered through onBoot");
      return loopback;
    },
    latestCanonicalObservation() {
      // Internal harness reference; localContext() clones before returning it.
      return latestCanonicalObservation;
    },
  };
};

class ThinkumentJSClient {
  constructor({ role, identityId, endpoints, backendSessionId, modules, polling }) {
    this.role = normalizedRole(role);
    this.identityId = String(identityId || "").trim();
    this.endpoints = normalizeEndpoints(endpoints);
    this.backendSessionId = String(backendSessionId || "").trim();
    this.modules = modules;
    this.polling = polling;
    if (!this.identityId) throw new TypeError("ThinkumentJS dry-run client identityId is required");

    this.app = null;
    this.probe = null;
    this.realPortal = null;
    this.portalState = {
      cursorOverride: NO_CURSOR_OVERRIDE,
      lastDispatchPacket: null,
      bootstrapEnquiry: null,
    };
    this.errors = [];
  }

  async boot({ canonicalHighWaterHint = null } = {}) {
    const { createPortal, bootThinkument, createWombRuntime } = this.modules;
    const realPortal = createPortal({
      endpoints: this.endpoints,
      identityId: this.identityId,
      requestTimeoutMs: this.polling.requestTimeoutMs,
      dispatchWaitMs: this.polling.dispatchWaitMs,
      jobPollPeriodMs: this.polling.jobPollPeriodMs,
      progressPollPeriodMs: this.polling.progressPollPeriodMs,
      progressPageSize: this.polling.progressPageSize,
    });
    this.realPortal = realPortal;

    const portalState = this.portalState;
    const role = this.role;
    const identityId = this.identityId;
    const testPortal = Object.freeze({
      identityId,
      enquire(args) {
        /*
         * A fresh dry-run session has one role-independent canonical head.
         * RuntimeHost reads it once, then every app start consumes that exact
         * bootstrap enquiry through the normal app.start() path. Subsequent
         * enquiries always hit the real portal.
         */
        if (portalState.bootstrapEnquiry !== null) {
          const cached = portalState.bootstrapEnquiry;
          portalState.bootstrapEnquiry = null;
          return Promise.resolve(clone(cached));
        }
        return realPortal.enquire(args);
      },
      pull: (args) => realPortal.pull(args),
      readDispatchProgress: (args) => realPortal.readDispatchProgress(args),
      readContext: (args) => realPortal.readContext(args),
      dispatch(packet, options) {
        if (String(packet.identity_id) !== identityId) throw new Error("ThinkumentJS emitted a dispatch under the wrong client identity");
        if (normalizedRole(packet.role) !== role) throw new Error("ThinkumentJS emitted a dispatch under the wrong sealed role");

        let wirePacket = packet;
        if (portalState.cursorOverride !== NO_CURSOR_OVERRIDE) {
          wirePacket = { ...packet, my_current_event_seq_number: clone(portalState.cursorOverride) };
        }
        portalState.cursorOverride = NO_CURSOR_OVERRIDE;
        portalState.lastDispatchPacket = clone(wirePacket);
        return realPortal.dispatch(wirePacket, options);
      },
    });

    const initialState = await realPortal.readContext();
    let latest;
    if (Number.isInteger(canonicalHighWaterHint) && canonicalHighWaterHint >= 0) {
      latest = { latest_event_seq: canonicalHighWaterHint };
    } else {
      latest = await realPortal.enquire();
    }
    portalState.bootstrapEnquiry = clone(latest);

    const clientSessionId = String(
      initialState.session_id || this.backendSessionId || `dry-run-${this.identityId}`,
    );

    this.probe = createOpinionlessProbe({
      createWombRuntime,
      expectedIdentityId: this.identityId,
      expectedRole: this.role,
    });

    const config = {
      kind: "thinkument_web_client_config_v1",
      sessionId: clientSessionId,
      rootId: `dry-run-root-${this.identityId}`,
      identityId: this.identityId,
      role: this.role,
      endpoints: this.endpoints,
      modules: {},
      initialState,
      initialEventSeq: Number(latest.latest_event_seq),
      polling: { ...this.polling },
    };

    this.app = await bootThinkument(
      config,
      { opinionation: this.probe.opinionation },
      {
        portalInstance: testPortal,
        app: {
          onError: async (error) => { this.errors.push(serializeError(error)); },
        },
      },
    );
    if (portalState.bootstrapEnquiry !== null) {
      throw new Error("ThinkumentJS app.start() did not consume its bootstrap enquiry");
    }
    this.probe.loopback();
    return {
      role: this.role,
      identity_id: this.identityId,
      cursor: Number(this.app.readQ().cursor),
    };
  }

  async stop() {
    if (this.app) this.app.stop();
    await this.probe?.opinionation?.dispose?.();
    this.app = null;
    this.probe = null;
    this.realPortal = null;
  }

  _recordsFrom(index) { return this.probe.records.slice(index); }

  _thetaPages() {
    return this.probe.records
      .filter((record) => record.heartbeat === "theta")
      .map((record) => record.theta_poll_page)
      .filter((page) => page && typeof page === "object");
  }

  _allCanonicalEvents() {
    const bySeq = new Map();
    for (const page of this._thetaPages()) {
      for (const event of page.events || []) {
        if (Number.isInteger(event?.event_seq)) bySeq.set(event.event_seq, event);
      }
    }
    return [...bySeq.values()]
      .sort((a, b) => a.event_seq - b.event_seq)
      .map(clone);
  }

  _allHiddenRanges() {
    const rows = [];
    for (const page of this._thetaPages()) {
      const ranges = page?.visibility_receipt?.hidden_event_seq_ranges;
      if (Array.isArray(ranges)) rows.push(...ranges);
    }
    return mergeRanges(rows);
  }

  async syncToKnown(knownHighWater = null) {
    const current = Number(this.app.readQ().cursor);
    if (Number.isInteger(knownHighWater) && knownHighWater >= 0) {
      if (current < knownHighWater) await this.app.syncTo(knownHighWater);
    } else {
      await this.app.sync();
    }
    return Number(this.app.readQ().cursor);
  }

  localContext() {
    const Q = this.app.readQ();
    const womb = this.probe.latestCanonicalObservation();

    /*
     * Matching cursor is enough: the observation was built from the exact
     * theta heartbeat that committed this Q position. Returning its W.U()
     * proves the context reached the public womb rather than re-reading the
     * server or copying private app internals into the assertion path.
     */
    if (womb && Number(womb.cursor) === Number(Q.cursor)) {
      return womb.U === null ? null : clone(womb.U);
    }

    return Q.latest_U === null ? null : clone(Q.latest_U);
  }

  async localPoll({ afterEventSeq, limit, knownHighWater = null }) {
    await this.syncToKnown(knownHighWater);
    const Q = this.app.readQ();
    const latest = Number(Q.cursor);
    const start = Number(afterEventSeq);

    if (!Number.isInteger(start) || start < 0) throw new TypeError("afterEventSeq must be a non-negative integer");
    if (start > latest) throw new RangeError(`afterEventSeq ${start} exceeds local canonical high-water ${latest}`);

    let normalizedLimit = null;
    if (limit !== null && limit !== undefined) {
      if (!Number.isInteger(limit) || limit < 0) throw new TypeError("limit must be null or a non-negative integer");
      normalizedLimit = limit;
    }

    const allEvents = this._allCanonicalEvents().filter((event) => event.event_seq > start);
    let scannedThrough = latest;
    if (normalizedLimit === 0) scannedThrough = start;
    else if (normalizedLimit !== null && allEvents.length >= normalizedLimit) {
      scannedThrough = allEvents[normalizedLimit - 1].event_seq;
    }

    const visible = normalizedLimit === 0
      ? []
      : allEvents.filter((event) => event.event_seq <= scannedThrough);
    const hiddenRanges = intersectRanges(this._allHiddenRanges(), start, scannedThrough);
    const hiddenCount = hiddenRanges.reduce(
      (total, row) => total + row.to_event_seq - row.from_event_seq + 1,
      0,
    );
    const sourcePages = this._thetaPages().filter((page) => {
      const from = Number(page.after_event_seq ?? 0);
      const through = Number(page.next_after_event_seq ?? from);
      return through > start && from < scannedThrough;
    });
    const template = sourcePages[0] || {};

    return {
      kind: template.kind || "live_session_events_since_v1",
      session_id: template.session_id || this.backendSessionId,
      role: this.role,
      events: visible.map(clone),
      after_event_seq: start,
      scanned_through_event_seq: scannedThrough,
      next_after_event_seq: scannedThrough,
      session_latest_event_seq: latest,
      canonical_gap_detected: sourcePages.some((page) => page.canonical_gap_detected === true),
      visibility_receipt: {
        kind: "live_session_event_visibility_receipt_v1",
        role: this.role,
        scanned_from_event_seq_exclusive: start,
        scanned_through_event_seq: scannedThrough,
        hidden_event_count: hiddenCount,
        hidden_event_seq_ranges: hiddenRanges,
        reason: hiddenCount ? "role_projection" : "none",
      },
    };
  }

  _dispatchDelta({ startRecordIndex, requestId, beforeCursor }) {
    const records = this._recordsFrom(startRecordIndex);
    const epsilonRecords = records.filter((record) => (
      record.heartbeat === "epsilon" && record.dispatch_request?.request_id === requestId
    ));
    const thetaRecords = records.filter((record) => record.heartbeat === "theta");

    return {
      epsilon_events: epsilonRecords
        .flatMap((record) => record.provisional_events || [])
        .map(clone),
      theta_events: thetaRecords
        .flatMap((record) => record.theta_poll_page?.events || [])
        .filter((event) => Number.isInteger(event?.event_seq) && event.event_seq > beforeCursor)
        .map(clone),
    };
  }

  _rawServerBoundaryPacket({ standardA, requestId, cursor }) {
    const action = String(standardA.action || "STEP").trim().toUpperCase();
    const packet = {
      action,
      role: this.role,
      identity_id: this.identityId,
      request_id: requestId,
      my_current_event_seq_number: clone(cursor),
    };
    if (action === "STEP") {
      packet.user_fill = standardA.user_fill === undefined ? {} : clone(standardA.user_fill);
      packet.user_signal = standardA.user_signal === undefined ? null : clone(standardA.user_signal);
    }
    return packet;
  }

  async _dispatchServerBoundaryFixture({ standardA, funked, requestId, cursor }) {
    const wirePacket = this._rawServerBoundaryPacket({ standardA, requestId, cursor });
    this.portalState.lastDispatchPacket = clone(wirePacket);

    let dispatchResult = null;
    let dispatchError = null;
    try {
      dispatchResult = await this.realPortal.dispatch(wirePacket, { funked });
    } catch (error) {
      dispatchError = serializeError(error);
    }
    return { dispatchResult, dispatchError };
  }

  async dispatch({
    standardA,
    funked,
    requestId,
    cursorOverridePresent,
    cursorOverride,
    knownHighWater = null,
  }) {
    assertPlainObject(standardA, "standard A");
    if (typeof funked !== "boolean") throw new TypeError("funked must be boolean");

    const actionRole = normalizedRole(standardA.role);
    if (actionRole !== this.role) throw new Error("standard A was routed to the wrong ThinkumentJS client");
    if (Object.hasOwn(standardA, "chainreactionTM_config")) {
      throw new Error("ThinkumentJS higher-app dispatch does not expose per-dispatch chainreactionTM_config; configure chain reaction in SM");
    }

    await this.syncToKnown(knownHighWater);
    const beforeCursor = Number(this.app.readQ().cursor);
    const startRecordIndex = this.probe.records.length;
    this.portalState.lastDispatchPacket = null;
    this.portalState.cursorOverride = NO_CURSOR_OVERRIDE;

    const localA = {
      action: String(standardA.action || "STEP").toUpperCase(),
      userFill: clone(standardA.user_fill || {}),
      userSignal: standardA.user_signal == null ? null : clone(standardA.user_signal),
      funked,
      requestId,
    };

    const loopback = this.probe.loopback();
    const validation = loopback.validateDispatch(localA);
    const serverBoundaryFixture = isServerBoundarySignalFixture(validation);
    let dispatchResult = null;
    let dispatchError = null;

    if (serverBoundaryFixture) {
      const wireCursor = cursorOverridePresent ? clone(cursorOverride) : beforeCursor;
      const fixture = await this._dispatchServerBoundaryFixture({
        standardA,
        funked,
        requestId,
        cursor: wireCursor,
      });
      dispatchResult = fixture.dispatchResult;
      dispatchError = fixture.dispatchError;

      const afterHint = dispatchResult?.dispatch_concurrency?.after_event_seq;
      if (Number.isInteger(afterHint) && afterHint >= 0) await this.app.syncTo(afterHint);
      else await this.app.sync();
    } else {
      this.portalState.cursorOverride = cursorOverridePresent ? clone(cursorOverride) : NO_CURSOR_OVERRIDE;
      try {
        dispatchResult = await loopback.dispatch(localA);
      } catch (error) {
        dispatchError = serializeError(error);
        try {
          await this.syncToKnown(knownHighWater);
        } catch (syncError) {
          this.errors.push(serializeError(syncError));
        }
      } finally {
        this.portalState.cursorOverride = NO_CURSOR_OVERRIDE;
      }
    }

    const afterCursor = Number(this.app.readQ().cursor);
    const delta = this._dispatchDelta({
      startRecordIndex,
      requestId,
      beforeCursor,
    });

    return {
      kind: "thinkumentjs_dry_run_dispatch_observation_v3",
      role: this.role,
      identity_id: this.identityId,
      request_id: requestId,
      before_cursor: beforeCursor,
      after_cursor: afterCursor,
      validation,
      server_boundary_fixture: serverBoundaryFixture
        ? {
          kind: "thinkumentjs_dry_run_server_boundary_signal_fixture_v1",
          guard_codes: guardErrorCodes(validation),
        }
        : null,
      wire_dispatch_packet: this.portalState.lastDispatchPacket,
      dispatch_result: dispatchResult == null ? null : clone(dispatchResult),
      dispatch_error: dispatchError,
      epsilon_events: delta.epsilon_events,
      theta_events: delta.theta_events,
    };
  }
}

class RuntimeHost {
  constructor() {
    this.clients = new Map();
    this.modules = null;
    this.thinkumentJsRoot = null;
    this.knownCanonicalHighWater = null;
    this.runOpen = false;
  }

  _client(role) {
    const client = this.clients.get(roleKey(role));
    if (!client) throw new Error(`no ThinkumentJS dry-run client for role ${String(role)}`);
    return client;
  }

  _noteHighWater(value) {
    if (!Number.isInteger(value) || value < 0) return;
    this.knownCanonicalHighWater = this.knownCanonicalHighWater === null
      ? value
      : Math.max(this.knownCanonicalHighWater, value);
  }

  async _ensureModules(root) {
    const normalizedRoot = path.resolve(String(root || "").trim());
    if (!normalizedRoot) throw new TypeError("thinkumentJsRoot is required");

    if (this.modules !== null) {
      if (normalizedRoot !== this.thinkumentJsRoot) {
        throw new Error(
          `persistent ThinkumentJS runtime cannot switch module roots: `
          + `current=${this.thinkumentJsRoot}, requested=${normalizedRoot}`,
        );
      }
      return;
    }

    const importFromRoot = async (relative) => (
      import(pathToFileURL(path.join(normalizedRoot, relative)).href)
    );
    const [portalModule, shimModule, wombModule] = await Promise.all([
      importFromRoot("platform/__web/portal.js"),
      importFromRoot("wrapper_shim.js"),
      importFromRoot("womb.js"),
    ]);

    this.thinkumentJsRoot = normalizedRoot;
    this.modules = {
      createPortal: portalModule.createPortal,
      bootThinkument: shimModule.bootThinkument,
      createWombRuntime: wombModule.createWombRuntime,
    };
  }

  async openRun(config) {
    assertPlainObject(config, "open_run config");
    if (this.runOpen || this.clients.size) {
      throw new Error("ThinkumentJS dry-run runtime already has an open run");
    }

    await this._ensureModules(config.thinkumentJsRoot);

    const polling = {
      eventPageSize: 500,
      basePeriodMs: 30_000,
      dispatchPeriodMs: 5_000,
      dispatchWindowMs: 60_000,
      remoteActivityPeriodMs: 15_000,
      remoteActivityWindowMs: 60_000,
      progressPollPeriodMs: 25,
      progressPageSize: 500,
      requestTimeoutMs: 30_000,
      dispatchWaitMs: 20_000,
      jobPollPeriodMs: 25,
      ...(config.polling || {}),
    };

    const clients = Array.isArray(config.clients) ? config.clients : [];
    if (!clients.length) throw new TypeError("open_run config.clients must be non-empty");

    this.knownCanonicalHighWater = null;
    for (const row of clients) {
      const client = new ThinkumentJSClient({
        role: normalizedRole(row.role),
        identityId: row.identityId,
        endpoints: row.endpoints,
        backendSessionId: config.backendSessionId,
        modules: this.modules,
        polling,
      });
      const key = roleKey(client.role);
      if (this.clients.has(key)) throw new Error(`duplicate ThinkumentJS dry-run role ${String(client.role)}`);
      this.clients.set(key, client);
    }

    try {
      /*
       * Boot roles sequentially so Django is not turned into a concurrent-read
       * benchmark. The first role reads the one role-independent canonical
       * head. No mutation can occur during boot, so all later roles can use
       * that same head while still fetching their own role-projected context.
       */
      let bootstrapHighWater = null;
      for (const client of this.clients.values()) {
        const boot = await client.boot({
          canonicalHighWaterHint: bootstrapHighWater,
        });
        const cursor = Number(boot.cursor);
        if (bootstrapHighWater === null) bootstrapHighWater = cursor;
        if (cursor !== bootstrapHighWater) {
          throw new Error(
            `canonical head changed while booting a fresh client set: `
            + `expected=${bootstrapHighWater}, actual=${cursor}`,
          );
        }
        this._noteHighWater(cursor);
      }
      this.runOpen = true;
    } catch (error) {
      await this.closeRun();
      throw error;
    }

    return {
      kind: "thinkumentjs_dry_run_open_run_v3",
      clients: [...this.clients.values()].map((client) => ({
        role: client.role,
        identity_id: client.identityId,
      })),
    };
  }

  async closeRun() {
    const clients = [...this.clients.values()];
    this.clients.clear();
    this.runOpen = false;
    this.knownCanonicalHighWater = null;

    await Promise.allSettled(
      clients.map((client) => client.stop()),
    );
    return { kind: "thinkumentjs_dry_run_closed_run_v3" };
  }

  async command(message) {
    switch (message.command) {
      case "sync_cursor": {
        const client = this._client(message.role);
        const cursor = await client.syncToKnown(this.knownCanonicalHighWater);
        this._noteHighWater(cursor);
        return {
          kind: "thinkumentjs_dry_run_cursor_v1",
          role: client.role,
          identity_id: client.identityId,
          cursor,
        };
      }

      case "read_context": {
        const client = this._client(message.role);
        const cursor = await client.syncToKnown(this.knownCanonicalHighWater);
        this._noteHighWater(cursor);
        const U = client.localContext();
        return {
          kind: "thinkumentjs_dry_run_context_v1",
          role: client.role,
          identity_id: client.identityId,
          cursor,
          U,
        };
      }

      case "poll_local": {
        const page = await this._client(message.role).localPoll({
          afterEventSeq: message.afterEventSeq,
          limit: message.limit,
          knownHighWater: this.knownCanonicalHighWater,
        });
        this._noteHighWater(Number(page?.session_latest_event_seq));
        return page;
      }

      case "dispatch": {
        const result = await this._client(message.role).dispatch({
          standardA: message.A,
          funked: Boolean(message.funked),
          requestId: String(message.requestId || "").trim(),
          cursorOverridePresent: message.cursorOverridePresent === true,
          cursorOverride: message.cursorOverride,
          knownHighWater: this.knownCanonicalHighWater,
        });
        this._noteHighWater(Number(result?.after_cursor));
        this._noteHighWater(Number(result?.dispatch_result?.dispatch_concurrency?.after_event_seq));
        return result;
      }

      case "close_run":
        return this.closeRun();

      case "close_runtime":
        await this.closeRun();
        return { kind: "thinkumentjs_dry_run_runtime_closed_v3" };

      default:
        throw new RangeError(`unknown runtime command ${String(message.command)}`);
    }
  }
}

const runtime = new RuntimeHost();
const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

const writeResponse = (value) => new Promise((resolve, reject) => {
  process.stdout.write(
    `${JSON.stringify(value)}\n`,
    (error) => error ? reject(error) : resolve(),
  );
});

for await (const line of rl) {
  const text = String(line || "").trim();
  if (!text) continue;

  let message;
  try {
    message = JSON.parse(text);
    assertPlainObject(message, "runtime message");
    if (!Number.isInteger(message.id)) throw new TypeError("runtime message.id must be an integer");

    const result = message.command === "open_run"
      ? await runtime.openRun(message.config || {})
      : await runtime.command(message);

    await writeResponse({ id: message.id, ok: true, result });

    if (message.command === "close_runtime") {
      rl.close();
      process.exit(0);
    }
  } catch (error) {
    await writeResponse({
      id: Number.isInteger(message?.id) ? message.id : -1,
      ok: false,
      error: serializeError(error),
    });

    if (message?.command === "close_runtime") {
      rl.close();
      process.exit(1);
    }
  }
}

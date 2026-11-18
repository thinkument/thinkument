import readline from "node:readline";
import path from "node:path";
import { createRequire } from "node:module";

const NONE_ROLE_KEY = "__thinkument_role_none__";
const SUFFICIENCE_SELECTOR =
  '[data-thinkument-sufficience="thinkument_test_sufficience_opinionation_v1"]';
const THINKUMENT_BROWSER_CONTROL_KIND = "thinkument_browser_control_v1";
const DEFAULT_BROWSER_BOOT_TIMEOUT_MS = 10_000;
const DEFAULT_DOM_ACTION_TIMEOUT_MS = 2_000;
const CURSOR_WAIT_POLL_MS = 25;
const CANONICAL_SYNC_RETRY_MS = 50;
const MAX_BROWSER_DIAGNOSTICS = 80;
const MAX_BOOT_RESPONSE_BODY_EXCERPT = 2_000;

const clone = (value) => structuredClone(value);

const normalizedRole = (role) => (
  role === null || role === undefined || String(role).trim() === ""
    ? null
    : String(role).trim()
);

const roleKey = (role) => (
  normalizedRole(role) === null
    ? NONE_ROLE_KEY
    : `role:${normalizedRole(role)}`
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

const serializeError = (error) => ({
  name: String(error?.name || "Error"),
  message: String(error?.message || error || "unknown error"),
  code: error?.code ?? null,
  status: Number.isInteger(error?.status) ? error.status : null,
  body: error?.body && typeof error.body === "object"
    ? clone(error.body)
    : null,
  receipt: error?.receipt && typeof error.receipt === "object"
    ? clone(error.receipt)
    : null,
});

const safeJsonForScript = (value) => JSON.stringify(value)
  .replaceAll("<", "\\u003c")
  .replaceAll(">", "\\u003e")
  .replaceAll("&", "\\u0026")
  .replaceAll("\u2028", "\\u2028")
  .replaceAll("\u2029", "\\u2029");

const patchClientConfigHtml = (html, polling) => {
  const pattern = /(<script type="application\/json" id="[^"]+">)([\s\S]*?)(<\/script>)/;
  const match = String(html).match(pattern);
  if (!match) throw new Error("run page lacks Thinkument client config script");

  const config = JSON.parse(match[2]);
  if (config.kind !== "thinkument_web_client_config_v1") {
    throw new Error("run page client config has unknown kind");
  }

  config.polling = {
    ...(config.polling || {}),
    ...(polling || {}),
  };

  return String(html).replace(
    pattern,
    `${match[1]}${safeJsonForScript(config)}${match[3]}`,
  );
};

const bootResponseBodyExcerpt = (body) => {
  const text = String(body ?? "");
  if (text.length <= MAX_BOOT_RESPONSE_BODY_EXCERPT) return text;
  return `${text.slice(0, MAX_BOOT_RESPONSE_BODY_EXCERPT)}…`;
};


const packetQ = (packet) => (
  packet?.context?.Q
  || packet?.Q
  || null
);

const parseJsonText = (value, label) => {
  try {
    return JSON.parse(String(value ?? "null"));
  } catch (error) {
    throw new SyntaxError(`${label} is not valid JSON: ${error.message}`);
  }
};

const mergeRanges = (rows) => {
  const pairs = rows
    .map((row) => ({
      start: Number(row?.from_event_seq),
      end: Number(row?.to_event_seq),
    }))
    .filter((row) => (
      Number.isInteger(row.start)
      && Number.isInteger(row.end)
      && row.start <= row.end
    ))
    .sort((a, b) => a.start - b.start || a.end - b.end);

  const merged = [];
  for (const row of pairs) {
    const previous = merged.at(-1);
    if (!previous || row.start > previous.end + 1) merged.push({ ...row });
    else previous.end = Math.max(previous.end, row.end);
  }
  return merged.map(({ start, end }) => ({
    from_event_seq: start,
    to_event_seq: end,
  }));
};

const visibleEventsFromQ = (Q) => {
  const bySeq = new Map();
  const add = (event) => {
    if (Number.isInteger(event?.event_seq)) {
      bySeq.set(event.event_seq, clone(event));
    }
  };
  const addTrident = (row) => {
    add(row?.start);
    for (const event of row?.informative_events || []) add(event);
    add(row?.end);
  };

  for (const row of Q?.actions || []) addTrident(row);
  if (Q?.open_action) addTrident(Q.open_action);
  for (const event of Q?.orphan_informative_events || []) add(event);
  for (const event of Q?.orphan_ends || []) add(event);

  return [...bySeq.values()].sort((a, b) => a.event_seq - b.event_seq);
};

const hiddenRangesFromVisible = (visible, startExclusive, endInclusive) => {
  if (endInclusive <= startExclusive) return [];
  const seen = new Set(
    visible
      .map((event) => event?.event_seq)
      .filter(Number.isInteger),
  );
  const ranges = [];
  let open = null;
  for (let seq = startExclusive + 1; seq <= endInclusive; seq += 1) {
    if (!seen.has(seq)) {
      if (open === null) open = seq;
      continue;
    }
    if (open !== null) {
      ranges.push({ from_event_seq: open, to_event_seq: seq - 1 });
      open = null;
    }
  }
  if (open !== null) {
    ranges.push({ from_event_seq: open, to_event_seq: endInclusive });
  }
  return mergeRanges(ranges);
};

const attrValue = (value) => String(value)
  .replaceAll("\\", "\\\\")
  .replaceAll('"', '\\"');

const publicLocalAction = ({ standardA, funked, requestId }) => {
  const action = String(standardA.action || "STEP").trim().toUpperCase();
  const A = { action };
  if (action === "STEP") {
    A.userFill = standardA.user_fill == null ? {} : clone(standardA.user_fill);
    A.userSignal = standardA.user_signal == null ? null : clone(standardA.user_signal);
    A.funked = Boolean(funked);
  }
  if (requestId) A.requestId = String(requestId);
  return A;
};

const fillAssignments = (userFill) => {
  const out = [];
  for (const [key, value] of Object.entries(userFill || {})) {
    const dot = String(key).indexOf(".");
    if (dot >= 0) {
      out.push({
        datumId: String(key).slice(0, dot),
        microName: String(key).slice(dot + 1),
        value,
      });
      continue;
    }

    if (
      value !== null
      && typeof value === "object"
      && !Array.isArray(value)
    ) {
      for (const [microName, microValue] of Object.entries(value)) {
        out.push({ datumId: String(key), microName, value: microValue });
      }
      continue;
    }

    out.push({ datumId: String(key), microName: null, value });
  }
  return out;
};

const pushDiagnostic = (rows, value) => {
  rows.push({
    at: new Date().toISOString(),
    ...value,
  });
  if (rows.length > MAX_BROWSER_DIAGNOSTICS) {
    rows.splice(0, rows.length - MAX_BROWSER_DIAGNOSTICS);
  }
};

const installBrowserDiagnostics = (page) => {
  const rows = [];

  page.on("pageerror", (error) => {
    pushDiagnostic(rows, {
      kind: "pageerror",
      error: serializeError(error),
    });
  });

  page.on("console", (message) => {
    if (!["error", "warning"].includes(message.type())) return;
    pushDiagnostic(rows, {
      kind: "console",
      level: message.type(),
      text: message.text(),
    });
  });

  page.on("requestfailed", (request) => {
    pushDiagnostic(rows, {
      kind: "requestfailed",
      method: request.method(),
      resource_type: request.resourceType(),
      url: request.url(),
      error_text: request.failure()?.errorText ?? null,
    });
  });

  page.on("response", (response) => {
    const status = response.status();
    if (status < 400) return;
    const request = response.request();
    pushDiagnostic(rows, {
      kind: "http_error",
      status,
      method: request.method(),
      resource_type: request.resourceType(),
      url: response.url(),
    });
  });

  return rows;
};

const fatalPageDiagnostic = (rows) => rows.find(
  (row) => row.kind === "pageerror",
);

const readClientConfigFromPage = async (page) => page.evaluate(() => {
  const root = document.querySelector("[data-thinkument-config-id]");
  if (!root) throw new Error("Thinkument root was not found");
  const configId = root.dataset.thinkumentConfigId;
  const node = document.getElementById(configId);
  if (!node) throw new Error("Thinkument config node was not found");
  return JSON.parse(node.textContent || "{}");
});

const browserBootSnapshot = async (page) => page.evaluate((selector) => {
  const root = document.querySelector("[data-thinkument-config-id]");
  const marker = document.querySelector(selector);

  let config = null;
  let configError = null;
  try {
    const configId = root?.dataset?.thinkumentConfigId;
    const node = configId ? document.getElementById(configId) : null;
    config = node ? JSON.parse(node.textContent || "{}") : null;
  } catch (error) {
    configError = String(error?.message || error);
  }

  return {
    href: location.href,
    ready_state: document.readyState,
    root_present: Boolean(root),
    boot_state: root?.dataset?.thinkumentBooted ?? null,
    sufficience_attached: Boolean(marker),
    browser_control_kind: root?.thinkumentClientControl?.kind ?? null,
    opinionation_module: config?.modules?.opinionation ?? null,
    config_kind: config?.kind ?? null,
    config_error: configError,
  };
}, SUFFICIENCE_SELECTOR);

const browserBootFailure = async ({
  page,
  diagnostics,
  prefix,
  cause = null,
}) => {
  let snapshot = null;
  try {
    snapshot = await browserBootSnapshot(page);
  } catch (error) {
    snapshot = {
      snapshot_error: serializeError(error),
    };
  }

  const error = new Error(
    `${prefix}; boot_snapshot=${JSON.stringify(snapshot)}; `
    + `browser_diagnostics=${JSON.stringify(diagnostics)}`,
  );
  error.name = "SufficienceBrowserBootError";
  if (cause) error.cause = cause;
  return error;
};

const waitForSufficienceBoot = async ({
  page,
  diagnostics,
  timeoutMs,
}) => {
  let handle;
  try {
    handle = await page.waitForFunction(
      ({ selector, controlKind }) => {
        const root = document.querySelector("[data-thinkument-config-id]");
        if (
          document.querySelector(selector)
          && root?.thinkumentClientControl?.kind === controlKind
        ) return "ready";
        if (root?.dataset?.thinkumentBooted === "error") return "error";
        return false;
      },
      {
        selector: SUFFICIENCE_SELECTOR,
        controlKind: THINKUMENT_BROWSER_CONTROL_KIND,
      },
      { timeout: timeoutMs },
    );
  } catch (error) {
    throw await browserBootFailure({
      page,
      diagnostics,
      prefix: `sufficience browser boot did not reach a DOM-ready state within ${timeoutMs}ms`,
      cause: error,
    });
  }

  const outcome = await handle.jsonValue();
  await handle.dispose();

  if (outcome !== "ready") {
    throw await browserBootFailure({
      page,
      diagnostics,
      prefix: "Thinkument wrapper reported browser boot failure before sufficience rendered",
    });
  }
};

const installDomPacketObserver = async (page) => {
  await page.evaluate(() => {
    globalThis.__thinkumentDryRunDomPackets = [];
    globalThis.__thinkumentDryRunDomObserver?.disconnect?.();

    const root = document.querySelector("[data-thinkument-config-id]");
    if (!root) throw new Error("Thinkument root not found for DOM observer");

    let previous = null;
    const capture = () => {
      const node = root.querySelector("[data-sufficience-packet]");
      if (!node) return;
      const raw = String(node.textContent || "");
      if (!raw || raw === previous) return;
      previous = raw;
      globalThis.__thinkumentDryRunDomPackets.push(raw);
    };

    const observer = new MutationObserver(capture);
    observer.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    globalThis.__thinkumentDryRunDomObserver = observer;
    capture();
  });
};

class BrowserRoleClient {
  constructor({ role, pageUrl, context, page, config, diagnostics }) {
    this.role = normalizedRole(role);
    this.pageUrl = String(pageUrl);
    this.context = context;
    this.page = page;
    this.config = config;
    this.identityId = String(config.identityId || "").trim();
    this.errors = diagnostics;
    if (!this.identityId) throw new TypeError("browser Thinkument identityId is required");
    if (normalizedRole(config.role) !== this.role) {
      throw new Error(
        `browser role mismatch: expected=${String(this.role)}, actual=${String(config.role)}`,
      );
    }
  }

  _throwIfFatalPageDiagnostic() {
    const fatal = fatalPageDiagnostic(this.errors);
    if (!fatal) return;
    const error = new Error(
      "browser page raised an uncaught JavaScript error while waiting for "
      + `canonical convergence: ${JSON.stringify(fatal)}; `
      + `all_diagnostics=${JSON.stringify(this.errors)}`,
    );
    error.name = "SufficienceBrowserRuntimeDiagnosticError";
    throw error;
  }

  async packetCount() {
    return this.page.evaluate(() => (
      globalThis.__thinkumentDryRunDomPackets?.length || 0
    ));
  }

  async packetsFrom(index) {
    const rows = await this.page.evaluate((start) => (
      (globalThis.__thinkumentDryRunDomPackets || []).slice(start)
    ), index);
    return rows.map((raw) => parseJsonText(raw, "captured sufficience packet"));
  }

  async currentPacket() {
    const textValue = await this.page.locator(
      "[data-sufficience-packet]",
    ).textContent();
    return parseJsonText(textValue, "current sufficience packet");
  }

  async currentQ() {
    const Q = packetQ(await this.currentPacket());
    assertPlainObject(Q, "rendered Thinkument Q");
    return clone(Q);
  }

  async cursor() {
    const Q = await this.currentQ();
    const cursor = Number(Q.cursor);
    if (!Number.isInteger(cursor) || cursor < 0) {
      throw new TypeError("rendered Q.cursor must be a non-negative integer");
    }
    return cursor;
  }

  async _syncTo(target) {
    await this.page.evaluate(
      async ({ wanted, controlKind }) => {
        const root = document.querySelector("[data-thinkument-config-id]");
        if (!root) throw new Error("Thinkument root was not found for sync");
        const control = root.thinkumentClientControl;
        if (!control || control.kind !== controlKind) {
          throw new Error("Thinkument browser control is unavailable");
        }
        await control.syncTo(wanted);
      },
      {
        wanted: Number(target),
        controlKind: THINKUMENT_BROWSER_CONTROL_KIND,
      },
    );
  }

  async waitForCursor(target, timeoutMs) {
    const wanted = Number(target);
    if (!Number.isInteger(wanted) || wanted < 0) {
      throw new TypeError("target cursor must be a non-negative integer");
    }

    const deadline = Date.now() + Number(timeoutMs);
    let lastSyncError = null;

    while (true) {
      this._throwIfFatalPageDiagnostic();
      let current = await this.cursor();
      if (current >= wanted) return current;

      try {
        await this._syncTo(wanted);
        lastSyncError = null;
      } catch (error) {
        lastSyncError = serializeError(error);
      }

      this._throwIfFatalPageDiagnostic();
      current = await this.cursor();
      if (current >= wanted) return current;

      const remaining = deadline - Date.now();
      if (remaining <= 0) {
        const error = new Error(
          "rendered Thinkument Q did not reach required canonical high-water: "
          + `role=${String(this.role)}, current=${current}, target=${wanted}, `
          + `last_sync_error=${JSON.stringify(lastSyncError)}, `
          + `diagnostics=${JSON.stringify(this.errors)}`,
        );
        error.name = "SufficienceBrowserCursorTimeout";
        throw error;
      }
      await this.page.waitForTimeout(
        Math.min(
          Math.max(CURSOR_WAIT_POLL_MS, CANONICAL_SYNC_RETRY_MS),
          remaining,
        ),
      );
    }
  }

  async readContext(knownHighWater, timeoutMs) {
    if (Number.isInteger(knownHighWater) && knownHighWater >= 0) {
      await this.waitForCursor(knownHighWater, timeoutMs);
    }
    const Q = await this.currentQ();
    return Q.latest_U == null ? null : clone(Q.latest_U);
  }

  async _thetaPages() {
    const packets = await this.packetsFrom(0);
    const pages = [];
    for (const packet of packets) {
      const page = packet?.information?.pollPage;
      if (page && typeof page === "object") {
        pages.push(page);
      }
    }
    return pages;
  }

  async _allCanonicalEvents() {
    const pages = await this._thetaPages();
    const bySeq = new Map();
    for (const page of pages) {
      for (const event of page.events || []) {
        if (Number.isInteger(event?.event_seq)) bySeq.set(event.event_seq, clone(event));
      }
    }
    const Q = await this.currentQ();
    for (const event of visibleEventsFromQ(Q)) {
      if (!bySeq.has(event.event_seq)) {
        bySeq.set(event.event_seq, event);
      }
    }
    return [...bySeq.values()].sort((a, b) => a.event_seq - b.event_seq);
  }

  async _allHiddenRanges() {
    const pages = await this._thetaPages();
    const rows = [];
    for (const page of pages) {
      const ranges = page?.visibility_receipt?.hidden_event_seq_ranges;
      if (Array.isArray(ranges)) rows.push(...ranges);
    }
    return rows;
  }

  async pollLocal({ afterEventSeq, limit, knownHighWater, timeoutMs }) {
    if (Number.isInteger(knownHighWater) && knownHighWater >= 0) {
      await this.waitForCursor(knownHighWater, timeoutMs);
    }
    const Q = await this.currentQ();
    const latest = Number(Q.cursor);
    const start = Number(afterEventSeq);
    if (!Number.isInteger(start) || start < 0) {
      throw new TypeError("afterEventSeq must be a non-negative integer");
    }
    if (start > latest) {
      throw new RangeError(`afterEventSeq ${start} exceeds rendered cursor ${latest}`);
    }

    let normalizedLimit = null;
    if (limit !== null && limit !== undefined) {
      if (!Number.isInteger(limit) || limit < 0) {
        throw new TypeError("limit must be null or a non-negative integer");
      }
      normalizedLimit = limit;
    }

    const allEvents = await this._allCanonicalEvents();
    const allVisible = allEvents.filter(
      (event) => event.event_seq > start,
    );
    let scannedThrough = latest;
    if (normalizedLimit === 0) {
      scannedThrough = start;
    } else if (normalizedLimit !== null && allVisible.length >= normalizedLimit) {
      scannedThrough = allVisible[normalizedLimit - 1].event_seq;
    }

    const visible = normalizedLimit === 0
      ? []
      : allVisible.filter((event) => event.event_seq <= scannedThrough);

    const rawHidden = await this._allHiddenRanges();
    let hiddenRanges;
    if (rawHidden.length > 0) {
      const out = [];
      for (const raw of rawHidden) {
        const fromSeq = Number(raw?.from_event_seq);
        const toSeq = Number(raw?.to_event_seq);
        if (!Number.isInteger(fromSeq) || !Number.isInteger(toSeq)) continue;
        const s = Math.max(fromSeq, start + 1);
        const e = Math.min(toSeq, scannedThrough);
        if (s <= e) out.push({ from_event_seq: s, to_event_seq: e });
      }
      hiddenRanges = mergeRanges(out);
    } else {
      hiddenRanges = hiddenRangesFromVisible(
        allEvents,
        start,
        scannedThrough,
      );
    }
    const hiddenCount = hiddenRanges.reduce(
      (total, row) => total + row.to_event_seq - row.from_event_seq + 1,
      0,
    );

    return {
      kind: "live_session_events_since_v1",
      session_id: String(this.config.sessionId || ""),
      role: this.role,
      events: visible,
      after_event_seq: start,
      scanned_through_event_seq: scannedThrough,
      next_after_event_seq: scannedThrough,
      session_latest_event_seq: latest,
      canonical_gap_detected: false,
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

  async _resetStructuredControls() {
    for (const locator of [
      this.page.locator('[data-sufficience-micro-include="1"]'),
      this.page.locator("[data-sufficience-signal-include]"),
      this.page.locator("[data-sufficience-funked]"),
    ]) {
      const count = await locator.count();
      for (let i = 0; i < count; i += 1) {
        const control = locator.nth(i);
        if (await control.isChecked()) await control.uncheck();
      }
    }
  }

  async _resolveStructuredAssignment(assignment) {
    const datum = attrValue(assignment.datumId);
    let microName = assignment.microName;

    if (!microName) {
      const candidates = this.page.locator(
        `[data-sufficience-micro-include="1"][data-datum-id="${datum}"]`,
      );
      if (await candidates.count() !== 1) return null;
      microName = await candidates.first().getAttribute("data-micro-name");
      if (!microName) return null;
    }

    const micro = attrValue(microName);
    const include = this.page.locator(
      `[data-sufficience-micro-include="1"][data-datum-id="${datum}"][data-micro-name="${micro}"]`,
    );
    const editor = this.page.locator(
      `[data-sufficience-micro-value="1"][data-datum-id="${datum}"][data-micro-name="${micro}"]`,
    );
    if (await include.count() !== 1 || await editor.count() !== 1) return null;

    return {
      datumId: assignment.datumId,
      microName: String(microName),
      value: assignment.value,
      include,
      editor,
    };
  }

  async _tryStructuredStep(localA) {
    await this._resetStructuredControls();
    const assignments = fillAssignments(localA.userFill || {});
    const resolved = [];
    const missingDatumIds = new Set();

    for (const assignment of assignments) {
      const row = await this._resolveStructuredAssignment(assignment);
      if (row === null) {
        missingDatumIds.add(String(assignment.datumId));
      } else {
        resolved.push(row);
      }
    }

    if (missingDatumIds.size) {
      return {
        ok: false,
        missingDatumIds: [...missingDatumIds],
      };
    }

    for (const assignment of resolved) {
      await assignment.include.check();
      await assignment.editor.fill(JSON.stringify(assignment.value));
    }

    const signal = localA.userSignal;
    if (signal !== null && signal !== undefined) {
      await this.page.locator("[data-sufficience-signal-include]").check();
      await this.page.locator("[data-sufficience-signal-datum]").fill(
        String(signal?.datum_id ?? ""),
      );
      await this.page.locator("[data-sufficience-signal-kind]").fill(
        String(signal?.kind ?? ""),
      );
      await this.page.locator("[data-sufficience-signal-info]").fill(
        JSON.stringify(signal?.info ?? null),
      );
    }

    if (localA.funked) {
      await this.page.locator("[data-sufficience-funked]").check();
    }
    await this.page.locator("[data-sufficience-request-id]").fill(
      String(localA.requestId || ""),
    );
    return { ok: true, missingDatumIds: [] };
  }

  async _missingTargetsAreExplicitlyObfuscated(missingDatumIds) {
    if (!missingDatumIds.length) return false;
    const Q = await this.currentQ();
    const rows = Array.isArray(Q?.latest_U?.datum_states_on_this_span)
      ? Q.latest_U.datum_states_on_this_span
      : [];
    const byId = new Map();
    for (const row of rows) {
      if (!row || typeof row !== "object" || Array.isArray(row)) continue;
      const id = String(row.datum_id ?? row.id ?? "").trim();
      if (id) byId.set(id, row);
    }

    return missingDatumIds.every((datumId) => {
      const row = byId.get(String(datumId));
      return Boolean(
        row
        && (
          row.kind === "role_mismatch_obfuscated_datum_v1"
          || row.role_mismatch_obfuscated === true
        )
      );
    });
  }

  async _openExactDiagnosticComposer() {
    const details = this.page.locator(
      "[data-sufficience-exact-action-composer]",
    );
    if (await details.count() !== 1) {
      throw new Error("sufficience exact-public-A diagnostic composer is missing");
    }
    const isOpen = await details.evaluate((node) => Boolean(node.open));
    if (!isOpen) {
      await details.locator("summary").click();
    }
  }

  async _writeExactPublicA(localA) {
    await this._openExactDiagnosticComposer();
    await this.page.locator("[data-sufficience-exact-action]").fill(
      JSON.stringify(localA),
    );
    return this.page.locator(
      "[data-sufficience-exact-action-dispatch]",
    );
  }

  async _clickAndObserve(button, requestId, timeoutMs) {
    const beforeLocal = await this.page.locator(
      "[data-sufficience-local-receipt]",
    ).textContent();
    const beforeDispatch = await this.page.locator(
      "[data-sufficience-dispatch-result]",
    ).textContent();

    await button.click();

    await this.page.waitForFunction(
      ({ rid, localBefore, dispatchBefore }) => {
        const read = (selector) => document.querySelector(selector)?.textContent || "null";
        const localText = read("[data-sufficience-local-receipt]");
        const dispatchText = read("[data-sufficience-dispatch-result]");
        let local = null;
        let result = null;
        try { local = JSON.parse(localText); } catch {}
        try { result = JSON.parse(dispatchText); } catch {}

        if (local?.kind === "thinkument_sufficience_local_error_v1") return true;
        if (
          local?.kind === "thinkument_outbound_dispatch_validation_v1"
          && local.ok === false
        ) return true;
        if (result && result.request_id === rid) return true;

        // The result slot is cleared synchronously at click start. Any later
        // non-null replacement therefore belongs to this click even if the
        // server receipt does not echo request_id.
        if (dispatchText !== dispatchBefore && result !== null) return true;

        // Successful local validation is only preflight, not completion.
        if (localText !== localBefore && local?.ok === true) return false;
        return false;
      },
      {
        rid: String(requestId || ""),
        localBefore: beforeLocal,
        dispatchBefore: beforeDispatch,
      },
      { timeout: timeoutMs },
    );
  }

  async dispatch({ standardA, funked, requestId, knownHighWater, timeoutMs }) {
    assertPlainObject(standardA, "standard A");
    if (standardA.my_current_event_seq_number !== null
      && standardA.my_current_event_seq_number !== undefined) {
      throw new Error(
        "real sufficience DOM cannot forge ThinkumentJS-owned canonical wire cursors",
      );
    }
    if (Object.hasOwn(standardA, "chainreactionTM_config")) {
      throw new Error(
        "real sufficience DOM does not expose per-dispatch chainreactionTM_config; configure it in SM",
      );
    }

    if (Number.isInteger(knownHighWater) && knownHighWater >= 0) {
      await this.waitForCursor(knownHighWater, timeoutMs);
    }

    const actionRole = normalizedRole(standardA.role);
    if (actionRole !== this.role) {
      throw new Error("standard A was routed to the wrong browser role client");
    }

    const localA = publicLocalAction({ standardA, funked, requestId });
    const beforeCursor = await this.cursor();
    const startPacketIndex = await this.packetCount();
    let usedRawComposer = false;

    const action = String(localA.action || "STEP").toUpperCase();
    let button;
    if (action === "STEP") {
      const structured = await this._tryStructuredStep(localA);
      if (structured.ok) {
        button = this.page.locator('[data-sufficience-action="STEP"]');
      } else if (
        await this._missingTargetsAreExplicitlyObfuscated(
          structured.missingDatumIds,
        )
      ) {
        usedRawComposer = true;
        button = await this._writeExactPublicA(localA);
      } else {
        throw new Error(
          "sufficience DOM is missing structured controls for readable STEP "
          + `target(s): ${structured.missingDatumIds.join(", ")}`,
        );
      }
    } else if (action === "UNDO" || action === "REDO") {
      await this.page.locator("[data-sufficience-request-id]").fill(
        String(localA.requestId || ""),
      );
      button = this.page.locator(
        `[data-sufficience-action="${action}"]`,
      );
    } else {
      usedRawComposer = true;
      button = await this._writeExactPublicA(localA);
    }

    await this._clickAndObserve(button, requestId, timeoutMs);

    const packets = await this.packetsFrom(startPacketIndex);
    const localReceipt = parseJsonText(
      await this.page.locator(
        "[data-sufficience-local-receipt]",
      ).textContent(),
      "sufficience local receipt",
    );
    const dispatchResult = parseJsonText(
      await this.page.locator(
        "[data-sufficience-dispatch-result]",
      ).textContent(),
      "sufficience dispatch result",
    );
    const afterCursor = await this.cursor();

    const epsilonEvents = [];
    const thetaEvents = [];
    for (const packet of packets) {
      if (packet?.trigger?.kind === "epsilon") {
        for (const row of packet?.information?.newEvents || []) {
          if (row?.event && typeof row.event === "object") {
            epsilonEvents.push(clone(row.event));
          }
        }
      }
      if (packet?.trigger?.kind === "theta") {
        for (const event of packet?.information?.newEvents || []) {
          if (event && typeof event === "object") thetaEvents.push(clone(event));
        }
      }
    }

    return {
      kind: "thinkumentjs_sufficience_browser_dispatch_observation_v1",
      role: this.role,
      identity_id: this.identityId,
      request_id: String(requestId),
      before_cursor: beforeCursor,
      after_cursor: afterCursor,
      used_raw_composer: usedRawComposer,
      local_receipt: localReceipt,
      dispatch_result: dispatchResult,
      epsilon_events: epsilonEvents,
      theta_events: thetaEvents,
      page_errors: this.errors
        .filter((row) => row.kind === "pageerror")
        .map((row) => clone(row.error)),
      network_diagnostics: this.errors
        .filter((row) => row.kind !== "pageerror")
        .map((row) => clone(row)),
    };
  }

  async close() {
    // disposeThinkument now awaits the real poll loop's termination. The
    // BrowserContext is closed only after the app has quiesced, so omega does
    // not deliberately strand requests against capability rows that Django is
    // about to retire.
    try {
      await this.page.evaluate(async () => {
        const roots = [
          ...document.querySelectorAll("[data-thinkument-config-id]"),
        ];
        await Promise.allSettled(
          roots.map((root) => root.disposeThinkument?.()),
        );
      });
    } catch {}
    try { await this.context.close(); } catch {}
  }
}

class RuntimeHost {
  constructor() {
    this.browser = null;
    this.chromium = null;
    this.frontendPackageRoot = null;
    this.clients = new Map();
    this.runOpen = false;
  }

  _client(role) {
    const client = this.clients.get(roleKey(role));
    if (!client) {
      throw new Error(`no sufficience browser client for role ${String(role)}`);
    }
    return client;
  }

  async _ensureBrowser(frontendPackageRoot) {
    const root = path.resolve(String(frontendPackageRoot || "").trim());
    if (!root) throw new TypeError("frontendPackageRoot is required");

    if (this.browser !== null) {
      if (root !== this.frontendPackageRoot) {
        throw new Error(
          `persistent browser cannot switch frontend package roots: current=${this.frontendPackageRoot}, requested=${root}`,
        );
      }
      return;
    }

    let playwright;
    try {
      const requireFromFrontend = createRequire(path.join(root, "package.json"));
      playwright = requireFromFrontend("playwright");
    } catch (error) {
      const wrapped = new Error(
        `Playwright is required in ${root}; run npm install in think-frontend`,
      );
      wrapped.cause = error;
      throw wrapped;
    }

    this.chromium = playwright.chromium;
    try {
      this.browser = await this.chromium.launch({ headless: true });
    } catch (error) {
      const wrapped = new Error(
        "Chromium for Playwright is not installed; run npm run install:dry-run-browser in think-frontend",
      );
      wrapped.cause = error;
      throw wrapped;
    }
    this.frontendPackageRoot = root;
  }

  async _bootClient({ row, polling, timeoutMs, bootTimeoutMs, domActionTimeoutMs }) {
    const role = normalizedRole(row.role);
    const url = String(row.pageUrl || "").trim();
    if (!url) throw new TypeError("browser client pageUrl is required");

    const context = await this.browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(domActionTimeoutMs);
    const diagnostics = installBrowserDiagnostics(page);

    try {
      // page.route() executes outside the open_run command's direct await
      // stack. Never let an exception escape this callback: on newer Node
      // runtimes an uncaught route-handler rejection can terminate the whole
      // persistent browser host instead of becoming a structured open_run
      // failure. Capture the first failure and let _bootClient surface it.
      let routeFailure = null;
      const rememberRouteFailure = (failure) => {
        if (routeFailure === null) routeFailure = failure;
      };

      await page.route(url, async (route) => {
        try {
          const response = await route.fetch();
          const body = await response.text();
          const headers = response.headers();
          const responseEvidence = {
            url: response.url(),
            status: response.status(),
            status_text: response.statusText(),
            content_type: headers["content-type"] ?? null,
            body_excerpt: bootResponseBodyExcerpt(body),
          };

          if (!response.ok()) {
            rememberRouteFailure({
              kind: "run_page_http_error",
              ...responseEvidence,
            });
            // Preserve the server's real response in the page. _bootClient
            // reports the captured evidence after page.goto() settles.
            await route.fulfill({ response, body });
            return;
          }

          let patched;
          try {
            patched = patchClientConfigHtml(body, polling);
          } catch (error) {
            rememberRouteFailure({
              kind: "run_page_config_patch_error",
              ...responseEvidence,
              patch_error: serializeError(error),
            });
            await route.fulfill({ response, body });
            return;
          }

          await route.fulfill({ response, body: patched });
        } catch (error) {
          rememberRouteFailure({
            kind: "run_page_route_handler_error",
            requested_url: url,
            error: serializeError(error),
          });
          // route.abort() is best-effort only. In particular, do not permit a
          // second Playwright error here to escape the route callback either.
          try { await route.abort(); } catch {}
        }
      });

      let navigationResponse = null;
      let navigationError = null;
      try {
        navigationResponse = await page.goto(url, {
          waitUntil: "domcontentloaded",
          timeout: timeoutMs,
        });
      } catch (error) {
        navigationError = error;
      }

      if (routeFailure !== null) {
        throw await browserBootFailure({
          page,
          diagnostics,
          prefix: `run page interception failed: ${JSON.stringify(routeFailure)}`,
          cause: navigationError,
        });
      }

      if (navigationError !== null) {
        throw await browserBootFailure({
          page,
          diagnostics,
          prefix: `run page navigation failed for ${url}: ${navigationError.message}`,
          cause: navigationError,
        });
      }

      if (navigationResponse === null) {
        throw await browserBootFailure({
          page,
          diagnostics,
          prefix: `run page navigation produced no response for ${url}`,
        });
      }

      if (!navigationResponse.ok()) {
        throw await browserBootFailure({
          page,
          diagnostics,
          prefix: `run page navigation returned HTTP ${navigationResponse.status()} ${navigationResponse.statusText()} for ${navigationResponse.url()}`,
        });
      }

      const configValue = await readClientConfigFromPage(page);
      if (configValue.kind !== "thinkument_web_client_config_v1") {
        throw await browserBootFailure({
          page,
          diagnostics,
          prefix: "run page rendered an unknown Thinkument client config",
        });
      }
      if (!String(configValue?.modules?.opinionation || "").trim()) {
        throw await browserBootFailure({
          page,
          diagnostics,
          prefix: "run page did not select a browser opinionation module",
        });
      }

      await waitForSufficienceBoot({
        page,
        diagnostics,
        timeoutMs: bootTimeoutMs,
      });

      const client = new BrowserRoleClient({
        role,
        pageUrl: url,
        context,
        page,
        config: configValue,
        diagnostics,
      });
      await installDomPacketObserver(page);
      return { key: roleKey(role), client };
    } catch (error) {
      try { await context.close(); } catch {}
      throw error;
    }
  }

  async openRun(config) {
    assertPlainObject(config, "open_run config");
    if (this.runOpen || this.clients.size) {
      throw new Error("sufficience browser runtime already has an open run");
    }
    await this._ensureBrowser(config.frontendPackageRoot);

    const clients = Array.isArray(config.clients) ? config.clients : [];
    if (!clients.length) throw new TypeError("open_run config.clients must be non-empty");

    const keys = clients.map((row) => roleKey(row.role));
    if (new Set(keys).size !== keys.length) {
      throw new Error("open_run config contains duplicate browser roles");
    }

    /*
     * Keep the real adaptive ThinkumentJS background loop alive, but do not
     * use an artificially hot timer as the test's synchronization primitive.
     * Proof boundaries call the real app.syncTo(highWater) path explicitly.
     * This is both higher fidelity and substantially gentler on a Django test
     * database with several role-isolated browser clients.
     */
    const polling = {
      eventPageSize: 500,
      progressPageSize: 500,
      basePeriodMs: 1_000,
      dispatchPeriodMs: 100,
      dispatchWindowMs: 750,
      remoteActivityPeriodMs: 250,
      remoteActivityWindowMs: 750,
      progressPollPeriodMs: 25,
      jobPollPeriodMs: 25,
      ...(config.polling || {}),
    };
    const timeoutMs = Number(config.timeoutMs || 30_000);
    const bootTimeoutMs = Math.min(
      timeoutMs,
      Number(config.bootTimeoutMs || DEFAULT_BROWSER_BOOT_TIMEOUT_MS),
    );
    const domActionTimeoutMs = Math.min(
      timeoutMs,
      Number(config.domActionTimeoutMs || DEFAULT_DOM_ACTION_TIMEOUT_MS),
    );

    // Keep role BrowserContexts isolated, but bootstrap them sequentially.
    // Concurrent initial navigations were needlessly concentrating Django
    // live-server/database work at lambda and made transient boot failures
    // harder to attribute. Runtime behavior after boot remains multi-client.
    const booted = [];
    try {
      for (const row of clients) {
        booted.push(await this._bootClient({
          row,
          polling,
          timeoutMs,
          bootTimeoutMs,
          domActionTimeoutMs,
        }));
      }
    } catch (error) {
      await Promise.allSettled(
        booted.map(({ client }) => client.close()),
      );
      throw error;
    }

    for (const { key, client } of booted) {
      this.clients.set(key, client);
    }
    this.runOpen = true;

    return {
      kind: "thinkumentjs_sufficience_browser_open_run_v1",
      clients: [...this.clients.values()].map((client) => ({
        role: client.role,
        identity_id: client.identityId,
        page_url: client.pageUrl,
      })),
    };
  }

  async closeRun() {
    const clients = [...this.clients.values()];
    this.clients.clear();
    this.runOpen = false;
    await Promise.allSettled(clients.map((client) => client.close()));
    return { kind: "thinkumentjs_sufficience_browser_closed_run_v1" };
  }

  async closeRuntime() {
    await this.closeRun();
    if (this.browser) {
      try { await this.browser.close(); } catch {}
    }
    this.browser = null;
    this.chromium = null;
    return { kind: "thinkumentjs_sufficience_browser_runtime_closed_v1" };
  }

  async command(message) {
    const timeoutMs = Number(message.timeoutMs || 30_000);
    switch (message.command) {
      case "sync_cursor": {
        const client = this._client(message.role);
        const target = Number(message.knownHighWater ?? 0);
        const cursor = await client.waitForCursor(target, timeoutMs);
        return {
          kind: "thinkumentjs_sufficience_browser_cursor_v1",
          role: client.role,
          identity_id: client.identityId,
          cursor,
        };
      }

      case "read_context": {
        const client = this._client(message.role);
        const U = await client.readContext(
          Number(message.knownHighWater ?? 0),
          timeoutMs,
        );
        return {
          kind: "thinkumentjs_sufficience_browser_context_v1",
          role: client.role,
          identity_id: client.identityId,
          U,
        };
      }

      case "poll_local":
        return this._client(message.role).pollLocal({
          afterEventSeq: message.afterEventSeq,
          limit: message.limit,
          knownHighWater: Number(message.knownHighWater ?? 0),
          timeoutMs,
        });

      case "dispatch":
        return this._client(message.role).dispatch({
          standardA: message.A,
          funked: Boolean(message.funked),
          requestId: String(message.requestId || "").trim(),
          knownHighWater: Number(message.knownHighWater ?? 0),
          timeoutMs,
        });

      case "close_run":
        return this.closeRun();

      case "close_runtime":
        return this.closeRuntime();

      default:
        throw new RangeError(`unknown browser runtime command ${String(message.command)}`);
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
    if (!Number.isInteger(message.id)) {
      throw new TypeError("runtime message.id must be an integer");
    }

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
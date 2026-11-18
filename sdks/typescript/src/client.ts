import {
  SessionCreatePayload,
  SessionCreateResponse,
  DispatchPayload,
  DispatchResponse,
  TapeEvent,
  RelayPayload,
  RelayResponse,
  HealthzResponse,
  ModulePublishPayload,
  ModuleRecord,
  ModuleSummary,
  RetireReceipt,
  RunAnalytics,
  StorageUploadRequest,
  StorageDescriptor
} from './types.js';
import { ThinkumentError, CloudServiceRequiredError, ConcurrencyConflictError } from './errors.js';

export interface ClientOptions {
  apiKey?: string;
  baseUrl?: string;
  daemonPort?: number;
}

export class ActiveSession {
  constructor(
    public readonly sessionId: string,
    public readonly role: string,
    private readonly baseUrl: string,
    private readonly headers: Record<string, string>
  ) {}

  async dispatch(payload: DispatchPayload): Promise<DispatchResponse> {
    const url = `${this.baseUrl}/api/v1/sessions/${this.sessionId}/dispatch/`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { ...this.headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: this.role, ...payload })
    });
    const receipt = (await res.json()) as any;
    const status = receipt.dispatch_outcome || receipt.status || (receipt.ok ? 'applied' : 'rejected');
    if (status === 'stale_rejected' || receipt.dispatch_outcome === 'stale_rejected') {
      throw new ConcurrencyConflictError(receipt.error || 'Concurrent update detected');
    }
    return {
      status,
      applied_seq: receipt.dispatch_concurrency?.after_event_seq ?? receipt.applied_seq,
      latest_seq: receipt.dispatch_concurrency?.after_event_seq ?? receipt.latest_seq,
      error: receipt.last_error || receipt.error,
      ...receipt
    } as DispatchResponse;
  }

  async getEvents(afterSeq: number = 0): Promise<TapeEvent[]> {
    const url = `${this.baseUrl}/api/v1/sessions/${this.sessionId}/events/?after_seq=${afterSeq}&role=${encodeURIComponent(this.role)}`;
    const res = await fetch(url, { headers: this.headers });
    const body = await res.json();
    return (body.events || []) as TapeEvent[];
  }

  async close(): Promise<void> {
    const url = `${this.baseUrl}/api/v1/sessions/${this.sessionId}/`;
    await fetch(url, { method: 'DELETE', headers: this.headers });
  }
}

export class LiveSessionHandle {
  constructor(
    public readonly sessionId: string,
    public readonly url: string,
    private readonly baseUrl: string,
    private readonly headers: Record<string, string>
  ) {}

  connect(role: string = 'default'): ActiveSession {
    return new ActiveSession(this.sessionId, role, this.baseUrl, this.headers);
  }
}

export class ThinkClient {
  public readonly baseUrl: string;
  public readonly apiKey?: string;
  private readonly headers: Record<string, string>;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = options.baseUrl || (options.daemonPort ? `http://127.0.0.1:${options.daemonPort}` : 'http://127.0.0.1:5052');
    this.apiKey = options.apiKey;
    this.headers = {};
    if (options.apiKey) {
      this.headers['Authorization'] = `Bearer ${options.apiKey}`;
    }
  }

  static local(port: number = 5052, host: string = '127.0.0.1'): ThinkClient {
    return new ThinkClient({ baseUrl: `http://${host}:${port}` });
  }

  static connect(apiKey: string, baseUrl: string = 'https://api.thinkument.com'): ThinkClient {
    return new ThinkClient({ apiKey, baseUrl });
  }

  private requireCloud(operationName: string): void {
    if (!this.apiKey && (this.baseUrl.includes('127.0.0.1') || this.baseUrl.includes('localhost'))) {
      throw new CloudServiceRequiredError(
        `Operation '${operationName}' requires Thinkument Sovereign Cloud and an API key. For local development, use .live, .embed, or .ops.`
      );
    }
  }

  async health(): Promise<HealthzResponse> {
    const res = await fetch(`${this.baseUrl}/healthz/`, { headers: this.headers });
    return (await res.json()) as HealthzResponse;
  }

  readonly live = {
    create: async (payload: SessionCreatePayload): Promise<LiveSessionHandle> => {
      const res = await fetch(`${this.baseUrl}/api/v1/sessions/`, {
        method: 'POST',
        headers: { ...this.headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = (await res.json()) as SessionCreateResponse;
      return new LiveSessionHandle(data.session_id, data.url, this.baseUrl, this.headers);
    }
  };

  readonly embed = {
    create: async (payload: SessionCreatePayload): Promise<LiveSessionHandle> => {
      return this.live.create(payload);
    }
  };

  readonly ops = {
    execute: async (payload: RelayPayload): Promise<RelayResponse> => {
      const res = await fetch(`${this.baseUrl}/api/v1/ops/execute/`, {
        method: 'POST',
        headers: { ...this.headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      return (await res.json()) as RelayResponse;
    }
  };

  readonly modules = {
    publish: async (payload: ModulePublishPayload | Record<string, any>): Promise<ModuleRecord> => {
      this.requireCloud('modules.publish');
      const body = 'manifest' in payload ? payload : { manifest: payload };
      const res = await fetch(`${this.baseUrl}/api/v1/modules/`, {
        method: 'POST',
        headers: { ...this.headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      return (await res.json()) as ModuleRecord;
    },
    get: async (moduleId: string): Promise<ModuleRecord> => {
      this.requireCloud('modules.get');
      const res = await fetch(`${this.baseUrl}/api/v1/modules/${encodeURIComponent(moduleId)}/`, {
        headers: this.headers
      });
      return (await res.json()) as ModuleRecord;
    },
    list: async (search?: string): Promise<ModuleSummary[]> => {
      this.requireCloud('modules.list');
      const qs = search ? `?search=${encodeURIComponent(search)}` : '';
      const res = await fetch(`${this.baseUrl}/api/v1/modules/${qs}`, {
        headers: this.headers
      });
      return (await res.json()) as ModuleSummary[];
    },
    retire: async (moduleId: string, version: string, reason?: string): Promise<RetireReceipt> => {
      this.requireCloud('modules.retire');
      const res = await fetch(`${this.baseUrl}/api/v1/modules/${encodeURIComponent(moduleId)}/versions/${encodeURIComponent(version)}/retire/`, {
        method: 'POST',
        headers: { ...this.headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: reason || 'retired via sdk' })
      });
      return (await res.json()) as RetireReceipt;
    }
  };

  readonly catalogue = {
    list: async (search?: string): Promise<ModuleSummary[]> => {
      this.requireCloud('catalogue.list');
      const qs = search ? `?search=${encodeURIComponent(search)}` : '';
      const res = await fetch(`${this.baseUrl}/api/v1/module-catalog/${qs}`, {
        headers: this.headers
      });
      return (await res.json()) as ModuleSummary[];
    },
    get: async (moduleId: string): Promise<ModuleRecord> => {
      return this.modules.get(moduleId);
    }
  };

  readonly analytics = {
    listRuns: async (limit: number = 25): Promise<RunAnalytics[]> => {
      this.requireCloud('analytics.listRuns');
      const res = await fetch(`${this.baseUrl}/api/v1/analytics/runs/?limit=${limit}`, {
        headers: this.headers
      });
      return (await res.json()) as RunAnalytics[];
    },
    getMessages: async (runId: string, afterSeq: number = 0): Promise<Record<string, any>> => {
      this.requireCloud('analytics.getMessages');
      const res = await fetch(`${this.baseUrl}/api/v1/analytics/?run_id=${encodeURIComponent(runId)}&after_seq=${afterSeq}`, {
        headers: this.headers
      });
      return (await res.json()) as Record<string, any>;
    }
  };

  readonly storage = {
    upload: async (content: string, filename?: string): Promise<StorageDescriptor> => {
      this.requireCloud('storage.upload');
      const res = await fetch(`${this.baseUrl}/api/v1/storage/upload/`, {
        method: 'POST',
        headers: { ...this.headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, filename: filename || 'asset' })
      });
      return (await res.json()) as StorageDescriptor;
    },
    getUrl: async (ref: string): Promise<StorageDescriptor> => {
      this.requireCloud('storage.getUrl');
      const res = await fetch(`${this.baseUrl}/api/v1/storage/${encodeURIComponent(ref)}/`, {
        headers: this.headers
      });
      return (await res.json()) as StorageDescriptor;
    }
  };
}

/**
 * Canonical Types generated from Thinkument OpenAPI 3.1 specification.
 */

export interface SessionCreatePayload {
  P: Record<string, any>;
  SM?: Record<string, any>;
  C?: Record<string, any>;
  slug?: string;
  title?: string;
  roles?: string[];
  public_view_role?: string;
  role_mismatch_policy?: Record<string, any>;
  opinionation_module?: string;
  metadata?: Record<string, any>;
}

export interface SessionCreateResponse {
  session_id: string;
  url: string;
  status: string;
  roles: string[];
  public_view_role?: string;
}

export interface DispatchPayload {
  action: string;
  user_fill?: Record<string, any>;
  user_signal?: Record<string, any>;
  cursor?: number;
  role?: string;
  identity_id?: string;
}

export interface DispatchResponse {
  status: 'applied' | 'stale_rejected' | 'rejected' | string;
  applied_seq?: number;
  latest_seq?: number;
  error?: string;
}

export interface TapeEvent {
  seq: number;
  type: string;
  role?: string;
  data: Record<string, any>;
  timestamp: string;
}

export interface RelayPayload {
  operation: string;
  args?: Record<string, any>;
  modality?: string;
  context?: Record<string, any>;
}

export interface RelayResponse {
  status: string;
  text?: string;
  embeddings?: number[] | number[][];
  usage?: Record<string, number>;
  data?: Record<string, any>;
  mocked?: boolean;
}

export interface HealthzResponse {
  status: string;
  version: string;
}

export interface ModulePublishPayload {
  manifest: Record<string, any>;
  authoring_template_version?: string;
}

export interface ModuleRecord {
  id: string;
  version_id?: string;
  status: string;
  source_manifest?: Record<string, any>;
  fingerprint?: string;
  [key: string]: any;
}

export interface ModuleSummary {
  id: string;
  name: string;
  version?: string;
  title?: string;
  status?: string;
}

export interface RetireReceipt {
  status: string;
  retired_at?: string;
  reason?: string;
}

export interface RunAnalytics {
  run_id: string;
  kind?: string;
  created_at?: string;
  status?: string;
  [key: string]: any;
}

export interface StorageUploadRequest {
  content: string;
  filename?: string;
}

export interface StorageDescriptor {
  ref: string;
  url?: string;
  filename?: string;
}

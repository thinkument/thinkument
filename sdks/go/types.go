package thinkument

type SessionCreatePayload struct {
	P                  map[string]any `json:"P"`
	SM                 map[string]any `json:"SM,omitempty"`
	C                  map[string]any `json:"C,omitempty"`
	Slug               string         `json:"slug,omitempty"`
	Title              string         `json:"title,omitempty"`
	Roles              []string       `json:"roles,omitempty"`
	PublicViewRole     string         `json:"public_view_role,omitempty"`
	RoleMismatchPolicy map[string]any `json:"role_mismatch_policy,omitempty"`
	OpinionationModule string         `json:"opinionation_module,omitempty"`
	Metadata           map[string]any `json:"metadata,omitempty"`
}

type SessionCreateResponse struct {
	SessionID      string   `json:"session_id"`
	URL            string   `json:"url"`
	Status         string   `json:"status"`
	Roles          []string `json:"roles"`
	PublicViewRole string   `json:"public_view_role,omitempty"`
}

type DispatchPayload struct {
	Action      string         `json:"action"`
	UserFill    map[string]any `json:"user_fill,omitempty"`
	UserSignal  map[string]any `json:"user_signal,omitempty"`
	Cursor      *int           `json:"cursor,omitempty"`
	Role        string         `json:"role,omitempty"`
	IdentityID  string         `json:"identity_id,omitempty"`
}

type DispatchResponse struct {
	Status     string `json:"status"`
	AppliedSeq *int   `json:"applied_seq,omitempty"`
	LatestSeq  *int   `json:"latest_seq,omitempty"`
	Error      string `json:"error,omitempty"`
}

type TapeEvent struct {
	Seq       int            `json:"seq"`
	Type      string         `json:"type"`
	Role      string         `json:"role,omitempty"`
	Data      map[string]any `json:"data"`
	Timestamp string         `json:"timestamp"`
}

type RelayPayload struct {
	Operation string         `json:"operation"`
	Args      map[string]any `json:"args,omitempty"`
	Modality  string         `json:"modality,omitempty"`
	Context   map[string]any `json:"context,omitempty"`
}

type RelayResponse struct {
	Status     string         `json:"status"`
	Text       string         `json:"text,omitempty"`
	Embeddings any            `json:"embeddings,omitempty"`
	Usage      map[string]int `json:"usage,omitempty"`
	Mocked     bool           `json:"mocked,omitempty"`
}

type HealthzResponse struct {
	Status  string `json:"status"`
	Version string `json:"version"`
}

type ModulePublishPayload struct {
	Manifest                 map[string]any `json:"manifest"`
	AuthoringTemplateVersion string         `json:"authoring_template_version,omitempty"`
}

type ModuleRecord struct {
	ID             string         `json:"id"`
	VersionID      string         `json:"version_id,omitempty"`
	Status         string         `json:"status"`
	SourceManifest map[string]any `json:"source_manifest,omitempty"`
	Fingerprint    string         `json:"fingerprint,omitempty"`
}

type ModuleSummary struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	Version string `json:"version,omitempty"`
	Title   string `json:"title,omitempty"`
	Status  string `json:"status,omitempty"`
}

type RetireReceipt struct {
	Status    string `json:"status"`
	RetiredAt string `json:"retired_at,omitempty"`
	Reason    string `json:"reason,omitempty"`
}

type RunAnalytics struct {
	RunID     string `json:"run_id"`
	Kind      string `json:"kind,omitempty"`
	CreatedAt string `json:"created_at,omitempty"`
	Status    string `json:"status,omitempty"`
}

type StorageUploadRequest struct {
	Content  string `json:"content"`
	Filename string `json:"filename,omitempty"`
}

type StorageDescriptor struct {
	Ref      string `json:"ref"`
	URL      string `json:"url,omitempty"`
	Filename string `json:"filename,omitempty"`
}

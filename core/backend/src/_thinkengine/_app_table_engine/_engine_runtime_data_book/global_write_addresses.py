# think-backend/src/thinkengine/_engine_session/implementation/app_table_engine/core/global_state_addresses.py

APP_TABLE_ASSIGNED_STATE_KEY_FOR_DATASPEC_FILLS = "form_fills"

# Program step kinds (string tokens match ui/control/page_flow_controller expectations)
KIND_ATSTART = "ATSTART"
KIND_STEPFN = "STEPFNSTEP"
KIND_FORMEXPAND = "FORMEXPANSIONSTEP"
KIND_MANUAL = "MANUALFILLNEEDEDSTEP"
KIND_ATCOMPLETE = "ATCOMPLETION"

# Canonical engine/runtime state keys (single source of truth)
KEY_SESSION_ID = "session_id"
KEY_PENDING_FORM = "pending_multiframespec"
KEY_PENDING_FORM_ID = "pending_multiframespec_id"

KEY_FORM_PREFILLS = "form_prefills"
KEY_FORM_FILLS = "form_fills"

# Forms emitted storage keys (state-owned)
KEY_FORMS_EMITTED = "forms_emitted"
KEY_FORMS_EMITTED_ORDER = "forms_emitted_order"

# Small engine-owned runtime history/query index.
# This stores invocation/write metadata and refs only; it must never store
# full historical giant payload copies.
KEY_RUNTIME_WRITE_INDEX = "_runtime_write_index_v1"

from __datomatonTM import (
    KEY_DATUM_LIFECYCLE,
)

# Manual IO cache/policy keys.
#
# IMPORTANT:
# - Manual IO runtime caches live on the engine instance, not in state.
# - This key is a metadata/policy key only, not a stored cache table.
KEY_MANUAL_IO_POLICY = "manual_io_policy_v1"

MANUAL_IO_PERSISTENCE_EAGER = "eager"
MANUAL_IO_PERSISTENCE_BOUNDARY = "boundary"
MANUAL_IO_PERSISTENCE_DISABLED = "disabled"

# Directive key consumed by router/multiframespec handler
KEY_multiframespec_PREFILL_VALIDATE_VALUES = "multiframespec_PREFILL_VALIDATE_VALUES"

# Keys that are engine-owned runtime invariants.
# Step fns MUST NOT patch these directly.
RESERVED_PATCH_KEYS = {
    KEY_PENDING_FORM,
    KEY_PENDING_FORM_ID,
    KEY_FORMS_EMITTED,
    KEY_FORMS_EMITTED_ORDER,
    KEY_SESSION_ID,
    KEY_RUNTIME_WRITE_INDEX,
    KEY_DATUM_LIFECYCLE,
    KEY_MANUAL_IO_POLICY,
}

# Back-compat alias (older imports)
_RESERVED_PATCH_KEYS = RESERVED_PATCH_KEYS

# Keys that should not be exposed as "globals" to step-fns/UI.
# These are engine/runtime/session internals, not application globals.
RESERVED_STATE_KEYS = {
    KEY_SESSION_ID,
    KEY_PENDING_FORM,
    KEY_PENDING_FORM_ID,
    KEY_FORMS_EMITTED,
    KEY_FORMS_EMITTED_ORDER,
    KEY_FORM_PREFILLS,
    KEY_FORM_FILLS,
    KEY_RUNTIME_WRITE_INDEX,
    KEY_DATUM_LIFECYCLE,
    KEY_MANUAL_IO_POLICY,
}

# Sentinel used by patch/undo machinery.
_MISSING = object()
MISSING = _MISSING  # back-compat-friendly alias
from __future__ import annotations

LANG_THINK_PROGRAM_V1 = "think_program_v1"
THINK_PROGRAM_KIND_V1 = "think_program_v1"
THINK_PROGRAM_SURFACE_VERSION_V1 = "v1"

_ALLOWED_TOP_LEVEL_KEYS_V1 = {
    "kind",
    "surface_version",
    "symbols",
    "puppeteering",
    "run",
}

_ALLOWED_PROGRAM_KEYS_V1 = {
    "info",
    "widgets",
    "flow",
}

_ALLOWED_PROGRAM_INFO_KEYS_V1 = {
    "id",
    "title",
    "description",
    "args",
}

_ALLOWED_WIDGET_DEF_KEYS_V1 = {
    "widget",
    "title",
    "args",
    "lifecycle",
    "wires",
    "tags",
    "roles",
    "system_flags",
    "authoritative",
}

_ALLOWED_FLOW_ITEM_KEYS_V1 = {
    "id",
    "title",
    "widgets",
    "roles",
    "authoritative",
    "overrides",
}


_ALLOWED_OVERRIDE_KEYS_V1 = {
    "args",
    "wires",
    "lifecycle",
    "tags",
    "roles",
    "system_flags",
    "title",
}

_DEFAULT_KERNEL_FLAGS_V1 = {
    "copy_form_frame_span_args_into_each_datum": True,
    "mount_explode_default": True,
}

_DEFAULT_LIFECYCLE_V1 = {
    "mount_explode": True,
    "max_reexplosions": 10,
    "max_proc_notes": 0,
    "max_messages": 8,
}

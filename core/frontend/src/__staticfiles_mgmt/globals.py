from __future__ import annotations

"""Application-wide constants and package-owned static configuration."""

from __staticfiles_mgmt.machinery import StaticRootSpec

from __examplepydirwstatics.static_assets import (
    STATIC_ROOT as EXAMPLE_DIR_STATIC_ROOT,
)
from live_vial._js.static_assets import (
    STATIC_ROOT as VIAL_JS_STATIC_ROOT,
)


BLUEPRINT_NAME = "thinkengine_flask_ui_app"
STATIC_PACKAGE = "live_vial._json_shell"


# ThinkumentJS owns only the base kernel static tree. Installed higher packages
# contribute namespaced roots and may claim the one installed default
# opinionation module. A concrete launch may select a different registered
# opinionation without mutating this aggregate registry.
STATIC_ROOT_SPECS = (
    StaticRootSpec(
        "__examplepydirwstatics",
        EXAMPLE_DIR_STATIC_ROOT,
    ),
    StaticRootSpec(
        "live_vial/_js",
        VIAL_JS_STATIC_ROOT,
    ),
)


STATIC_SUBDIR = str(STATIC_ROOT_SPECS[0].path)
STATIC_URL_PATH = "/static"

WEB_SHIM_FILENAME = "wrapper_shim.js"


LOCAL_FLASK_RUNTIME_PROFILE = "single_process_threaded_local_v1"
LOCAL_FLASK_RUNTIME_PROFILE_EXTENSION_KEY = (
    "thinkument_local_flask_runtime_profile"
)
LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY = (
    "thinkument_local_flask_session_ids"
)
LOCAL_FLASK_OWNER_PID_EXTENSION_KEY = (
    "thinkument_local_flask_owner_pid"
)


from __staticfiles_mgmt.machinery import (
    InvalidStaticAssetName,
    StaticAssetCollisionError,
    StaticAssetError,
    StaticNamespaceCollisionError,
    StaticOpinionationCollisionError,
    django_get_static_paths,
    get_opinionation_module_filename,
    get_static_paths,
    get_static_root_specs,
    resolve_static_asset_path,
    select_opinionation_module_filename,
    static_asset_matches,
    validate_opinionation_module_filename,
    validate_static_namespace,
)


__all__ = [
    "BLUEPRINT_NAME",
    "InvalidStaticAssetName",
    "LOCAL_FLASK_OWNER_PID_EXTENSION_KEY",
    "LOCAL_FLASK_RUNTIME_PROFILE",
    "LOCAL_FLASK_RUNTIME_PROFILE_EXTENSION_KEY",
    "LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY",
    "STATIC_PACKAGE",
    "STATIC_ROOT_SPECS",
    "STATIC_SUBDIR",
    "STATIC_URL_PATH",
    "StaticAssetCollisionError",
    "StaticAssetError",
    "StaticNamespaceCollisionError",
    "StaticOpinionationCollisionError",
    "StaticRootSpec",
    "WEB_SHIM_FILENAME",
    "django_get_static_paths",
    "get_opinionation_module_filename",
    "get_static_paths",
    "get_static_root_specs",
    "resolve_static_asset_path",
    "select_opinionation_module_filename",
    "static_asset_matches",
    "validate_opinionation_module_filename",
    "validate_static_namespace",
]

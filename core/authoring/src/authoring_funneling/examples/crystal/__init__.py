"""Crystal's strict Python and JSON widget family, published as one pack.

The family demonstrates two authoring forms above one strict profile and
lifecycle: imperative typed Python widgets and a portable JSON-defined widget.
Its own checked HAI appPack and rendering bed require no Metal chrome metadata.
"""
from .declare_pack import app_pack_manifest_v1, register_app_pack_v1
from .publication import authoring_profile_v1, publication_rows, shared_static_roots_v1
from .widgets import CRYSTAL_WIDGET_IDS, register_widget, widget_rows

__all__ = [
    "app_pack_manifest_v1",
    "register_app_pack_v1",
    "authoring_profile_v1",
    "publication_rows",
    "shared_static_roots_v1",
    "widget_rows",
    "register_widget",
    "CRYSTAL_WIDGET_IDS",
]

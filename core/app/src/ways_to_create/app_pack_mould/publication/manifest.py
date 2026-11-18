from __future__ import annotations

"""Compatibility import for the manifest contract now owned by think-app.

Concrete packs should import ``bootstrap_higher_app.app_pack_contract`` (or
return a plain manifest mapping) rather than depend on framework-4-services itself.
"""

from bootstrap_higher_app.app_pack_contract import (
    APP_PACK_ENTRYPOINT_GROUP,
    APP_PACK_MANIFEST_KIND,
    DEFAULT_APP_PACK_ID,
    AppPackManifestV1,
    coerce_app_pack_manifest_v1,
)


__all__ = [
    "APP_PACK_ENTRYPOINT_GROUP",
    "APP_PACK_MANIFEST_KIND",
    "DEFAULT_APP_PACK_ID",
    "AppPackManifestV1",
    "coerce_app_pack_manifest_v1",
]

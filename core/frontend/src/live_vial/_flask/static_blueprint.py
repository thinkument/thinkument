from __future__ import annotations

"""Flask adapter for think-frontend's aggregated static roots."""

from flask import Blueprint, send_file
from werkzeug.exceptions import NotFound

from __staticfiles_mgmt.globals import (
    InvalidStaticAssetName,
    StaticAssetCollisionError,
    resolve_static_asset_path,
)


class AggregatedStaticBlueprint(Blueprint):
    """Blueprint whose ``.static`` endpoint resolves all registered roots."""

    def send_static_file(self, filename: str):
        try:
            path = resolve_static_asset_path(filename)
        except (FileNotFoundError, InvalidStaticAssetName) as exc:
            raise NotFound() from exc

        return send_file(
            path,
            conditional=True,
        )


__all__ = ["AggregatedStaticBlueprint"]
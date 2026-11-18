from __future__ import annotations

"""Verify pure backend-compliant PSMC authoring templates."""

import pytest
from authoring_pure_backend_no_funnel import (
    PROGRAM,
    WIDGETS,
    with_app_pack,
    APP_PACK_SESSION_METADATA_KEY,
)


def test_template_thinkprogram_structure():
    assert PROGRAM is not None
    assert "program_id" in PROGRAM
    assert "flow" in PROGRAM
    assert "widgets" in PROGRAM
    assert "editor" in WIDGETS


def test_template_with_app_pack():
    sm = with_app_pack(app_pack="packito")
    assert APP_PACK_SESSION_METADATA_KEY in sm
    assert sm[APP_PACK_SESSION_METADATA_KEY]["app_pack"] == "packito"

from __future__ import annotations

from _thinksessions.sesh_metadata.__sesh_meta_chainreactionTM_config_surface import (
    register_chainreactiontm_session_metadata_pocket,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM.funks import (
    register_builtin_chainreactionTM_filler_funks,
)


def bootstrap_chainreactiontm_defaults() -> None:
    register_chainreactiontm_session_metadata_pocket(replace=True)
    register_builtin_chainreactionTM_filler_funks()


bootstrap_chainreactiontm_defaults()
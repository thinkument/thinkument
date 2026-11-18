from __future__ import annotations

from _thinksessions.libs_read_write_augmented.chainreactionTM.funks import basic_microtype_v1
from _thinksessions.libs_read_write_augmented.chainreactionTM.funks import title_semantic_v1


def register_builtin_chainreactionTM_filler_funks() -> None:
    basic_microtype_v1.register()
    title_semantic_v1.register()
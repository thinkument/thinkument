from __future__ import annotations

"""
authoring_funneling.d_module_composition_and_stitching.stitching_registry
=========================================================================
Extensible registration of Session Metadata ($SM$) pocket stitching policies.
Enforces the 3 formal laws of $SM$ composition without ad-hoc engine patching.
"""

from enum import Enum
from typing import Any, Dict, Mapping, Optional


class SMPocketStitchingPolicy(str, Enum):
    """Canonical composition policy for an SM metadata pocket during module stitching."""
    HOST_SOVEREIGN = "host_sovereign"        # Host dst value unconditionally wins (physical session bounds)
    LEXICAL_ROLE_REMAP = "lexical_role_remap" # Role references in pocket are remapped via role_map
    STEP_LOCAL_DELEGATE = "step_local"       # Preserved locally for the inlined steps/widgets
    DISJOINT_NAMESPACED = "disjoint_merge"   # Deep-merged under import namespace prefix


class SMPocketStitchingRegistry:
    """Central registry mapping SM pocket names to their composition policy."""
    _POLICIES: Dict[str, SMPocketStitchingPolicy] = {}

    @classmethod
    def register_pocket_policy(
        cls,
        pocket_name: str,
        policy: SMPocketStitchingPolicy,
    ) -> None:
        cls._POLICIES[str(pocket_name)] = policy

    @classmethod
    def get_pocket_policy(
        cls,
        pocket_name: str,
    ) -> SMPocketStitchingPolicy:
        # Default policy for unrecognized dynamic app pockets is DISJOINT_NAMESPACED
        return cls._POLICIES.get(str(pocket_name), SMPocketStitchingPolicy.DISJOINT_NAMESPACED)

    @classmethod
    def all_policies(cls) -> Dict[str, SMPocketStitchingPolicy]:
        return dict(cls._POLICIES)


# Register canonical framework pockets
SMPocketStitchingRegistry.register_pocket_policy("session_storage", SMPocketStitchingPolicy.HOST_SOVEREIGN)
SMPocketStitchingRegistry.register_pocket_policy("manual_io", SMPocketStitchingPolicy.HOST_SOVEREIGN)
SMPocketStitchingRegistry.register_pocket_policy("app_pack_mould", SMPocketStitchingPolicy.HOST_SOVEREIGN)
SMPocketStitchingRegistry.register_pocket_policy("roles", SMPocketStitchingPolicy.LEXICAL_ROLE_REMAP)
SMPocketStitchingRegistry.register_pocket_policy("role_mismatch_policy", SMPocketStitchingPolicy.LEXICAL_ROLE_REMAP)
SMPocketStitchingRegistry.register_pocket_policy("paquete_aesthetics", SMPocketStitchingPolicy.STEP_LOCAL_DELEGATE)
SMPocketStitchingRegistry.register_pocket_policy("chain_reaction", SMPocketStitchingPolicy.STEP_LOCAL_DELEGATE)
SMPocketStitchingRegistry.register_pocket_policy("funk", SMPocketStitchingPolicy.STEP_LOCAL_DELEGATE)


__all__ = [
    "SMPocketStitchingPolicy",
    "SMPocketStitchingRegistry",
]

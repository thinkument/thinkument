from __future__ import annotations

"""
authoring_funneling.d_module_composition_and_stitching.registry
===============================================================
In-memory module registry and catalog discovery for Thinkument Modules.
Enables local resolution of published (P x C) modules during compilation.
"""

from copy import deepcopy
from typing import Any, Dict, List, Mapping, Optional, Tuple

from bindings2bindingsTM import CompilationError
from .manifest import normalize_think_module_v1, validate_think_module_v1


def parse_module_reference(ref: str) -> Tuple[str, Optional[str]]:
    """Parse a module reference string like 'company/flow@1.0.0' or 'company/flow:1.0.0' or 'flow'.
    
    Returns:
        (module_name, version_or_None)
    """
    clean = str(ref or "").strip()
    if "@" in clean:
        parts = clean.split("@", 1)
        return parts[0].strip(), parts[1].strip()
    if ":" in clean:
        parts = clean.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    return clean, None


class ModuleCatalogRegistry:
    """Catalog of registered Thinkument modules available for import."""
    _MODULES: Dict[str, Dict[str, Dict[str, Any]]] = {}

    @classmethod
    def register_module(cls, manifest: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate, normalize, and register a module manifest."""
        normalized = normalize_think_module_v1(manifest)
        name = normalized["name"]
        version = normalized["version"]

        if name not in cls._MODULES:
            cls._MODULES[name] = {}

        cls._MODULES[name][version] = deepcopy(normalized)
        return deepcopy(normalized)

    @classmethod
    def get_module(cls, ref: str) -> Dict[str, Any]:
        """Lookup a module by reference string (e.g. 'pkg@1.0.0' or 'pkg').
        
        If version is omitted, returns the latest registered version.
        Raises CompilationError if not found.
        """
        name, version = parse_module_reference(ref)
        if name not in cls._MODULES or not cls._MODULES[name]:
            raise CompilationError(
                "module_not_found",
                ("module", name),
                f"Module {name!r} is not registered in the catalog",
            )

        versions = cls._MODULES[name]
        if version is not None:
            if version not in versions:
                raise CompilationError(
                    "module_version_not_found",
                    ("module", name, version),
                    f"Version {version!r} of module {name!r} not found. Available: {list(versions.keys())}",
                )
            return deepcopy(versions[version])

        # Return latest registered version (by simple sorted key fallback)
        sorted_versions = sorted(versions.keys())
        return deepcopy(versions[sorted_versions[-1]])

    @classmethod
    def list_modules(cls, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """List summary records of all registered modules."""
        results: List[Dict[str, Any]] = []
        q = (query or "").lower().strip()
        for name, version_map in cls._MODULES.items():
            for version, manifest in version_map.items():
                if not q or q in name.lower() or q in manifest.get("title", "").lower():
                    results.append({
                        "name": name,
                        "version": version,
                        "title": manifest.get("title", name),
                        "interface": deepcopy(manifest["interface"]),
                    })
        return results

    @classmethod
    def retire_module(cls, ref: str) -> bool:
        """Evict a module from the catalog."""
        name, version = parse_module_reference(ref)
        if name not in cls._MODULES:
            return False
        if version is not None:
            removed = cls._MODULES[name].pop(version, None)
            if not cls._MODULES[name]:
                cls._MODULES.pop(name, None)
            return removed is not None
        cls._MODULES.pop(name, None)
        return True

    @classmethod
    def clear(cls) -> None:
        """Clear all registered modules (used in testing)."""
        cls._MODULES.clear()


__all__ = [
    "ModuleCatalogRegistry",
    "parse_module_reference",
]

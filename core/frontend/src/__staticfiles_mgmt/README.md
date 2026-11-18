# Package-owned browser assets

Each package declares browser-only physical directories. Installed providers
contribute them to one logical static namespace, shared by Flask and Django.

```text
service home/settings_storage.py
  → public/PSMC_sessions/bootstrap/bootstrap_back_front_hai_pkgs.py
  → think-app bootstrap_higher_app/higher_bootstrap.py
  → think-app bootstrap_higher_app/bootstrap.py
  → think-frontend __staticfiles_mgmt registry and validation
      ← installed thinkument.static_roots.v1 entry points
          ← framework-4-services: shared HAI runtime + each discovered pack's static_root
          ← _creativity_registrar: explicit family shared-root providers
  → Django STATICFILES_DIRS → finders → collectstatic → configured backend

Flask AggregatedStaticBlueprint → the same registry and logical resolver
```

Discovery follows installed package metadata. Framework and service do not
enumerate creative families or packs. Service adds its own endpoint shims and
UI-webapp static roots alongside the package registry.

## Declare a root

Keep Python helpers outside the browser directory, without an `__init__.py`
inside it. A physical root and logical prefix have different jobs:

```text
physical root / relative filename → logical prefix / relative filename
```

For example, Metal's physical `shared_rendering/static/composition.js` is
published as `_funneled_apps/metal/shared_rendering/composition.js`.
Browser imports use this logical layout; they need not match Python source
paths. CSS imports and URLs must resolve within the published layout too.
Pack styles are declared by the browser pack's `styleUrls`; host shells do not
assume an undeclared kernel stylesheet. Service's explicit `extraCss` remains
available for a launch's additional styles.

```python
from pathlib import Path
from __staticfiles_mgmt import StaticRootSpec

def static_roots_v1():
    return (StaticRootSpec(
        name="example:browser",
        path=Path(__file__).with_name("static").resolve(),
        logical_prefix="example/browser",
        # Optional: only when contributing the installed default opinionation.
        opinionation_module=None,
    ),)
```

Register the provider in the owning distribution:

```toml
[tool.poetry.plugins."thinkument.static_roots.v1"]
example = "example.static_assets:static_roots_v1"
```

A pack's own browser directory is declared by `AppPackManifestV1.static_root`;
framework-4-services mounts it automatically. Register shared roots separately. A family
registrar may deduplicate intentional reuse before returning roots, provided
the normalized mount path and opinionation declaration agree. Bundle every
declared browser resource in the distribution's wheel and sdist.

## Composition and verification

Settings-time discovery validates roots, logical ownership, collisions, and the
single installed default opinionation. Python `.py`, `.pyc`, `.pyo` files and
files under `__pycache__` fail with their owning root and logical path. Invalid
roots must be corrected; collection does not silently filter Python. Other
browser resource types are supported without an extension allowlist.

Settings discovery does not activate runtime contributors or install Django
persistence. `AppConfig.ready()` performs those operations through the separate
runtime bootstrap. Discovery caches describe the installed process composition;
installing packages requires restarting the process. Tests replacing providers
must restore their changes and clear the relevant discovery caches.

Tests verify resolver/Django/Flask equivalence, fresh and repeated filesystem
collection, manifest CSS dependencies, real browser delivery, and installed-wheel
resources outside the checkout. Local collection uses temporary destinations
and needs no cloud credentials. Manifest storage rewrites hashed CSS references.

The explicit remote publication audit checks required files from the current
local inventory against S3 and public HTTP contents. Historical extra objects
in a development bucket do not change that inventory. Bucket cleanup is a
separate operation; a local test never uploads or deletes remote assets.

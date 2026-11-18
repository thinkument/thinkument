from __future__ import annotations

"""One app-owned composition membrane for hosts above ``think-app``.

Higher hosts depend on ``think-app`` and call this module. They never need
to know which lower or adjacent distributions the app currently installs.

There are two metadata-driven extension planes beneath this membrane:

* static roots/opinionations are discovered by think-frontend's aggregate
  static registry during settings/import-safe composition;
* runtime contributors are discovered here after the base composition has been
  validated.

A package therefore owns its files and registration callback, while
``think-app`` owns only whether that package is part of the installed base.
"""

from pathlib import Path
from typing import TypeAlias

from bootstrap_higher_app.installed_contributors import (
    RuntimeContributorActivationV1,
    activate_installed_runtime_contributors_v1,
)


DjangoStaticfilesDir: TypeAlias = Path | tuple[str, Path]


def django_staticfiles_dirs_for_installed_composition_v1(
) -> tuple[DjangoStaticfilesDir, ...]:
    """Return every installed Thinkument static contribution for Django.

    Discovery is metadata-driven. Adding or removing an app dependency that
    publishes ``thinkument.static_roots.v1`` changes this result without any
    package-name edit in Django or in this function.
    """

    from bootstrap_higher_app.bootstrap import django_staticfiles_dirs_v1

    return tuple(django_staticfiles_dirs_v1())


def activate_installed_thinkument_composition_v1(
) -> tuple[RuntimeContributorActivationV1, ...]:
    """Validate static composition, then activate installed runtime callbacks.

    This is the runtime counterpart to settings-time static composition and is
    intentionally host-neutral. Flask, Django, and future hosts use this same
    function instead of maintaining package-specific activation lists.
    """

    from bootstrap_higher_app.bootstrap import activate_bootstrap_higher_app_v1

    activate_bootstrap_higher_app_v1()
    return activate_installed_runtime_contributors_v1()


__all__ = [
    "DjangoStaticfilesDir",
    "activate_installed_thinkument_composition_v1",
    "django_staticfiles_dirs_for_installed_composition_v1",
]

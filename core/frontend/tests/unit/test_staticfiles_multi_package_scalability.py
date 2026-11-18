from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import __staticfiles_mgmt.machinery as machinery


class _FakeEntryPoint:
    def __init__(
        self,
        provider,
        *,
        distribution: str,
        name: str,
    ) -> None:
        self.dist = SimpleNamespace(name=distribution)
        self.name = name
        self.value = f"{distribution}.static_assets:thinkument_static_roots_v1"
        self._provider = provider

    def load(self):
        return self._provider


@pytest.fixture(autouse=True)
def _clear_external_static_cache():
    machinery._external_static_root_specs.cache_clear()
    yield
    machinery._external_static_root_specs.cache_clear()


def _provider(
    *,
    root: Path,
    namespace: str,
    opinionation_module: str | None = None,
):
    def provide():
        return (
            machinery.StaticRootSpec(
                name=f"package:{namespace}",
                path=root,
                logical_prefix=namespace,
                opinionation_module=opinionation_module,
            ),
        )

    return provide


def test_any_number_of_installed_packages_compose_without_host_package_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots: dict[str, Path] = {}
    entry_points = []

    for namespace in ("feature_a", "feature_b", "feature_c"):
        root = tmp_path / namespace
        (root / "opinionations").mkdir(parents=True)
        (root / "opinionations" / "compact.js").write_text(
            f"export const owner = {namespace!r};\n",
            encoding="utf-8",
        )
        roots[namespace] = root.resolve()

        entry_points.append(
            _FakeEntryPoint(
                _provider(
                    root=root,
                    namespace=namespace,
                    opinionation_module=(
                        "opinionations/compact.js"
                        if namespace == "feature_c"
                        else None
                    ),
                ),
                distribution=namespace,
                name="static_roots",
            )
        )

    monkeypatch.setattr(
        machinery,
        "_base_static_root_specs",
        lambda: (),
    )
    monkeypatch.setattr(
        machinery,
        "_selected_static_root_entry_points",
        lambda: tuple(reversed(entry_points)),
    )
    machinery._external_static_root_specs.cache_clear()

    specs = machinery.get_static_root_specs()

    assert {spec.logical_prefix for spec in specs} == set(roots)
    assert set(machinery.django_get_static_paths()) == {
        (namespace, root)
        for namespace, root in roots.items()
    }

    for namespace, root in roots.items():
        logical = f"{namespace}/opinionations/compact.js"
        expected = root / "opinionations" / "compact.js"

        assert machinery.resolve_static_asset_path(logical) == expected
        assert machinery.validate_opinionation_module_filename(logical) == logical

    assert (
        machinery.get_opinionation_module_filename()
        == "feature_c/opinionations/compact.js"
    )

    # Explicit launch choice is pure. It may select any installed JS module and
    # never changes the singleton installed-default claim.
    assert (
        machinery.select_opinionation_module_filename(
            explicit="feature_a/opinionations/compact.js"
        )
        == "feature_a/opinionations/compact.js"
    )
    assert (
        machinery.get_opinionation_module_filename()
        == "feature_c/opinionations/compact.js"
    )

    machinery.validate_static_namespace()

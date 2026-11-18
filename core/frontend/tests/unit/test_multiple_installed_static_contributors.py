from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import __staticfiles_mgmt.machinery as machinery


class _FakeEntryPoint:
    def __init__(
        self,
        loaded,
        *,
        name: str,
        distribution: str,
    ) -> None:
        self.name = name
        self.value = f"{distribution}.static_assets:thinkument_static_roots_v1"
        self.dist = SimpleNamespace(name=distribution)
        self._loaded = loaded

    def load(self):
        return self._loaded


@pytest.fixture(autouse=True)
def _clear_cache():
    machinery._external_static_root_specs.cache_clear()
    yield
    machinery._external_static_root_specs.cache_clear()


def test_multiple_independent_installed_packages_compose_without_central_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hai_root = tmp_path / "hai"
    wrench_root = tmp_path / "wrench"
    hai_root.mkdir()
    wrench_root.mkdir()

    heartbeat = hai_root / "heartbeat.js"
    helper = wrench_root / "helper.mjs"
    heartbeat.write_text("export default {};\n", encoding="utf-8")
    helper.write_text("export default {};\n", encoding="utf-8")

    def hai_provider():
        return (
            machinery.StaticRootSpec(
                name="package:hai-test",
                path=hai_root,
                logical_prefix="hai_test",
                opinionation_module="heartbeat.js",
            ),
        )

    def wrench_provider():
        return (
            machinery.StaticRootSpec(
                name="package:wrench-test",
                path=wrench_root,
                logical_prefix="wrench_test",
            ),
        )

    monkeypatch.setattr(machinery, "_base_static_root_specs", lambda: ())
    monkeypatch.setattr(
        machinery,
        "_selected_static_root_entry_points",
        lambda: (
            _FakeEntryPoint(
                wrench_provider,
                name="wrench",
                distribution="wrench-test",
            ),
            _FakeEntryPoint(
                hai_provider,
                name="hai",
                distribution="hai-test",
            ),
        ),
    )

    specs = machinery.get_static_root_specs()
    assert {spec.name for spec in specs} == {
        "package:hai-test",
        "package:wrench-test",
    }

    machinery.validate_static_namespace()

    assert machinery.resolve_static_asset_path(
        "hai_test/heartbeat.js"
    ) == heartbeat.resolve()
    assert machinery.resolve_static_asset_path(
        "wrench_test/helper.mjs"
    ) == helper.resolve()

    assert (
        machinery.get_opinionation_module_filename()
        == "hai_test/heartbeat.js"
    )
    assert (
        machinery.select_opinionation_module_filename(
            explicit="wrench_test/helper.mjs"
        )
        == "wrench_test/helper.mjs"
    )

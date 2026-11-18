from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import bootstrap_higher_app.installed_contributors as contributors
import bootstrap_higher_app.higher_bootstrap as bootstrap_higher_app
import bootstrap_higher_app.bootstrap as base_bootstrap


class _FakeEntryPoint:
    def __init__(
        self,
        callback,
        *,
        distribution: str,
        name: str,
        value: str,
    ) -> None:
        self.dist = SimpleNamespace(name=distribution)
        self.name = name
        self.value = value
        self._callback = callback

    def load(self):
        if isinstance(self._callback, BaseException):
            raise self._callback
        return self._callback


@pytest.fixture(autouse=True)
def _reset_contributors():
    contributors._reset_runtime_contributors_for_tests()
    yield
    contributors._reset_runtime_contributors_for_tests()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _local_path_dependencies(pyproject: Path) -> set[str]:
    text = pyproject.read_text(encoding="utf-8")
    return set(
        re.findall(
            r"(?m)^([A-Za-z0-9_-]+)\s*=\s*\{\s*path\s*=",
            text,
        )
    )


def test_runtime_contributors_are_deterministic_and_activate_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    first = _FakeEntryPoint(
        lambda: calls.append("first"),
        distribution="a-feature",
        name="register",
        value="a_feature.bootstrap:register_v1",
    )
    second = _FakeEntryPoint(
        lambda: calls.append("second"),
        distribution="b-feature",
        name="register",
        value="b_feature.bootstrap:register_v1",
    )

    # Deliberately return reverse order. Central discovery owns deterministic
    # ordering and callers must not depend on packaging enumeration order.
    monkeypatch.setattr(
        contributors,
        "_metadata_entry_points",
        lambda: (second, first),
    )

    first_receipts = (
        contributors.activate_installed_runtime_contributors_v1()
    )
    second_receipts = (
        contributors.activate_installed_runtime_contributors_v1()
    )

    assert calls == ["first", "second"]
    assert [row.distribution for row in first_receipts] == [
        "a-feature",
        "b-feature",
    ]
    assert [row.activated_now for row in first_receipts] == [True, True]
    assert [row.activated_now for row in second_receipts] == [False, False]


def test_runtime_contributor_contract_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = (
        _FakeEntryPoint(
            RuntimeError("load boom"),
            distribution="broken-load",
            name="register",
            value="broken_load.bootstrap:register_v1",
        ),
        _FakeEntryPoint(
            object(),
            distribution="not-callable",
            name="register",
            value="not_callable.bootstrap:register_v1",
        ),
        _FakeEntryPoint(
            lambda: (_ for _ in ()).throw(RuntimeError("call boom")),
            distribution="broken-call",
            name="register",
            value="broken_call.bootstrap:register_v1",
        ),
    )

    for entry_point in cases:
        contributors._reset_runtime_contributors_for_tests()
        monkeypatch.setattr(
            contributors,
            "_metadata_entry_points",
            lambda entry_point=entry_point: (entry_point,),
        )

        with pytest.raises(contributors.RuntimeContributorError):
            contributors.activate_installed_runtime_contributors_v1()


def test_bootstrap_higher_app_orders_base_before_installed_contributors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    order: list[str] = []

    monkeypatch.setattr(
        base_bootstrap,
        "activate_bootstrap_higher_app_v1",
        lambda: order.append("base"),
    )
    monkeypatch.setattr(
        bootstrap_higher_app,
        "activate_installed_runtime_contributors_v1",
        lambda: order.append("contributors") or (),
    )

    
    assert (
        bootstrap_higher_app.activate_installed_thinkument_composition_v1()
        == ()
    )
    assert order == ["base", "contributors"]


def test_settings_bootstrap_validates_static_roots_without_runtime_activation(tmp_path, monkeypatch):
    import __staticfiles_mgmt.machinery as machinery

    root = tmp_path / 'browser'
    root.mkdir()
    (root / 'index.js').write_text('export default {};')
    spec = machinery.StaticRootSpec(name='feature', path=root, logical_prefix='feature')
    monkeypatch.setattr(machinery, '_base_static_root_specs', lambda: (spec,))
    monkeypatch.setattr(machinery, '_external_static_root_specs', lambda: ())

    def unexpected_activation():
        pytest.fail('settings discovery activated runtime contributors')

    monkeypatch.setattr(bootstrap_higher_app, 'activate_installed_runtime_contributors_v1', unexpected_activation)
    assert bootstrap_higher_app.django_staticfiles_dirs_for_installed_composition_v1() == (('feature', root),)
    (root / 'private.py').write_text('private = True')
    with pytest.raises(machinery.StaticAssetError, match='feature.*private.py'):
        bootstrap_higher_app.django_staticfiles_dirs_for_installed_composition_v1()


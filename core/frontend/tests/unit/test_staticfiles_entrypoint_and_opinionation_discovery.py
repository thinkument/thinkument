from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urljoin

import pytest

import __staticfiles_mgmt.machinery as machinery
from live_vial._flask._helpers_for_local_server import (
    build_local_flask_launch_spec,
)
from live_vial._js.static_assets import STATIC_ROOT as VIAL_JS_STATIC_ROOT


TEST_OPINIONATION_LOGICAL_NAME = "test_opinionations/sufficience.js"


class _FakeEntryPoint:
    def __init__(
        self,
        loaded,
        *,
        name: str = "tests_external_portfolio",
        value: str = (
            "tests_external_portfolio.frontend:"
            "thinkument_static_roots_v1"
        ),
        distribution: str = "tests-external-portfolio",
    ) -> None:
        self.name = name
        self.value = value
        self.dist = SimpleNamespace(name=distribution)
        self._loaded = loaded

    def load(self):
        if isinstance(self._loaded, BaseException):
            raise self._loaded
        return self._loaded


class _FakeEntryPoints(tuple):
    def select(self, *, group: str):
        if group == machinery.THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP:
            return self
        return ()


@pytest.fixture(autouse=True)
def _clear_external_static_cache():
    machinery._external_static_root_specs.cache_clear()
    yield
    machinery._external_static_root_specs.cache_clear()


def _install_only(
    monkeypatch: pytest.MonkeyPatch,
    *entry_points: _FakeEntryPoint,
) -> None:
    monkeypatch.setattr(
        machinery,
        "_base_static_root_specs",
        lambda: (),
    )
    monkeypatch.setattr(
        machinery,
        "_selected_static_root_entry_points",
        lambda: tuple(entry_points),
    )
    machinery._external_static_root_specs.cache_clear()


def _spec(
    *,
    root: Path,
    logical_prefix: str,
    name: str | None = None,
    opinionation_module: str | None = None,
) -> machinery.StaticRootSpec:
    return machinery.StaticRootSpec(
        name=name or f"test:{logical_prefix or 'base'}",
        path=root,
        logical_prefix=logical_prefix,
        opinionation_module=opinionation_module,
    )


def _sufficience_fixture() -> Path:
    return (
        VIAL_JS_STATIC_ROOT
        / "test_opinionations"
        / "sufficience.js"
    ).resolve()


@pytest.mark.parametrize('relative', ['module.py', 'module.pyc', 'module.pyo', '__pycache__/module.txt'])
def test_static_namespace_rejects_python_with_owner_diagnostics(tmp_path, monkeypatch, relative):
    root = tmp_path / 'browser'
    root.mkdir()
    source = root / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('private')
    spec = _spec(root=root, logical_prefix='feature')
    _install_only(monkeypatch, _FakeEntryPoint(lambda: spec))

    with pytest.raises(machinery.StaticAssetError) as error:
        machinery.validate_static_namespace()
    for detail in (spec.name, str(root), str(source), f'feature/{relative}'):
        assert detail in str(error.value)


def test_python_beside_browser_root_does_not_enter_publication(tmp_path, monkeypatch):
    root = tmp_path / 'browser'
    root.mkdir()
    (tmp_path / 'owner.py').write_text('private = True')
    (tmp_path / '__pycache__').mkdir()
    (tmp_path / '__pycache__' / 'owner.pyc').write_bytes(b'cache')
    for filename in ('index.js', 'style.css', 'icon.svg', 'data.json', 'font.woff2'):
        (root / filename).write_bytes(b'public')
    spec = _spec(root=root, logical_prefix='feature')
    _install_only(monkeypatch, _FakeEntryPoint(lambda: spec))

    machinery.validate_static_namespace()
    assert machinery.resolve_static_asset_path('feature/data.json') == root / 'data.json'
    with pytest.raises(FileNotFoundError):
        machinery.resolve_static_asset_path('feature/owner.py')


def _patch_flask_backend(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_id: str,
):
    from live_vial._flask import adapter

    adapter.reset_access_handles()
    created: list[dict] = []

    def create_live_session_from_program(**kwargs):
        created.append(dict(kwargs))
        return {"session_id": session_id}

    monkeypatch.setattr(
        adapter,
        "create_live_session_from_program",
        create_live_session_from_program,
    )
    monkeypatch.setattr(
        adapter,
        "get_live_session_context",
        lambda **kwargs: {"kind": "ATSTART"},
    )
    monkeypatch.setattr(
        adapter,
        "get_live_session_latest_event_seq",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        adapter,
        "delete_live_session",
        lambda **kwargs: {"ok": True},
    )
    return adapter, created


def _launch_spec(*, opinionation_module=...):
    out = {
        "program_language": "think_program_v1",
        "program": {"kind": "placeholder"},
        "session_metadata": {},
        "roles": {},
        "role_mismatch_policy": {},
        "public_view_role": None,
        "start_on_create": False,
    }
    if opinionation_module is not ...:
        out["opinionation_module"] = opinionation_module
    return out


def test_metadata_entrypoint_discovery_contributes_namespaced_static_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "portfolio_static"
    (root / "assets").mkdir(parents=True)
    widget = root / "assets" / "widget.js"
    widget.write_text("export default 1;\n", encoding="utf-8")

    def provider():
        return (
            machinery.StaticRootSpec(
                name="package:tests_external",
                path=root,
                logical_prefix="tests_external",
            ),
        )

    entry_points = _FakeEntryPoints((_FakeEntryPoint(provider),))
    monkeypatch.setattr(
        machinery,
        "_base_static_root_specs",
        lambda: (),
    )
    monkeypatch.setattr(
        machinery,
        "_metadata_entry_points",
        lambda: entry_points,
    )

    specs = machinery.get_static_root_specs()

    assert specs == (
        machinery.StaticRootSpec(
            name="package:tests_external",
            path=root.resolve(),
            logical_prefix="tests_external",
        ),
    )
    assert machinery.django_get_static_paths() == (
        ("tests_external", root.resolve()),
    )
    assert machinery.resolve_static_asset_path(
        "tests_external/assets/widget.js"
    ) == widget.resolve()
    assert machinery.static_asset_matches(
        "tests_external/assets/widget.js"
    ) == (widget.resolve(),)

    with pytest.raises(FileNotFoundError):
        machinery.resolve_static_asset_path("assets/widget.js")

    machinery.validate_static_namespace()


def test_entrypoint_provider_contract_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    cases = (
        (
            _FakeEntryPoint(RuntimeError("load boom"), name="load_boom"),
            machinery.StaticAssetError,
            "could not load Thinkument static-root provider",
        ),
        (
            _FakeEntryPoint(object(), name="not_callable"),
            machinery.StaticAssetError,
            "must resolve to a callable",
        ),
        (
            _FakeEntryPoint(lambda: (), name="empty"),
            machinery.StaticAssetError,
            "returned no roots",
        ),
        (
            _FakeEntryPoint(
                lambda: {"path": str(root)},
                name="wrong_shape",
            ),
            machinery.StaticAssetError,
            "must return StaticRootSpec or a tuple/list",
        ),
        (
            _FakeEntryPoint(
                lambda: (object(),),
                name="wrong_item",
            ),
            machinery.StaticAssetError,
            "did not return StaticRootSpec",
        ),
    )

    for entry_point, error_type, message in cases:
        _install_only(monkeypatch, entry_point)
        with pytest.raises(error_type, match=message):
            machinery.get_static_root_specs(
                require_exists=False
            )
        machinery._external_static_root_specs.cache_clear()


def test_installed_package_static_root_must_be_namespaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "unprefixed"
    root.mkdir()

    def provider():
        return machinery.StaticRootSpec(
            name="package:unprefixed",
            path=root,
        )

    _install_only(
        monkeypatch,
        _FakeEntryPoint(provider),
    )

    with pytest.raises(
        machinery.StaticNamespaceCollisionError,
        match="must declare logical_prefix",
    ):
        machinery.get_static_root_specs()


def test_static_root_registry_rejects_duplicate_name_physical_root_and_missing_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()

    monkeypatch.setattr(
        machinery,
        "_base_static_root_specs",
        lambda: (
            _spec(
                root=one,
                logical_prefix="one",
                name="same",
            ),
            _spec(
                root=two,
                logical_prefix="two",
                name="same",
            ),
        ),
    )
    monkeypatch.setattr(
        machinery,
        "_selected_static_root_entry_points",
        lambda: (),
    )
    machinery._external_static_root_specs.cache_clear()

    with pytest.raises(
        machinery.StaticNamespaceCollisionError,
        match="same static-root name",
    ):
        machinery.get_static_root_specs()

    monkeypatch.setattr(
        machinery,
        "_base_static_root_specs",
        lambda: (
            _spec(
                root=one,
                logical_prefix="one",
                name="one",
            ),
            _spec(
                root=one,
                logical_prefix="two",
                name="two",
            ),
        ),
    )

    with pytest.raises(
        machinery.StaticNamespaceCollisionError,
        match="same physical static root",
    ):
        machinery.get_static_root_specs()

    missing = tmp_path / "missing"

    monkeypatch.setattr(
        machinery,
        "_base_static_root_specs",
        lambda: (
            _spec(
                root=missing,
                logical_prefix="missing",
            ),
        ),
    )

    with pytest.raises(
        machinery.StaticAssetError,
        match="are missing",
    ):
        machinery.get_static_root_specs()

    assert (
        machinery.get_static_root_specs(
            require_exists=False
        )[0].path
        == missing.resolve()
    )


def test_installed_opinionation_claim_is_logical_namespaced_and_singleton(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_root = tmp_path / "default"
    other_root = tmp_path / "other"
    default_root.mkdir()
    other_root.mkdir()

    default_module = default_root / "default.js"
    default_module.write_text(
        "export default {};\n",
        encoding="utf-8",
    )

    (other_root / "alternate.js").write_text(
        "export default {};\n",
        encoding="utf-8",
    )

    specs = (
        _spec(
            root=other_root,
            logical_prefix="other",
        ),
        _spec(
            root=default_root,
            logical_prefix="default_ui",
            opinionation_module="default.js",
        ),
    )

    monkeypatch.setattr(
        machinery,
        "get_static_root_specs",
        lambda *, require_exists=True: specs,
    )

    assert (
        machinery.get_opinionation_module_filename()
        == "default_ui/default.js"
    )

    assert (
        machinery.resolve_static_asset_path(
            "default_ui/default.js"
        )
        == default_module.resolve()
    )

    assert (
        machinery.select_opinionation_module_filename()
        == "default_ui/default.js"
    )

    assert machinery.select_opinionation_module_filename(
        explicit="other/alternate.js",
    ) == "other/alternate.js"

    assert machinery.select_opinionation_module_filename(
        explicit=None,
        use_installed_default=False,
    ) is None

    # Per-launch selection is pure and never mutates the installed claim.
    assert (
        machinery.get_opinionation_module_filename()
        == "default_ui/default.js"
    )


def test_opinionation_claim_and_explicit_selection_validation_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    (first / "one.js").write_text(
        "export default {};\n",
        encoding="utf-8",
    )
    (second / "two.mjs").write_text(
        "export default {};\n",
        encoding="utf-8",
    )
    (second / "not-module.txt").write_text(
        "nope\n",
        encoding="utf-8",
    )

    specs = (
        _spec(
            root=first,
            logical_prefix="first",
            opinionation_module="one.js",
        ),
        _spec(
            root=second,
            logical_prefix="second",
            opinionation_module="two.mjs",
        ),
    )

    monkeypatch.setattr(
        machinery,
        "get_static_root_specs",
        lambda *, require_exists=True: specs,
    )

    with pytest.raises(
        machinery.StaticOpinionationCollisionError
    ):
        machinery.get_opinionation_module_filename()

    # Explicit selection does not consult singleton-default precedence; it
    # must still name exactly one registered JavaScript asset.
    assert machinery.validate_opinionation_module_filename(
        "second/two.mjs"
    ) == "second/two.mjs"

    with pytest.raises(
        machinery.InvalidStaticAssetName
    ):
        machinery.validate_opinionation_module_filename(
            "second/not-module.txt"
        )

    with pytest.raises(
        machinery.InvalidStaticAssetName
    ):
        machinery.validate_opinionation_module_filename(
            "../escape.js"
        )

    with pytest.raises(FileNotFoundError):
        machinery.validate_opinionation_module_filename(
            "second/missing.js"
        )


def test_missing_or_non_javascript_installed_opinionation_claim_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    monkeypatch.setattr(
        machinery,
        "get_static_root_specs",
        lambda *, require_exists=True: (
            _spec(
                root=root,
                logical_prefix="pkg",
                opinionation_module="missing.js",
            ),
        ),
    )

    with pytest.raises(
        machinery.StaticAssetError,
        match="is missing",
    ):
        machinery.get_opinionation_module_filename()

    text_file = root / "opinionation.txt"
    text_file.write_text(
        "not js\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        machinery,
        "get_static_root_specs",
        lambda *, require_exists=True: (
            _spec(
                root=root,
                logical_prefix="pkg",
                opinionation_module="opinionation.txt",
            ),
        ),
    )

    with pytest.raises(
        machinery.StaticAssetError,
        match="must be a .js or .mjs",
    ):
        machinery.get_opinionation_module_filename()


def test_static_namespace_detects_file_collision_and_file_directory_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    (first / "same.js").write_text(
        "one\n",
        encoding="utf-8",
    )
    (second / "same.js").write_text(
        "two\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        machinery,
        "get_static_root_specs",
        lambda *args, **kwargs: (
            _spec(
                root=first,
                logical_prefix="",
            ),
            _spec(
                root=second,
                logical_prefix="",
            ),
        ),
    )

    with pytest.raises(
        machinery.StaticNamespaceCollisionError,
        match="multiple physical owners",
    ):
        machinery.validate_static_namespace()

    first.joinpath("same.js").unlink()
    second.joinpath("same.js").unlink()

    (first / "pkg").write_text(
        "file\n",
        encoding="utf-8",
    )
    (second / "pkg").mkdir()
    (second / "pkg" / "child.js").write_text(
        "child\n",
        encoding="utf-8",
    )

    with pytest.raises(
        machinery.StaticNamespaceCollisionError,
        match="file/directory conflicts",
    ):
        machinery.validate_static_namespace()


def test_flask_launch_spec_keeps_opinionation_out_of_session_metadata() -> None:
    wrapper = {
        "program_language": "think_program_v1",
        "program": {"kind": "placeholder"},
    }

    defaulted = build_local_flask_launch_spec(
        wrapper=wrapper
    )
    assert "opinionation_module" not in defaulted
    assert (
        "opinionation_module"
        not in defaulted["session_metadata"]
    )

    surfaced = build_local_flask_launch_spec(
        wrapper={
            **wrapper,
            "session_surface": {
                "opinionation_module": (
                    "default_ui/default.js"
                ),
            },
        }
    )

    assert (
        surfaced["opinionation_module"]
        == "default_ui/default.js"
    )
    assert (
        "opinionation_module"
        not in surfaced["session_metadata"]
    )

    overridden = build_local_flask_launch_spec(
        wrapper={
            **wrapper,
            "session_surface": {
                "opinionation_module": (
                    "default_ui/default.js"
                ),
            },
        },
        ui_session_opts={
            "opinionation_module": (
                TEST_OPINIONATION_LOGICAL_NAME
            ),
        },
    )

    assert (
        overridden["opinionation_module"]
        == TEST_OPINIONATION_LOGICAL_NAME
    )
    assert (
        "opinionation_module"
        not in overridden["session_metadata"]
    )

    disabled = build_local_flask_launch_spec(
        wrapper=wrapper,
        ui_session_opts={
            "opinionation_module": None,
        },
    )

    assert "opinionation_module" in disabled
    assert disabled["opinionation_module"] is None
    assert (
        "opinionation_module"
        not in disabled["session_metadata"]
    )


def test_invalid_launch_opinionation_fails_before_backend_session_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from live_vial._flask import adapter
    from live_vial._flask.server_wrapper import (
        create_app_for_program,
    )

    adapter.reset_access_handles()

    root = tmp_path / "root"
    root.mkdir()

    specs = (
        _spec(
            root=root,
            logical_prefix="test_ui",
        ),
    )

    monkeypatch.setattr(
        machinery,
        "get_static_root_specs",
        lambda *, require_exists=True: specs,
    )

    allocations = 0

    def unexpected_allocation(**kwargs):
        nonlocal allocations
        allocations += 1
        return {
            "session_id": "should-not-exist",
        }

    monkeypatch.setattr(
        adapter,
        "create_live_session_from_program",
        unexpected_allocation,
    )

    with pytest.raises(FileNotFoundError):
        create_app_for_program(
            launch_spec=_launch_spec(
                opinionation_module=(
                    "test_ui/missing.js"
                ),
            )
        )

    assert allocations == 0
    adapter.reset_access_handles()


def test_flask_page_selects_serves_and_browser_resolves_real_sufficience_opinionation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from live_vial._flask.server_wrapper import (
        close_app_sessions,
        create_app_for_program,
        get_app_launch_bundle,
    )

    fixture = _sufficience_fixture()

    assert fixture.is_file(), fixture
    assert (VIAL_JS_STATIC_ROOT / "womb.js").is_file()

    # sufficience.js now lives inside VIAL_JS_STATIC_ROOT itself. It is already
    # part of the ordinary aggregate static namespace, so do NOT register
    # fixture.parent as a second StaticRootSpec.
    machinery.validate_static_namespace()

    assert machinery.resolve_static_asset_path(
        TEST_OPINIONATION_LOGICAL_NAME
    ).resolve() == fixture

    assert machinery.static_asset_matches(
        TEST_OPINIONATION_LOGICAL_NAME
    ) == (fixture,)

    adapter, allocations = _patch_flask_backend(
        monkeypatch,
        session_id="sufficience-static-e2e-session",
    )

    app = create_app_for_program(
        launch_spec=_launch_spec(
            opinionation_module=(
                TEST_OPINIONATION_LOGICAL_NAME
            )
        )
    )

    try:
        assert len(allocations) == 1

        bundle = get_app_launch_bundle(app)
        access_id = bundle["selected_access_id"]
        client = app.test_client()

        page = client.get(
            f"/think/run/{access_id}/page/"
        )
        assert page.status_code == 200

        html = page.get_data(as_text=True)

        expected_url = (
            "/think/static/"
            "test_opinionations/sufficience.js"
        )

        assert (
            f'"opinionation":"{expected_url}"'
            in html
        )

        module = client.get(expected_url)
        assert module.status_code == 200

        source = module.get_data(as_text=True)

        assert "SUFFICIENCE_OPINIONATION_ID" in source
        assert "thinkument_front_opinionation_v2" in source
        assert "createOpinionation" in source

        assert (
            'SUFFICIENCE_BROWSER_WOMB_SPECIFIER = "../womb.js"'
            in source
        )
        assert (
            "SUFFICIENCE_NODE_WOMB_SPECIFIER"
            in source
        )

        # The browser-relative import resolves through the aggregate static
        # namespace.
        womb_url = urljoin(
            expected_url,
            "../womb.js",
        )

        assert womb_url == "/think/static/womb.js"

        womb_module = client.get(
            womb_url
        )

        assert womb_module.status_code == 200
        assert (
            "createWombRuntime"
            in womb_module.get_data(as_text=True)
        )

        assert (
            module.headers["X-Content-Type-Options"]
            == "nosniff"
        )
        assert (
            module.headers["Cache-Control"]
            .startswith("no-store")
        )

    finally:
        close_app_sessions(app)
        adapter.reset_access_handles()


def test_explicit_null_disables_an_installed_default_for_only_that_flask_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from live_vial._flask.server_wrapper import (
        close_app_sessions,
        create_app_for_program,
        get_app_launch_bundle,
    )

    root = tmp_path / "default"
    root.mkdir()

    (root / "default.js").write_text(
        "export default {};\n",
        encoding="utf-8",
    )

    specs = (
        _spec(
            root=root,
            logical_prefix="default_ui",
            opinionation_module="default.js",
        ),
    )

    monkeypatch.setattr(
        machinery,
        "get_static_root_specs",
        lambda *, require_exists=True: specs,
    )

    adapter, _ = _patch_flask_backend(
        monkeypatch,
        session_id="disabled-opinionation-session",
    )

    assert (
        machinery.get_opinionation_module_filename()
        == "default_ui/default.js"
    )

    app = create_app_for_program(
        launch_spec=_launch_spec(
            opinionation_module=None
        )
    )

    try:
        access_id = get_app_launch_bundle(
            app
        )["selected_access_id"]

        page = app.test_client().get(
            f"/think/run/{access_id}/page/"
        )

        assert page.status_code == 200
        assert (
            '"opinionation":""'
            in page.get_data(as_text=True)
        )

        # Disabling one launch does not mutate the installed composition.
        assert (
            machinery.get_opinionation_module_filename()
            == "default_ui/default.js"
        )

    finally:
        close_app_sessions(app)
        adapter.reset_access_handles()

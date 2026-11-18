from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin

import pytest

import __staticfiles_mgmt as staticfiles
import __staticfiles_mgmt.machinery as machinery
import ways_to_create.app_pack_mould.static_assets as hai_static_assets
from ways_to_create.app_pack_mould.static_assets import (
    STATIC_ROOT_SPEC as HAI_STATIC_ROOT_SPEC,
    THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP,
    thinkument_static_roots_v1,
)
from bootstrap_higher_app.bootstrap import (
    inspect_thinkument_frontend_assets_v1,
    thinkument_opinionation_module_filename_v1,
)
from live_vial._flask import adapter
from live_vial._flask._helpers_for_local_server import (
    build_local_flask_launch_spec,
)
from live_vial._flask.server_wrapper import (
    close_app_sessions,
    create_app_for_program,
    get_app_launch_bundle,
)
from live_vial._json_shell.html_shell_rendering import (
    build_thinkument_client_config,
)


HAI_DEFAULT_OPINIONATION = (
    "bootstrap_higher_app/thinkumentJS_app_heartbeat.js"
)
TEST_OPINIONATION_LOGICAL_NAME = (
    "test_opinionations/sufficience.js"
)


def _app_packs_examples_src_root() -> Path:
    return Path(hai_static_assets.__file__).resolve().parents[1]


def _sufficience_fixture() -> Path:
    live_vial_root = Path(adapter.__file__).resolve().parents[1]
    return (
        live_vial_root
        / "_js"
        / "thinkumentJS"
        / "test_opinionations"
        / "sufficience.js"
    ).resolve()


def _composed_test_specs() -> tuple[machinery.StaticRootSpec, ...]:
    fixture = _sufficience_fixture()
    assert fixture.is_file(), fixture

    discovered = machinery.get_static_root_specs()
    passive_specs = tuple(
        spec
        for spec in discovered
        if (
            spec.logical_prefix != HAI_STATIC_ROOT_SPEC.logical_prefix
            and spec.opinionation_module is None
        )
    )
    return (*passive_specs, HAI_STATIC_ROOT_SPEC)


def _patch_backend(monkeypatch: pytest.MonkeyPatch):
    adapter.reset_access_handles()
    created: list[dict] = []
    sequence = 0

    def create_live_session_from_program(**kwargs):
        nonlocal sequence
        sequence += 1
        created.append(dict(kwargs))
        return {"session_id": f"app-opinionation-test-{sequence}"}

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
    return created


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


def _page_for(app):
    access_id = get_app_launch_bundle(app)["selected_access_id"]
    return app.test_client().get(f"/think/run/{access_id}/page/")


def test_hai_physically_owns_the_default_static_contribution() -> None:
    roots = thinkument_static_roots_v1()

    assert THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP == "thinkument.static_roots.v1"
    assert roots[0] == HAI_STATIC_ROOT_SPEC
    assert HAI_STATIC_ROOT_SPEC.name == "package:think-app"
    assert HAI_STATIC_ROOT_SPEC.logical_prefix == "bootstrap_higher_app"
    assert HAI_STATIC_ROOT_SPEC.opinionation_module == "thinkumentJS_app_heartbeat.js"
    assert HAI_STATIC_ROOT_SPEC.path.name == "js"
    assert (
        HAI_STATIC_ROOT_SPEC.path / HAI_STATIC_ROOT_SPEC.opinionation_module
    ).is_file()
    assert not tuple(HAI_STATIC_ROOT_SPEC.path.rglob("*.py"))

    assert HAI_STATIC_ROOT_SPEC.path.resolve() == (
        _app_packs_examples_src_root()
        / "app_pack_mould"
        / "js"
    ).resolve()

    by_name = {spec.name: spec for spec in roots[1:]}
    assert set(by_name) >= {
        "app-pack:example_notes",
    }

    for app_pack_id in ("example_notes",):
        spec = by_name[f"app-pack:{app_pack_id}"]

        assert (
            spec.logical_prefix
            == f"bootstrap_higher_app/app_packs_examples/{app_pack_id}"
        )
        assert spec.path.resolve() == (
            _app_packs_examples_src_root()
            / "app_packs_examples"
            / app_pack_id
            / "js"
        ).resolve()
        assert (spec.path / "index.js").is_file()
        assert not tuple(spec.path.rglob("*.py"))


def test_client_config_has_one_opinionation_module_and_no_portfolio_list() -> None:
    config = build_thinkument_client_config(
        root_id="root",
        identity_id="identity",
        role="maker",
        endpoints={
            "latestEventSeq": "/latest",
            "events": "/events",
            "eps": "/eps",
            "dispatch": "/dispatch",
            "dispatchFunked": "/dispatch-funked",
        },
        initial_state={"session_id": "session"},
        initial_event_seq=0,
        opinionation_module_url="/static/acme/opinionation.js",
    )

    assert config["modules"] == {
        "opinionation": "/static/acme/opinionation.js",
    }
    assert "renderportfolioPortfolios" not in config["modules"]


def test_launch_spec_keeps_opinionation_out_of_session_metadata() -> None:
    wrapper = {
        "program_language": "think_program_v1",
        "program": {"kind": "placeholder"},
    }

    defaulted = build_local_flask_launch_spec(wrapper=wrapper)
    assert "opinionation_module" not in defaulted
    assert "opinionation_module" not in defaulted["session_metadata"]

    selected = build_local_flask_launch_spec(
        wrapper=wrapper,
        ui_session_opts={
            "opinionation_module": TEST_OPINIONATION_LOGICAL_NAME,
        },
    )
    assert selected["opinionation_module"] == TEST_OPINIONATION_LOGICAL_NAME
    assert "opinionation_module" not in selected["session_metadata"]

    disabled = build_local_flask_launch_spec(
        wrapper=wrapper,
        ui_session_opts={"opinionation_module": None},
    )
    assert disabled["opinionation_module"] is None
    assert "opinionation_module" not in disabled["session_metadata"]


def test_bootstrap_higher_app_reports_hai_owned_default_and_full_static_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = _composed_test_specs()

    monkeypatch.setattr(
        machinery,
        "get_static_root_specs",
        lambda *args, **kwargs: specs,
    )
    monkeypatch.setattr(
        staticfiles,
        "get_static_root_specs",
        lambda *args, **kwargs: specs,
    )
    monkeypatch.setattr(
        staticfiles,
        "get_opinionation_module_filename",
        machinery.get_opinionation_module_filename,
    )
    monkeypatch.setattr(
        staticfiles,
        "validate_static_namespace",
        machinery.validate_static_namespace,
    )

    report = inspect_thinkument_frontend_assets_v1()

    assert report["kind"] == "thinkument_frontend_assets_v1"
    assert report["opinionation_module"] == HAI_DEFAULT_OPINIONATION
    assert (
        thinkument_opinionation_module_filename_v1()
        == HAI_DEFAULT_OPINIONATION
    )

    hai_rows = [
        row
        for row in report["static_roots"]
        if row["name"] == "package:think-app"
    ]
    assert len(hai_rows) == 1
    assert hai_rows[0]["logical_prefix"] == "bootstrap_higher_app"
    assert (
        hai_rows[0]["opinionation_module"]
        == "thinkumentJS_app_heartbeat.js"
    )

    assert (
        machinery.resolve_static_asset_path(
            TEST_OPINIONATION_LOGICAL_NAME
        ).resolve()
        == _sufficience_fixture()
    )


def test_hai_default_override_and_disable_are_launch_local_and_browser_resolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = _composed_test_specs()
    fixture = _sufficience_fixture()

    monkeypatch.setattr(
        machinery,
        "get_static_root_specs",
        lambda *args, **kwargs: specs,
    )

    machinery.validate_static_namespace()
    assert (
        machinery.get_opinionation_module_filename()
        == HAI_DEFAULT_OPINIONATION
    )
    assert (
        machinery.select_opinionation_module_filename(
            explicit=TEST_OPINIONATION_LOGICAL_NAME
        )
        == TEST_OPINIONATION_LOGICAL_NAME
    )

    created = _patch_backend(monkeypatch)
    apps = []

    try:
        default_app = create_app_for_program(
            launch_spec=_launch_spec()
        )
        override_app = create_app_for_program(
            launch_spec=_launch_spec(
                opinionation_module=TEST_OPINIONATION_LOGICAL_NAME
            )
        )
        disabled_app = create_app_for_program(
            launch_spec=_launch_spec(
                opinionation_module=None
            )
        )
        apps.extend((default_app, override_app, disabled_app))

        assert len(created) == 3
        for call in created:
            assert "opinionation_module" not in call["session_metadata"]

        default_url = (
            "/think/static/bootstrap_higher_app/"
            "thinkumentJS_app_heartbeat.js"
        )
        default_page = _page_for(default_app)
        assert default_page.status_code == 200
        assert (
            f'"opinionation":"{default_url}"'
            in default_page.get_data(as_text=True)
        )

        default_module = default_app.test_client().get(default_url)
        assert default_module.status_code == 200
        default_source = default_module.get_data(as_text=True)
        assert "app_packs_examples_CORE_OPINIONATION_ID" in default_source
        assert 'from "../womb.js"' in default_source

        default_womb_url = urljoin(default_url, "../womb.js")
        assert default_womb_url == "/think/static/womb.js"
        assert (
            default_app.test_client()
            .get(default_womb_url)
            .status_code
            == 200
        )

        override_url = (
            "/think/static/test_opinionations/sufficience.js"
        )
        override_page = _page_for(override_app)
        assert override_page.status_code == 200
        assert (
            f'"opinionation":"{override_url}"'
            in override_page.get_data(as_text=True)
        )

        override_module = override_app.test_client().get(override_url)
        assert override_module.status_code == 200
        assert override_module.get_data() == fixture.read_bytes()
        assert "createOpinionation" in override_module.get_data(
            as_text=True
        )

        override_womb_url = urljoin(override_url, "../womb.js")
        assert override_womb_url == "/think/static/womb.js"
        assert (
            override_app.test_client()
            .get(override_womb_url)
            .status_code
            == 200
        )

        disabled_page = _page_for(disabled_app)
        assert disabled_page.status_code == 200
        assert (
            '"opinionation":""'
            in disabled_page.get_data(as_text=True)
        )

        # All launches share one immutable installed default claim.
        assert (
            machinery.get_opinionation_module_filename()
            == HAI_DEFAULT_OPINIONATION
        )
    finally:
        for app in apps:
            close_app_sessions(app)
        adapter.reset_access_handles()


def test_invalid_explicit_opinionation_fails_before_session_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = _composed_test_specs()

    monkeypatch.setattr(
        machinery,
        "get_static_root_specs",
        lambda *args, **kwargs: specs,
    )
    machinery.validate_static_namespace()

    adapter.reset_access_handles()
    allocations = 0

    def unexpected_create(**kwargs):
        nonlocal allocations
        allocations += 1
        return {"session_id": "unexpected"}

    monkeypatch.setattr(
        adapter,
        "create_live_session_from_program",
        unexpected_create,
    )

    with pytest.raises(FileNotFoundError):
        create_app_for_program(
            launch_spec=_launch_spec(
                opinionation_module="test_opinionations/missing.js"
            )
        )

    assert allocations == 0
    assert (
        machinery.get_opinionation_module_filename()
        == HAI_DEFAULT_OPINIONATION
    )
    adapter.reset_access_handles()
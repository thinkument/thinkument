from __future__ import annotations

import argparse

import pytest

from ways_to_run.live_run_atelier._whichserver_agnostic_demo_launcher import (
    add_live_run_opinionation_arguments_v1,
    choose_public_view_role_v1,
    live_demo_opinionation_selection_v1,
    live_run_opinionation_from_namespace_v1,
    split_session_metadata_v1,
)


def test_opinionation_selection_distinguishes_default_override_and_disable() -> None:
    default = live_demo_opinionation_selection_v1(
        module=None,
        disable=False,
    )
    assert default.module is None
    assert default.use_installed_default is True

    override = live_demo_opinionation_selection_v1(
        module="test_opinionations/sufficience.js",
        disable=False,
    )
    assert override.module == "test_opinionations/sufficience.js"
    assert override.use_installed_default is True

    disabled = live_demo_opinionation_selection_v1(
        module=None,
        disable=True,
    )
    assert disabled.module is None
    assert disabled.use_installed_default is False

    with pytest.raises(ValueError):
        live_demo_opinionation_selection_v1(
            module="x.js",
            disable=True,
        )


def test_shared_cli_makes_opinionation_override_and_disable_mutually_exclusive() -> None:
    parser = argparse.ArgumentParser()
    add_live_run_opinionation_arguments_v1(parser)

    args = parser.parse_args([])
    selection = live_run_opinionation_from_namespace_v1(args)
    assert selection.module is None
    assert selection.use_installed_default is True

    args = parser.parse_args([
        "--opinionation-module",
        "test_opinionations/sufficience.js",
    ])
    selection = live_run_opinionation_from_namespace_v1(args)
    assert selection.module == "test_opinionations/sufficience.js"

    args = parser.parse_args(["--no-opinionation"])
    selection = live_run_opinionation_from_namespace_v1(args)
    assert selection.use_installed_default is False

    with pytest.raises(SystemExit):
        parser.parse_args([
            "--opinionation-module",
            "x.js",
            "--no-opinionation",
        ])


def test_sm_split_and_default_role_are_host_neutral_and_ordered() -> None:
    metadata, roles, policy = split_session_metadata_v1({
        "storage": {"max_events": 20},
        "roles": {
            "maker": {"read_roles": []},
            "reviewer": {"read_roles": []},
        },
        "role_mismatch_policy": {"mode": "obfuscate"},
    })

    assert metadata == {"storage": {"max_events": 20}}
    assert list(roles) == ["maker", "reviewer"]
    assert policy == {"mode": "obfuscate"}
    assert choose_public_view_role_v1(
        roles=roles,
        requested=None,
    ) == "maker"

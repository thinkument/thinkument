"""Installed browser defaults are inert extensions of the transport boot envelope."""
from dataclasses import dataclass

import pytest
from live_vial._json_shell import html_shell_rendering as shell


@dataclass
class Provider:
    name: str
    values: object
    value = "independent.provider:boot"
    dist = None

    def load(self):
        return lambda: self.values


class Providers(tuple):
    def select(self, *, group):
        assert group == shell.THINKUMENT_BROWSER_BOOT_ENTRYPOINT_GROUP
        return self


def test_installed_browser_defaults_are_composed_without_transport_overrides(monkeypatch):
    monkeypatch.setattr(shell, "entry_points", lambda: Providers((Provider("runtime", {"appPackDefault": "second_pack"}),)))
    config = shell.build_thinkument_client_config(
        root_id="root", identity_id="identity", role="maker",
        endpoints={key: "/" + key for key in ("latestEventSeq", "events", "eps", "dispatch", "dispatchFunked")},
        initial_state={}, initial_event_seq=0,
    )
    assert config["appPackDefault"] == "second_pack"
    assert config["kind"] == "thinkument_web_client_config_v1"


@pytest.mark.parametrize("values", [{"kind": "replace"}, {"bad": lambda: None}, ["not a mapping"]])
def test_invalid_browser_contributors_report_the_provider(monkeypatch, values):
    monkeypatch.setattr(shell, "entry_points", lambda: Providers((Provider("invalid", values),)))
    with pytest.raises(ValueError, match="invalid browser boot provider.*independent.provider"):
        shell.installed_browser_boot_config_v1()


def test_duplicate_boot_keys_report_both_providers(monkeypatch):
    monkeypatch.setattr(shell, "entry_points", lambda: Providers((Provider("one", {"default": 1}), Provider("two", {"default": 2}))))
    with pytest.raises(ValueError, match="two.*duplicate.*one"):
        shell.installed_browser_boot_config_v1()

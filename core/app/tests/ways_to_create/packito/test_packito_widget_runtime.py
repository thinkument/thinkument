from __future__ import annotations

from packito_fixture.py.widget_runtime import lifecycle_shell_v1


def test_lifecycle_shell_preserves_renderer_and_kernel_owned_args() -> None:
    prior = {
        "id": "opening",
        "title": "old",
        "micros": [{"name": "old"}],
        "lifecycle": {"max_reexplosions": 12},
        "args": {
            "hai_renderer": "packito.choice.v1",
            "prompt": "Choose an opening direction",
            "__kernel": {
                "past_wires": {
                    "source": {
                        "key": "previous",
                        "value": {"state": {"accepted_choice": "alpha"}},
                    }
                }
            },
        },
        "platform_owned_marker": {"keep": True},
    }

    next_shell = lifecycle_shell_v1(
        prior,
        title="new",
        micros=[{"name": "choice", "type": "select"}],
    )

    assert next_shell["title"] == "new"
    assert next_shell["micros"] == [{"name": "choice", "type": "select"}]
    assert next_shell["args"]["hai_renderer"] == "packito.choice.v1"
    assert next_shell["args"]["__kernel"] == prior["args"]["__kernel"]
    assert next_shell["platform_owned_marker"] == {"keep": True}

    # The helper must copy, not alias, the current-effective shell.
    next_shell["args"]["prompt"] = "changed"
    next_shell["args"]["__kernel"]["past_wires"]["source"]["key"] = "changed"
    assert prior["args"]["prompt"] == "Choose an opening direction"
    assert prior["args"]["__kernel"]["past_wires"]["source"]["key"] == "previous"

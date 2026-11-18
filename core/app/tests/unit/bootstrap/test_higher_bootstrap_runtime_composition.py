from __future__ import annotations

from typing import Any

import bootstrap_higher_app.runtime as runtime


def test_flask_create_uses_the_full_installed_composition(
    monkeypatch,
) -> None:
    calls: list[str] = []
    sentinel = object()

    monkeypatch.setattr(
        runtime,
        "activate_installed_thinkument_composition_v1",
        lambda: calls.append("activate"),
    )
    monkeypatch.setattr(
        runtime,
        "_create_app_for_program",
        lambda *, launch_spec: (
            calls.append(f"create:{launch_spec['kind']}"),
            sentinel,
        )[1],
    )

    result = runtime.create_app_for_program(
        launch_spec={"kind": "launch"}
    )

    assert result is sentinel
    assert calls == ["activate", "create:launch"]


def test_flask_serve_uses_the_full_installed_composition(
    monkeypatch,
) -> None:
    calls: list[tuple[str, Any]] = []

    monkeypatch.setattr(
        runtime,
        "activate_installed_thinkument_composition_v1",
        lambda: calls.append(("activate", None)),
    )
    monkeypatch.setattr(
        runtime,
        "_serve_program_wrapper_on_flask",
        lambda wrapper, **kwargs: calls.append(
            ("serve", (dict(wrapper), dict(kwargs)))
        ),
    )

    runtime.serve_program_wrapper_on_flask(
        {"program_language": "x", "program": {}},
        port=5050,
    )

    assert calls[0] == ("activate", None)
    assert calls[1][0] == "serve"
    assert calls[1][1][1] == {"port": 5050}

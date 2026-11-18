from __future__ import annotations

"""
Reusable ThinkWidgetTM fixtures.

The fixtures intentionally exercise the full highest app-writing grammar:

- mount reexplosion;
- fill reexplosion;
- custom-signal reexplosion;
- custom-signal terminal satisfaction;
- terminal fill satisfaction;
- productive revision cycles;
- authoritative and non-authoritative datums on one span;
- guarded and unguarded datum roles;
- message events and arbitrary returned datum events;
- mapping, scalar, and null datum-event payload normalization;
- micro and datum-level semantic validators;
- all built-in demo micro types;
- custom public widget args;
- downstream history wires;
"""

from typing import Any, Dict, Mapping

from _thinkprogram.thinkwidgetTM import (
    MISSING_SIGNAL_FALLBACK_TO_FILL,
    DatumLifecycleWidget,
    Reexplode,
    signal_catcher,
    thinkwidgetTM_config,
)


W_COMPLEX = "demo.eventspollable.complex_input.v1"
W_SUPPORT = "demo.eventspollable.optional_support.v1"
W_REVIEW = "demo.eventspollable.manual_review.v1"
W_RELEASE = "demo.eventspollable.release.v1"



def _shell_args(
    fill_data: Mapping[str, Any],
    *,
    shell_custom_arg: str,
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    out = {
        "shell_custom_arg": shell_custom_arg,
    }
    out.update(dict(extra or {}))
    return out


def _lifecycle(
    fill_data: Mapping[str, Any],
    *,
    widget: str,
) -> Dict[str, Any]:
    out = dict(dict(fill_data["fill_shell"]).get("lifecycle") or {})
    out.update(
        {
            "widget": widget,
            "mount_explode": True,
            "max_reexplosions": 24,
            "max_messages": 16,
            "max_proc_notes": 8,
        }
    )
    return out


def _event_decl(
    name: str,
    payload: Any,
    *,
    channel: str = "ui",
    audience: str = "downstream-apps",
) -> Dict[str, Any]:
    return {
        "name": str(name),
        "channel": str(channel),
        "audience": str(audience),
        "payload": payload,
    }


def _reexplode(
    *,
    next_fill_shell: Mapping[str, Any],
    pre_computed_fills: Mapping[str, Any],
    prefill_hints: Mapping[str, Any] | None = None,
    events: list[Mapping[str, Any]] | None = None,
) -> Reexplode:
    """Compatibility constructor for eventful Reexplode results."""
    kwargs: Dict[str, Any] = {
        "next_fill_shell": dict(next_fill_shell),
        "pre_computed_fills": dict(pre_computed_fills),
    }
    if prefill_hints is not None:
        kwargs["prefill_hints"] = dict(prefill_hints)

    event_rows = [dict(row) for row in list(events or [])]
    try:
        return Reexplode(**kwargs, events=event_rows)
    except TypeError:
        result = Reexplode(**kwargs)
        try:
            setattr(result, "events", event_rows)
        except Exception:
            pass
        return result


def _text(
    name: str,
    *,
    min_words: int = 1,
    custom: str,
) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "text",
        "required": True,
        "args": {
            "semantic_name": "min_words",
            "minimum_words": min_words,
            "custom_micro_arg": custom,
        },
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.text:min_words",
                "args": {"min_words": min_words},
            }
        ],
        "style": {"density": "compact"},
    }


def _textarea(
    name: str,
    *,
    min_words: int,
    custom: str,
) -> Dict[str, Any]:
    row = _text(name, min_words=min_words, custom=custom)
    row["type"] = "textarea"
    return row


def _integer(
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "integer",
        "required": True,
        "args": {
            "minimum": minimum,
            "maximum": maximum,
            "semantic_name": "bounded_integer",
        },
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.number:min_number",
                "args": {"min_value": minimum},
            },
            {
                "path": "_thinkprogram._iomicrosTM.validators.number:max_number",
                "args": {"max_value": maximum},
            },
        ],
    }


def _number(
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "number",
        "required": True,
        "args": {
            "minimum": minimum,
            "maximum": maximum,
            "semantic_name": "bounded_number",
        },
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.number:min_number",
                "args": {"min_value": minimum},
            },
            {
                "path": "_thinkprogram._iomicrosTM.validators.number:max_number",
                "args": {"max_value": maximum},
            },
        ],
    }


def _select(name: str, options: list[str]) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "select",
        "required": True,
        "args": {
            "options": list(options),
            "semantic_name": "allowed_choice",
        },
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.choice:in_allowed",
                "args": {"options": list(options)},
            }
        ],
    }


def _slug(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "slug",
        "required": True,
        "args": {
            "semantic_name": "slug_identifier",
            "pattern": r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        },
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.text:pattern",
                "args": {
                    "pattern": r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
                },
            }
        ],
    }


def _email(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "email",
        "required": True,
        "args": {"semantic_name": "basic_email"},
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.email:is_basic_email",
                "args": {},
            }
        ],
    }


def _date(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "date",
        "required": True,
        "args": {"semantic_name": "iso_date"},
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.date:is_iso_date",
                "args": {},
            }
        ],
    }


def _code(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "code",
        "required": True,
        "args": {
            "semantic_name": "nonempty_multiline_code",
            "min_lines": 2,
        },
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.code:is_nonempty_code",
                "args": {},
            },
            {
                "path": "_thinkprogram._iomicrosTM.validators.code:min_code_lines",
                "args": {"min_lines": 2},
            },
        ],
    }


def _latex_math(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "latex_math",
        "required": True,
        "args": {"semantic_name": "latex_math_fragment"},
    }


def _image_url(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "image_url",
        "required": True,
        "args": {"semantic_name": "displayable_image_url"},
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.image:image_url",
                "args": {},
            }
        ],
    }


def _image_filepath(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "image_filepath",
        "required": True,
        "args": {"semantic_name": "local_image_filepath"},
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.image:image_filepath",
                "args": {},
            }
        ],
    }


def _describe_shell(
    *,
    position: Mapping[str, Any],
    fill_data: Mapping[str, Any],
    prompt: str,
    min_words: int,
    datum_custom: Mapping[str, Any],
    shell_custom_arg: str,
) -> Dict[str, Any]:
    return {
        "id": position["datum_id"],
        "title": prompt,
        "args": _shell_args(
            fill_data,
            shell_custom_arg=shell_custom_arg,
            extra={"datum_custom": dict(datum_custom)},
        ),
        "micros": [
            _text(
                "description",
                min_words=min_words,
                custom="description-custom",
            ),
            _textarea(
                "long_description",
                min_words=4,
                custom="long-description-custom",
            ),
            _slug("slug"),
            _email("contact_email"),
            _date("target_date"),
            _code("snippet"),
            _latex_math("formula"),
            _image_url("hero_image_url"),
            _image_filepath("local_image_path"),
            _integer("count", minimum=2, maximum=6),
            _number("confidence", minimum=1, maximum=10),
            {
                "name": "metadata",
                "type": "object-json",
                "required": True,
                "args": {
                    "semantic_name": "dead_json_metadata",
                    "custom_micro_arg": "metadata-custom",
                },
            },
            {
                "name": "ready",
                "type": "boolean",
                "required": True,
                "args": {
                    "semantic_name": "boolean_ready",
                    "custom_micro_arg": "ready-custom",
                },
            },
            {
                "name": "pause_ack",
                "type": "hidden-pause",
                "required": True,
                "args": {
                    "semantic_name": "hidden_pause_ack",
                    "custom_micro_arg": "pause-custom",
                },
            },
        ],
        "macro_validation_lambdas": [
            {
                "path": (
                    "_thinkprogram._iomicrosTM.validators.datum:"
                    "require_at_least_k"
                ),
                "args": {
                    "fields": ["description", "long_description"],
                    "k": 2,
                },
            },
            {
                "path": (
                    "_thinkprogram._iomicrosTM.validators.datum:"
                    "require_all_or_none"
                ),
                "args": {
                    "fields": ["hero_image_url", "local_image_path"],
                },
            },
        ],
        "lifecycle": _lifecycle(fill_data, widget=W_COMPLEX),
    }


@thinkwidgetTM_config(
    W_COMPLEX,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "prompt": {"type": "str", "required": True},
        "min_words": {
            "type": "int",
            "required": False,
            "default": 3,
        },
        "datum_custom": {"type": "dict", "required": True},
    },
    wires={},
)
class ComplexInputWidget(DatumLifecycleWidget):
    def _author_args(self, fill_data: Mapping[str, Any]) -> Dict[str, Any]:
        shell = dict(fill_data["fill_shell"])
        args = dict(shell.get("args") or {})
        args.pop("__kernel", None)
        return args

    def _on_mount(self, position, fill_data, limits, stats):
        author_args = self._author_args(fill_data)
        self.prompt = author_args["prompt"]
        self.min_words = int(author_args.get("min_words", 3))
        self.datum_custom = dict(author_args["datum_custom"])
        self.phase = "describe"
        self.message("info", "complex widget mounted")

        return _reexplode(
            next_fill_shell=_describe_shell(
                position=position,
                fill_data=fill_data,
                prompt=self.prompt,
                min_words=self.min_words,
                datum_custom=self.datum_custom,
                shell_custom_arg="describe-shell",
            ),
            pre_computed_fills={
                "description": "",
                "long_description": "",
                "slug": "",
                "contact_email": "",
                "target_date": "",
                "snippet": "",
                "formula": "",
                "hero_image_url": "",
                "local_image_path": "",
                "count": 2,
                "confidence": 5,
                "metadata": {},
                "ready": True,
                "pause_ack": True,
            },
            prefill_hints={
                "description": "Describe the event surface completely",
                "long_description": (
                    "Describe every downstream event surface branch"
                ),
                "slug": "event-surface-proof",
                "contact_email": "demo@example.com",
                "target_date": "2026-07-13",
                "snippet": "value = 1\nprint(value)",
                "formula": "x^2 + y^2",
                "hero_image_url": "https://example.com/image.png",
                "local_image_path": "./images/example.png",
                "count": 3,
                "confidence": 8,
                "metadata": {"origin": "prefill"},
                "ready": True,
                "pause_ack": True,
            },
            events=[
                _event_decl(
                    "complex.shell.describe.opened",
                    {
                        "phase": "describe",
                        "shell_custom_arg": "describe-shell",
                    },
                ),
                _event_decl(
                    "complex.payload.scalar",
                    "scalar-payload",
                ),
                _event_decl(
                    "complex.payload.none",
                    None,
                ),
            ],
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        current = dict(fill_data["current_fills"])

        if self.phase == "describe":
            self.describe_fill = dict(current)
            self.description = current["description"]
            self.count = current["count"]
            self.confidence = current["confidence"]
            self.metadata = current["metadata"]
            self.phase = "confirm"
            self.message("info", "complex widget reexploded to confirmation")

            return _reexplode(
                next_fill_shell={
                    "id": position["datum_id"],
                    "title": "Confirm complex input",
                    "args": _shell_args(
                        fill_data,
                        shell_custom_arg="confirm-shell",
                        extra={"datum_custom": self.datum_custom},
                    ),
                    "micros": [
                        _select("decision", ["accept", "revise"]),
                        {
                            "name": "publish",
                            "type": "checkbox",
                            "required": True,
                            "args": {
                                "semantic_name": "boolean_publish",
                                "custom_micro_arg": "publish-custom",
                            },
                        },
                    ],
                    "lifecycle": _lifecycle(
                        fill_data,
                        widget=W_COMPLEX,
                    ),
                },
                # A custom signal may return True without also submitting a
                # fill. Keep the active confirmation shell semantically valid
                # so final commit validation can succeed on that signal-only
                # transition.
                pre_computed_fills={
                    "decision": "accept",
                    "publish": True,
                },
                prefill_hints={
                    "decision": "accept",
                    "publish": True,
                },
                events=[
                    _event_decl(
                        "complex.shell.confirm.opened",
                        {
                            "phase": "confirm",
                            "description": self.description,
                        },
                    )
                ],
            )

        if self.phase == "confirm":
            if current["decision"] == "revise":
                self.phase = "describe"
                self.message("warning", "complex widget revision requested")
                revision_fill = {
                    "description": self.describe_fill["description"],
                    "count": self.describe_fill["count"],
                    "confidence": self.describe_fill["confidence"],
                    "metadata": self.describe_fill["metadata"],
                }
                return _reexplode(
                    next_fill_shell={
                        "id": position["datum_id"],
                        "title": self.prompt,
                        "args": _shell_args(
                            fill_data,
                            shell_custom_arg="describe-shell-revision",
                            extra={"datum_custom": self.datum_custom},
                        ),
                        "micros": [
                            _text(
                                "description",
                                min_words=self.min_words,
                                custom="description-custom",
                            ),
                            _integer("count", minimum=2, maximum=6),
                            _number("confidence", minimum=1, maximum=10),
                            {
                                "name": "metadata",
                                "type": "object-json",
                                "required": True,
                                "args": {
                                    "semantic_name": "dead_json_metadata",
                                },
                            },
                        ],
                        "macro_validation_lambdas": [
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM.validators."
                                    "datum:min_words_in_field"
                                ),
                                "args": {
                                    "field": "description",
                                    "min_words": self.min_words,
                                },
                            }
                        ],
                        "lifecycle": _lifecycle(
                            fill_data,
                            widget=W_COMPLEX,
                        ),
                    },
                    pre_computed_fills=revision_fill,
                    events=[
                        _event_decl(
                            "complex.shell.revision.opened",
                            {"phase": "describe-revision"},
                        )
                    ],
                )

            self.commit = {
                "describe_fill": dict(self.describe_fill),
                "decision": current["decision"],
                "publish": current["publish"],
            }
            self.phase = "done"
            self.message("success", "complex widget satisfied")
            return True

        raise AssertionError(f"unexpected phase: {self.phase!r}")

    @signal_catcher("reseed")
    def reseed(self, signal, position, fill_data, limits, stats):
        self.last_reseed_signal = dict(signal)
        self.message("warning", "complex widget reseeded")
        return _reexplode(
            next_fill_shell=dict(fill_data["fill_shell"]),
            pre_computed_fills=dict(fill_data["current_fills"]),
            prefill_hints={
                **dict(fill_data["prefill_hints"]),
                "signal_reason": dict(signal.get("info") or {}).get("reason"),
            },
            events=[
                _event_decl(
                    "complex.signal.reseed.received",
                    dict(signal.get("info") or {}),
                )
            ],
        )

    @signal_catcher("accept_generated")
    def accept_generated(self, signal, position, fill_data, limits, stats):
        if self.phase != "confirm":
            raise ValueError("accept_generated is valid only on confirm shell")
        self.commit = {
            "describe_fill": dict(self.describe_fill),
            "decision": "accept",
            "publish": True,
            "accepted_by_signal": True,
            "signal_info": dict(signal.get("info") or {}),
        }
        self.phase = "done"
        self.message("success", "complex widget signal-satisfied")
        return True



@thinkwidgetTM_config(
    W_SUPPORT,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "support_label": {"type": "str", "required": True},
    },
    wires={},
)
class OptionalSupportWidget(DatumLifecycleWidget):
    """Roleless, non-authoritative same-span widget."""

    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        args = dict(shell.get("args") or {})
        self.support_label = args.get("support_label")
        self.phase = "optional"
        self.message("info", "optional support mounted")
        return _reexplode(
            next_fill_shell={
                "id": position["datum_id"],
                "title": "Optional support note",
                "args": _shell_args(
                    fill_data,
                    shell_custom_arg="optional-support-shell",
                    extra={"support_label": self.support_label},
                ),
                "micros": [
                    {
                        "name": "note",
                        "type": "text",
                        "required": True,
                        "args": {
                            "semantic_name": "optional_support_note",
                        },
                        "validators": [
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM.validators."
                                    "text:is_nonempty_str"
                                ),
                                "args": {},
                            }
                        ],
                    }
                ],
                "lifecycle": _lifecycle(fill_data, widget=W_SUPPORT),
            },
            pre_computed_fills={"note": ""},
            prefill_hints={"note": "Optional note"},
            events=[
                _event_decl(
                    "support.shell.opened",
                    {"unguarded": True, "authoritative": False},
                )
            ],
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.commit = {
            "note": dict(fill_data["current_fills"])["note"],
        }
        self.phase = "done"
        self.message("success", "optional support satisfied")
        return True


@thinkwidgetTM_config(
    W_REVIEW,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "review_mode": {"type": "str", "required": True},
    },
    wires={
        "complex_commit": {
            "multiplicity": "one",
            "required": True,
        }
    },
)
class ManualReviewWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        args = dict(shell.get("args") or {})
        kernel = dict(args.get("__kernel") or {})
        past = dict(kernel.get("past_wires") or {})
        wire = dict(past.get("complex_commit") or {})
        value = dict(wire.get("value") or {})
        state = dict(value.get("state") or {})

        self.complex_commit_seen = dict(state.get("commit") or {})
        self.review_mode = args.get("review_mode")
        self.message("info", "manual review mounted")

        return _reexplode(
            next_fill_shell={
                "id": position["datum_id"],
                "title": "Manual human review",
                "args": _shell_args(
                    fill_data,
                    shell_custom_arg="manual-review-shell",
                    extra={
                        "review_mode": self.review_mode,
                        "complex_commit_seen": self.complex_commit_seen,
                    },
                ),
                "micros": [
                    _select("approval", ["approve", "reject"]),
                    _text(
                        "comment",
                        min_words=2,
                        custom="review-comment-custom",
                    ),
                ],
                "lifecycle": _lifecycle(fill_data, widget=W_REVIEW),
            },
            pre_computed_fills={
                "approval": "",
                "comment": "",
            },
            prefill_hints={
                "approval": "approve",
                "comment": "Reviewed and approved",
            },
            events=[
                _event_decl(
                    "review.shell.opened",
                    {
                        "review_mode": self.review_mode,
                        "has_complex_commit": bool(self.complex_commit_seen),
                    },
                )
            ],
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        current = dict(fill_data["current_fills"])
        self.commit = {
            "approval": current["approval"],
            "comment": current["comment"],
            "complex_commit_seen": self.complex_commit_seen,
        }
        self.message("success", "manual review satisfied")
        return True


@thinkwidgetTM_config(
    W_RELEASE,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "release_channel": {"type": "str", "required": True},
    },
    wires={
        "review_commit": {
            "multiplicity": "one",
            "required": True,
        }
    },
)
class ReleaseWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        args = dict(shell.get("args") or {})
        kernel = dict(args.get("__kernel") or {})
        past = dict(kernel.get("past_wires") or {})
        wire = dict(past.get("review_commit") or {})
        value = dict(wire.get("value") or {})
        state = dict(value.get("state") or {})

        self.review_commit_seen = dict(state.get("commit") or {})
        self.release_channel = args.get("release_channel")
        self.message("info", "release widget mounted")

        return _reexplode(
            next_fill_shell={
                "id": position["datum_id"],
                "title": "Release decision",
                "args": _shell_args(
                    fill_data,
                    shell_custom_arg="release-shell",
                    extra={
                        "release_channel": self.release_channel,
                        "review_commit_seen": self.review_commit_seen,
                    },
                ),
                "micros": [_select("status", ["released", "blocked"])],
                "lifecycle": _lifecycle(fill_data, widget=W_RELEASE),
            },
            pre_computed_fills={"status": ""},
            prefill_hints={"status": "released"},
            events=[
                _event_decl(
                    "release.shell.opened",
                    {
                        "release_channel": self.release_channel,
                        "has_review_commit": bool(self.review_commit_seen),
                    },
                )
            ],
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.commit = {
            "status": dict(fill_data["current_fills"])["status"],
            "review_commit_seen": self.review_commit_seen,
            "release_channel": self.release_channel,
        }
        self.message("success", "release widget satisfied")
        return True


DEMO_WIDGET_CLASSES = (
    ComplexInputWidget,
    OptionalSupportWidget,
    ManualReviewWidget,
    ReleaseWidget,
)


__all__ = [
    "DEMO_WIDGET_CLASSES",
    "ComplexInputWidget",
    "ManualReviewWidget",
    "OptionalSupportWidget",
    "ReleaseWidget",
    "W_COMPLEX",
    "W_RELEASE",
    "W_REVIEW",
    "W_SUPPORT",
]
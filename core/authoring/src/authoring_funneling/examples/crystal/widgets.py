"""Independent Crystal typed widgets."""
from hashlib import sha256
import json
from authoring_funneling.a_typed_PSMCW_authoring import (
    StrictServiceWidget,
    strict_widget,
    Dict,
    List,
    Nullable,
)
from _thinkprogram.thinkwidgetTM.types import Reexplode

SEED = "crystal.seed"
CONSUMER = "crystal.consumer"
CRYSTAL_WIDGET_IDS = (SEED, CONSUMER, 'crystal.json_ideator')


@strict_widget(
    SEED,
    args={"title": {"type": "str", "default": "Draft"}, "count": {"type": "int", "default": 1}},
    inputs={},
    outputs={
        "result": Dict({"title": str, "count": int, "note": Nullable(str)}),
        "entries": Dict({"rows": List(Dict({"title": str, "count": int}))}),
    },
)
class CrystalSeed(StrictServiceWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        title = self.configuration.get("title", "Draft")
        count = self.configuration.get("count", 1)
        self.outputs.write_many({
            "result": {"title": title, "count": count, "note": None},
            "entries": {"rows": [{"title": title, "count": count}]},
        })
        return Reexplode(
            next_fill_shell=self.replacement_shell(
                fill_data["fill_shell"],
                title=title,
                micros=[{"name": "confirm", "type": "text", "required": True}],
            ),
            pre_computed_fills={},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.outputs.keep_port("result")
        self.outputs.keep_port("entries")
        return True


@strict_widget(
    CONSUMER,
    inputs={
        "context": Dict({
            "heading": str,
            "items": List(Dict({"label": str, "count": int})),
            "note": Nullable(str),
        })
    },
    outputs={
        "result": Dict({
            "heading": str,
            "items": List(Dict({"label": str, "count": int})),
            "note": Nullable(str),
        })
    },
)
class CrystalConsumer(StrictServiceWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        context = self.mouth.read("context")
        self.outputs.write_port("result", context)
        return Reexplode(
            next_fill_shell=self.replacement_shell(
                fill_data["fill_shell"],
                title=context["heading"],
                micros=[{"name": "ack", "type": "text", "required": True}],
            ),
            pre_computed_fills={},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.outputs.keep_port("result")
        return True


_CRYSTAL_WIDGET_REGISTRY = {
    SEED: CrystalSeed,
    CONSUMER: CrystalConsumer,
}


def register_widget(widget_id, widget_cls=None):
    """Register a widget class into Crystal's independent registry."""
    if widget_cls is None:
        def decorator(cls):
            register_widget(widget_id, cls)
            return cls
        return decorator
    _CRYSTAL_WIDGET_REGISTRY[widget_id] = widget_cls
    return widget_cls


def widget_rows():
    """Tuple of all registered Crystal widget IDs."""
    return tuple(sorted(CRYSTAL_WIDGET_IDS))


def library_catalog_fingerprint_v1():
    classes = {**_CRYSTAL_WIDGET_REGISTRY,
               'crystal.json_ideator': CRYSTAL_JSON_WIDGET_ARTIFACT_V1.widget_class}
    payload = []
    for name, cls in sorted(classes.items()):
        config = cls.get_class_static_decorated_config()
        payload.append({'id': name, 'contract': config.get('strict_ports_v1'),
                        'args': config.get('args', {})})
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return sha256(encoded.encode()).hexdigest()


def register_crystal_widgets_v1():
    from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
        pull_thinkwidget_class_into_kernel_v1,
        kernel_widget_class_repr_v1,
    )
    from authoring_funneling import register_prepared_json_widget_v1
    registered_json = register_prepared_json_widget_v1(CRYSTAL_JSON_WIDGET_ARTIFACT_V1)
    _CRYSTAL_WIDGET_REGISTRY['crystal.json_ideator'] = registered_json
    for name, cls in _CRYSTAL_WIDGET_REGISTRY.items():
        try:
            existing = kernel_widget_class_repr_v1(name)
        except (ValueError, KeyError):
            existing = None
        if existing is None:
            pull_thinkwidget_class_into_kernel_v1(cls)
    return {"app_pack": "crystal", "widgets": list(widget_rows())}

# JSON lifecycle authoring shares the same independent Crystal presentation bed.
from pathlib import Path
from authoring_funneling import prepare_json_widget_v1
CRYSTAL_JSON_WIDGET_ARTIFACT_V1 = prepare_json_widget_v1(
    Path(__file__).with_name("json_widgets").joinpath("crystal_ideator.json").read_text())

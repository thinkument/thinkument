"""Tests proving Promise[T] output declarations and the Thinkument Law of Wire Typing Symmetry."""
import pytest
from bindings2bindingsTM import Dict, Str, Int, Promise, D
from authoring_funneling.a_typed_PSMCW_authoring import (
    StrictServiceWidget, strict_widget, compile_strict_program
)
from authoring_funneling.a_typed_PSMCW_authoring.widget import OUTPUT_STATE, MOUTH_STATE


class MockAsyncHandle:
    def __init__(self, ref: str):
        self.ref = ref
        self.status = "ongoing"


def test_producer_promise_and_consumer_symmetry():
    # 1. Producer widget statically announces an asynchronous promise output
    @strict_widget(
        "typed_test.producer.v1",
        overwrite=True,
        outputs={"book_draft": Promise(Dict({"title": Str, "words": Int}))}
    )
    class BookProducerWidget(StrictServiceWidget):
        def _on_mount(self, *args):
            handle = MockAsyncHandle("job_book_999")
            self.outputs.write_port("book_draft", handle)
            return True
        def _on_fill(self, *args):
            self.outputs.keep_port("book_draft")
            return True

    # 2. Consumer widget declares clean semantic input port (never promise-knowing!)
    @strict_widget(
        "typed_test.consumer.v1",
        overwrite=True,
        inputs={"draft": Dict({"title": Str, "words": Int})},
        outputs={"summary": Dict({"msg": Str})}
    )
    class BookConsumerWidget(StrictServiceWidget):
        def _on_mount(self, *args):
            received = self.mouth.read("draft")
            # Runtime receives the promise descriptor
            ref = received["ref"]
            self.outputs.write_port("summary", {"msg": f"Monitoring {ref}"})
            return True
        def _on_fill(self, *args):
            self.outputs.keep_port("summary")
            return True


    # 3. Compile Higher P program with wire from producer to consumer
    program = {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {},
        "puppeteering": {},
        "run": {
            "program": {
                "info": {"id": "promise_demo", "title": "Promise Demo"},
                "widgets": {
                    "producer": {"widget": "typed_test.producer.v1"},
                    "consumer": {
                        "widget": "typed_test.consumer.v1",
                        "bindings": {
                            "sources": {"p": {"widget": "producer", "port": "book_draft"}},
                            "inputs": {"draft": D.ref("p")}
                        }
                    }
                },
                "flow": [
                    {"id": "step1", "widgets": ["producer"]},
                    {"id": "step2", "widgets": ["consumer"]}
                ]
            },
            "config": {}
        }
    }

    compiled = compile_strict_program(program)
    assert compiled is not None

    # 4. Execute Producer
    producer = BookProducerWidget(q={}, emit=lambda *a, **k: {})
    p_args = {
        **compiled["run"]["program"]["widgets"]["producer"]["args"],
        **compiled["run"]["program"]["flow"][0]["overrides"]["args"]["producer"]
    }
    p_fill = {"fill_shell": {"args": p_args, "micros": []}, "current_fills": {}}
    producer._on_mount({}, p_fill, {}, {})
    assert producer.outputs.read("book_draft", "ref") == "job_book_999"
    assert producer.outputs.read("book_draft", "status") == "ongoing"


    # 5. Execute Consumer with wire from producer
    consumer_args = {
        **compiled["run"]["program"]["widgets"]["consumer"]["args"],
        **compiled["run"]["program"]["flow"][1]["overrides"]["args"]["consumer"]
    }
    history_wire = {
        "key": "producer",
        "public_step_name": "promise_demo.step1",
        "value": {
            "state": {
                OUTPUT_STATE: {
                    "book_draft": {"ref": "job_book_999", "status": "ongoing"}
                }
            }
        }
    }
    c_fill = {
        "fill_shell": {
            "args": {
                **consumer_args,
                "__kernel": {"past_wires": {"strict_sources_v1": [history_wire]}}
            },
            "micros": []
        },
        "current_fills": {}
    }
    consumer = BookConsumerWidget(q={}, emit=lambda *a, **k: {})
    consumer._on_mount({}, c_fill, {}, {})
    assert consumer.mouth.read("draft") == {"ref": "job_book_999", "status": "ongoing"}
    assert consumer.outputs.read("summary", "msg") == "Monitoring job_book_999"

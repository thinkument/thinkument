"""Universal Vendor Interceptor ('The Transcendental Mocking Seam').

Provides deterministic schema-valid mocks, custom Python handlers, local air-gapped
Ollama/vLLM bridges, and language-agnostic HTTP webhook proxies without altering
authored JSON/Python widget manifests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Mapping, Optional


@dataclass(frozen=True)
class VendorInvocation:
    """Canonical declarative envelope emitted whenever a widget node needs cognitive/vendor work."""

    operation: str
    modality: str
    args: Dict[str, Any]
    call_key: str
    vendor: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


def default_mock_interceptor(invocation: VendorInvocation | Dict[str, Any]) -> Dict[str, Any]:
    """Default deterministic schema-valid mock generator (<1ms, $0.00).

    Returns schema-guarded responses conforming to FunctionVocab contracts.
    """
    if isinstance(invocation, dict):
        invocation = VendorInvocation(
            operation=invocation.get("operation", "vendor_op"),
            modality=invocation.get("modality", "general"),
            args=invocation.get("args") or {},
            call_key=invocation.get("call_key", "op:1"),
            vendor=invocation.get("vendor"),
            context=invocation.get("context"),
        )
    op = invocation.operation
    args = invocation.args or {}

    if op.startswith("vendor.llm") or invocation.modality == "llm":
        model = args.get("model", "mock-model")
        prompt = args.get("prompt") or ""
        if not prompt and "messages" in args:
            messages = args.get("messages") or []
            prompt = messages[-1].get("content", "") if messages else ""
        short_prompt = (prompt[:40] + "...") if len(prompt) > 40 else prompt
        return {
            "text": f"[Mock {model}]: Simulated completion for '{short_prompt}'",
            "usage": {
                "prompt_tokens": max(1, len(prompt.split())),
                "completion_tokens": 16,
            },
        }

    if op.startswith("vendor.image") or invocation.modality == "image":
        return {
            "image_url": "mock://storage/generated_image.png",
            "usage": {"units": 1},
        }

    if op.startswith("vendor.embeddings") or invocation.modality in ("embedding", "embeddings"):
        return {
            "embeddings": [[0.0] * 128] if isinstance(args.get("input"), list) else [0.0] * 128,
            "usage": {"prompt_tokens": 5},
            "status": "success",
        }

    return {
        "status": "success",
        "mocked": True,
        "operation": op,
        "usage": {"units": 1},
    }


def create_ollama_interceptor(
    endpoint: str = "http://localhost:11434",
    default_model: str = "llama3",
) -> Callable[[VendorInvocation], Dict[str, Any]]:
    """Create an air-gapped local AI interceptor routing vendor.llm ops to local Ollama."""
    base_url = endpoint.rstrip("/")

    def ollama_interceptor(invocation: VendorInvocation | Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(invocation, dict):
            invocation = VendorInvocation(
                operation=invocation.get("operation", "vendor.llm.chat_completion"),
                modality=invocation.get("modality", "llm"),
                args=invocation.get("args") or {},
                call_key=invocation.get("call_key", "op:1"),
                vendor=invocation.get("vendor"),
                context=invocation.get("context"),
            )
        args = invocation.args or {}
        model = args.get("model") or default_model
        prompt = args.get("prompt") or ""
        if not prompt and "messages" in args:
            messages = args.get("messages") or []
            prompt = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)

        payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "text": data.get("response", ""),
                    "usage": {
                        "prompt_tokens": data.get("prompt_eval_count", 0),
                        "completion_tokens": data.get("eval_count", 0),
                    },
                }
        except urllib.error.URLError as exc:
            return {
                "text": f"[Ollama Error: {exc}]",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                "error": str(exc),
            }

    return ollama_interceptor


def create_webhook_interceptor(target_url: str) -> Callable[[VendorInvocation], Dict[str, Any]]:
    """Create a language-agnostic HTTP proxy interceptor forwarding invocations to a local port."""

    def webhook_interceptor(invocation: VendorInvocation | Dict[str, Any]) -> Dict[str, Any]:
        payload_dict = invocation.to_dict() if isinstance(invocation, VendorInvocation) else dict(invocation)
        payload = json.dumps(payload_dict).encode("utf-8")
        req = urllib.request.Request(
            target_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    return webhook_interceptor


def load_interceptor_from_file(file_path: str) -> Callable[[VendorInvocation], Dict[str, Any]]:
    """Load a custom interceptor function from a user-supplied Python file."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("user_mocks", file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load mock interceptor module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for attr in ("intercept_vendor_op", "vendor_interceptor", "intercept", "mock_handler"):
        if hasattr(module, attr) and callable(getattr(module, attr)):
            return getattr(module, attr)

    raise AttributeError(
        f"File {file_path} must export one of: intercept_vendor_op, vendor_interceptor, intercept, or mock_handler"
    )

from __future__ import annotations

import os
from typing import Any, Dict, Final, Iterable
from urllib.parse import urlparse

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.validators._common import unwrap
from _thinkprogram._iomicrosTM.validators.file import normalize_extensions, validate_local_filepath
from _thinkprogram._iomicrosTM.validators.url import validate_url

IMAGE_URL_MICRO_KIND: Final[str] = "image_url"
IMAGE_FILEPATH_MICRO_KIND: Final[str] = "image_filepath"
_THIS_MODULE: Final[str] = "_thinkprogram._iomicrosTM.validators.image"
IMAGE_URL_VALIDATOR_PATH: Final[str] = f"{_THIS_MODULE}:image_url"
IMAGE_URL_HAS_ALLOWED_EXTENSION_VALIDATOR_PATH: Final[str] = f"{_THIS_MODULE}:image_url_has_allowed_extension"
IMAGE_FILEPATH_VALIDATOR_PATH: Final[str] = f"{_THIS_MODULE}:image_filepath"
_IMAGE_EXTENSIONS: Final[tuple[str, ...]] = (
    ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"
)


def _allowed(allowed_extensions: Iterable[str] | None) -> list[str]:
    out = normalize_extensions(allowed_extensions)
    return out or list(_IMAGE_EXTENSIONS)


def _url_path(value: Any) -> str:
    return urlparse(str(unwrap(value) or "").strip()).path or ""


def _validate_image_url(value: Any) -> tuple[bool, str | None]:
    ok, message = validate_url(value)
    if not ok:
        return ok, message
    path = _url_path(value)
    if not path or path == "/":
        return False, "image URL must identify a concrete resource path"
    return True, None


def _validate_image_filepath(value: Any) -> tuple[bool, str | None]:
    ok, message = validate_local_filepath(value)
    if not ok:
        return ok, message
    base = os.path.basename(str(unwrap(value)).replace("\\", "/")).lower()
    if not any(base.endswith(ext) for ext in _IMAGE_EXTENSIONS):
        return False, "filepath must end with a common image extension"
    return True, None


def image_validator_path(kind: str) -> str:
    key = str(kind or "").strip().lower()
    paths = {
        IMAGE_URL_MICRO_KIND: IMAGE_URL_VALIDATOR_PATH,
        "image_url_has_allowed_extension": IMAGE_URL_HAS_ALLOWED_EXTENSION_VALIDATOR_PATH,
        IMAGE_FILEPATH_MICRO_KIND: IMAGE_FILEPATH_VALIDATOR_PATH,
    }
    if key not in paths:
        raise ValueError(f"unknown image validator kind {kind!r}; known={sorted(paths)}")
    return paths[key]


def image_validator_spec(kind: str, *, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {"path": image_validator_path(kind), "args": dict(args or {})}


def image_url_validator_spec(*, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return image_validator_spec(IMAGE_URL_MICRO_KIND, args=args)


def image_url_has_allowed_extension_validator_spec(
    *,
    allowed_extensions: Iterable[str] | None = None,
    args: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    merged = dict(args or {})
    if allowed_extensions is not None:
        merged["allowed_extensions"] = list(allowed_extensions)
    return image_validator_spec("image_url_has_allowed_extension", args=merged)


def image_filepath_validator_spec(*, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return image_validator_spec(IMAGE_FILEPATH_MICRO_KIND, args=args)


def validate_image_micro_value(kind: str, value: Any) -> tuple[bool, str | None]:
    key = str(kind or "").strip().lower()
    if key == IMAGE_URL_MICRO_KIND:
        return _validate_image_url(value)
    if key == IMAGE_FILEPATH_MICRO_KIND:
        return _validate_image_filepath(value)
    raise ValueError(f"unknown image micro validator kind {kind!r}")


def build_image_guidance(kind: str) -> Dict[str, Any]:
    key = str(kind or "").strip().lower()
    if key == IMAGE_URL_MICRO_KIND:
        return {
            "message": "Provide a credential-free http(s) URL to a concrete image resource.",
            "modality": IMAGE_URL_MICRO_KIND,
        }
    if key == "image_url_has_allowed_extension":
        return {
            "message": "Provide an image URL whose path ends with an allowed image extension.",
            "modality": IMAGE_URL_MICRO_KIND,
        }
    if key == IMAGE_FILEPATH_MICRO_KIND:
        return {
            "message": "Provide a local image filepath such as ./images/example.png.",
            "modality": IMAGE_FILEPATH_MICRO_KIND,
        }
    raise ValueError(f"unknown image guidance kind {kind!r}")


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [
            "https://example.com/cat.png",
            {"__boxed__": True, "value": "https://cdn.example.org/assets/image.webp?x=1"},
            "https://signed.example.com/render/abc123",
        ],
        "invalid_examples": [
            "images/cat.png", "/tmp/cat.png", "not-a-url",
            "https:///broken", "https://example.com", "ftp://example.com/cat.png",
            "https://user:pass@example.com/cat.png", None,
        ],
        "modality": IMAGE_URL_MICRO_KIND,
    }],
    description="Credential-free HTTP(S) URL with a concrete resource path.",
)
def image_url(value: Any) -> tuple[bool, str | None]:
    return _validate_image_url(value)


@guidance_for("image_url")
def image_url_guidance() -> Dict[str, Any]:
    return build_image_guidance(IMAGE_URL_MICRO_KIND)


@validator(
    arg_combos=[{
        "args": {"allowed_extensions": [".png", ".jpg", ".jpeg", ".webp"]},
        "valid_examples": [
            "https://example.com/cat.png",
            {"__boxed__": True, "value": "https://cdn.example.org/assets/image.jpeg?x=1"},
        ],
        "invalid_examples": [
            "https://example.com/render/no-extension",
            "https://example.com/image.txt",
            None,
        ],
        "modality": IMAGE_URL_MICRO_KIND,
    }],
    description="HTTP(S) image URL with an explicitly allowed path extension.",
)
def image_url_has_allowed_extension(
    value: Any,
    *,
    allowed_extensions: Iterable[str] | None = None,
) -> tuple[bool, str | None]:
    ok, message = _validate_image_url(value)
    if not ok:
        return ok, message
    allowed = _allowed(allowed_extensions)
    path = _url_path(value).lower()
    ok = any(path.endswith(ext) for ext in allowed)
    return ok, None if ok else "image URL must end with one of: " + ", ".join(allowed)


@guidance_for("image_url_has_allowed_extension")
def image_url_has_allowed_extension_guidance(
    *,
    allowed_extensions: Iterable[str] | None = None,
) -> Dict[str, Any]:
    allowed = _allowed(allowed_extensions)
    return {
        "message": "Use an image URL ending with one of: " + ", ".join(allowed),
        "args": {"allowed_extensions": allowed},
        "modality": IMAGE_URL_MICRO_KIND,
    }


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [
            "tests/assets/example.png", "./images/cat.jpg", "/tmp/generated.webp",
            {"__boxed__": True, "value": r"C:\images\portrait.jpeg"}, "hero_image.png",
        ],
        "invalid_examples": [
            "https://example.com/cat.png", "not-a-path", "document.txt", "", None,
        ],
        "modality": IMAGE_FILEPATH_MICRO_KIND,
    }],
    description="Local-looking filepath ending in a common image extension.",
)
def image_filepath(value: Any) -> tuple[bool, str | None]:
    return _validate_image_filepath(value)


@guidance_for("image_filepath")
def image_filepath_guidance() -> Dict[str, Any]:
    return build_image_guidance(IMAGE_FILEPATH_MICRO_KIND)


__all__ = [
    "IMAGE_URL_MICRO_KIND",
    "IMAGE_FILEPATH_MICRO_KIND",
    "IMAGE_URL_VALIDATOR_PATH",
    "IMAGE_URL_HAS_ALLOWED_EXTENSION_VALIDATOR_PATH",
    "IMAGE_FILEPATH_VALIDATOR_PATH",
    "image_validator_path",
    "image_validator_spec",
    "image_url_validator_spec",
    "image_url_has_allowed_extension_validator_spec",
    "image_filepath_validator_spec",
    "validate_image_micro_value",
    "build_image_guidance",
    "image_url",
    "image_url_guidance",
    "image_url_has_allowed_extension",
    "image_url_has_allowed_extension_guidance",
    "image_filepath",
    "image_filepath_guidance",
]

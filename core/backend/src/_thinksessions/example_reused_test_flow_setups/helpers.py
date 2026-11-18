from typing import Dict, Any

def valid_complex_describe_fill() -> Dict[str, Any]:
    """Return a valid first-span fill, including the optional support datum."""

    return {
        "complex": {
            "description": (
                "Complete deterministic event surface proof"
            ),
            "long_description": (
                "Describe every downstream event "
                "surface branch completely"
            ),
            "slug": "event-surface-proof",
            "contact_email": "demo@example.com",
            "target_date": "2026-07-13",
            "snippet": "value = 1\nprint(value)",
            "formula": "x^2 + y^2",
            "hero_image_url": (
                "https://example.com/image.png"
            ),
            "local_image_path": (
                "./images/example.png"
            ),
            "count": 3,
            "confidence": 8,
            "metadata": {
                "source": "manual",
            },
            "ready": True,
            "pause_ack": True,
        },
        "support": {
            "note": "Optional support note",
        },
    }


def invalid_multi_datum_fill() -> Dict[str, Any]:
    """Return one invalid atomic fill touching two current datums."""

    return {
        "complex": {
            "description": "x",
            "long_description": "y",
            "slug": "INVALID SLUG",
            "contact_email": "not-an-email",
            "target_date": "not-a-date",
            "snippet": "one line",
            "formula": "",
            "hero_image_url": "not-a-url",
            "local_image_path": "not-a-path",
            "count": "100",
            "confidence": "-100",
            "metadata": {
                "still": "dead-json",
            },
            "ready": True,
            "pause_ack": True,
        },
        "support": {
            "note": "",
        },
    }


def valid_complex_confirm_fill() -> Dict[str, Any]:
    """Return the valid confirmation-shell action."""

    return {
        "complex": {
            "decision": "accept",
            "publish": True,
        }
    }


def valid_review_fill() -> Dict[str, Any]:
    """Return the valid manual reviewer action."""

    return {
        "review": {
            "approval": "approve",
            "comment": "Reviewed and approved",
        }
    }


def valid_release_fill() -> Dict[str, Any]:
    """Return the valid release-role action."""

    return {
        "release": {
            "status": "released",
        }
    }


__all__ = [
    "valid_complex_confirm_fill",
    "valid_complex_describe_fill",
    "valid_release_fill",
    "valid_review_fill",
]
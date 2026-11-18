from __future__ import annotations

ADAPTER_RESERVED_STATE_KEY = "__datum_widget_class_adapter_v1__"

CONFIG_KEY = "__datum_widget_class_config_v1__"
SIGNAL_CATCHERS_KEY = "__datum_widget_signal_catchers_v1__"

MISSING_SIGNAL_RAISE = "raise"
MISSING_SIGNAL_FALLBACK_TO_FILL = "fallback_to_fill_handler"

MESSAGE_EVENT_NAME = "datum.message"
MESSAGE_EVENT_CHANNEL = "ui"
MESSAGE_EVENT_AUDIENCE = "frontend"

MESSAGE_SHAPE_V1 = {
    "level": "success | info | warning | error",
    "text": "str",
}

MESSAGE_EVENT_PAYLOAD_SHAPE_V1 = {
    "message": MESSAGE_SHAPE_V1,
}

CLASS_ADAPTER_EVENT_MARRIAGE_V1 = {
    "method": "self.message(level, text)",
    "event": {
        "name": MESSAGE_EVENT_NAME,
        "channel": MESSAGE_EVENT_CHANNEL,
        "audience": MESSAGE_EVENT_AUDIENCE,
        "payload": MESSAGE_EVENT_PAYLOAD_SHAPE_V1,
    },
    "platform_result": {
        "messages": [MESSAGE_SHAPE_V1],
    },
}
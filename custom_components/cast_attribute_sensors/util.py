"""Utility functions for Cast Attribute Sensors."""

from __future__ import annotations

import base64
import json
import math
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .const import (
    KIND_ATTRIBUTE,
    KIND_SNAPSHOT,
    KIND_STATE,
    MAX_SENSOR_STATE_LENGTH,
    UID_SEPARATOR,
    UID_VERSION,
)


def humanize(attribute: str) -> str:
    """Convert an attribute key into a readable entity name."""
    return attribute.replace("_", " ").strip().capitalize()


def encode_attribute(attribute: str) -> str:
    """Encode an arbitrary attribute key for use inside a unique ID."""
    return (
        base64.urlsafe_b64encode(attribute.encode("utf-8")).decode("ascii").rstrip("=")
    )


def decode_attribute(encoded: str) -> str | None:
    """Decode an attribute key stored in a unique ID."""
    try:
        padding = "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None


def build_unique_id(source_registry_id: str, kind: str, attribute: str | None) -> str:
    """Build a stable unique ID for a generated sensor."""
    parts = [UID_VERSION, source_registry_id, kind]
    if kind == KIND_ATTRIBUTE:
        if attribute is None:
            raise ValueError("Attribute sensor requires an attribute key")
        parts.append(encode_attribute(attribute))
    return UID_SEPARATOR.join(parts)


def parse_unique_id(unique_id: str) -> tuple[str, str, str | None] | None:
    """Parse one of this integration's sensor unique IDs."""
    parts = unique_id.split(UID_SEPARATOR)
    if len(parts) < 3 or parts[0] != UID_VERSION:
        return None

    source_registry_id = parts[1]
    kind = parts[2]

    if kind in (KIND_STATE, KIND_SNAPSHOT) and len(parts) == 3:
        return source_registry_id, kind, None

    if kind == KIND_ATTRIBUTE and len(parts) == 4:
        attribute = decode_attribute(parts[3])
        if attribute is not None:
            return source_registry_id, kind, attribute

    return None


def _json_default(value: Any) -> Any:
    """Convert common non-JSON values to serializable representations."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, set):
        return sorted(value, key=str)
    return str(value)


def normalize_native_value(
    value: Any,
) -> tuple[str | int | float | Decimal | None, dict[str, Any]]:
    """Convert any source attribute into a legal, lossless sensor representation.

    Home Assistant limits entity state strings to 255 characters and sensor states
    cannot directly contain mappings or sequences. Values that cannot be represented
    directly are summarized in the state and preserved in the ``raw_value`` attribute.
    """
    if value is None:
        return None, {}

    if isinstance(value, bool):
        return ("true" if value else "false"), {"raw_value": value}

    if isinstance(value, int):
        return value, {}

    if isinstance(value, float):
        if math.isfinite(value):
            return value, {}
        return str(value), {"raw_value": str(value)}

    if isinstance(value, Decimal):
        return value, {}

    if isinstance(value, (date, datetime)):
        text = value.isoformat()
        return text, {"raw_value": value}

    if isinstance(value, str):
        if len(value) <= MAX_SENSOR_STATE_LENGTH:
            return value, {}
        preview_length = MAX_SENSOR_STATE_LENGTH - 16
        return (
            f"{value[:preview_length]}… [truncated]",
            {"raw_value": value, "value_truncated": True},
        )

    if isinstance(value, (Mapping, list, tuple, set)):
        try:
            serialized = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                default=_json_default,
            )
        except (TypeError, ValueError):
            serialized = str(value)

        if len(serialized) <= MAX_SENSOR_STATE_LENGTH:
            return serialized, {"raw_value": value}

        item_count = len(value)
        return (
            f"{type(value).__name__} ({item_count} items)",
            {"raw_value": value, "value_truncated": True},
        )

    text = str(value)
    if len(text) <= MAX_SENSOR_STATE_LENGTH:
        return text, {"raw_value": text}

    preview_length = MAX_SENSOR_STATE_LENGTH - 16
    return (
        f"{text[:preview_length]}… [truncated]",
        {"raw_value": text, "value_truncated": True},
    )

"""Value and unique-ID utilities."""

from __future__ import annotations

import base64
import json
import math
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .const import KIND_ATTRIBUTE, KIND_SNAPSHOT, KIND_STATE, MAX_SENSOR_STATE_LENGTH


def humanize(value: str) -> str:
    """Convert a machine key to a readable label."""
    return value.replace("_", " ").replace("-", " ").strip().capitalize()


def encode_key(value: str) -> str:
    """Encode arbitrary text for a stable unique ID."""
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def decode_key(value: str) -> str | None:
    """Decode a unique-ID component."""
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
    except (UnicodeDecodeError, ValueError):
        return None


def sensor_unique_id(source_id: str, kind: str, attribute: str | None = None) -> str:
    """Return a source-stable sensor unique ID retained across regrouping."""
    parts = ["v2", source_id, kind]
    if kind == KIND_ATTRIBUTE:
        if attribute is None:
            raise ValueError("attribute is required")
        parts.append(encode_key(attribute))
    return "|".join(parts)


def parse_sensor_unique_id(value: str) -> tuple[str, str, str | None] | None:
    """Parse a metadata sensor unique ID retained from v2 and later."""
    parts = value.split("|")
    if len(parts) < 3 or parts[0] != "v2":
        return None
    source_id, kind = parts[1], parts[2]
    if kind in {KIND_STATE, KIND_SNAPSHOT} and len(parts) == 3:
        return source_id, kind, None
    if kind == KIND_ATTRIBUTE and len(parts) == 4:
        attribute = decode_key(parts[3])
        if attribute is not None:
            return source_id, kind, attribute
    return None


def _json_default(value: Any) -> Any:
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
    """Convert arbitrary attributes into legal, lossless sensor values."""
    if value is None:
        return None, {}
    if isinstance(value, bool):
        return ("true" if value else "false"), {"raw_value": value}
    if isinstance(value, int):
        return value, {}
    if isinstance(value, float):
        return (
            (value, {})
            if math.isfinite(value)
            else (str(value), {"raw_value": str(value)})
        )
    if isinstance(value, Decimal):
        return value, {}
    if isinstance(value, (date, datetime)):
        return value.isoformat(), {"raw_value": value}
    if isinstance(value, str):
        if len(value) <= MAX_SENSOR_STATE_LENGTH:
            return value, {}
        return (
            f"{value[: MAX_SENSOR_STATE_LENGTH - 16]}… [truncated]",
            {"raw_value": value, "value_truncated": True},
        )
    if isinstance(value, (Mapping, list, tuple, set)):
        try:
            serialized = json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), default=_json_default
            )
        except (TypeError, ValueError):
            serialized = str(value)
        if len(serialized) <= MAX_SENSOR_STATE_LENGTH:
            return serialized, {"raw_value": value}
        return (
            f"{type(value).__name__} ({len(value)} items)",
            {"raw_value": value, "value_truncated": True},
        )
    text = str(value)
    if len(text) <= MAX_SENSOR_STATE_LENGTH:
        return text, {"raw_value": text}
    return (
        f"{text[: MAX_SENSOR_STATE_LENGTH - 16]}… [truncated]",
        {"raw_value": text, "value_truncated": True},
    )

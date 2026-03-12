"""
Low-visibility diagnostics logging for maintenance email import decisions.

Writes JSON-lines entries under sync_exchange/logs without showing anything in UI.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any


def _log_path() -> str:
    base_dir = os.path.dirname(__file__)
    return os.path.join(base_dir, "sync_exchange", "logs", "maintenance_import_diagnostics.log")


def _sanitize(value: Any) -> Any:
    """Keep log payload compact and JSON-serializable."""
    if isinstance(value, str):
        # Avoid huge payloads in log file.
        return value if len(value) <= 300 else (value[:300] + "...<truncated>")
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    return str(value)


def log_import_diagnostic(event: str, **fields: Any) -> None:
    """Append a diagnostics event as one JSON line. Never raises."""
    try:
        path = _log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)

        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event": event,
        }
        for key, value in fields.items():
            entry[str(key)] = _sanitize(value)

        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Diagnostics must never interfere with normal app behavior.
        pass

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core.runtime import SERVER_DIR
from core.security import redact_obj

AUDIT_DIR = SERVER_DIR / "logs"
AUDIT_FILE = AUDIT_DIR / "audit.jsonl"


def new_run_id() -> str:
    return str(uuid.uuid4())


def audit_event(event_type: str, **fields: Any) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event_type": event_type,
        **fields,
    }
    safe_event = redact_obj(event)
    line = json.dumps(safe_event, sort_keys=True, ensure_ascii=False)
    try:
        with AUDIT_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        return

from __future__ import annotations

from datetime import datetime
from typing import Dict


def hello() -> Dict[str, object]:
    """Return a friendly greeting payload."""
    return {
        "ok": True,
        "message": "Hello from the Sample Hello extension!",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

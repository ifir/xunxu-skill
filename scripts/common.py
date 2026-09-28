#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default

def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def fingerprint(path: Path) -> str:
    stat = path.stat()
    identity = f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"
    return hashlib.sha256(identity.encode()).hexdigest()

def modified_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")

def result_record(path: Path, text: str, method: str, error: str | None = None) -> dict[str, Any]:
    return {"source": str(path), "fingerprint": fingerprint(path), "modified_at": modified_at(path), "method": method, "text": text, "error": error}

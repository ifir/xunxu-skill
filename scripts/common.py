#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

FINGERPRINT_CHUNK = 64 * 1024

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default

def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def fingerprint(path: Path) -> str:
    """Return a move-stable fingerprint on macOS and Windows.

    Device/inode values are deliberately excluded: Windows file indexes are not
    consistently exposed and a copy between supported environments changes them.
    Size, nanosecond mtime and sampled content preserve cache hits after a rename
    while making accidental collisions far less likely than metadata alone.
    """
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(f"v2:{stat.st_size}:{stat.st_mtime_ns}:".encode())
    with path.open("rb") as handle:
        digest.update(handle.read(FINGERPRINT_CHUNK))
        if stat.st_size > FINGERPRINT_CHUNK:
            handle.seek(max(0, stat.st_size - FINGERPRINT_CHUNK))
            digest.update(handle.read(FINGERPRINT_CHUNK))
    return digest.hexdigest()

def modified_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")

def result_record(path: Path, text: str, method: str, error: str | None = None) -> dict[str, Any]:
    return {"source": str(path), "fingerprint": fingerprint(path), "modified_at": modified_at(path), "method": method, "text": text, "error": error}

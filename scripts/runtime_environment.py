#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any

SANDBOX_ENV_KEYS = (
    "APP_SANDBOX_CONTAINER_ID", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED",
    "CLAUDE_CODE_REMOTE", "WORKBUDDY_SANDBOX", "DOUBAO_SANDBOX", "CONTAINER",
)

def detect() -> dict[str, Any]:
    signals = [key for key in SANDBOX_ENV_KEYS if os.environ.get(key)]
    for marker in (Path("/.dockerenv"), Path("/run/.containerenv")):
        if marker.exists():
            signals.append(str(marker))
    system = platform.system().lower()
    sandboxed = bool(signals)
    native_macos = system == "darwin" and not sandboxed and bool(shutil.which("swift"))
    return {
        "execution_mode": "sandboxed-or-remote" if sandboxed else "local-host",
        "host_os": system, "machine": platform.machine(), "sandbox_signals": sorted(set(signals)),
        "native_macos_frameworks_allowed": native_macos,
        "portable_script_required": sandboxed or system != "darwin",
        "note": "运行模式只决定后端优先级；最终仍以命令或 Python 解码能力的实际探测结果为准。",
    }

def main() -> int:
    argparse.ArgumentParser(description="检测当前代理是在本机还是沙箱/远程环境中运行").parse_args()
    print(json.dumps(detect(), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

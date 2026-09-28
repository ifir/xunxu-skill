#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

from analyze_media import AUDIO_SUFFIXES, IMAGE_SUFFIXES, VIDEO_SUFFIXES

def _module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False

def required_capabilities(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return ["faster_whisper"]
    if suffix in AUDIO_SUFFIXES:
        return ["faster_whisper"]
    if suffix in IMAGE_SUFFIXES:
        return ["paddleocr", "paddle"]
    if suffix == ".pdf":
        return ["pdf"]
    return []

def check(paths: list[Path]) -> dict[str, Any]:
    modules = {name: _module(name) for name in ("faster_whisper", "paddleocr", "paddle", "pypdf")}
    commands = {name: shutil.which(name) for name in ("pdftotext", "pdfinfo")}
    missing: set[str] = set()
    kinds: set[str] = set()
    for path in paths:
        suffix = path.suffix.lower()
        if suffix in VIDEO_SUFFIXES:
            kinds.add("video")
        elif suffix in AUDIO_SUFFIXES:
            kinds.add("audio")
        elif suffix in IMAGE_SUFFIXES:
            kinds.add("image")
        for capability in required_capabilities(path):
            if capability == "pdf":
                if not (commands["pdftotext"] or modules["pypdf"]): missing.add("pdf")
            elif not modules.get(capability):
                missing.add(capability)
    packages = []
    if "faster_whisper" in missing: packages.append("faster-whisper==1.2.1")
    if "paddleocr" in missing: packages.append("paddleocr==3.7.0")
    if "paddle" in missing: packages.append("与系统匹配的 PaddlePaddle runtime")
    if "pdf" in missing: packages.append("pypdf==6.1.1")
    return {
        "status": "ready" if not missing else "installation-required",
        "media_kinds": sorted(kinds), "missing": sorted(missing), "packages": packages,
        "modules": modules, "commands": commands,
        "requires_user_confirmation": bool(missing),
        "model_download_may_be_required": "faster_whisper" in {cap for path in paths for cap in required_capabilities(path)},
        "install_commands": {
            "macos_linux": "python3 -m pip install faster-whisper==1.2.1" if "faster_whisper" in missing else "",
            "windows": "py -3 -m pip install faster-whisper==1.2.1" if "faster_whisper" in missing else "",
        },
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="只读检查本地文件分析能力；不安装依赖或下载模型")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    paths = [path.expanduser().resolve() for path in args.paths]
    print(json.dumps(check(paths), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

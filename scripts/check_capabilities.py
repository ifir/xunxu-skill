#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from analyze_media import AUDIO_SUFFIXES, IMAGE_SUFFIXES, VIDEO_SUFFIXES

PINNED = {
    "pypdf": "pypdf==6.1.1",
    "faster_whisper": "faster-whisper==1.2.1",
    "paddleocr": "paddleocr==3.7.0",
}

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
    commands = {name: shutil.which(name) for name in ("pdftotext", "pdfinfo", "ffmpeg", "ffprobe")}
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
            if capability == "faster_whisper" and suffix in VIDEO_SUFFIXES and commands["ffmpeg"] and commands["ffprobe"]:
                continue
            if capability == "pdf":
                if not (commands["pdftotext"] or modules["pypdf"]): missing.add("pdf")
            elif not modules.get(capability):
                missing.add(capability)
    packages = []
    if "faster_whisper" in missing: packages.append("faster-whisper==1.2.1")
    if "paddleocr" in missing: packages.append("paddleocr==3.7.0")
    if "paddle" in missing: packages.append("与系统匹配的 PaddlePaddle runtime")
    if "pdf" in missing: packages.append("pypdf==6.1.1")
    video_present = "video" in kinds
    transcription_ready = modules["faster_whisper"]
    keyframes_ready = bool(commands["ffmpeg"] and commands["ffprobe"])
    return {
        "status": "ready" if not missing else "installation-required",
        "media_kinds": sorted(kinds), "missing": sorted(missing), "packages": packages,
        "modules": modules, "commands": commands,
        "requires_user_confirmation": bool(missing),
        "model_download_may_be_required": "faster_whisper" in {cap for path in paths for cap in required_capabilities(path)},
        "video_pipeline": {
            "primary": "audio-transcription", "primary_ready": transcription_ready,
            "fallback": "distributed-keyframes", "fallback_ready": keyframes_ready,
            "usable": (transcription_ready or keyframes_ready) if video_present else None,
        },
        "install_commands": {
            "macos_linux": "python3 -m pip install faster-whisper==1.2.1" if "faster_whisper" in missing else "",
            "windows": "py -3 -m pip install faster-whisper==1.2.1" if "faster_whisper" in missing else "",
        },
        "keyframe_install_hint": "安装包含 ffmpeg 与 ffprobe 的 FFmpeg 发行版，并确保命令位于 PATH" if video_present and not keyframes_ready else "",
    }

def assess_plan(paths: list[Path]) -> dict[str, Any]:
    """Assess only dependencies relevant to this plan; never install them."""
    modules = {name: _module(name) for name in ("faster_whisper", "paddleocr", "paddle", "pypdf")}
    commands = {name: shutil.which(name) for name in ("pdftotext", "pdfinfo", "ffmpeg", "ffprobe")}
    required: set[str] = set()
    conditional: set[str] = set()
    reasons: list[str] = []
    kinds: dict[str, int] = {}
    for path in paths:
        suffix = path.suffix.lower()
        if suffix in VIDEO_SUFFIXES:
            kinds["video"] = kinds.get("video", 0) + 1
            if not modules["faster_whisper"] and not (commands["ffmpeg"] and commands["ffprobe"]):
                required.add("faster_whisper"); reasons.append("待识别视频既无音轨转写能力，也无 FFmpeg 关键帧兜底")
            elif not modules["faster_whisper"]:
                reasons.append("视频可使用现有 FFmpeg 关键帧兜底，faster-whisper 不是本次必装项")
        elif suffix in AUDIO_SUFFIXES:
            kinds["audio"] = kinds.get("audio", 0) + 1
            if not modules["faster_whisper"]:
                required.add("faster_whisper"); reasons.append("待识别音频需要本地语音转写")
        elif suffix in IMAGE_SUFFIXES:
            kinds["image"] = kinds.get("image", 0) + 1
            if not (modules["paddleocr"] and modules["paddle"]):
                conditional.add("paddleocr"); reasons.append("图片可优先使用代理视觉；仅在视觉不可用或文字细节不足时才需要 PaddleOCR")
        elif suffix == ".pdf":
            kinds["pdf"] = kinds.get("pdf", 0) + 1
            if not (commands["pdftotext"] or modules["pypdf"]):
                required.add("pypdf"); reasons.append("待识别 PDF 缺少 pdftotext 与 pypdf")
        else:
            kinds["document"] = kinds.get("document", 0) + 1
    required_packages = [PINNED[name] for name in sorted(required)]
    conditional_packages = [PINNED[name] for name in sorted(conditional) if name not in required]
    requirements_packages = set(PINNED.values())
    if not required_packages and not conditional_packages:
        requirements_status = "not-needed"
    elif set(required_packages) == requirements_packages:
        requirements_status = "full-install-required"
    elif required_packages:
        requirements_status = "minimal-install-required"
    else:
        requirements_status = "conditional-only"
    version = [sys.version_info.major, sys.version_info.minor, sys.version_info.micro]
    python_compatible = tuple(version[:2]) >= (3, 10)
    if os.name == "nt":
        prefix = f'"{sys.executable}" -m pip install'
    else:
        prefix = f'"{sys.executable}" -m pip install'
    minimal_command = prefix + " " + " ".join(required_packages) if required_packages else ""
    full_command = prefix + " -r requirements.txt" if requirements_status == "full-install-required" else ""
    authorization_required = bool(required_packages)
    return {
        "status": "authorization-required" if authorization_required else ("conditional" if conditional_packages else "ready"),
        "analysis_files": len(paths), "analysis_kinds": kinds,
        "python": {"executable": sys.executable, "version": platform.python_version(), "compatible": python_compatible, "minimum": "3.10", "virtual_environment": sys.prefix != getattr(sys, "base_prefix", sys.prefix)},
        "requirements_file": "requirements.txt", "requirements_status": requirements_status,
        "required_packages": required_packages, "conditional_packages": conditional_packages,
        "external_tools": {"ffmpeg": commands["ffmpeg"], "ffprobe": commands["ffprobe"], "pdftotext": commands["pdftotext"], "pdfinfo": commands["pdfinfo"]},
        "reasons": sorted(set(reasons)), "authorization_required": authorization_required,
        "model_download_may_be_required": "faster_whisper" in required,
        "recommended_install_scope": "full-requirements" if requirements_status == "full-install-required" else ("minimal-packages" if required_packages else "none"),
        "minimal_install_command": minimal_command, "full_install_command": full_command,
        "blocking_reason": "当前 Python 低于 3.10；应先经用户授权选择兼容解释器并创建独立虚拟环境" if authorization_required and not python_compatible else "",
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="只读检查本地文件分析能力；不安装依赖或下载模型")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--plan", action="store_true", help="按本次待分析文件评估 requirements.txt 是否必要")
    args = parser.parse_args()
    paths = [path.expanduser().resolve() for path in args.paths]
    print(json.dumps(assess_plan(paths) if args.plan else check(paths), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

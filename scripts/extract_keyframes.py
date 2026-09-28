#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from common import fingerprint, modified_at
from runtime_environment import detect as detect_environment

def _imageio_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def select_backend() -> dict[str, Any]:
    environment = detect_environment()
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    bundled = _imageio_ffmpeg()
    swift_script = Path(__file__).with_name("avframes.swift")
    swift = shutil.which("swift") if environment["native_macos_frameworks_allowed"] else None
    if ffmpeg and ffprobe:
        return {"name": "ffmpeg-cli", "ffmpeg": ffmpeg, "ffprobe": ffprobe, "environment": environment}
    if environment["portable_script_required"] and bundled:
        return {"name": "python-imageio-ffmpeg", "ffmpeg": bundled, "ffprobe": None, "environment": environment}
    if swift and swift_script.is_file():
        return {"name": "macos-avfoundation", "swift": swift, "script": str(swift_script), "environment": environment}
    if bundled:
        return {"name": "python-imageio-ffmpeg", "ffmpeg": bundled, "ffprobe": None, "environment": environment}
    return {"name": "unavailable", "environment": environment}

def available() -> bool:
    return select_backend()["name"] != "unavailable"

def probe_duration(path: Path, command: str | None = None) -> float:
    command = command or shutil.which("ffprobe")
    if not command:
        raise RuntimeError("缺少 ffprobe")
    process = subprocess.run(
        [command, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "ffprobe 无法读取视频时长")
    try:
        duration = float(json.loads(process.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("视频时长不可用") from exc
    if duration <= 0:
        raise RuntimeError("视频时长无效")
    return duration

def _duration_with_ffmpeg(command: str, path: Path) -> float:
    process = subprocess.run([command, "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=60, check=False)
    match = __import__("re").search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", process.stderr)
    if not match:
        raise RuntimeError("FFmpeg 无法读取视频时长")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

def sample_times(duration: float, count: int = 5) -> list[float]:
    count = max(1, min(count, 9))
    if count == 1:
        return [max(0.0, duration * 0.5)]
    # Avoid title slates and end credits while still covering the full timeline.
    return [round(duration * (0.05 + index * 0.90 / (count - 1)), 6) for index in range(count)]

def extract(path: Path, output_dir: Path, count: int = 5, width: int = 1280) -> dict[str, Any]:
    backend = select_backend()
    if backend["name"] == "unavailable":
        return {
            "source": str(path), "fingerprint": fingerprint(path), "modified_at": modified_at(path),
            "method": "installation-required", "frames": [],
            "error": "没有可用抽帧后端；沙箱/Windows/macOS 可安装 imageio-ffmpeg==0.6.0，macOS 本机还可使用 AVFoundation", "requires_user_confirmation": True,
            "tools": ["imageio-ffmpeg==0.6.0"], "environment": backend["environment"],
        }
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if backend["name"] == "macos-avfoundation":
            process = subprocess.run([backend["swift"], backend["script"], str(path), str(output_dir), str(count)], capture_output=True, text=True, timeout=120, check=False)
            frames = []
            for line in process.stdout.splitlines():
                if not line.startswith("FRAME\t"): continue
                _, seconds, frame_path = line.split("\t", 2)
                if Path(frame_path).is_file(): frames.append({"path": frame_path, "time_seconds": round(float(seconds), 3)})
            if not frames: raise RuntimeError(process.stderr.strip() or "AVFoundation 未能提取关键帧")
            return {"source": str(path), "fingerprint": fingerprint(path), "modified_at": modified_at(path), "method": "keyframes", "frames": frames, "sample_strategy": "5%-95%均匀关键帧", "requires_agent_vision": True, "backend": backend["name"], "environment": backend["environment"], "error": None}
        command = str(backend["ffmpeg"])
        duration = probe_duration(path, str(backend["ffprobe"])) if backend.get("ffprobe") else _duration_with_ffmpeg(command, path)
        frames = []
        for index, seconds in enumerate(sample_times(duration, count), start=1):
            target = output_dir / f"frame-{index:02d}.jpg"
            if not target.is_file():
                process = subprocess.run(
                    [command, "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale='min({max(320, width)},iw)':-2", "-q:v", "3", str(target)],
                    capture_output=True, text=True, timeout=90, check=False,
                )
                if process.returncode != 0 or not target.is_file():
                    continue
            frames.append({"path": str(target), "time_seconds": round(seconds, 3)})
        method = "keyframes" if frames else "unavailable"
        error = None if frames else "ffmpeg 未能提取代表性关键帧"
        return {
            "source": str(path), "fingerprint": fingerprint(path), "modified_at": modified_at(path),
            "method": method, "frames": frames, "duration_seconds": round(duration, 3),
            "sample_strategy": "5%-95%均匀关键帧", "requires_agent_vision": bool(frames), "backend": backend["name"], "environment": backend["environment"], "error": error,
        }
    except Exception as exc:
        return {
            "source": str(path), "fingerprint": fingerprint(path), "modified_at": modified_at(path),
            "method": "unavailable", "frames": [], "backend": backend["name"], "environment": backend["environment"], "error": str(exc),
        }

def main() -> int:
    parser = argparse.ArgumentParser(description="均匀抽取视频关键帧作为音轨转写的兜底证据")
    parser.add_argument("path", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--width", type=int, default=1280)
    args = parser.parse_args()
    path = args.path.expanduser().resolve()
    if not path.is_file():
        parser.error(f"文件不存在: {path}")
    print(json.dumps(extract(path, args.output_dir.expanduser().resolve(), args.count, args.width), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

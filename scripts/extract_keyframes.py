#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from common import fingerprint, modified_at

def available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

def probe_duration(path: Path) -> float:
    command = shutil.which("ffprobe")
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

def sample_times(duration: float, count: int = 5) -> list[float]:
    count = max(1, min(count, 9))
    if count == 1:
        return [max(0.0, duration * 0.5)]
    # Avoid title slates and end credits while still covering the full timeline.
    return [round(duration * (0.05 + index * 0.90 / (count - 1)), 6) for index in range(count)]

def extract(path: Path, output_dir: Path, count: int = 5, width: int = 1280) -> dict[str, Any]:
    if not available():
        return {
            "source": str(path), "fingerprint": fingerprint(path), "modified_at": modified_at(path),
            "method": "installation-required", "frames": [],
            "error": "关键帧兜底需要 ffmpeg 和 ffprobe", "requires_user_confirmation": True,
            "tools": ["ffmpeg", "ffprobe"],
        }
    try:
        duration = probe_duration(path)
        output_dir.mkdir(parents=True, exist_ok=True)
        command = shutil.which("ffmpeg")
        frames = []
        for index, seconds in enumerate(sample_times(duration, count), start=1):
            target = output_dir / f"frame-{index:02d}.jpg"
            if not target.is_file():
                process = subprocess.run(
                    [str(command), "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale='min({max(320, width)},iw)':-2", "-q:v", "3", str(target)],
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
            "sample_strategy": "5%-95%均匀关键帧", "requires_agent_vision": bool(frames), "error": error,
        }
    except Exception as exc:
        return {
            "source": str(path), "fingerprint": fingerprint(path), "modified_at": modified_at(path),
            "method": "unavailable", "frames": [], "error": str(exc),
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

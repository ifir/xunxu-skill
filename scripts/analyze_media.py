#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import fingerprint, load_json, modified_at, now_iso, write_json
from ocr_image import extract_text
from transcribe_media import transcribe

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".bmp", ".heic", ".heif", ".avif"}
AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".amr", ".ape"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".mts", ".m2ts"}

def analyze(path: Path, model: str, language: str | None, max_seconds: float, keyframe_dir: Path | None = None) -> dict:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return extract_text(path)
    if suffix in AUDIO_SUFFIXES:
        return transcribe(path, model, language, max_seconds)
    if suffix in VIDEO_SUFFIXES:
        transcription = transcribe(path, model, language, max_seconds)
        if transcription.get("method") == "transcription" and str(transcription.get("text") or "").strip() and not transcription.get("error"):
            return transcription
        from extract_keyframes import extract
        frames = extract(path, keyframe_dir or path.parent / ".cache" / "keyframes" / fingerprint(path))
        frames["fallback_reason"] = transcription.get("error") or "音轨没有可用语音文本"
        frames["transcription_method"] = transcription.get("method")
        return frames
    return {"source": str(path), "fingerprint": fingerprint(path), "modified_at": modified_at(path), "method": "unsupported", "text": "", "error": "该媒体类型未配置分析器"}

def main() -> int:
    parser = argparse.ArgumentParser(description="路由图片 OCR 或音视频语音转写，并复用原始识别缓存")
    parser.add_argument("path", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language")
    parser.add_argument("--max-seconds", type=float, default=300.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keyframe-dir", type=Path)
    args = parser.parse_args()
    path = args.path.expanduser().resolve()
    if not path.is_file(): parser.error(f"文件不存在: {path}")
    cache_path = (args.cache or path.parent / ".cache" / ".organizer.raw-analysis.json").expanduser().resolve()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = load_json(cache_path, {"version": 1, "items": {}}); cache.setdefault("items", {})
    key = fingerprint(path)
    if key in cache["items"] and not args.force:
        result = dict(cache["items"][key]); result["cache_hit"] = True
    else:
        keyframe_dir = args.keyframe_dir.expanduser().resolve() if args.keyframe_dir else None
        result = analyze(path, args.model, args.language, args.max_seconds, keyframe_dir); result["cache_hit"] = False
        # Missing capabilities and runtime failures are not durable analysis
        # results. Caching them would keep returning the fallback after tools
        # are installed or a transient failure is fixed.
        if result.get("method") not in {"unavailable", "installation-required", "unsupported"} and not result.get("error"):
            cache["items"][key] = result; cache["updated_at"] = now_iso(); write_json(cache_path, cache)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

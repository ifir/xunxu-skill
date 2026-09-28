#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import result_record

def transcribe(path: Path, model_name: str, language: str | None, max_seconds: float | None) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        result = result_record(path, "", "installation-required", "缺少 faster-whisper==1.2.1；必须先征得用户同意，才能安装依赖并在首次使用时下载模型")
        result.update({"packages": ["faster-whisper==1.2.1"], "requires_user_confirmation": True, "model_download_may_be_required": True})
        return result
    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(path), language=language, vad_filter=True, beam_size=5)
        chunks, elapsed = [], 0.0
        for segment in segments:
            if max_seconds is not None and segment.start >= max_seconds: break
            chunks.append(segment.text.strip())
            elapsed = max(elapsed, float(segment.end))
        result = result_record(path, " ".join(filter(None, chunks)), "transcription")
        result.update({"language": getattr(info, "language", language), "duration_processed": elapsed, "model": model_name})
        return result
    except Exception as exc:
        return result_record(path, "", "transcription", str(exc))

def main() -> int:
    parser = argparse.ArgumentParser(description="使用 faster-whisper 将本地音频或视频语音转为文字")
    parser.add_argument("path", type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language")
    parser.add_argument("--max-seconds", type=float, default=300.0)
    args = parser.parse_args()
    path = args.path.expanduser().resolve()
    if not path.is_file(): parser.error(f"文件不存在: {path}")
    print(json.dumps(transcribe(path, args.model, args.language, args.max_seconds), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from analyze_document import extract_text
from common import now_iso
from check_capabilities import check as check_capabilities
from run_queue import atomic_json, latest_run, read_json

DOCUMENT_SUFFIXES = {
    ".txt", ".text", ".md", ".markdown", ".rst", ".adoc", ".csv", ".tsv",
    ".json", ".jsonc", ".yaml", ".yml", ".toml", ".xml", ".ini", ".cfg", ".conf",
    ".log", ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".c",
    ".h", ".cpp", ".hpp", ".sh", ".ps1", ".bat", ".cmd", ".sql", ".html", ".css",
    ".rtf", ".docx", ".pptx", ".xlsx", ".epub", ".pdf",
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".bmp", ".heic", ".heif", ".avif"}
AUDIO_VIDEO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".amr", ".ape", ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".mts", ".m2ts"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".mts", ".m2ts"}

def _document_job(path: str, max_chars: int, max_pages: int) -> dict[str, Any]:
    return extract_text(Path(path), max_chars, max_pages)

def _media_job(path: Path, kind: str, max_chars: int, model: str, max_seconds: float, frame_dir: Path | None = None) -> dict[str, Any]:
    if kind == "image":
        from ocr_image import extract_text as ocr
        result = ocr(path)
    elif kind == "video":
        from transcribe_media import transcribe
        transcription = transcribe(path, model, None, max_seconds)
        if transcription.get("method") == "transcription" and str(transcription.get("text") or "").strip() and not transcription.get("error"):
            result = transcription
        else:
            from extract_keyframes import extract
            keyframes = extract(path, frame_dir or path.parent / ".cache" / "keyframes")
            keyframes["fallback_reason"] = transcription.get("error") or "音轨没有可用语音文本"
            keyframes["transcription_method"] = transcription.get("method")
            result = keyframes
    else:
        from transcribe_media import transcribe
        result = transcribe(path, model, None, max_seconds)
    result["text"] = str(result.get("text") or "")[:max_chars]
    return result

def _record(job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    record = {
        "fingerprint": job.get("fingerprint"), "source": job.get("source"),
        "previous_fingerprint": job.get("previous_fingerprint", ""), "cache_status": job.get("cache_status", "new"),
        "name_hint": job.get("name_hint", ""), "analysis_depth": job.get("analysis_depth"),
        "method": result.get("method"), "text": result.get("text", ""),
        "error": result.get("error"), "extracted_at": now_iso(),
    }
    for key in ("sample_strategy", "sampled_pages", "truncated", "frames", "duration_seconds", "requires_agent_vision", "fallback_reason", "transcription_method", "requires_user_confirmation", "tools"):
        if key in result:
            record[key] = result[key]
    return record

def _previous_evidence(root: Path, fingerprint: str) -> dict[str, Any] | None:
    if not fingerprint:
        return None
    matches = sorted((root / ".cache" / "runs").glob(f"*/evidence/{fingerprint}.json"), reverse=True)
    return read_json(matches[0], None) if matches else None

def _attach_diff(root: Path, job: dict[str, Any], record: dict[str, Any], limit: int = 4000) -> None:
    previous = _previous_evidence(root, str(job.get("previous_fingerprint") or ""))
    if not previous:
        record["diff_status"] = "previous-evidence-unavailable"
        return
    before = str(previous.get("text") or "").splitlines()
    after = str(record.get("text") or "").splitlines()
    diff = "\n".join(difflib.unified_diff(before, after, fromfile="previous", tofile="current", n=2))
    record["diff_status"] = "changed" if diff else "sample-unchanged"
    record["diff"] = diff[:limit]

def analyze_jobs(root: Path, run: Path, workers: int, max_chars: int, max_pages: int, include_media: bool, model: str, max_seconds: float) -> dict[str, Any]:
    evidence_dir = run / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    jobs = [read_json(path, {}) for path in sorted((run / "jobs").glob("*.json"))]
    jobs = [job for job in jobs if job.get("status") == "pending" and not (evidence_dir / f"{job.get('fingerprint')}.json").is_file()]
    documents: list[tuple[dict[str, Any], Path]] = []
    media: list[tuple[dict[str, Any], Path, str]] = []
    media_candidates: list[Path] = []
    unavailable = 0
    for job in jobs:
        path = root / str(job.get("source", ""))
        suffix = path.suffix.lower()
        if job.get("method_required") == "filename-only":
            atomic_json(evidence_dir / f"{job['fingerprint']}.json", _record(job, {"method": "filename-only", "text": "", "error": None}))
        elif job.get("kind") == "file" and (suffix in DOCUMENT_SUFFIXES or path.name.lower() in {"makefile", "dockerfile", "cmakelists.txt"}):
            documents.append((job, path))
        elif suffix in IMAGE_SUFFIXES:
            media_candidates.append(path)
            if include_media:
                media.append((job, path, "image"))
        elif suffix in AUDIO_VIDEO_SUFFIXES:
            media_candidates.append(path)
            if include_media:
                media.append((job, path, "video" if suffix in VIDEO_SUFFIXES else "audio"))
        else:
            atomic_json(evidence_dir / f"{job['fingerprint']}.json", _record(job, {"method": "unavailable", "text": "", "error": "批处理器不支持该格式"}))
            unavailable += 1
    capability = check_capabilities(media_candidates) if media_candidates else {"status": "ready", "missing": [], "packages": [], "requires_user_confirmation": False}
    if media_candidates and capability.get("requires_user_confirmation"):
        return {"run_id": run.name, "status": "installation-required", "media_files": len(media_candidates), "capability": capability, "message": "缺少媒体分析能力。必须先询问用户是否安装，未获同意不得安装、下载模型、标记任务完成或继续请求移动确认。"}
    if media_candidates and not include_media:
        return {"run_id": run.name, "status": "media-analysis-confirmation-required", "media_files": len(media_candidates), "capability": capability, "message": "媒体工具已就绪，但必须先确认执行本地媒体分析；不得写入 unavailable 兜底。"}
    completed = 0
    if documents:
        with ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {executor.submit(_document_job, str(path), max_chars, max_pages): job for job, path in documents}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {"method": "unavailable", "text": "", "error": str(exc)}
                record = _record(job, result)
                if job.get("cache_status") == "modified": _attach_diff(root, job, record)
                atomic_json(evidence_dir / f"{job['fingerprint']}.json", record)
                completed += 1
    # OCR and Whisper are deliberately serialized: loading several large models
    # usually makes a batch slower and can exhaust memory. Document extraction
    # still uses the full bounded process pool above.
    blocked = []
    for job, path, kind in media:
        frame_dir = run / "keyframes" / str(job["fingerprint"]) if kind == "video" else None
        result = _media_job(path, kind, max_chars, model, max_seconds, frame_dir)
        if result.get("method") == "installation-required":
            blocked.append({"source": job.get("source"), "reason": result.get("error"), "tools": result.get("tools", [])})
            continue
        record = _record(job, result)
        if job.get("cache_status") == "modified": _attach_diff(root, job, record)
        atomic_json(evidence_dir / f"{job['fingerprint']}.json", record)
        completed += 1
    if blocked:
        return {"run_id": run.name, "status": "installation-required", "blocked": blocked, "message": "音轨转写没有得到证据，且关键帧兜底工具缺失。必须询问用户是否安装 FFmpeg，不能完成视频意图识别或进入移动确认。"}
    items = []
    for path in sorted(evidence_dir.glob("*.json")):
        item = read_json(path, {})
        items.append({"fingerprint": item.get("fingerprint"), "source": item.get("source"), "method": item.get("method"), "characters": len(str(item.get("text") or "")), "frames": len(item.get("frames") or []), "requires_agent_vision": bool(item.get("requires_agent_vision")), "evidence": path.name, "error": item.get("error")})
    index = {"version": 1, "run_id": run.name, "updated_at": now_iso(), "max_characters_per_file": max_chars, "items": items}
    atomic_json(run / "evidence-index.json", index)
    return {"run_id": run.name, "status": "completed", "workers": workers, "new_evidence": completed, "unavailable": unavailable, "total_evidence": len(items), "index": str(run / "evidence-index.json")}

def main() -> int:
    parser = argparse.ArgumentParser(description="多进程提取紧凑文件证据；正文只落盘，不输出到终端")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--max-chars", type=int, default=8000)
    parser.add_argument("--max-pages", type=int, default=6)
    parser.add_argument("--include-media", action="store_true")
    parser.add_argument("--model", default="small")
    parser.add_argument("--max-seconds", type=float, default=300.0)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    run = root / ".cache" / "runs" / args.run_id if args.run_id else latest_run(root)
    result = analyze_jobs(root, run, max(1, min(args.workers, 16)), max(1000, args.max_chars), max(1, args.max_pages), args.include_media, args.model, args.max_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

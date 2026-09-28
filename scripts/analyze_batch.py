#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from analyze_document import extract_text
from common import now_iso
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

def _document_job(path: str, max_chars: int, max_pages: int) -> dict[str, Any]:
    return extract_text(Path(path), max_chars, max_pages)

def _media_job(path: Path, kind: str, max_chars: int, model: str, max_seconds: float) -> dict[str, Any]:
    if kind == "image":
        from ocr_image import extract_text as ocr
        result = ocr(path)
    else:
        from transcribe_media import transcribe
        result = transcribe(path, model, None, max_seconds)
    result["text"] = str(result.get("text") or "")[:max_chars]
    return result

def _record(job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "fingerprint": job.get("fingerprint"), "source": job.get("source"),
        "name_hint": job.get("name_hint", ""), "analysis_depth": job.get("analysis_depth"),
        "method": result.get("method"), "text": result.get("text", ""),
        "error": result.get("error"), "extracted_at": now_iso(),
    }

def analyze_jobs(root: Path, run: Path, workers: int, max_chars: int, max_pages: int, include_media: bool, model: str, max_seconds: float) -> dict[str, Any]:
    evidence_dir = run / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    jobs = [read_json(path, {}) for path in sorted((run / "jobs").glob("*.json"))]
    jobs = [job for job in jobs if job.get("status") == "pending" and not (evidence_dir / f"{job.get('fingerprint')}.json").is_file()]
    documents: list[tuple[dict[str, Any], Path]] = []
    media: list[tuple[dict[str, Any], Path, str]] = []
    unavailable = 0
    for job in jobs:
        path = root / str(job.get("source", ""))
        suffix = path.suffix.lower()
        if job.get("method_required") == "filename-only":
            atomic_json(evidence_dir / f"{job['fingerprint']}.json", _record(job, {"method": "filename-only", "text": "", "error": None}))
        elif job.get("kind") == "file" and (suffix in DOCUMENT_SUFFIXES or path.name.lower() in {"makefile", "dockerfile", "cmakelists.txt"}):
            documents.append((job, path))
        elif include_media and suffix in IMAGE_SUFFIXES:
            media.append((job, path, "image"))
        elif include_media and suffix in AUDIO_VIDEO_SUFFIXES:
            media.append((job, path, "audio-video"))
        else:
            atomic_json(evidence_dir / f"{job['fingerprint']}.json", _record(job, {"method": "unavailable", "text": "", "error": "批处理器没有启用或不支持该格式"}))
            unavailable += 1
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
                atomic_json(evidence_dir / f"{job['fingerprint']}.json", _record(job, result))
                completed += 1
    # OCR and Whisper are deliberately serialized: loading several large models
    # usually makes a batch slower and can exhaust memory. Document extraction
    # still uses the full bounded process pool above.
    for job, path, kind in media:
        result = _media_job(path, kind, max_chars, model, max_seconds)
        atomic_json(evidence_dir / f"{job['fingerprint']}.json", _record(job, result))
        completed += 1
    items = []
    for path in sorted(evidence_dir.glob("*.json")):
        item = read_json(path, {})
        items.append({"fingerprint": item.get("fingerprint"), "source": item.get("source"), "method": item.get("method"), "characters": len(str(item.get("text") or "")), "evidence": path.name, "error": item.get("error")})
    index = {"version": 1, "run_id": run.name, "updated_at": now_iso(), "max_characters_per_file": max_chars, "items": items}
    atomic_json(run / "evidence-index.json", index)
    return {"run_id": run.name, "workers": workers, "new_evidence": completed, "unavailable": unavailable, "total_evidence": len(items), "index": str(run / "evidence-index.json")}

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

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

TERMINAL = {"completed", "failed", "unavailable", "stale", "skipped"}

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def read_json(path: Path, default: Any) -> Any:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError): return default

def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try: os.unlink(temp_name)
        except OSError: pass
        raise

def latest_run(root: Path) -> Path:
    runs = root / ".cache" / "runs"
    active = [path for path in runs.glob("*") if path.is_dir() and read_json(path / "summary.json", {}).get("status") != "completed"]
    if not active: raise ValueError("没有可恢复的分析运行")
    return sorted(active, key=lambda path: path.name)[-1]

def summarize(run: Path) -> dict[str, Any]:
    jobs = [read_json(path, {}) for path in (run / "jobs").glob("*.json")]
    counts: dict[str, int] = {}
    for job in jobs: counts[job.get("status", "unknown")] = counts.get(job.get("status", "unknown"), 0) + 1
    total, done = len(jobs), sum(value for key, value in counts.items() if key in TERMINAL)
    summary = {"run_id": run.name, "status": "completed" if total == done else "running", "total": total, "done": done, "remaining": total - done, "counts": counts, "updated_at": now_iso()}
    atomic_json(run / "summary.json", summary); return summary

def create_run(root: Path, analysis_file: Path, config_file: Path) -> dict[str, Any]:
    analysis = read_json(analysis_file, {})
    items = analysis.get("items", [])
    run_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    run = root / ".cache" / "runs" / run_id
    (run / "jobs").mkdir(parents=True); (run / "results").mkdir(); (run / "failures").mkdir()
    manifest = {"version": 1, "run_id": run_id, "root": str(root), "created_at": now_iso(), "config": read_json(config_file, {}), "analysis_source": str(analysis_file), "batch_size": 12, "retry_limit": 2}
    atomic_json(run / "manifest.json", manifest)
    for item in items:
        job = dict(item); fp = str(job["fingerprint"]); source = root / job["source"]
        try:
            stat = source.stat(); job.update({"size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
        except OSError:
            job.update({"size": None, "mtime_ns": None})
        job.update({"status": "pending", "attempts": 0, "created_at": now_iso(), "started_at": None, "completed_at": None, "worker": None, "error": None})
        atomic_json(run / "jobs" / f"{fp}.json", job)
    return summarize(run)

def reset_stale(run: Path, minutes: int) -> int:
    cutoff, reset = datetime.now().astimezone() - timedelta(minutes=minutes), 0
    for path in (run / "jobs").glob("*.json"):
        job = read_json(path, {})
        if job.get("status") != "running" or not job.get("started_at"): continue
        try: started = datetime.fromisoformat(job["started_at"])
        except ValueError: started = cutoff - timedelta(seconds=1)
        if started < cutoff:
            job.update({"status": "pending", "worker": None, "started_at": None, "error": "stale worker lease reset"}); atomic_json(path, job); reset += 1
    return reset

def claim(run: Path, worker: str, limit: int, stale_minutes: int) -> dict[str, Any]:
    reset_stale(run, stale_minutes); claimed = []
    for path in sorted((run / "jobs").glob("*.json")):
        if len(claimed) >= limit: break
        job = read_json(path, {})
        if job.get("status") != "pending": continue
        job.update({"status": "running", "worker": worker, "started_at": now_iso(), "attempts": int(job.get("attempts", 0)) + 1}); atomic_json(path, job); claimed.append(job)
    heartbeat(run, worker, claimed[-1].get("fingerprint") if claimed else None)
    return {"run_id": run.name, "worker": worker, "claimed": claimed, "summary": summarize(run)}

def heartbeat(run: Path, worker: str, current: str | None) -> None:
    atomic_json(run / "heartbeat.json", {"run_id": run.name, "worker": worker, "current": current, "updated_at": now_iso()})

def complete(root: Path, run: Path, fingerprint: str, result_file: Path | None, status: str, error: str | None) -> dict[str, Any]:
    job_path = run / "jobs" / f"{fingerprint}.json"; job = read_json(job_path, None)
    if not isinstance(job, dict): raise ValueError("任务不存在")
    source = root / job["source"]
    if status == "completed":
        try:
            stat = source.stat()
            if stat.st_size != job.get("size") or stat.st_mtime_ns != job.get("mtime_ns"): status, error = "stale", "文件在分析期间发生变化"
        except OSError: status, error = "stale", "源文件不存在"
    result = read_json(result_file, {}) if result_file else {}
    retry_limit = int(read_json(run / "manifest.json", {}).get("retry_limit", 2))
    retrying = status == "failed" and int(job.get("attempts", 0)) < retry_limit
    final_status = "pending" if retrying else status
    result.update({"fingerprint": fingerprint, "source": job["source"], "status": status, "error": error, "completed_at": now_iso(), "will_retry": retrying})
    target = run / ("results" if status == "completed" else "failures") / f"{fingerprint}.attempt-{job.get('attempts', 0)}.json"; atomic_json(target, result)
    job.update({"status": final_status, "completed_at": None if retrying else now_iso(), "worker": None if retrying else job.get("worker"), "started_at": None if retrying else job.get("started_at"), "error": error}); atomic_json(job_path, job)
    return {"job": job, "summary": summarize(run)}

def merge_results(root: Path, run: Path) -> dict[str, Any]:
    summary = summarize(run)
    if summary["remaining"]:
        raise ValueError("运行尚未完成，不能合并意图结果")
    intent_path = root / ".cache" / ".organizer.intent.json"
    intent = read_json(intent_path, {"version": 1, "items": {}}); intent.setdefault("items", {})
    merged, ignored = 0, 0
    for job_path in sorted((run / "jobs").glob("*.json")):
        job = read_json(job_path, {})
        if job.get("status") == "unavailable":
            failures = sorted((run / "failures").glob(f"{job['fingerprint']}.attempt-*.json"))
            reason = read_json(failures[-1], {}).get("error", "分析能力不可用") if failures else "分析能力不可用"
            intent["items"][job["fingerprint"]] = {"source": job["source"], "modified_at": datetime.fromtimestamp(job["mtime_ns"] / 1_000_000_000).astimezone().isoformat(timespec="seconds"), "intent": "", "suggested_name": "", "intent_group": "", "method": "unavailable", "confidence": "low", "error": reason, "analyzed_at": job.get("completed_at") or now_iso()}
            merged += 1; continue
        if job.get("status") != "completed": ignored += 1; continue
        matches = sorted((run / "results").glob(f"{job['fingerprint']}.attempt-*.json"))
        legacy = run / "results" / f"{job['fingerprint']}.json"
        if legacy.is_file(): matches.append(legacy)
        if not matches: ignored += 1; continue
        result = read_json(matches[-1], {})
        required = {"intent", "suggested_name", "intent_group", "method", "confidence"}
        if not required.issubset(result): ignored += 1; continue
        entry = {key: result.get(key) for key in required | {"category", "analyzed_at"} if result.get(key) is not None}
        entry.update({"source": job["source"], "modified_at": datetime.fromtimestamp(job["mtime_ns"] / 1_000_000_000).astimezone().isoformat(timespec="seconds")})
        if not entry.get("analyzed_at"): entry["analyzed_at"] = result.get("completed_at") or now_iso()
        previous = str(job.get("previous_fingerprint") or "")
        if previous and previous != job["fingerprint"]:
            intent["items"].pop(previous, None)
            entry["supersedes"] = previous
        intent["items"][job["fingerprint"]] = entry; merged += 1
    intent["updated_at"] = now_iso(); atomic_json(intent_path, intent)
    try:
        from organizer import write_index
        index_path = write_index(root, intent)
    except Exception:
        index_path = root / ".cache" / "file2intent.md"
    atomic_json(run / "merge.json", {"run_id": run.name, "merged": merged, "ignored": ignored, "merged_at": now_iso()})
    return {"run_id": run.name, "merged": merged, "ignored": ignored, "intent_cache": str(intent_path), "intent_index": str(index_path)}

def main() -> int:
    parser = argparse.ArgumentParser(description="可恢复的逐文件意图分析任务队列")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create"); create.add_argument("--root", type=Path, required=True); create.add_argument("--analysis-file", type=Path); create.add_argument("--config-file", type=Path)
    claim_p = sub.add_parser("claim"); claim_p.add_argument("--root", type=Path, required=True); claim_p.add_argument("--run-id"); claim_p.add_argument("--worker", required=True); claim_p.add_argument("--limit", type=int, default=12); claim_p.add_argument("--stale-minutes", type=int, default=30)
    finish = sub.add_parser("complete"); finish.add_argument("--root", type=Path, required=True); finish.add_argument("--run-id", required=True); finish.add_argument("--fingerprint", required=True); finish.add_argument("--result-file", type=Path); finish.add_argument("--status", choices=sorted(TERMINAL), default="completed"); finish.add_argument("--error")
    resume = sub.add_parser("resume"); resume.add_argument("--root", type=Path, required=True); resume.add_argument("--run-id"); resume.add_argument("--stale-minutes", type=int, default=30)
    merge = sub.add_parser("merge"); merge.add_argument("--root", type=Path, required=True); merge.add_argument("--run-id", required=True)
    args = parser.parse_args(); root = args.root.expanduser().resolve()
    try:
        if args.command == "create":
            result = create_run(root, (args.analysis_file or root / ".cache" / ".organizer.analysis-required.json").resolve(), (args.config_file or root / ".cache" / ".organizer.config.json").resolve())
        elif args.command == "claim":
            run = root / ".cache" / "runs" / args.run_id if args.run_id else latest_run(root); result = claim(run, args.worker, max(1, min(args.limit, 20)), args.stale_minutes)
        elif args.command == "complete":
            result = complete(root, root / ".cache" / "runs" / args.run_id, args.fingerprint, args.result_file, args.status, args.error)
        elif args.command == "resume":
            run = root / ".cache" / "runs" / args.run_id if args.run_id else latest_run(root); reset = reset_stale(run, args.stale_minutes); result = {"reset": reset, "summary": summarize(run)}
        else:
            result = merge_results(root, root / ".cache" / "runs" / args.run_id)
    except ValueError as exc: parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())

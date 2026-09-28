#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import traceback
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import analyze_media
import organizer
import run_queue

def write(path: Path, data: bytes | str = b"test") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str): path.write_text(data, encoding="utf-8")
    else: path.write_bytes(data)
    old = time.time() - 1200
    os.utime(path, (old, old))
    return path

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def configure(root: Path, rename: bool = False, existing: bool = False, trust: bool | None = None, private: list[str] | None = None) -> dict:
    return organizer.save_config(root, rename, existing, trust, private or [])

def plan(root: Path) -> dict:
    return organizer.make_plan(root, organizer.cache_path(root, ".organizer.plan.json"), 0)

def add_intent(root: Path, item: dict, **values: str) -> None:
    path = organizer.cache_path(root, ".organizer.intent.json")
    data = organizer.load_json(path, {"version": 1, "items": {}}); data.setdefault("items", {})
    data["items"][item["fingerprint"]] = {"source": item["source"], "modified_at": item.get("modified_at", ""), "intent": values.get("intent", "测试意图"), "suggested_name": values.get("suggested_name", "测试意图"), "intent_group": values.get("intent_group", "测试分类"), "category": values.get("category", item.get("media_category", "文档资料")), "method": values.get("method", "text"), "confidence": values.get("confidence", "high"), "analyzed_at": organizer.now_iso()}
    organizer.write_json(path, data)

class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="xunxu-test-")
        self.root = Path(self.temp.name).resolve()

    def tearDown(self) -> None:
        self.temp.cleanup()

class ClassificationTests(Base):
    def test_all_eleven_categories(self) -> None:
        samples = {"文档资料": "a.csv", "电子书": "a.epub", "图片": "a.png", "视频": "a.mp4", "音频": "a.mp3", "字幕": "a.srt", "压缩包": "a.zip", "安装包": "a.dmg", "字体": "a.ttf", "代码": "a.py", "其它": "a.unknown"}
        for name in samples.values(): write(self.root / name)
        configure(self.root); data = plan(self.root)
        actual = {item["source"]: item["category"] for item in data["moves"]}
        self.assertEqual(actual, {name: category for category, name in samples.items()})

    def test_ambiguous_and_special_code(self) -> None:
        write(self.root / "package.json", '{"dependencies":{"x":"1"}}')
        write(self.root / "notes.md", "ordinary prose")
        write(self.root / "config.json", '{"export":true}')
        configure(self.root, rename=True, trust=True); data = plan(self.root)
        found = {item["source"]: item["category"] for item in data["moves"]}
        self.assertEqual(found["package.json"], "代码")
        self.assertEqual(found["notes.md"], "文档资料")
        self.assertEqual(found["config.json"], "其它")

class ConfigurationAndNamingTests(Base):
    def test_trust_name_policy(self) -> None:
        write(self.root / "quarterly-report.txt", "report evidence")
        write(self.root / "a1b2c3d4e5f60718.txt", "unknown evidence")
        configure(self.root, rename=True, trust=True); data = plan(self.root)
        analysis = {item["source"]: item for item in data["analysis_required"]}
        self.assertNotIn("quarterly-report.txt", analysis)
        self.assertEqual(analysis["a1b2c3d4e5f60718.txt"]["analysis_depth"], "full")

    def test_distrust_uses_meaningful_name_as_targeted_hint(self) -> None:
        write(self.root / "quarterly-report.txt", "report evidence")
        write(self.root / "a1b2c3d4e5f60718.txt", "unknown evidence")
        configure(self.root, rename=True, trust=False); data = plan(self.root)
        analysis = {item["source"]: item for item in data["analysis_required"]}
        self.assertEqual(analysis["quarterly-report.txt"]["analysis_depth"], "targeted")
        self.assertEqual(analysis["quarterly-report.txt"]["name_hint"], "quarterly-report")
        self.assertEqual(analysis["a1b2c3d4e5f60718.txt"]["analysis_depth"], "full")

    def test_rename_format_and_group_limit(self) -> None:
        source = write(self.root / "abcdef1234567890.txt", "contract")
        configure(self.root, rename=True, trust=True); first = plan(self.root); job = first["analysis_required"][0]
        add_intent(self.root, job, intent="住房合同", suggested_name="住房租赁合同内容摘要超过十五个字符", intent_group="非常非常长的合同分类目录", category="文档资料")
        data = plan(self.root); move = data["moves"][0]
        expected_date = datetime.fromtimestamp(source.stat().st_mtime).strftime("%y%m%d")
        self.assertTrue(move["new_name"].startswith(expected_date + "-"))
        self.assertLessEqual(len(Path(move["new_name"]).stem.split("-", 1)[1]), 15)
        self.assertLessEqual(len(move["intent_group"]), 8)

class PrivacyAndTraversalTests(Base):
    def test_private_file_filename_only_and_private_folder_pruned(self) -> None:
        write(self.root / "secret-note.txt", "must not be consumed")
        write(self.root / "private-folder" / "inside.txt", "hidden")
        configure(self.root, rename=True, existing=True, trust=False, private=["secret", "private-folder"]); data = plan(self.root)
        analysis = {item["source"]: item for item in data["analysis_required"]}
        self.assertEqual(analysis["secret-note.txt"]["method_required"], "filename-only")
        self.assertNotIn("private-folder/inside.txt", {item["source"] for item in data["moves"]})
        self.assertTrue(any("私密文件夹" in item["reason"] for item in data["skipped"]))

    def test_hidden_incomplete_symlink_and_recent(self) -> None:
        write(self.root / ".hidden.txt")
        write(self.root / "pending.crdownload")
        write(self.root / "recent.txt"); os.utime(self.root / "recent.txt", None)
        target = write(self.root / "target.txt")
        try: (self.root / "link.txt").symlink_to(target)
        except OSError: self.skipTest("symlink unavailable")
        configure(self.root); data = organizer.make_plan(self.root, organizer.cache_path(self.root, ".organizer.plan.json"), 600)
        reasons = " ".join(item["reason"] for item in data["skipped"])
        self.assertIn("隐藏", reasons); self.assertIn("未完成", reasons); self.assertIn("最近", reasons); self.assertIn("符号链接", reasons)

    def test_path_escape_rejected(self) -> None:
        configure(self.root)
        item = {"source": "a.txt", "destination": "../escape.txt", "category": "文档资料", "intent_group": ""}
        with self.assertRaises(ValueError): organizer.validate_mapping(self.root, item, organizer.load_json(organizer.cache_path(self.root, ".organizer.config.json"), {}))

class ExecutionSafetyTests(Base):
    def test_move_preserves_content_and_creates_outputs(self) -> None:
        source = write(self.root / "report.txt", "immutable bytes")
        before = digest(source)
        configure(self.root); data = plan(self.root)
        result = organizer.apply_plan(self.root, organizer.cache_path(self.root, ".organizer.plan.json"))
        destination = self.root / data["moves"][0]["destination"]
        self.assertEqual(digest(destination), before)
        self.assertFalse(source.exists())
        self.assertTrue((self.root / "organizer.change.md").is_file())
        self.assertTrue((self.root / "organizer.report.html").is_file())
        self.assertFalse((self.root / "网页可视化目录.sh").exists())
        self.assertFalse(result["stopped_on_failure"])

    def test_destination_conflict_never_overwrites(self) -> None:
        write(self.root / "same.txt", "source")
        existing = write(self.root / "文档资料" / "same.txt", "destination")
        configure(self.root); data = plan(self.root)
        self.assertEqual(data["moves"][0]["status"], "conflict")
        organizer.apply_plan(self.root, organizer.cache_path(self.root, ".organizer.plan.json"))
        self.assertEqual(existing.read_text(), "destination")
        self.assertTrue((self.root / "same.txt").exists())

    def test_source_change_after_plan_is_skipped(self) -> None:
        source = write(self.root / "change.txt", "before")
        configure(self.root); plan(self.root)
        source.write_text("after and longer", encoding="utf-8")
        result = organizer.apply_plan(self.root, organizer.cache_path(self.root, ".organizer.plan.json"))
        self.assertIn("发生变化", result["results"][0]["status"])

    def test_config_change_after_plan_rejected(self) -> None:
        write(self.root / "a.txt")
        configure(self.root); plan(self.root); configure(self.root, existing=True)
        with self.assertRaises(ValueError): organizer.apply_plan(self.root, organizer.cache_path(self.root, ".organizer.plan.json"))

    def test_idempotent_second_plan(self) -> None:
        write(self.root / "a.txt")
        configure(self.root); plan(self.root); organizer.apply_plan(self.root, organizer.cache_path(self.root, ".organizer.plan.json"))
        configure(self.root); second = plan(self.root)
        self.assertEqual(second["moves"], [])

    def test_existing_directory_switch(self) -> None:
        write(self.root / "old" / "nested.mp3")
        configure(self.root, existing=False); self.assertFalse(any(item["source"].endswith("nested.mp3") for item in plan(self.root)["moves"]))
        configure(self.root, existing=True); self.assertTrue(any(item["source"].endswith("nested.mp3") for item in plan(self.root)["moves"]))

class QueueTests(Base):
    def make_analysis(self, count: int = 2) -> list[Path]:
        items, paths = [], []
        for index in range(count):
            path = write(self.root / f"item-{index}.txt", f"item {index}"); paths.append(path)
            items.append({"kind": "file", "source": path.name, "fingerprint": organizer.fingerprint(path, path.stat()), "method_required": "content", "analysis_depth": "targeted", "name_hint": path.stem})
        organizer.write_json(organizer.cache_path(self.root, ".organizer.analysis-required.json"), {"items": items})
        configure(self.root, rename=True, trust=False)
        return paths

    def test_queue_checkpoint_merge_and_resume(self) -> None:
        self.make_analysis(2)
        summary = run_queue.create_run(self.root, organizer.cache_path(self.root, ".organizer.analysis-required.json"), organizer.cache_path(self.root, ".organizer.config.json"))
        run = self.root / ".cache" / "runs" / summary["run_id"]
        claimed = run_queue.claim(run, "worker-a", 1, 30)["claimed"][0]
        result_file = write(self.root / "result.json", json.dumps({"intent": "报告", "suggested_name": "报告", "intent_group": "文档", "method": "text", "confidence": "high"}))
        run_queue.complete(self.root, run, claimed["fingerprint"], result_file, "completed", None)
        with self.assertRaises(ValueError): run_queue.merge_results(self.root, run)
        job = run_queue.claim(run, "worker-b", 1, 30)["claimed"][0]
        run_queue.complete(self.root, run, job["fingerprint"], result_file, "completed", None)
        merged = run_queue.merge_results(self.root, run)
        self.assertEqual(merged["merged"], 2)
        self.assertTrue((run / "summary.json").is_file()); self.assertTrue((run / "heartbeat.json").is_file())

    def test_failed_job_retries_then_stops(self) -> None:
        self.make_analysis(1); summary = run_queue.create_run(self.root, organizer.cache_path(self.root, ".organizer.analysis-required.json"), organizer.cache_path(self.root, ".organizer.config.json")); run = self.root / ".cache" / "runs" / summary["run_id"]
        first = run_queue.claim(run, "w", 1, 30)["claimed"][0]
        retry = run_queue.complete(self.root, run, first["fingerprint"], None, "failed", "temporary")["job"]
        self.assertEqual(retry["status"], "pending")
        second = run_queue.claim(run, "w", 1, 30)["claimed"][0]
        final = run_queue.complete(self.root, run, second["fingerprint"], None, "failed", "again")["job"]
        self.assertEqual(final["status"], "failed")

    def test_stale_running_lease_is_recovered(self) -> None:
        self.make_analysis(1); summary = run_queue.create_run(self.root, organizer.cache_path(self.root, ".organizer.analysis-required.json"), organizer.cache_path(self.root, ".organizer.config.json")); run = self.root / ".cache" / "runs" / summary["run_id"]
        job = run_queue.claim(run, "dead-worker", 1, 30)["claimed"][0]; path = run / "jobs" / f"{job['fingerprint']}.json"
        job["started_at"] = (datetime.now().astimezone() - timedelta(hours=1)).isoformat(); run_queue.atomic_json(path, job)
        self.assertEqual(run_queue.reset_stale(run, 30), 1)
        self.assertEqual(run_queue.read_json(path, {})["status"], "pending")

class ReportAndMediaTests(Base):
    def test_static_report_file_details(self) -> None:
        file = write(self.root / "图片" / "测试图.png")
        report = organizer.write_report(self.root, organizer.now_iso(), [{"source": "原始随机名.png", "destination": "图片/测试图.png", "status": "已移动", "rename": "原始随机名.png → 测试图.png"}])
        page = report.read_text(encoding="utf-8")
        self.assertEqual(report.parent, self.root)
        self.assertNotIn("/reveal?path=", page); self.assertNotIn("file://", page)
        self.assertIn('data-original="原始随机名.png"', page)
        self.assertIn('data-current="测试图.png"', page)
        self.assertIn("data-modified=", page); self.assertIn("data-size=", page); self.assertIn("data-bytes=", page)
        self.assertIn("<dialog id=\"file-detail\">", page)
        self.assertIn("data-location=", page)

    def test_media_dependency_absence_is_safe_or_analyzer_returns_structure(self) -> None:
        image = write(self.root / "image.png", b"not real")
        result = analyze_media.analyze(image, "small", None, 1)
        self.assertIn(result.get("method"), {"ocr", "unavailable"})
        self.assertIn("fingerprint", result)

    def test_installers_and_archives_never_request_analysis(self) -> None:
        write(self.root / "setup.dmg"); write(self.root / "bundle.zip")
        configure(self.root, rename=True, trust=False); data = plan(self.root)
        self.assertEqual(data["analysis_required"], [])

class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.records = []
    def addSuccess(self, test): super().addSuccess(test); self.records.append((str(test), "passed", ""))
    def addSkip(self, test, reason): super().addSkip(test, reason); self.records.append((str(test), "skipped", reason))
    def addFailure(self, test, err): super().addFailure(test, err); self.records.append((str(test), "failed", self._exc_info_to_string(err, test)))
    def addError(self, test, err): super().addError(test, err); self.records.append((str(test), "error", self._exc_info_to_string(err, test)))

def write_report(output: Path, result: RecordingResult, elapsed: float) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    counts = {key: sum(status == key for _, status, _ in result.records) for key in ("passed", "failed", "error", "skipped")}
    payload = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "elapsed_seconds": round(elapsed, 3), "total": result.testsRun, "counts": counts, "successful": result.wasSuccessful(), "tests": [{"name": name, "status": status, "detail": detail} for name, status, detail in result.records]}
    json_path = output / "xunxu-test-report.json"; json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = [f"| {status} | {name.replace('|', '/')} |" for name, status, _ in result.records]
    notes = ["- 媒体测试默认验证安全降级；未安装 PaddleOCR/faster-whisper 时不会下载模型。", "- 静态 HTML 测试覆盖文件详情弹窗、原始名称、当前名称、修改时间、大小和位置，不打开文件或文件夹。", "- 对话自动触发与提问顺序需另做真实会话验收，Python 测试无法模拟产品路由。"]
    md = f"# 循序（Xunxu）测试报告\n\n- 时间：{payload['generated_at']}\n- 结果：{'通过' if result.wasSuccessful() else '失败'}\n- 总数：{result.testsRun}\n- 通过：{counts['passed']}\n- 失败：{counts['failed'] + counts['error']}\n- 跳过：{counts['skipped']}\n- 耗时：{elapsed:.3f} 秒\n\n## 用例\n\n| 状态 | 用例 |\n|---|---|\n" + "\n".join(rows) + "\n\n## 边界说明\n\n" + "\n".join(notes) + "\n"
    md_path = output / "xunxu-test-report.md"; md_path.write_text(md, encoding="utf-8")
    return md_path, json_path

def main() -> int:
    parser = argparse.ArgumentParser(description="运行循序（xunxu）自动化测试并生成报告")
    parser.add_argument("--output", type=Path, default=SKILL / ".test-results")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    stream = io.StringIO(); runner = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordingResult)
    start = time.monotonic(); result = runner.run(suite); elapsed = time.monotonic() - start
    print(stream.getvalue()); md, js = write_report(args.output.resolve(), result, elapsed); print(f"Markdown report: {md}\nJSON report: {js}")
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__": raise SystemExit(main())

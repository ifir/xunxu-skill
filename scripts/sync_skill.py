#!/usr/bin/env python3
from __future__ import annotations

import argparse
import filecmp
import shutil
from pathlib import Path

EXCLUDES = {".git", ".DS_Store", ".test-results", "__pycache__"}

def files(root: Path) -> dict[str, Path]:
    return {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file() and not any(part in EXCLUDES for part in path.relative_to(root).parts)}

def sync(source: Path, destination: Path, check: bool) -> list[str]:
    source_files, destination_files = files(source), files(destination)
    changes = []
    for relative, src in source_files.items():
        dst = destination / relative
        if not dst.is_file() or not filecmp.cmp(src, dst, shallow=False):
            changes.append(f"update {relative}")
            if not check:
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    for relative, dst in destination_files.items():
        if relative == "README.md" or relative in source_files: continue
        changes.append(f"remove {relative}")
        if not check: dst.unlink()
    return changes

def main() -> int:
    parser = argparse.ArgumentParser(description="同步循序 Skill 的安装目录和 Git 仓库")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(); source = args.source.expanduser().resolve(); destination = args.destination.expanduser().resolve()
    if not (source / "SKILL.md").is_file(): parser.error(f"source 不是循序 Skill: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    changes = sync(source, destination, args.check)
    print("\n".join(changes) if changes else "in sync")
    return 1 if args.check and changes else 0

if __name__ == "__main__": raise SystemExit(main())

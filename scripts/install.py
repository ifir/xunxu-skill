#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

EXCLUDES = {".git", ".DS_Store", ".test-results", "__pycache__"}

def default_destination(product: str) -> Path | None:
    home = Path.home()
    if product == "codex":
        return home / ".codex" / "skills" / "xunxu"
    if product == "claude":
        return home / ".claude" / "skills" / "xunxu"
    return None

def install(source: Path, destination: Path, dry_run: bool = False) -> list[str]:
    if destination.exists():
        raise ValueError(f"目标已存在，未覆盖任何内容: {destination}")
    if destination == source or source in destination.parents:
        raise ValueError("安装目标不能位于源码目录内部")
    files = [p for p in source.rglob("*") if p.is_file() and not any(part in EXCLUDES for part in p.relative_to(source).parts)]
    actions = [f"copy {p.relative_to(source).as_posix()}" for p in files]
    if not dry_run:
        destination.mkdir(parents=True)
        for path in files:
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return actions

def main() -> int:
    parser = argparse.ArgumentParser(description="在 macOS 或 Windows 安装循序 Agent Skill")
    parser.add_argument("--product", choices=("codex", "claude", "generic"), required=True)
    parser.add_argument("--destination", type=Path, help="generic 必填；也可覆盖已知产品的默认目标")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    destination = (args.destination.expanduser() if args.destination else default_destination(args.product))
    if destination is None:
        parser.error("generic 安装必须提供 --destination")
    destination = destination.resolve()
    if not (source / "SKILL.md").is_file():
        parser.error(f"无效 Skill 源目录: {source}")
    try:
        actions = install(source, destination, args.dry_run)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"{'would install' if args.dry_run else 'installed'} {len(actions)} files -> {destination}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

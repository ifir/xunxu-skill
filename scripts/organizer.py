#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

FINGERPRINT_CHUNK = 64 * 1024

CATEGORIES = ("文档资料", "电子书", "图片", "视频", "音频", "字幕", "压缩包", "安装包", "字体", "代码", "其它")
EXTENSIONS = {
    "文档资料": "pdf doc docx docm dot dotx dotm xls xlsx xlsm xlsb xlt xltx xltm csv tsv ppt pptx pptm pot potx potm pps ppsx ppsm odt ods odp ott ots otp rtf txt text pages numbers key wps et dps hwp hwpx tex ltx",
    "电子书": "epub mobi azw azw3 kf8 fb2 fb3 djvu djv chm ibooks lit lrf pdb cbz cbr cb7 cbt opf ncx",
    "图片": "jpg jpeg jpe jfif png apng gif webp heic heif avif bmp dib tif tiff svg svgz ico icns jp2 j2k jpf jpx jxl tga pcx pnm pbm pgm ppm psd psb xcf kra ai eps dng cr2 cr3 nef nrw arw srf sr2 raf orf rw2 pef x3f erf mrw raw",
    "视频": "mp4 m4v mov qt mkv avi wmv flv f4v webm mpeg mpg mpe m2v m2ts mts 3gp 3g2 vob ogv rm rmvb asf divx dv",
    "音频": "mp3 m4a m4b aac wav wave flac ogg oga opus wma aif aiff aifc amr ape alac ac3 dts au snd ra mid midi caf cue",
    "字幕": "srt ass ssa vtt sub idx smi sami sbv ttml dfxp sup usf stl lrc",
    "压缩包": "zip zipx rar 7z tar gz gzip bz bz2 bzip2 xz zst zstd lz lz4 lzh lha tgz tbz tbz2 txz taz cab arj ace cpio xar",
    "安装包": "dmg pkg mpkg app exe msi msp mst msix msixbundle appx appxbundle apk xapk apks aab ipa deb rpm appimage snap flatpak flatpakref flatpakrepo run bin iso crx xpi vsix mobileconfig",
    "字体": "ttf otf ttc otc woff woff2 eot pfa pfb afm pfm bdf pcf fon fnt suit dfont",
    "代码": "c h cc cpp cxx c++ hh hpp hxx inl ipp tcc mm cs csx fs fsi fsx fsscript vb java kt kts scala sc groovy gvy gy gsh go rs swift dart zig nim nims d di v py pyw pyi pyx pxd pxi rb rake gemspec php phtml php3 php4 php5 phps pl pm pod t raku rakumod rakutest lua tcl tk awk sed sh bash zsh fish ksh csh ps1 psm1 psd1 bat cmd ex exs erl hrl gleam hs lhs elm ml mli re rei clj cljs cljc bb edn lisp lsp cl el scm ss rkt r rmd jl mlx sas do ado mata f for f77 f90 f95 f03 f08 fpp asm s inc cu cuh vhd vhdl sv svh vh sol move cairo vy html htm xhtml css scss sass less styl js mjs cjs jsx mts cts tsx vue svelte astro sql psql graphql gql proto thrift avsc fbs capnp prisma openapi jinja jinja2 j2 mustache hbs handlebars ejs pug jade liquid twig erb haml slim mk mak cmake gradle sbt tf tfvars tfstate hcl nomad nix dhall rego bicep pp ipynb qmd sln suo csproj fsproj vbproj vcxproj props targets proj pbxproj iml ipr iws code-workspace sublime-project sublime-workspace o obj a lib so dylib dll pdb bc ll wasm class jar war ear pyc pyo whl egg gem nupkg crate map patch diff http rest",
}
EXT_MAP = {f".{suffix}": category for category, values in EXTENSIONS.items() for suffix in values.split()}
DOC_AMBIGUOUS = {".md", ".markdown", ".rst", ".adoc", ".asciidoc"}
CONFIG_AMBIGUOUS = {".json", ".jsonc", ".json5", ".yaml", ".yml", ".toml", ".xml", ".ini", ".cfg", ".conf", ".properties", ".env", ".lock", ".rc"}
SPECIAL_CODE_NAMES = {"makefile", "cmakelists.txt", "dockerfile", "containerfile", "jenkinsfile", "vagrantfile", "gemfile", "rakefile", "procfile", "justfile", "tiltfile", "brewfile", "podfile", "cartfile", "build", "workspace", "module.bazel", "meson.build", "package.json", "tsconfig.json", "jsconfig.json", "pom.xml", "build.xml", "composer.json", "requirements.txt", "pipfile", "pyproject.toml", "cargo.toml", "cargo.lock", "go.mod", "go.sum", "docker-compose.yml", "compose.yml", "taskfile.yml", "taskfile.yaml", "editorconfig", "gitignore", "gitattributes", "gitmodules", "dockerignore", "npmrc", "yarnrc"}
GENERATED = {".organizer.plan.json", ".organizer.config.json", ".organizer.state.json", ".organizer.intent.json", ".organizer.analysis-required.json", ".organizer.dependencies.json", ".organizer.raw-analysis.json", "organizer.report.html", "organizer.change.md", "index-catch.md", "file2intent.md", "网页可视化目录.sh"}
INCOMPLETE = {".crdownload", ".part", ".download"}
WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
CODE_MARKERS = ("#!/", "import ", "function ", "class ", "const ", "let ", "def ", "package ", "dependencies", "devdependencies", "compileroptions", "<project", "services:", "apiversion:", "resource ")
MEANINGLESS_RE = re.compile(r"^(?:(?:img|dsc|pxl|vid|mov)[_-]?\d{3,}|(?:img|dsc|pxl|vid|mov|audio|recording|screenrecording)?[_-]?[0-9a-f]{12,}(?:[._@!%+-].*)?)$", re.I)

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default

def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def cache_path(root: Path, name: str) -> Path:
    return root / ".cache" / name

def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()

def read_head(path: Path, limit: int = 65536) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read(limit)
    except OSError:
        return b""

def text_head(path: Path) -> str:
    raw = read_head(path)
    if b"\x00" in raw:
        return ""
    return raw.decode("utf-8", errors="ignore")

def looks_like_code(path: Path) -> bool:
    sample = text_head(path).lower()
    return any(marker in sample for marker in CODE_MARKERS)

def classify(path: Path, allow_content: bool) -> tuple[str, str]:
    name, suffix = path.name.lower(), path.suffix.lower()
    if name in SPECIAL_CODE_NAMES or name.startswith(("dockerfile.", "makefile.")):
        return "代码", "特殊开发文件名"
    if suffix == ".ts":
        if allow_content:
            head = read_head(path, 1024)
            if len(head) > 188 and head[0] == 0x47 and head[188] == 0x47:
                return "视频", "MPEG-TS 文件特征"
            if looks_like_code(path):
                return "代码", "TypeScript 内容特征"
        return "其它", ".ts 类型无法仅凭名称判断"
    if suffix == ".m":
        if allow_content and any(marker in text_head(path) for marker in ("#import", "@interface", "@implementation")):
            return "代码", "Objective-C 内容特征"
        return "其它", ".m 类型无法仅凭名称判断"
    if suffix in DOC_AMBIGUOUS:
        if name.startswith(("readme", "changelog", "contributing", "license", "security")):
            return "代码", "开发文档名称"
        if allow_content and looks_like_code(path):
            return "代码", "开发文档内容特征"
        return "文档资料", "独立文本标记文档"
    if suffix in CONFIG_AMBIGUOUS:
        if allow_content and looks_like_code(path):
            return "代码", "开发配置内容特征"
        return "其它", "通用配置或数据文件"
    category = EXT_MAP.get(suffix)
    if category:
        return category, f"扩展名 {suffix}"
    if allow_content:
        head = read_head(path, 1024)
        if head.startswith(b"%PDF"):
            return "文档资料", "PDF 文件特征"
        if head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a")):
            return "图片", "图片文件特征"
        if text_head(path).startswith("#!"):
            return "代码", "脚本 shebang"
    return "其它", "未匹配已知类型"

def parse_bool(value: str | bool | None, name: str, required: bool = True) -> bool | None:
    if value is None and not required:
        return None
    if isinstance(value, bool):
        return value
    lowered = str(value or "").strip().lower()
    if lowered in {"yes", "y", "true", "1", "是", "允许"}:
        return True
    if lowered in {"no", "n", "false", "0", "否", "不允许"}:
        return False
    raise ValueError(f"{name} 必须是 yes 或 no")

def private_parts(value: str | None) -> list[str]:
    if not value or value.strip().lower() in {"无", "none", "no"}:
        return []
    return sorted({part.strip() for part in re.split(r"[、,，]", value) if part.strip()}, key=str.casefold)

def save_config(root: Path, allow_rename: bool, include_existing: bool, trust: bool | None, private: list[str]) -> dict[str, Any]:
    config = {"version": 2, "created_at": now_iso(), "allow_rename": allow_rename, "include_existing": include_existing, "trust_meaningful_names": trust if allow_rename else None, "private_names": private}
    write_json(cache_path(root, ".organizer.config.json"), config)
    return config

def config_digest(config: dict[str, Any]) -> str:
    raw = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()

def is_private(path: Path, root: Path, private: list[str]) -> bool:
    needles = [unicodedata.normalize("NFKC", item).casefold() for item in private]
    for part in path.relative_to(root).parts:
        normalized = unicodedata.normalize("NFKC", part).casefold()
        if any(needle in normalized for needle in needles):
            return True
    return False

def is_meaningful(path: Path) -> bool:
    stem = unicodedata.normalize("NFKC", path.stem).strip(" ._-()[]")
    compact = re.sub(r"[\W_]+", "", stem, flags=re.UNICODE)
    if len(compact) < 4 or MEANINGLESS_RE.fullmatch(stem):
        return False
    alpha = sum(ch.isalpha() or "\u3400" <= ch <= "\u9fff" for ch in compact)
    digits = sum(ch.isdigit() for ch in compact)
    return alpha >= 2 and alpha >= digits / 2

def fingerprint(path: Path, stat: os.stat_result) -> str:
    digest = hashlib.sha256()
    digest.update(f"v2:{stat.st_size}:{stat.st_mtime_ns}:".encode())
    try:
        with path.open("rb") as handle:
            digest.update(handle.read(FINGERPRINT_CHUNK))
            if stat.st_size > FINGERPRINT_CHUNK:
                handle.seek(max(0, stat.st_size - FINGERPRINT_CHUNK))
                digest.update(handle.read(FINGERPRINT_CHUNK))
    except OSError:
        digest.update(b"unreadable")
    return digest.hexdigest()

def folder_fingerprint(path: Path, root: Path) -> str:
    # Folder identities are intentionally path-based. Directory inode/file-index
    # behavior differs between APFS, NTFS and network drives.
    relative_name = unicodedata.normalize("NFC", relative(path, root)).casefold()
    return hashlib.sha256(f"dir-v2:{relative_name}".encode("utf-8")).hexdigest()

def collect_files(root: Path, include_existing: bool, private: list[str]) -> tuple[list[Path], list[Path], list[dict[str, str]]]:
    files, folders, skipped = [], [], []
    if not include_existing:
        candidates: Iterable[Path] = root.iterdir()
    else:
        found: list[Path] = []
        for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            kept = []
            for dirname in dirnames:
                candidate = current_path / dirname
                if dirname.startswith("."):
                    continue
                if candidate.is_symlink():
                    skipped.append({"source": relative(candidate, root), "reason": "符号链接"}); continue
                if is_private(candidate, root, private):
                    skipped.append({"source": relative(candidate, root), "reason": "私密文件夹：不遍历、不读取"}); continue
                kept.append(dirname)
                found.append(candidate)
            dirnames[:] = kept
            found.extend(current_path / filename for filename in filenames)
        candidates = found
    for path in sorted(candidates, key=lambda p: p.as_posix().casefold()):
        rel = relative(path, root)
        if path.name in GENERATED:
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            if path.parent == root:
                skipped.append({"source": rel, "reason": "隐藏项"})
            continue
        if not include_existing and path.name in CATEGORIES:
            continue
        if path.is_symlink():
            skipped.append({"source": rel, "reason": "符号链接"}); continue
        if is_private(path, root, private):
            if path.is_dir():
                skipped.append({"source": rel, "reason": "私密文件夹：不遍历、不读取"})
            elif path.is_file():
                files.append(path)
            continue
        if path.is_file():
            files.append(path)
        elif path.is_dir() and path.parent == root and path.name not in CATEGORIES:
            folders.append(path)
        elif not include_existing and path.parent == root:
            skipped.append({"source": rel, "reason": "已有目录（配置未允许整理）"})
    return files, folders, skipped

def clipped_text(value: str, limit: int) -> str:
    # The strict Windows component rules are also valid on macOS, which keeps
    # generated names portable when a directory is later synchronized.
    cleaned = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "-", unicodedata.normalize("NFKC", value)).strip(" .-_")
    cleaned = cleaned[:limit].rstrip(" .-_")
    if cleaned.casefold() in WINDOWS_RESERVED:
        cleaned = f"{cleaned}-文件"[:limit].rstrip(" .-_")
    return cleaned

def sanitized_name(original: str, suggested: str, mtime_ns: int) -> str:
    suffix = Path(original).suffix
    summary = clipped_text(Path(suggested).stem, 15)
    if not summary:
        return original
    date = datetime.fromtimestamp(mtime_ns / 1_000_000_000).strftime("%y%m%d")
    return f"{date}-{summary}{suffix}"

def intent_group(value: Any) -> str:
    return clipped_text(str(value or ""), 8)

def write_index(root: Path, intent_data: dict[str, Any], path_lookup: dict[str, str] | None = None) -> Path:
    cache_dir = root / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "file2intent.md"
    rows = []
    lookup = path_lookup or {}
    for fp, item in sorted(intent_data.get("items", {}).items()):
        if not isinstance(item, dict):
            continue
        file_path = lookup.get(fp) or str(item.get("path") or item.get("source") or "")
        values = [
            fp[:16], file_path, str(item.get("modified_at") or ""), str(item.get("intent") or ""),
            intent_group(item.get("intent_group")), str(item.get("method") or ""),
            str(item.get("confidence") or ""), str(item.get("analyzed_at") or ""),
        ]
        rows.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in values) + " |")
    content = "# 文件内容意图索引缓存\n\n> 本索引用于避免对未变化文件重复读取或媒体识别；不会保存原始内容。\n\n| 缓存指纹 | 当前路径 | 最新修改时间 | 内容意图摘要 | 通用意图 | 识别方式 | 置信度 | 识别时间 |\n|---|---|---|---|---|---|---|---|\n"
    path.write_text(content + ("\n".join(rows) if rows else "| - | - | - | 暂无缓存 | - | - | - | - |") + "\n", encoding="utf-8")
    return path

def retire_superseded_cache(intent_data: dict[str, Any]) -> None:
    items = intent_data.get("items", {})
    if not isinstance(items, dict):
        return
    superseded = {str(item.get("supersedes")) for item in items.values() if isinstance(item, dict) and item.get("supersedes")}
    for fingerprint_value in superseded:
        items.pop(fingerprint_value, None)

def make_plan(root: Path, plan_path: Path, min_age: int) -> dict[str, Any]:
    config = load_json(cache_path(root, ".organizer.config.json"), None)
    if not isinstance(config, dict):
        raise ValueError("请先运行 configure 收集本次整理配置")
    allow_rename, include_existing = bool(config.get("allow_rename")), bool(config.get("include_existing"))
    trust = bool(config.get("trust_meaningful_names")) if allow_rename else False
    private = [str(item) for item in config.get("private_names", [])]
    intent = load_json(cache_path(root, ".organizer.intent.json"), {"items": {}}).get("items", {})
    state = load_json(cache_path(root, ".organizer.state.json"), {"items": {}}).get("items", {})
    state_by_path: dict[str, tuple[str, dict[str, Any]]] = {}
    if isinstance(state, dict):
        for state_fp, record in state.items():
            if isinstance(record, dict) and record.get("path"):
                state_by_path[str(record["path"])] = (str(state_fp), record)
    current = datetime.now().astimezone()
    files, folders, skipped = collect_files(root, include_existing, private)
    moves, folder_renames, analysis = [], [], []
    for source in files:
        rel_source = relative(source, root)
        try:
            stat = source.stat()
        except OSError:
            skipped.append({"source": rel_source, "reason": "无法读取文件状态"}); continue
        private_item = is_private(source, root, private)
        if source.suffix.lower() in INCOMPLETE:
            skipped.append({"source": rel_source, "reason": "未完成下载"}); continue
        if current.timestamp() - stat.st_mtime < min_age:
            skipped.append({"source": rel_source, "reason": f"最近 {min_age} 秒内仍可能写入"}); continue
        fp = fingerprint(source, stat)
        within_category = bool(source.relative_to(root).parts and source.relative_to(root).parts[0] in CATEGORIES)
        matching_state = state.get(fp) if isinstance(state, dict) else None
        previous_state = state_by_path.get(rel_source)
        previous_fp = previous_state[0] if previous_state and previous_state[0] != fp else ""
        cache_changed = bool(previous_state and not matching_state and (previous_state[1].get("size") != stat.st_size or previous_state[1].get("mtime_ns") != stat.st_mtime_ns))
        already = bool(matching_state) or (within_category and not cache_changed)
        category, reason = classify(source, allow_content=allow_rename and not private_item and not already)
        cached = intent.get(fp) if isinstance(intent, dict) else None
        needs_analysis = allow_rename and not already and category not in {"安装包", "压缩包"} and (cache_changed or private_item or (not trust) or (not is_meaningful(source)))
        suggested, group = "", ""
        if isinstance(cached, dict):
            if cached.get("confidence") in {"high", "medium"}:
                suggested = str(cached.get("suggested_name") or "")
                group = intent_group(cached.get("intent_group"))
                if cached.get("category") in CATEGORIES:
                    category, reason = cached["category"], f"意图识别：{cached.get('intent', '')}"
            needs_analysis = False
        if needs_analysis:
            if private_item:
                analysis.append({"kind": "file", "source": rel_source, "fingerprint": fp, "media_category": category, "method_required": "filename-only", "name_hint": source.stem, "analysis_depth": "filename-only", "reason": "私密文件：只允许依据文件名识别意图，禁止读取内容"})
            else:
                meaningful = is_meaningful(source)
                if cache_changed:
                    reason_text, depth = "缓存文件已修改：优先比较旧证据差异并重新识别意图", "diff"
                else:
                    reason_text = "名称不足以可靠表达意图" if trust else ("不信任名称：以名称作为待验证线索，先做定向轻量读取" if meaningful else "不信任名称：名称无有效线索，执行标准内容识别")
                    depth = "targeted" if (not trust and meaningful) else "full"
                analysis.append({"kind": "file", "source": rel_source, "fingerprint": fp, "previous_fingerprint": previous_fp, "cache_status": "modified" if cache_changed else "new", "media_category": category, "method_required": "content", "name_hint": source.stem if meaningful else "", "analysis_depth": depth, "reason": reason_text})
        new_name = sanitized_name(source.name, suggested, stat.st_mtime_ns) if suggested else source.name
        destination = root / category / group / new_name if group else root / category / new_name
        if source.resolve(strict=False) == destination.resolve(strict=False):
            skipped.append({"source": rel_source, "reason": "已处于正确分类且无需改名"}); continue
        status = "analysis-required" if needs_analysis else ("conflict" if destination.exists() else "planned")
        moves.append({"source": rel_source, "destination": relative(destination, root), "original_name": source.name, "new_name": new_name, "renamed": source.name != new_name, "intent_group": group, "category": category, "reason": reason, "status": status, "private": private_item, "already_organized": already, "fingerprint": fp, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")})
    if allow_rename and include_existing:
        for folder in folders:
            stat = folder.stat()
            fp = folder_fingerprint(folder, root)
            cached = intent.get(fp) if isinstance(intent, dict) else None
            needs_analysis = (not trust) or (not is_meaningful(folder))
            suggested = ""
            if isinstance(cached, dict):
                if cached.get("confidence") in {"high", "medium"}:
                    suggested = str(cached.get("suggested_name") or "")
                needs_analysis = False
            if needs_analysis:
                meaningful = is_meaningful(folder)
                analysis.append({"kind": "folder", "source": relative(folder, root), "fingerprint": fp, "name_hint": folder.name if meaningful else "", "analysis_depth": "targeted" if (not trust and meaningful) else "full", "reason": "文件夹名称不足以可靠表达意图" if trust else ("不信任名称：用名称作为线索并抽样验证子项" if meaningful else "不信任名称：抽样识别非私密子项")})
            new_name = clipped_text(str(suggested), 8) if suggested else folder.name
            destination = root / new_name
            if folder == destination:
                continue
            status = "analysis-required" if needs_analysis else ("conflict" if destination.exists() else "planned")
            folder_renames.append({"source": relative(folder, root), "destination": relative(destination, root), "original_name": folder.name, "new_name": new_name, "renamed": True, "reason": f"文件夹意图：{cached.get('intent', '')}" if isinstance(cached, dict) else "等待文件夹意图识别", "status": status, "fingerprint": fp})
    analysis_paths = [root / item["source"] for item in analysis if item.get("kind") == "file" and item.get("method_required") == "content"]
    if analysis_paths:
        from check_capabilities import assess_plan
        dependency_assessment = assess_plan(analysis_paths)
    else:
        dependency_assessment = {"status": "not-needed", "analysis_files": 0, "requirements_file": "requirements.txt", "requirements_status": "not-needed", "required_packages": [], "conditional_packages": [], "authorization_required": False, "reasons": ["本次没有需要内容识别的文件"]}
    data = {"version": 3, "root": str(root), "created_at": current.isoformat(timespec="seconds"), "config_digest": config_digest(config), "config": config, "min_age_seconds": min_age, "dependency_assessment": dependency_assessment, "analysis_required": analysis, "moves": moves, "folder_renames": folder_renames, "skipped": skipped}
    write_json(plan_path, data)
    write_json(cache_path(root, ".organizer.analysis-required.json"), {"version": 1, "created_at": data["created_at"], "root": str(root), "items": analysis})
    write_json(cache_path(root, ".organizer.dependencies.json"), {"version": 1, "created_at": data["created_at"], "root": str(root), **dependency_assessment})
    return data

def safe_path(root: Path, value: str) -> Path:
    candidate = (root / value).resolve(strict=False)
    if candidate == root or root not in candidate.parents:
        raise ValueError(f"路径越界: {value}")
    return candidate

def append_log(root: Path, run_time: str, config: dict[str, Any], results: list[dict[str, str]]) -> Path:
    path = root / "organizer.change.md"
    fresh = not path.exists()
    with path.open("a", encoding="utf-8") as handle:
        if fresh:
            handle.write("# 文件整理变更记录\n\n> 本文件仅追加记录；整理器不会删除文件。\n")
        private_label = "、".join(config.get("private_names", [])) or "无"
        handle.write(f"\n## {run_time}\n\n配置：允许改名={config.get('allow_rename')}；整理已有目录={config.get('include_existing')}；信任有意义名称={config.get('trust_meaningful_names')}；私密名称={private_label}\n\n")
        handle.write("| 状态 | 原位置 | 目标位置 | 名称变化 | 分类依据 |\n|---|---|---|---|---|\n")
        for item in results:
            values = [str(item.get(k, "")).replace("|", "\\|").replace("\n", " ") for k in ("status", "source", "destination", "rename", "reason")]
            handle.write("| " + " | ".join(values) + " |\n")
    return path

def listed_files(root: Path, category: str) -> list[Path]:
    folder = root / category
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.rglob("*") if p.is_file() and not p.is_symlink() and not any(part.startswith(".") for part in p.relative_to(folder).parts)), key=lambda p: p.as_posix().casefold())

def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB": return f"{int(value)} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"

def report_metadata(root: Path, results: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    output = {}
    state = load_json(cache_path(root, ".organizer.state.json"), {"items": {}}).get("items", {})
    for item in state.values() if isinstance(state, dict) else []:
        if isinstance(item, dict) and item.get("path"):
            output[str(item["path"])] = {"original": str(item.get("original_name") or Path(str(item["path"])).name), "current": Path(str(item["path"])).name}
    for item in results:
        destination = item.get("destination", "")
        if destination and item.get("status", "").startswith("已"):
            output[destination] = {"original": Path(item.get("source", "")).name, "current": Path(destination).name}
    return output

def split_markdown_row(line: str) -> list[str]:
    values, current, escaped = [], [], False
    for character in line.strip().strip("|"):
        if escaped:
            current.append(character); escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            values.append("".join(current).strip()); current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    values.append("".join(current).strip())
    return values

def read_change_history(root: Path) -> list[dict[str, Any]]:
    try:
        lines = (root / "organizer.change.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    runs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_table = False
    for line in lines:
        if line.startswith("## "):
            current = {"run_at": line[3:].strip(), "config": "", "items": []}; runs.append(current); in_table = False
        elif current is not None and line.startswith("配置："):
            current["config"] = line.strip()
        elif current is not None and line.startswith("| 状态 |"):
            in_table = True
        elif current is not None and in_table and line.startswith("|---"):
            continue
        elif current is not None and in_table and line.startswith("|"):
            values = split_markdown_row(line)
            if len(values) >= 5:
                current["items"].append(dict(zip(("status", "source", "destination", "rename", "reason"), values[:5])))
        elif current is not None and in_table and line.strip():
            in_table = False
    return [run for run in runs if run["items"]]

def write_report(root: Path, run_time: str, results: list[dict[str, str]]) -> Path:
    groups = [(category, listed_files(root, category)) for category in CATEGORIES]
    groups = [(category, files) for category, files in groups if files]
    metadata, nodes = report_metadata(root, results), []
    for category, files in groups:
        items = []
        for path in files:
            rel = relative(path, root); details = metadata.get(rel, {}); stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")
            items.append(f'''<li><button class="file-button" type="button" data-original="{html.escape(details.get('original', path.name), quote=True)}" data-current="{html.escape(path.name, quote=True)}" data-modified="{html.escape(modified, quote=True)}" data-size="{html.escape(format_size(stat.st_size), quote=True)}" data-bytes="{stat.st_size}" data-location="{html.escape(rel, quote=True)}">{html.escape(relative(path, root / category))}</button></li>''')
        nodes.append(f'<details class="folder"><summary><span>{html.escape(category)}</span><b>{len(files)}</b></summary><ul>{"".join(items)}</ul></details>')
    history = read_change_history(root); history_nodes = []
    for index, run in enumerate(reversed(history)):
        rows = []
        for item in run["items"]:
            cells = "".join(f"<td>{html.escape(str(item[key]))}</td>" for key in ("status", "source", "destination", "rename", "reason"))
            rows.append(f"<tr>{cells}</tr>")
        config = f'<p class="run-config">{html.escape(str(run.get("config", "")))}</p>' if run.get("config") else ""
        opened = " open" if index == 0 else ""
        history_nodes.append(f'<details class="history-run"{opened}><summary><span>{html.escape(str(run["run_at"]))}</span><b>{len(run["items"])}</b></summary>{config}<div class="table-wrap"><table><thead><tr><th>状态</th><th>原位置</th><th>目标位置</th><th>名称变化</th><th>分类依据</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></details>')
    history_html = "".join(history_nodes) or "<p>暂无历史整理记录</p>"
    historical_items = sum(len(run["items"]) for run in history)
    total = sum(len(files) for _, files in groups)
    style = """*{box-sizing:border-box}:root{color-scheme:light dark;--bg:#f7f8fa;--panel:#fff;--text:#17202a;--muted:#68707c;--line:#e5e8ec;--accent:#315efb;--soft:#eef2ff}@media(prefers-color-scheme:dark){:root{--bg:#111318;--panel:#1a1d24;--text:#eef1f5;--muted:#a4abb6;--line:#30343c;--accent:#8fa9ff;--soft:#232b45}}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif}main{max-width:980px;margin:auto;padding:28px 18px 48px}header{display:flex;justify-content:space-between;gap:20px;align-items:end}h1{font-size:24px;margin:0 0 4px}p{margin:0;color:var(--muted)}.stats{display:flex;gap:18px}.stat b{display:block;font-size:20px}.stat span{color:var(--muted)}.tree{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin:22px 0}details{background:var(--panel);border:1px solid var(--line);border-radius:8px}summary{display:flex;align-items:center;padding:11px 12px;cursor:pointer;list-style:none}summary::-webkit-details-marker{display:none}summary:before{content:\"›\";margin-right:8px;color:var(--accent)}details[open] summary:before{transform:rotate(90deg)}summary b{margin-left:auto;background:var(--soft);color:var(--accent);border-radius:12px;padding:1px 8px}ul{list-style:none;margin:0;padding:0 12px 10px}.folder li{border-top:1px solid var(--line)}.file-button{display:block;width:100%;padding:8px 2px;border:0;background:transparent;color:var(--text);font:inherit;text-align:left;word-break:break-all;cursor:pointer}.file-button:hover,.file-button:focus{color:var(--accent);text-decoration:underline}.changes summary{font-weight:600}.changes ul{padding:0 12px 12px}.changes li{display:grid;grid-template-columns:1fr auto 1fr auto;gap:8px;border-top:1px solid var(--line);padding:8px 2px;align-items:center}.changes strong{color:var(--accent)}.changes em{font-style:normal;color:var(--muted);font-size:12px}dialog{width:min(520px,calc(100% - 32px));border:1px solid var(--line);border-radius:12px;background:var(--panel);color:var(--text);padding:0;box-shadow:0 18px 60px #0004}dialog::backdrop{background:#0007}.dialog-head{display:flex;align-items:center;padding:15px 18px;border-bottom:1px solid var(--line)}.dialog-head h2{font-size:17px;margin:0}.close{margin-left:auto;border:0;background:transparent;color:var(--muted);font-size:22px;cursor:pointer}.facts{display:grid;grid-template-columns:100px 1fr;margin:0;padding:10px 18px 18px}.facts dt,.facts dd{margin:0;padding:7px 0;border-bottom:1px solid var(--line)}.facts dt{color:var(--muted)}.facts dd{word-break:break-all}footer{margin-top:14px;color:var(--muted);font-size:12px}@media(max-width:640px){header{display:block}.stats{margin-top:14px}.changes li{grid-template-columns:1fr auto 1fr}.changes em{grid-column:1/-1}.facts{grid-template-columns:86px 1fr}}"""
    modal = '''<dialog id="file-detail"><div class="dialog-head"><h2>文件详情</h2><button class="close" id="detail-close" type="button" aria-label="关闭">×</button></div><dl class="facts"><dt>原始文件名</dt><dd id="detail-original"></dd><dt>当前文件名</dt><dd id="detail-current"></dd><dt>修改时间</dt><dd id="detail-modified"></dd><dt>文件大小</dt><dd><span id="detail-size"></span>（<span id="detail-bytes"></span> 字节）</dd><dt>当前位置</dt><dd id="detail-location"></dd></dl></dialog>'''
    script = '''<script>const d=document.getElementById("file-detail");document.addEventListener("click",e=>{const b=e.target.closest(".file-button");if(!b)return;for(const k of ["original","current","modified","size","bytes","location"]){document.getElementById("detail-"+k).textContent=b.dataset[k]||"-"}d.showModal()});document.getElementById("detail-close").addEventListener("click",()=>d.close());d.addEventListener("click",e=>{if(e.target===d)d.close()});</script>'''
    history_style = """<style>main{max-width:1180px}h2{font-size:18px;margin:26px 0 10px}.tree{margin:12px 0}.history{display:grid;gap:10px}.history-run summary{font-weight:600}.run-config{padding:0 12px 10px;font-size:12px}.table-wrap{overflow:auto;border-top:1px solid var(--line)}table{width:100%;border-collapse:collapse;min-width:900px;font-size:12px}th,td{padding:8px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);word-break:break-word}th{color:var(--muted);font-weight:600;background:var(--soft)}tbody tr:last-child td{border-bottom:0}</style>"""
    document = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>文件整理报告</title><style>{style}</style>{history_style}</head><body><main><header><div><h1>文件整理报告</h1><p>{html.escape(str(root))}<br>报告刷新：{html.escape(run_time)}</p></div><div class="stats"><div class="stat"><b>{len(history)}</b><span>整理批次</span></div><div class="stat"><b>{historical_items}</b><span>历史变更</span></div><div class="stat"><b>{total}</b><span>已归类</span></div></div></header><h2>当前目录</h2><div class="tree">{"".join(nodes) or '<p>暂无已归类文件</p>'}</div><h2>全部历史变更</h2><div class="history">{history_html}</div><footer>历史明细来自只追加的 organizer.change.md。点击当前目录中的文件名可查看原始名称、修改时间与大小；页面不会打开文件或文件夹。</footer></main>{modal}{script}</body></html>'''
    path = root / "organizer.report.html"; path.write_text(document, encoding="utf-8"); return path

def validate_mapping(root: Path, item: dict[str, Any], config: dict[str, Any]) -> tuple[Path, Path]:
    source_rel, destination_rel = Path(item["source"]), Path(item["destination"])
    category = item.get("category")
    if category not in CATEGORIES:
        raise ValueError("计划目标不属于固定一级分类")
    allowed_parents = {Path(category)}
    group = intent_group(item.get("intent_group"))
    if group:
        allowed_parents.add(Path(category) / group)
    if destination_rel.parent not in allowed_parents:
        raise ValueError("计划目标不是固定分类目录或合法意图子目录")
    if source_rel.name in GENERATED or destination_rel.name in GENERATED:
        raise ValueError("计划包含整理器生成文件")
    if not config.get("include_existing") and source_rel.parent != Path("."):
        raise ValueError("配置不允许整理已有目录")
    if not config.get("allow_rename") and source_rel.name != destination_rel.name:
        raise ValueError("配置不允许重命名")
    return safe_path(root, str(source_rel)), safe_path(root, str(destination_rel))

def apply_folder_renames(root: Path, data: dict[str, Any], config: dict[str, Any], results: list[dict[str, str]]) -> bool:
    if not (config.get("allow_rename") and config.get("include_existing")):
        return False
    for item in data.get("folder_renames", []):
        result = {"source": item["source"], "destination": item["destination"], "reason": item["reason"], "rename": f"{item['original_name']} → {item['new_name']}", "status": ""}
        try:
            source_rel, destination_rel = Path(item["source"]), Path(item["destination"])
            if source_rel.parent != Path(".") or destination_rel.parent != Path(".") or source_rel.name in CATEGORIES or destination_rel.name in CATEGORIES:
                raise ValueError("文件夹重命名范围无效")
            source, destination = safe_path(root, str(source_rel)), safe_path(root, str(destination_rel))
            if item.get("status") != "planned":
                result["status"] = "跳过：预演状态不可执行"
            elif source.is_symlink() or not source.is_dir():
                result["status"] = "跳过：来源不存在或不是普通文件夹"
            elif destination.exists():
                result["status"] = "跳过：目标同名文件夹已存在"
            else:
                os.rename(str(source), str(destination))
                result["status"] = "已重命名文件夹"
        except (OSError, ValueError) as exc:
            result["status"] = f"失败：{exc}"
            results.append(result)
            return True
        results.append(result)
    return False

def apply_plan(root: Path, plan_path: Path) -> dict[str, Any]:
    data = load_json(plan_path, None)
    config = load_json(cache_path(root, ".organizer.config.json"), None)
    if not isinstance(data, dict) or not isinstance(config, dict):
        raise ValueError("缺少有效计划或本次配置")
    if Path(data.get("root", "")).resolve() != root:
        raise ValueError("计划根目录与当前根目录不一致")
    if data.get("config_digest") != config_digest(config):
        raise ValueError("配置在预演后发生变化，请重新生成计划")
    if data.get("analysis_required"):
        raise ValueError("仍有待完成的意图识别，不允许执行")
    results, failed = [], False
    state_path = cache_path(root, ".organizer.state.json")
    state = load_json(state_path, {"version": 1, "items": {}})
    intent_data = load_json(cache_path(root, ".organizer.intent.json"), {"version": 1, "items": {}})
    state.setdefault("items", {})
    intent_data.setdefault("items", {})
    retire_superseded_cache(intent_data)
    path_lookup: dict[str, str] = {}
    root_device = root.stat().st_dev
    for item in data.get("moves", []):
        rename = f"{item.get('original_name', '')} → {item.get('new_name', '')}" if item.get("renamed") else "未改名"
        result = {"source": item["source"], "destination": item["destination"], "reason": item["reason"], "rename": rename, "status": ""}
        try:
            source, destination = validate_mapping(root, item, config)
            if item.get("status") != "planned":
                result["status"] = "跳过：预演状态不可执行"
            elif source.is_symlink() or not source.is_file():
                result["status"] = "跳过：来源不存在或不是普通文件"
            elif destination.exists():
                result["status"] = "跳过：目标同名文件已存在"
            else:
                stat = source.stat()
                if stat.st_size != item["size"] or stat.st_mtime_ns != item["mtime_ns"]:
                    result["status"] = "跳过：文件在预演后发生变化"
                elif stat.st_dev != root_device:
                    result["status"], failed = "失败：无法保证仅使用同盘移动", True
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(str(source), str(destination))
                    result["status"] = "已移动"
                    new_stat = destination.stat()
                    new_fp = fingerprint(destination, new_stat)
                    record = {"path": relative(destination, root), "original_name": item.get("original_name") or Path(item["source"]).name, "current_name": destination.name, "organized_at": now_iso(), "category": item["category"], "source_fingerprint": item["fingerprint"], "size": new_stat.st_size, "mtime_ns": new_stat.st_mtime_ns}
                    state["items"][new_fp] = record
                    state["items"][item["fingerprint"]] = record
                    path_lookup[item["fingerprint"]] = relative(destination, root)
                    path_lookup[new_fp] = relative(destination, root)
                    if item["fingerprint"] in intent_data["items"]:
                        cached_item = intent_data["items"][item["fingerprint"]]
                        cached_item["path"] = relative(destination, root)
                        cached_item["modified_at"] = datetime.fromtimestamp(new_stat.st_mtime).astimezone().isoformat(timespec="seconds")
                        intent_data["items"][new_fp] = dict(cached_item)
        except (OSError, ValueError) as exc:
            result["status"], failed = f"失败：{exc}", True
        results.append(result)
        if failed:
            break
    if not failed:
        failed = apply_folder_renames(root, data, config, results)
    run_time = now_iso()
    state["updated_at"] = run_time
    write_json(state_path, state)
    write_json(cache_path(root, ".organizer.intent.json"), intent_data)
    index_path = write_index(root, intent_data, path_lookup)
    log_path = append_log(root, run_time, config, results)
    report_path = write_report(root, run_time, results)
    return {"run_at": run_time, "results": results, "log": str(log_path), "report": str(report_path), "state": str(state_path), "index": str(index_path), "stopped_on_failure": failed}

def main() -> int:
    parser = argparse.ArgumentParser(description="按配置预演并安全整理下载目录")
    sub = parser.add_subparsers(dest="command", required=True)
    configure = sub.add_parser("configure", help="保存本次整理配置")
    configure.add_argument("--root", type=Path, required=True)
    configure.add_argument("--allow-rename", required=True)
    configure.add_argument("--include-existing", required=True)
    configure.add_argument("--trust-meaningful-names")
    configure.add_argument("--private-names", default="")
    preview = sub.add_parser("plan", help="生成预演，不移动文件")
    preview.add_argument("--root", type=Path, required=True)
    preview.add_argument("--plan-file", type=Path)
    preview.add_argument("--min-age-seconds", type=int, default=600)
    execute = sub.add_parser("apply", help="执行已确认计划")
    execute.add_argument("--root", type=Path, required=True)
    execute.add_argument("--plan-file", type=Path)
    index_cmd = sub.add_parser("index", help="从机器缓存刷新 .cache/file2intent.md")
    index_cmd.add_argument("--root", type=Path, required=True)
    report_cmd = sub.add_parser("report", help="从当前目录和完整变更日志刷新静态 HTML 报告")
    report_cmd.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"目标不是目录: {root}")
    try:
        if args.command == "configure":
            allow = bool(parse_bool(args.allow_rename, "allow-rename"))
            include = bool(parse_bool(args.include_existing, "include-existing"))
            trust = parse_bool(args.trust_meaningful_names, "trust-meaningful-names", required=False)
            if allow and trust is None:
                parser.error("允许重命名时必须回答 trust-meaningful-names")
            result = save_config(root, allow, include, trust, private_parts(args.private_names))
        elif args.command == "index":
            intent_data = load_json(cache_path(root, ".organizer.intent.json"), {"version": 1, "items": {}})
            result = {"index": str(write_index(root, intent_data))}
        elif args.command == "report":
            history = read_change_history(root)
            result = {"report": str(write_report(root, now_iso(), [])), "runs": len(history), "changes": sum(len(run["items"]) for run in history)}
        else:
            plan_path = (args.plan_file or cache_path(root, ".organizer.plan.json")).expanduser().resolve()
            if args.command == "plan":
                result = make_plan(root, plan_path, max(0, args.min_age_seconds))
            else:
                if not plan_path.is_file():
                    parser.error(f"找不到计划文件: {plan_path}")
                result = apply_plan(root, plan_path)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

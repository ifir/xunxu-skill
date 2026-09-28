#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from common import result_record

TEXT_SUFFIXES = {
    ".txt", ".text", ".md", ".markdown", ".rst", ".adoc",
    ".csv", ".tsv", ".json", ".jsonc", ".yaml", ".yml",
    ".toml", ".xml", ".ini", ".cfg", ".conf", ".log",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go",
    ".rs", ".c", ".h", ".cpp", ".hpp", ".sh", ".ps1",
    ".bat", ".cmd", ".sql", ".html", ".css", ".rtf",
}

def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")

def _clean(text: str, limit: int) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]

def _sample_indexes(total: int, count: int) -> list[int]:
    if total <= 0 or count <= 0:
        return []
    if total <= count:
        return list(range(total))
    if count == 1:
        return [0]
    return sorted({round(index * (total - 1) / (count - 1)) for index in range(count)})

def _balanced_sample(parts: list[tuple[str, str]], limit: int) -> str:
    """Build bounded evidence from the beginning, middle and end."""
    usable = [(label, text.strip()) for label, text in parts if text and text.strip()]
    if not usable:
        return ""
    labels_size = sum(len(label) + 4 for label, _ in usable)
    separators_size = max(0, len(usable) - 1) * 2
    budget = max(1, (limit - labels_size - separators_size) // len(usable))
    sampled = []
    for label, text in usable:
        if len(text) <= budget:
            excerpt = text
        else:
            separator_size = len("\n…\n") * 2
            third = max(1, (budget - separator_size) // 3)
            middle = max(0, len(text) // 2 - third // 2)
            excerpt = text[:third] + "\n…\n" + text[middle:middle + third] + "\n…\n" + text[-third:]
        sampled.append(f"[{label}]\n{excerpt}")
    return _clean("\n\n".join(sampled), limit)

def _sample_text_file(path: Path, limit: int) -> tuple[str, bool]:
    size = path.stat().st_size
    read_size = max(4096, limit * 2)
    if size <= read_size * 2:
        raw = path.read_bytes()
        return _clean(_decode(raw), limit), len(raw) > limit
    offsets = (0, max(0, size // 2 - read_size // 2), max(0, size - read_size))
    parts = []
    with path.open("rb") as handle:
        for label, offset in zip(("开头", "中间", "结尾"), offsets):
            handle.seek(offset); parts.append((label, _decode(handle.read(read_size))))
    return _balanced_sample(parts, limit), True

def _xml_text(data: bytes) -> str:
    root = ET.fromstring(data)
    return "\n".join(value.strip() for value in root.itertext() if value.strip())

def _zip_xml(path: Path, prefixes: tuple[str, ...], limit: int, extensions: tuple[str, ...] = (".xml",)) -> tuple[str, bool]:
    with zipfile.ZipFile(path) as archive:
        members = []
        for name in archive.namelist():
            normalized = name.replace("\\", "/")
            if normalized.lower().endswith(extensions) and normalized.startswith(prefixes):
                members.append(name)
        members.sort()
        indexes = _sample_indexes(len(members), min(6, len(members)))
        parts: list[tuple[str, str]] = []
        for position, index in enumerate(indexes):
            name = members[index]
            try:
                text = _xml_text(archive.read(name))
            except (ET.ParseError, KeyError, OSError):
                continue
            label = f"{position + 1}/{len(indexes)} {Path(name).name}"
            parts.append((label, text))
    return _balanced_sample(parts, limit), len(members) > len(indexes) or any(len(text) > limit // max(1, len(parts)) for _, text in parts)

def _xlsx_text(path: Path, limit: int, max_rows: int = 20, max_columns: int = 12) -> tuple[str, bool]:
    """Return a compact, intent-oriented workbook preview without Office."""
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root:
                shared.append("".join(item.itertext()).strip())
        sheet_names: list[str] = []
        if "xl/workbook.xml" in names:
            root = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet_names = [node.attrib.get("name", "") for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "sheet"]
        output = ["工作表：" + "、".join(filter(None, sheet_names))] if sheet_names else []
        sheets = sorted(name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))
        selected = _sample_indexes(len(sheets), min(6, len(sheets)))
        for sheet_index in selected:
            member = sheets[sheet_index]
            label = sheet_names[sheet_index] if sheet_index < len(sheet_names) else Path(member).stem
            rows: list[str] = []
            root = ET.fromstring(archive.read(member))
            all_rows = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "row"]
            for row_index in _sample_indexes(len(all_rows), min(max_rows, len(all_rows))):
                row = all_rows[row_index]
                values: list[str] = []
                for cell in (node for node in row if node.tag.rsplit("}", 1)[-1] == "c"):
                    cell_type = cell.attrib.get("t")
                    value = ""
                    if cell_type == "inlineStr":
                        value = "".join(cell.itertext()).strip()
                    else:
                        value_node = next((node for node in cell if node.tag.rsplit("}", 1)[-1] in {"v", "f"}), None)
                        value = value_node.text.strip() if value_node is not None and value_node.text else ""
                        if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                            value = shared[int(value)]
                        elif cell_type == "b":
                            value = "TRUE" if value == "1" else "FALSE"
                    values.append(value[:200])
                    if len(values) >= max_columns:
                        break
                if any(values):
                    rows.append(" | ".join(values))
                if len(rows) >= max_rows:
                    break
            output.append(f"[{label}]\n" + "\n".join(rows))
            if len("\n".join(output)) >= limit:
                break
        return _clean("\n".join(output), limit), len(sheets) > len(selected) or any(len([node for node in ET.fromstring(archive.read(member)).iter() if node.tag.rsplit("}", 1)[-1] == "row"]) > max_rows for member in (sheets[index] for index in selected))

def _pdf_page_count(path: Path) -> int | None:
    command = shutil.which("pdfinfo")
    if not command:
        return None
    process = subprocess.run([command, str(path)], capture_output=True, text=True, timeout=30, check=False)
    match = re.search(r"^Pages:\s*(\d+)", process.stdout, re.MULTILINE)
    return int(match.group(1)) if match else None

def _pdf_text(path: Path, limit: int, max_pages: int) -> tuple[str, str, str | None, bool, list[int]]:
    command = shutil.which("pdftotext")
    if command:
        with tempfile.TemporaryDirectory(prefix="xunxu-pdf-") as directory:
            page_count = _pdf_page_count(path)
            pages = [index + 1 for index in _sample_indexes(page_count, min(max_pages, page_count))] if page_count else list(range(1, max_pages + 1))
            parts = []
            for page in pages:
                output = Path(directory) / f"page-{page}.txt"
                process = subprocess.run([command, "-f", str(page), "-l", str(page), "-enc", "UTF-8", str(path), str(output)], capture_output=True, text=True, timeout=60, check=False)
                if process.returncode == 0 and output.is_file():
                    parts.append((f"第{page}页", _decode(output.read_bytes())))
            text = _balanced_sample(parts, limit)
            if text:
                return text, "pdf-pdftotext-sampled", None, bool(page_count and page_count > len(pages)), pages
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "unavailable", "缺少 pdftotext 与 pypdf；请安装 requirements.txt", False, []
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                return "", "unavailable", "PDF 已加密", False, []
        except Exception:
            return "", "unavailable", "PDF 已加密", False, []
    metadata = reader.metadata or {}
    header = "\n".join(f"{key}: {metadata.get(key)}" for key in ("/Title", "/Subject", "/Author") if metadata.get(key))
    page_count = len(reader.pages)
    indexes = _sample_indexes(page_count, min(max_pages, page_count))
    parts = [("元数据", header)] if header else []
    for index in indexes:
        parts.append((f"第{index + 1}页", reader.pages[index].extract_text() or ""))
    text = _balanced_sample(parts, limit)
    return (text, "pdf-pypdf-sampled", None, page_count > len(indexes), [index + 1 for index in indexes]) if text else ("", "pdf-needs-ocr", "PDF 无文本层；需渲染代表页后 OCR", False, [index + 1 for index in indexes])

def extract_text(path: Path, limit: int = 8_000, max_pages: int = 6) -> dict:
    suffix = path.suffix.lower()
    try:
        if suffix in TEXT_SUFFIXES or path.name.lower() in {"makefile", "dockerfile", "cmakelists.txt"}:
            text, truncated = _sample_text_file(path, limit)
            result = result_record(path, text, "text-sampled"); result.update({"sample_strategy": "beginning-middle-end", "truncated": truncated}); return result
        if suffix == ".docx":
            text, truncated = _zip_xml(path, ("word/",), limit); result = result_record(path, text, "docx-sampled"); result.update({"sample_strategy": "beginning-middle-end", "truncated": truncated}); return result
        if suffix == ".pptx":
            text, truncated = _zip_xml(path, ("ppt/slides/", "ppt/notesSlides/"), limit); result = result_record(path, text, "pptx-sampled"); result.update({"sample_strategy": "distributed-members", "truncated": truncated}); return result
        if suffix == ".xlsx":
            text, truncated = _xlsx_text(path, limit); result = result_record(path, text, "xlsx-sampled"); result.update({"sample_strategy": "distributed-sheets-and-rows", "truncated": truncated}); return result
        if suffix == ".epub":
            text, truncated = _zip_xml(path, ("META-INF/", "OEBPS/", "OPS/", "EPUB/"), limit, (".xml", ".xhtml", ".html", ".opf", ".ncx")); result = result_record(path, text, "epub-sampled"); result.update({"sample_strategy": "distributed-chapters", "truncated": truncated}); return result
        if suffix == ".pdf":
            text, method, error, truncated, pages = _pdf_text(path, limit, max_pages)
            result = result_record(path, text, method, error); result.update({"sample_strategy": "distributed-pages", "sampled_pages": pages, "truncated": truncated}); return result
        return result_record(path, "", "unsupported", f"暂不支持直接解析 {suffix or '无扩展名'}")
    except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        return result_record(path, "", "unavailable", str(exc))
    except Exception as exc:
        return result_record(path, "", "unavailable", f"解析失败：{exc}")

def main() -> int:
    parser = argparse.ArgumentParser(description="跨平台提取文档证据文本，不修改源文件")
    parser.add_argument("path", type=Path)
    parser.add_argument("--limit", type=int, default=8_000)
    parser.add_argument("--max-pages", type=int, default=6)
    parser.add_argument("--output", type=Path, help="写入 JSON 文件，避免证据正文占用终端 token")
    args = parser.parse_args()
    path = args.path.expanduser().resolve()
    if not path.is_file():
        parser.error(f"文件不存在: {path}")
    result = extract_text(path, max(1_000, args.limit), max(1, args.max_pages))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(json.dumps({"output": str(output), "method": result.get("method"), "characters": len(result.get("text", ""))}, ensure_ascii=False))
    else:
        print(payload, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

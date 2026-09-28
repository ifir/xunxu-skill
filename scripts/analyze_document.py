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

def _xml_text(data: bytes) -> str:
    root = ET.fromstring(data)
    return "\n".join(value.strip() for value in root.itertext() if value.strip())

def _zip_xml(path: Path, prefixes: tuple[str, ...], limit: int) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            normalized = name.replace("\\", "/")
            if not normalized.endswith(".xml") or not normalized.startswith(prefixes):
                continue
            try:
                chunks.append(_xml_text(archive.read(name)))
            except (ET.ParseError, KeyError, OSError):
                continue
            if sum(map(len, chunks)) >= limit:
                break
    return _clean("\n".join(chunks), limit)

def _xlsx_text(path: Path, limit: int, max_rows: int = 20, max_columns: int = 12) -> str:
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
        for sheet_index, member in enumerate(sheets):
            label = sheet_names[sheet_index] if sheet_index < len(sheet_names) else Path(member).stem
            rows: list[str] = []
            root = ET.fromstring(archive.read(member))
            for row in (node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "row"):
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
        return _clean("\n".join(output), limit)

def _pdf_text(path: Path, limit: int, max_pages: int) -> tuple[str, str, str | None]:
    command = shutil.which("pdftotext")
    if command:
        with tempfile.TemporaryDirectory(prefix="xunxu-pdf-") as directory:
            output = Path(directory) / "evidence.txt"
            process = subprocess.run(
                [command, "-f", "1", "-l", str(max_pages), "-enc", "UTF-8", str(path), str(output)],
                capture_output=True, text=True, timeout=60, check=False,
            )
            if process.returncode == 0 and output.is_file():
                text = _clean(_decode(output.read_bytes()[: limit * 4]), limit)
                if text:
                    return text, "pdf-pdftotext", None
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "unavailable", "缺少 pdftotext 与 pypdf；请安装 requirements.txt"
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                return "", "unavailable", "PDF 已加密"
        except Exception:
            return "", "unavailable", "PDF 已加密"
    metadata = reader.metadata or {}
    header = "\n".join(f"{key}: {metadata.get(key)}" for key in ("/Title", "/Subject", "/Author") if metadata.get(key))
    page_count = len(reader.pages)
    indexes = list(range(min(max_pages, page_count)))
    if page_count > max_pages:
        indexes.extend(index for index in (page_count // 2, page_count - 1) if index not in indexes)
    chunks = [header] if header else []
    for index in indexes:
        chunks.append(reader.pages[index].extract_text() or "")
        if sum(map(len, chunks)) >= limit:
            break
    text = _clean("\n".join(chunks), limit)
    return (text, "pdf-pypdf", None) if text else ("", "pdf-needs-ocr", "PDF 无文本层；需渲染代表页后 OCR")

def extract_text(path: Path, limit: int = 8_000, max_pages: int = 6) -> dict:
    suffix = path.suffix.lower()
    try:
        if suffix in TEXT_SUFFIXES or path.name.lower() in {"makefile", "dockerfile", "cmakelists.txt"}:
            text = _clean(_decode(path.read_bytes()[: limit * 4]), limit)
            return result_record(path, text, "text")
        if suffix == ".docx":
            return result_record(path, _zip_xml(path, ("word/",), limit), "docx-xml")
        if suffix == ".pptx":
            return result_record(path, _zip_xml(path, ("ppt/slides/", "ppt/notesSlides/"), limit), "pptx-xml")
        if suffix == ".xlsx":
            return result_record(path, _xlsx_text(path, limit), "xlsx-preview")
        if suffix == ".epub":
            return result_record(path, _zip_xml(path, ("META-INF/", "OEBPS/", "OPS/", "EPUB/"), limit), "epub-xml")
        if suffix == ".pdf":
            text, method, error = _pdf_text(path, limit, max_pages)
            return result_record(path, text, method, error)
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

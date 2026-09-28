#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import result_record

def extract_text(path: Path, lang: str = "ch") -> dict:
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return result_record(path, "", "unavailable", "缺少 paddleocr；请按 requirements-media.txt 安装可选依赖和匹配的 PaddlePaddle runtime")
    try:
        engine = PaddleOCR(use_doc_orientation_classify=True, use_doc_unwarping=False, use_textline_orientation=True, lang=lang)
        output = engine.predict(input=str(path))
        chunks = []
        for item in output:
            data = getattr(item, "json", item)
            if callable(data):
                data = data()
            if isinstance(data, str):
                try: data = json.loads(data)
                except ValueError: data = {}
            if isinstance(data, dict):
                payload = data.get("res", data)
                chunks.extend(str(value) for value in payload.get("rec_texts", []) if str(value).strip())
        return result_record(path, "\n".join(chunks), "ocr")
    except Exception as exc:
        return result_record(path, "", "ocr", str(exc))

def main() -> int:
    parser = argparse.ArgumentParser(description="使用 PaddleOCR 在本地提取图片文字")
    parser.add_argument("path", type=Path)
    parser.add_argument("--lang", default="ch")
    args = parser.parse_args()
    path = args.path.expanduser().resolve()
    if not path.is_file(): parser.error(f"文件不存在: {path}")
    print(json.dumps(extract_text(path, args.lang), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

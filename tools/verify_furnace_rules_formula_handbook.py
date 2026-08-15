"""Deterministically verify the generated Markdown/PDF furnace-rule handbook."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from pypdf import PdfReader


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()

    markdown = args.markdown.read_text(encoding="utf-8")
    legacy = re.findall(r"^## 1\.[1-8] ", markdown, flags=re.MULTILINE)
    abc = re.findall(r"^## ([ABC]\d{1,2}) ", markdown, flags=re.MULTILINE)
    expected = {*(f"A{i}" for i in range(1, 10)), *(f"B{i}" for i in range(1, 14)), *(f"C{i}" for i in range(1, 12))}
    if len(legacy) != 8:
        raise SystemExit(f"legacy rule count mismatch: {len(legacy)}")
    if len(abc) != 33 or set(abc) != expected:
        raise SystemExit(f"ABC rule set mismatch: count={len(abc)}")
    required_markdown = (
        "S_normal = 100 ×",
        "S_B4 = 100 ×",
        "S_C11 = 100 ×",
        "g_H(x;a,b)",
        "当前仓库没有原8类历史",
    )
    for marker in required_markdown:
        if marker not in markdown:
            raise SystemExit(f"markdown marker missing: {marker}")

    reader = PdfReader(str(args.pdf))
    page_texts = [(page.extract_text() or "") for page in reader.pages]
    pdf_text = "\n".join(page_texts)
    required_pdf = (
        "炉况诊断8类与ABC33规则数学公式手册",
        "正常顺行",
        "热制度上行风险",
        "严重管道/崩滑料复合报警",
        "复风重启风险报警",
        "发布边界与权威来源",
    )
    for marker in required_pdf:
        if marker not in pdf_text:
            raise SystemExit(f"PDF text marker missing: {marker}")
    if len(reader.pages) < 35:
        raise SystemExit(f"PDF page count unexpectedly small: {len(reader.pages)}")

    page_markers = {}
    for marker in ("1.1 正常顺行", "B4 热制度上行风险", "C11 复风重启风险报警"):
        page_markers[marker] = [index + 1 for index, text in enumerate(page_texts) if marker in text]
        if not page_markers[marker]:
            raise SystemExit(f"PDF page marker missing: {marker}")

    print(json.dumps({
        "ok": True,
        "legacy_rules": len(legacy),
        "abc_rules": len(abc),
        "pdf_pages": len(reader.pages),
        "pdf_bytes": args.pdf.stat().st_size,
        "page_markers": page_markers,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

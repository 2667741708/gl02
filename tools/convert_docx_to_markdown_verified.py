"""Convert a DOCX body to readable Markdown with a text-payload audit.

The Markdown syntax itself adds characters (for example ``#`` and HTML table
tags).  Therefore fidelity is verified against the ordered source fragments
that are handed to the renderer, not against the raw Markdown byte count.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph


NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+){0,6})(?:[、.．\s]|$)")


@dataclass(frozen=True)
class TextFragment:
    """One ordered piece of visible DOCX body text."""

    body_index: int
    kind: str
    item_index: int
    text: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fragment_digest(fragments: Iterable[TextFragment]) -> str:
    payload = [asdict(fragment) for fragment in fragments]
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _heading_level(paragraph: Paragraph, text: str) -> int | None:
    style = paragraph.style.name if paragraph.style is not None else ""
    if style == "Title":
        return 1
    style_match = re.match(r"Heading\s+(\d+)", style, flags=re.IGNORECASE)
    if style_match:
        return min(max(int(style_match.group(1)), 1), 6)
    numbered = NUMBERED.match(text)
    if numbered and len(text) <= 80:
        depth = numbered.group(1).count(".") + 1
        if depth <= 3:
            return min(depth + 1, 6)
    return None


def _table_rows(table: Table) -> list[list[str]]:
    """Return actual XML cells so merged cells are not duplicated by the grid."""
    rows: list[list[str]] = []
    for tr in table._tbl.tr_lst:  # noqa: SLF001 - required for real cell traversal
        row: list[str] = []
        for tc in tr.tc_lst:
            row.append(_Cell(tc, table).text)
        rows.append(row)
    return rows


def _html_cell(text: str) -> str:
    return html.escape(text, quote=False).replace("\n", "<br>")


def convert_document(source: Path, output: Path, report_path: Path) -> dict[str, object]:
    """Convert ``source`` and write a machine-verifiable fidelity report."""
    document: DocumentObject = Document(source)
    markdown: list[str] = [
        "<!-- 由 tools/convert_docx_to_markdown_verified.py 从 DOCX 自动生成。 -->",
        "<!-- 正文文字一致性以配套 JSON 报告为准；Markdown 标记不计入源文字。 -->",
        "",
    ]
    source_fragments: list[TextFragment] = []
    emitted_fragments: list[TextFragment] = []
    paragraph_total = 0
    paragraph_count = 0
    blank_paragraph_count = 0
    whitespace_only_paragraph_count = 0
    table_count = 0
    table_cell_count = 0

    for body_index, child in enumerate(document.element.body.iterchildren()):
        if isinstance(child, CT_P):
            paragraph_total += 1
            paragraph = Paragraph(child, document)
            text = paragraph.text
            if not text:
                blank_paragraph_count += 1
                continue
            if not text.strip():
                whitespace_only_paragraph_count += 1
                continue
            fragment = TextFragment(body_index, "paragraph", 0, text)
            source_fragments.append(fragment)
            level = _heading_level(paragraph, text)
            markdown.append(f"{'#' * level} {text}" if level else text)
            markdown.append("")
            emitted_fragments.append(fragment)
            paragraph_count += 1
            continue

        if isinstance(child, CT_Tbl):
            table = Table(child, document)
            rows = _table_rows(table)
            markdown.append("<table>")
            for row_index, row in enumerate(rows):
                markdown.append("  <tr>")
                for cell_index, cell_text in enumerate(row):
                    fragment = TextFragment(
                        body_index,
                        "table_cell",
                        row_index * 10000 + cell_index,
                        cell_text,
                    )
                    source_fragments.append(fragment)
                    markdown.append(f"    <td>{_html_cell(cell_text)}</td>")
                    emitted_fragments.append(fragment)
                    table_cell_count += 1
                markdown.append("  </tr>")
            markdown.extend(["</table>", ""])
            table_count += 1

    exact_match = source_fragments == emitted_fragments
    source_digest = _fragment_digest(source_fragments)
    emitted_digest = _fragment_digest(emitted_fragments)
    if not exact_match or source_digest != emitted_digest:
        raise RuntimeError("DOCX source text fragments did not survive Markdown rendering")

    rendered = "\n".join(markdown).rstrip() + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")

    all_text = "".join(fragment.text for fragment in source_fragments)
    section_codes = sorted(
        {
            match.group(1)
            for fragment in source_fragments
            if fragment.kind == "paragraph"
            for match in [NUMBERED.match(fragment.text)]
            if match
        },
        key=lambda code: tuple(int(part) for part in code.split(".")),
    )
    focus_section_codes: list[str] = []
    in_focus_section = False
    for fragment in source_fragments:
        if fragment.kind != "paragraph":
            continue
        stripped = fragment.text.strip()
        if stripped == "5.3 炉况调剂方法":
            in_focus_section = True
        elif in_focus_section and stripped == "5.4 高炉的休风与送风":
            break
        if in_focus_section:
            match = NUMBERED.match(fragment.text)
            if match:
                focus_section_codes.append(match.group(1))
    report: dict[str, object] = {
        "source": str(source.resolve()),
        "output": str(output.resolve()),
        "source_sha256": _sha256_bytes(source.read_bytes()),
        "markdown_sha256": _sha256_bytes(rendered.encode("utf-8")),
        "paragraphs_total_body": paragraph_total,
        "paragraphs_with_visible_text": paragraph_count,
        "paragraphs_blank": blank_paragraph_count,
        "paragraphs_whitespace_only": whitespace_only_paragraph_count,
        "tables": table_count,
        "table_cells": table_cell_count,
        "ordered_text_fragments": len(source_fragments),
        "source_text_characters_including_whitespace": len(all_text),
        "source_text_characters_excluding_whitespace": len(
            re.sub(r"\s+", "", all_text)
        ),
        "source_text_fragment_sha256": source_digest,
        "emitted_text_fragment_sha256": emitted_digest,
        "exact_ordered_text_payload_match": exact_match,
        "numbered_section_count": len(section_codes),
        "high_furnace_foreman_section_5_3_codes": focus_section_codes,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert DOCX to Markdown and verify ordered visible-text payloads."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("logs/docx_markdown_validation.json"),
    )
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    report = convert_document(args.source, args.output, args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

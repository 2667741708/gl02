"""Render the ABC33 DOCX as readable Markdown with GFM tables and LaTeX.

The generic verified converter is intentionally lossless and therefore emits
HTML tables.  This renderer is the human-facing companion: it keeps the DOCX
body order, uses Markdown tables, and normalizes formula-like cells to LaTeX.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph


FORMULA_MARKERS = (
    "Score(", "clip(", "g_H(", "g_L(", "g_A(", "z60_", "z15std_",
    "slope30_", "Σ", "max(", "min(", "abs(", "confidence",
)


def _heading_level(paragraph: Paragraph, text: str) -> int | None:
    style = paragraph.style.name if paragraph.style is not None else ""
    if style == "Title":
        return 1
    match = re.match(r"Heading\s+(\d+)", style, flags=re.I)
    if match:
        return min(max(int(match.group(1)), 1), 6)
    if re.match(r"^[一二三四五六七八九十]+、", text) and len(text) < 80:
        return 1
    if re.match(r"^[ABC](?:[1-9]|1[0-3])\s", text) and len(text) < 100:
        return 2
    return None


def _rows(table: Table) -> list[list[str]]:
    result: list[list[str]] = []
    for tr in table._tbl.tr_lst:  # noqa: SLF001 - actual cells, no merged duplicates
        result.append([_Cell(tc, table).text.strip() for tc in tr.tc_lst])
    return result


def _latex_token(match: re.Match[str]) -> str:
    token = match.group(0)
    operators = {"Score", "clip", "max", "min", "abs"}
    if token in operators:
        return rf"\operatorname{{{token}}}"
    if token == "confidence":
        return r"\operatorname{confidence}"
    if token == "g_H":
        return r"g_{\mathrm H}"
    if token == "g_L":
        return r"g_{\mathrm L}"
    if token == "g_A":
        return r"g_{\mathrm A}"
    match_z = re.fullmatch(r"z60_(.+)", token)
    if match_z:
        return rf"z_{{60}}^{{\mathrm{{{match_z.group(1).replace('_', r'\_')}}}}}"
    match_std = re.fullmatch(r"z15std_(.+)", token)
    if match_std:
        return rf"z_{{15,\mathrm{{std}}}}^{{\mathrm{{{match_std.group(1).replace('_', r'\_')}}}}}"
    match_slope = re.fullmatch(r"slope30_(.+)", token)
    if match_slope:
        return rf"\operatorname{{slope}}_{{30}}^{{\mathrm{{{match_slope.group(1).replace('_', r'\_')}}}}}"
    if token in {"A_i", "w_i", "s_i"}:
        return token[0] + "_i"
    if "_" in token:
        return rf"\mathrm{{{token.replace('_', r'\_')}}}"
    return token


def _as_latex(text: str) -> str:
    value = text.strip()
    protected: dict[str, str] = {}

    def protect(rendered: str) -> str:
        key = f"PHX{len(protected)}XHP"
        protected[key] = rendered
        # Spaces keep the placeholder from becoming part of an adjacent
        # identifier token such as ``z60_P_top（顶压平均）``.
        return f" {key} "

    # Full-width parentheses in the source are explanatory labels, not
    # executable grouping.  Keep them as proper LaTeX text annotations.
    value = re.sub(
        r"（([^（）]*)）",
        lambda match: protect(r"\left(\text{" + match.group(1).replace("_", r"\_") + r"}\right)"),
        value,
    )
    range_notation = {
        "T_top_A-D": r"\{T_{\mathrm{top},A},T_{\mathrm{top},B},T_{\mathrm{top},C},T_{\mathrm{top},D}\}",
        "P_top_gas_A-D": r"\{P_{\mathrm{top},A},P_{\mathrm{top},B},P_{\mathrm{top},C},P_{\mathrm{top},D}\}",
        "P_static_layer_A-F": r"\{P_{\mathrm{static},\ell,d}:d\in A\ldots F\}",
        "T_body_L7-L16_A-H": r"\{T_{\mathrm{body},\ell,d}:\ell\in[7,16],d\in A\ldots H\}",
    }
    for source, rendered in range_notation.items():
        value = value.replace(source, protect(rendered))
    value = re.sub(r"[A-Za-z][A-Za-z0-9_]*", _latex_token, value)
    value = value.replace("Σ", r"\sum ")
    value = value.replace("*", r"\times ")
    value = value.replace(">=", r"\ge ").replace("<=", r"\le ")
    value = value.replace("-", "-")
    value = re.sub(r"([\u3400-\u9fff]+(?:[：，、；。/]|\s)*)", r"\\text{\1}", value)
    for key, rendered in protected.items():
        value = value.replace(key, rendered)
    return f"${value}$"


def _cell(text: str) -> str:
    compact = "；".join(part.strip() for part in text.splitlines() if part.strip())
    if any(marker in compact for marker in FORMULA_MARKERS):
        compact = _as_latex(compact)
    return compact.replace("|", r"\|")


def convert(source: Path, output: Path) -> None:
    document: DocumentObject = Document(source)
    lines = [
        "<!-- 人工可读版：标准 Markdown 表格与 LaTeX 公式。 -->",
        "<!-- 原始文字保真证明见 logs/abc33_source_docx_markdown_validation_20260809.json。 -->",
        "",
    ]
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            level = _heading_level(paragraph, text)
            lines.extend([f"{'#' * level} {text}" if level else text, ""])
            continue
        if isinstance(child, CT_Tbl):
            rows = _rows(Table(child, document))
            if not rows:
                continue
            width = max(len(row) for row in rows)
            normalized = [row + [""] * (width - len(row)) for row in rows]
            lines.append("| " + " | ".join(_cell(item) for item in normalized[0]) + " |")
            lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
            for row in normalized[1:]:
                lines.append("| " + " | ".join(_cell(item) for item in row) + " |")
            lines.append("")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    convert(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

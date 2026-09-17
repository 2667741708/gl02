from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P


DOC_ID = "bf_three_rules_two_systems_20260712"
DOC_TITLE = "冀钢炼铁三规二制"
TOC_ENTRY = re.compile(r"^\s*(\d+)[.．、]\s*(.+?)(?:…{2,}|\.{4,})\s*\d+\s*$")
NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+){0,6})\s*(?:[、.．]\s*)?(.*)$")

REGULATION_PATTERNS = (
    ("安全操作规程", re.compile(r"安全.*操作规程")),
    ("技术操作规程", re.compile(r"(?:技术|工艺).*操作规程")),
    ("设备使用维护规程", re.compile(r"设备.*(?:使用|维护).*规程")),
    ("岗位交接班制度", re.compile(r"岗位交接班制度")),
    ("生产联系确认制", re.compile(r"生产联系确认制")),
)

# Exact original heading variants observed in the frozen source DOCX. These
# classify headings only; they never rewrite the original clause/table text.
REGULATION_HEADING_ALIASES = {
    '安全操作规程': '安全操作规程',
    '技术操作规程': '技术操作规程',
    '工艺操作规程': '技术操作规程',
    '工艺技术规程': '技术操作规程',
    '工艺技术操作规程': '技术操作规程',
    '工艺技术技作规程': '技术操作规程',
    '设备使用维护规程': '设备使用维护规程',
    '设备维护规程': '设备使用维护规程',
    '设备维护操作规程': '设备使用维护规程',
    '设备操维护规程': '设备使用维护规程',
    '岗位交接班制度': '岗位交接班制度',
    '生产联系确认制': '生产联系确认制',
}


@dataclass
class SourceItem:
    block_index: int
    item_index: int
    kind: str
    text: str
    chapter_code: str
    chapter_title: str
    regulation_type: str
    section_code: str
    section_title: str
    hierarchy_path: list[str]


@dataclass
class KnowledgeChunk:
    chunk_id: str
    parent_chunk_id: str | None
    title: str
    content: str
    enriched_content: str
    granularity: str
    chapter_code: str
    chapter_title: str
    regulation_type: str
    section_code: str
    hierarchy_path: list[str]
    source_block_start: int
    source_block_end: int
    content_hash: str


def clean_text(value: str) -> str:
    lines = [re.sub(r"[ \t\u3000]+", " ", line).strip() for line in value.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line).strip()


def iter_blocks(document: DocumentObject) -> Iterable[tuple[str, str]]:
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            text = clean_text(paragraph.text)
            if text:
                yield "paragraph", text
        elif isinstance(child, CT_Tbl):
            table = Table(child, document)
            rows: list[str] = []
            for row in table.rows:
                cells = [clean_text(cell.text).replace("\n", " / ") for cell in row.cells]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                yield "table", "\n".join(rows)


def toc_chapters(document: DocumentObject) -> dict[int, str]:
    chapters: dict[int, str] = {}
    for paragraph in document.paragraphs[:80]:
        text = clean_text(paragraph.text)
        match = TOC_ENTRY.match(text)
        if match:
            chapters[int(match.group(1))] = match.group(2).strip()
    if len(chapters) < 28:
        raise ValueError(f"目录应至少识别 28 个岗位/制度，实际识别 {len(chapters)} 个")
    return chapters


def normalized(value: str) -> str:
    return re.sub(r"[\s.．、:：·]+", "", value).lower()


def match_chapter(text: str, chapters: dict[int, str]) -> tuple[str, str] | None:
    first_line = text.split("\n", 1)[0]
    match = re.match(r"^\s*(\d+)[.．、]\s*(.+)$", first_line)
    if not match:
        return None
    number = int(match.group(1))
    expected = chapters.get(number)
    if expected:
        actual_norm = normalized(match.group(2)).replace("三规一制", "").replace("三规二制", "")
        expected_norm = normalized(expected)
        aliases = ("高炉", "原料", "岗位")
        actual_core = actual_norm
        expected_core = expected_norm
        for prefix in aliases:
            actual_core = actual_core.removeprefix(prefix)
            expected_core = expected_core.removeprefix(prefix)
        if (
            actual_norm.startswith(expected_norm)
            or expected_norm.startswith(actual_norm)
            or (len(expected_norm) >= 3 and expected_norm in actual_norm)
            or actual_core.startswith(expected_core)
            or expected_core.startswith(actual_core)
        ):
            return str(number), expected
    return None


def match_regulation(text: str, chapter_title: str) -> str | None:
    # A regulation mention inside a clause is not a heading. In particular,
    # assigning the chapter's制度 label to every short paragraph dropped its
    # original clauses and short tables before chunk creation.
    if '\n' in text or ' | ' in text:
        return None
    candidate = re.sub(r'^\s*(?:\d+(?:\.\d+)*[.．、]*|[一二三四五六七八九十]+[.．、]+|[（(][一二三四五六七八九十\d]+[）)])\s*', '', text).strip()
    candidate = candidate.rstrip(':：').strip()
    if chapter_title and candidate != chapter_title and candidate.startswith(chapter_title):
        candidate = candidate[len(chapter_title):].strip()
    return REGULATION_HEADING_ALIASES.get(candidate)


def parse_source_items(document: DocumentObject) -> tuple[dict[int, str], list[SourceItem]]:
    chapters = toc_chapters(document)
    items: list[SourceItem] = []
    current_chapter_code = ""
    current_chapter_title = ""
    current_regulation = "综合规定"
    hierarchy: dict[int, tuple[str, str]] = {}
    item_index = 0

    for block_index, (kind, block_text) in enumerate(iter_blocks(document)):
        chapter = match_chapter(block_text, chapters)
        if chapter:
            current_chapter_code, current_chapter_title = chapter
            current_regulation = current_chapter_title if int(current_chapter_code) >= 27 else "综合规定"
            hierarchy.clear()
            remaining_lines = block_text.split("\n")[1:]
            block_text = "\n".join(remaining_lines).strip()
            if not block_text:
                continue
        if not current_chapter_code:
            continue

        for logical_text in block_text.split("\n") if kind == "paragraph" else [block_text]:
            logical_text = clean_text(logical_text)
            if not logical_text:
                continue
            regulation = match_regulation(logical_text, current_chapter_title)
            if regulation and len(logical_text) <= 80:
                current_regulation = regulation
                hierarchy.clear()
                continue

            section_code = ""
            section_title = ""
            match = NUMBERED.match(logical_text) if kind == "paragraph" else None
            if match:
                section_code = match.group(1)
                section_title = match.group(2).strip()
                depth = section_code.count(".") + 1
                hierarchy = {d: value for d, value in hierarchy.items() if d < depth}
                hierarchy[depth] = (section_code, section_title)
            path = [
                f"{code} {title}".strip()
                for _, (code, title) in sorted(hierarchy.items())
            ]
            item_index += 1
            items.append(
                SourceItem(
                    block_index=block_index,
                    item_index=item_index,
                    kind=kind,
                    text=logical_text,
                    chapter_code=current_chapter_code,
                    chapter_title=current_chapter_title,
                    regulation_type=current_regulation,
                    section_code=section_code,
                    section_title=section_title,
                    hierarchy_path=path,
                )
            )
    return chapters, items


def stable_id(*parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:14]
    return f"{DOC_ID}_{digest}"


def make_chunk(
    granularity: str,
    items: list[SourceItem],
    title: str,
    section_code: str,
    hierarchy_path: list[str],
    part: int,
    parent_chunk_id: str | None = None,
) -> KnowledgeChunk:
    first, last = items[0], items[-1]
    content = "\n".join(item.text for item in items)
    path_text = " > ".join(hierarchy_path) if hierarchy_path else title
    enriched = (
        f"【文档】{DOC_TITLE}\n"
        f"【岗位/制度】{first.chapter_code}. {first.chapter_title}\n"
        f"【规程类型】{first.regulation_type}\n"
        f"【层级路径】{path_text}\n"
        f"【粒度】{granularity}\n"
        f"【原文】\n{content}"
    )
    chunk_id = stable_id(
        granularity,
        first.chapter_code,
        first.regulation_type,
        section_code,
        str(part),
        str(first.item_index),
        str(last.item_index),
    )
    return KnowledgeChunk(
        chunk_id=chunk_id,
        parent_chunk_id=parent_chunk_id,
        title=title,
        content=content,
        enriched_content=enriched,
        granularity=granularity,
        chapter_code=first.chapter_code,
        chapter_title=first.chapter_title,
        regulation_type=first.regulation_type,
        section_code=section_code,
        hierarchy_path=hierarchy_path,
        source_block_start=first.block_index,
        source_block_end=last.block_index,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def split_items(items: list[SourceItem], max_chars: int) -> list[list[SourceItem]]:
    groups: list[list[SourceItem]] = []
    current: list[SourceItem] = []
    chars = 0
    for item in items:
        item_chars = len(item.text) + 1
        if current and chars + item_chars > max_chars:
            groups.append(current)
            current = []
            chars = 0
        current.append(item)
        chars += item_chars
    if current:
        groups.append(current)
    return groups


def build_chunks(items: list[SourceItem]) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []

    # Fine grain: one source paragraph/table per chunk.  This preserves exact
    # thresholds, prohibitions and exception clauses for citation-style QA.
    for item in items:
        title = " > ".join(item.hierarchy_path[-3:]) or f"{item.chapter_code}. {item.chapter_title}"
        chunks.append(make_chunk("atomic", [item], title, item.section_code, item.hierarchy_path, 1))

    # Topic grain: group siblings by their immediate numbered parent.  For
    # example, all 5.1.1.x clauses form one or more 5.1.1 topic chunks.
    topic_groups: dict[tuple[str, str, str, str], list[SourceItem]] = {}
    for item in items:
        if not item.section_code or "." not in item.section_code:
            continue
        parent_code = item.section_code.rsplit(".", 1)[0]
        key = (item.chapter_code, item.regulation_type, parent_code, " > ".join(item.hierarchy_path[:-1]))
        topic_groups.setdefault(key, []).append(item)
    for (chapter_code, regulation, parent_code, path), group in topic_groups.items():
        del chapter_code, regulation
        for part, subgroup in enumerate(split_items(group, 1800), start=1):
            hierarchy_path = subgroup[0].hierarchy_path[:-1] or [parent_code]
            title = path or f"{subgroup[0].chapter_title} {parent_code}"
            chunks.append(make_chunk("topic", subgroup, title, parent_code, hierarchy_path, part))

    # Section grain: group each岗位/制度中的一种规程，分片保持在可控上下文长度。
    section_groups: dict[tuple[str, str], list[SourceItem]] = {}
    for item in items:
        section_groups.setdefault((item.chapter_code, item.regulation_type), []).append(item)
    for (_, regulation), group in section_groups.items():
        for part, subgroup in enumerate(split_items(group, 2600), start=1):
            title = f"{subgroup[0].chapter_title} - {regulation} - 第{part}部分"
            chunks.append(make_chunk("section", subgroup, title, "", [subgroup[0].chapter_title, regulation], part))

    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="Build hierarchical RAG chunks for 冀钢炼铁三规二制.")
    parser.add_argument("docx", type=Path)
    parser.add_argument("--output", type=Path, default=Path("logs/three_rules_hierarchical_chunks.json"))
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    document = Document(args.docx)
    chapters, items = parse_source_items(document)
    chunks = build_chunks(items)
    payload = {
        "document": {
            "doc_id": DOC_ID,
            "title": DOC_TITLE,
            "source_file": str(args.docx.resolve()),
            "chapter_count": len(chapters),
            "source_item_count": len(items),
        },
        "chapters": [{"code": str(code), "title": title} for code, title in sorted(chapters.items())],
        "counts": {
            "chunks": len(chunks),
            "atomic": sum(chunk.granularity == "atomic" for chunk in chunks),
            "topic": sum(chunk.granularity == "topic" for chunk in chunks),
            "section": sum(chunk.granularity == "section" for chunk in chunks),
            "tables": sum(item.kind == "table" for item in items),
        },
        "chunks": [asdict(chunk) for chunk in chunks],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["document"], ensure_ascii=False))
    print(json.dumps(payload["counts"], ensure_ascii=False))
    print(f"output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

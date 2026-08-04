from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


def strip_code(text: str) -> str:
    return re.sub(r"^\s*\d+(?:\.\d+){0,6}\s*(?:[、.．]\s*)?", "", text).strip()


def focus_text(text: str, limit: int = 34) -> str:
    body = strip_code(text).replace("\n", " ")
    body = re.split(r"[。；;：:]", body, maxsplit=1)[0].strip()
    return body[:limit] or "该条款"


def parent_path(chunk: dict) -> str:
    path = list(chunk.get("hierarchy_path") or [])
    if len(path) > 1:
        return " > ".join(path[:-1])
    return chunk.get("title") or "高炉工长规定"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an exhaustive 高炉长/工长 verification question bank from 三规二制 chunks.")
    parser.add_argument("--input", type=Path, default=Path("logs/three_rules_hierarchical_chunks.json"))
    parser.add_argument("--output", type=Path, default=Path("PT/三规二制高炉长工长知识库测试题库.md"))
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    chunks = [chunk for chunk in payload["chunks"] if chunk["chapter_code"] == "1"]
    atomic = [chunk for chunk in chunks if chunk["granularity"] == "atomic"]
    topics = [chunk for chunk in chunks if chunk["granularity"] == "topic"]
    all_codes = {chunk["section_code"] for chunk in atomic if chunk["section_code"]}
    parent_codes = {
        code
        for code in all_codes
        if any(other.startswith(code + ".") for other in all_codes if other != code)
    }
    leaves = [
        chunk
        for chunk in atomic
        if not chunk["section_code"] or chunk["section_code"] not in parent_codes
    ]

    grouped_topics: dict[str, list[dict]] = defaultdict(list)
    grouped_leaves: dict[str, list[dict]] = defaultdict(list)
    for chunk in topics:
        grouped_topics[chunk["regulation_type"]].append(chunk)
    for chunk in leaves:
        grouped_leaves[chunk["regulation_type"]].append(chunk)

    lines = [
        "# 《三规二制》高炉长/工长知识库测试题库",
        "",
        "更新时间：2026-07-12",
        "",
        "## 使用说明",
        "",
        "本题库依据《冀钢炼铁三规二制》中第 1 章“高炉工长”生成。原文没有独立的“高炉长”章节，因此涉及高炉长时，只把高炉工长条款作为其监督、审核和抽查范围，不额外编造高炉长职责。",
        "",
        "每题均包含：测试问题、标准答案、原文章节路径、期望命中的知识块 ID。标准答案尽量保持原文，不做常识扩写。建议逐题在 8093 提问后填写测试记录。",
        "",
        f"- 章节汇总题：{len(topics)} 题。",
        f"- 原子条款题：{len(leaves)} 题。",
        f"- 合计：{len(topics) + len(leaves)} 题。",
        "",
        "测试记录建议：`检索命中：通过/失败；答案完整性：通过/部分/失败；是否出现原文外补写：是/否`。",
        "",
        "## A. 章节汇总题",
        "",
    ]

    topic_number = 0
    for regulation in sorted(grouped_topics):
        lines.extend([f"### {regulation}", ""])
        for chunk in sorted(grouped_topics[regulation], key=lambda item: (item["section_code"], item["source_block_start"])):
            topic_number += 1
            qid = f"FG-T-{topic_number:04d}"
            lines.extend(
                [
                    f"#### {qid} {chunk['title']}",
                    "",
                    f"- 测试问题：请完整说明《三规二制》中高炉工长“{chunk['title']}”的全部规定。",
                    f"- 标准答案：{chunk['content'].replace(chr(10), '<br>')}",
                    f"- 原文章节：`{chunk['section_code'] or '未编号'}`；路径：`{' > '.join(chunk['hierarchy_path'])}`。",
                    f"- 期望知识块：`{chunk['chunk_id']}`（topic）。",
                    "- 测试记录：检索命中 `[ ]`；答案完整 `[ ]`；无原文外补写 `[ ]`。",
                    "",
                ]
            )

    lines.extend(["## B. 原子条款题", ""])
    atomic_number = 0
    for regulation in sorted(grouped_leaves):
        lines.extend([f"### {regulation}", ""])
        for chunk in sorted(grouped_leaves[regulation], key=lambda item: item["source_block_start"]):
            atomic_number += 1
            qid = f"FG-A-{atomic_number:04d}"
            focus = focus_text(chunk["content"])
            path = parent_path(chunk)
            if "|" in chunk["content"]:
                question = f"《三规二制》中高炉工长“{path}”对应表格列出了哪些参数、要求或记录内容？"
            else:
                question = f"高炉工长在“{path}”中，关于“{focus}”需要记住什么？请按原文回答。"
            lines.extend(
                [
                    f"#### {qid} {chunk['section_code'] or '表格/未编号条款'}",
                    "",
                    f"- 测试问题：{question}",
                    f"- 标准答案：{chunk['content'].replace(chr(10), '<br>')}",
                    f"- 原文章节：`{chunk['section_code'] or '未编号/表格'}`；路径：`{' > '.join(chunk['hierarchy_path']) or chunk['title']}`。",
                    f"- 期望知识块：`{chunk['chunk_id']}`（atomic）。",
                    "- 测试记录：检索命中 `[ ]`；答案完整 `[ ]`；无原文外补写 `[ ]`。",
                    "",
                ]
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"topics={topic_number} atomic={atomic_number} total={topic_number + atomic_number}")
    print(f"output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

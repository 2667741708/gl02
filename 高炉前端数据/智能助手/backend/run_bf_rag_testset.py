from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from bf_knowledge_rag import DEFAULT_DB_PATH, search_knowledge


def load_cases(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        cases = []
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError(f"jsonl line {line_no} must be an object")
                cases.append(item)
        return cases
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("testset must be a JSON array")
    return data


def run_case(case: dict[str, Any], db_path: Path, top_k: int, mode: str) -> dict[str, Any]:
    question = str(case["question"])
    expected_intent = str(case.get("expected_intent") or "")
    expected_intents = list(
        case.get("expected_intents")
        or case.get("acceptable_intents")
        or ([expected_intent] if expected_intent else [])
    )
    expected_categories = list(case.get("expected_categories") or [])
    expected_sources = list(case.get("expected_sources") or [])

    start = time.perf_counter()
    pack = search_knowledge(question, db_path=db_path, top_k=top_k, mode=mode)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

    evidence = pack.get("evidence") or []
    intent = (pack.get("intent") or {}).get("intent_type")
    top_categories = [item.get("knowledge_category") for item in evidence[:3]]
    top_sources = [item.get("source_file") for item in evidence[:3]]
    top1_category = top_categories[0] if top_categories else None
    top1_source = top_sources[0] if top_sources else None

    intent_ok = not expected_intents or intent in expected_intents
    if "condition_diagnosis" in expected_intents and intent == "mixed":
        intent_ok = True
    category_top1_ok = not expected_categories or top1_category in expected_categories
    category_top3_ok = not expected_categories or any(cat in expected_categories for cat in top_categories)
    source_top3_ok = not expected_sources or any(source in expected_sources for source in top_sources)
    ok = intent_ok and category_top3_ok and (source_top3_ok if expected_sources else True)

    return {
        "id": case.get("id"),
        "group": case.get("group"),
        "difficulty": case.get("difficulty"),
        "query_style": case.get("query_style"),
        "question": question,
        "expected_intent": expected_intent,
        "expected_intents": expected_intents,
        "intent": intent,
        "top1_source": top1_source,
        "top1_category": top1_category,
        "top3_sources": top_sources,
        "top3_categories": top_categories,
        "elapsed_ms": elapsed_ms,
        "retrieval_mode": pack.get("retrieval_mode"),
        "vector_enabled": pack.get("vector_enabled"),
        "candidate_counts": pack.get("candidate_counts"),
        "intent_ok": intent_ok,
        "category_top1_ok": category_top1_ok,
        "category_top3_ok": category_top3_ok,
        "source_top3_ok": source_top3_ok,
        "ok": ok,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get("group") or "unknown"), []).append(row)

    def pct(n: int, d: int) -> float:
        return round((n / d * 100) if d else 0.0, 1)

    def summarize_bucket(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "total": len(items),
            "ok": sum(1 for item in items if item["ok"]),
            "ok_rate": pct(sum(1 for item in items if item["ok"]), len(items)),
            "intent_ok": sum(1 for item in items if item["intent_ok"]),
            "top1_category_ok": sum(1 for item in items if item["category_top1_ok"]),
            "top3_category_ok": sum(1 for item in items if item["category_top3_ok"]),
            "avg_ms": round(sum(item["elapsed_ms"] for item in items) / len(items), 1),
            "max_ms": max(item["elapsed_ms"] for item in items),
        }

    summary_by_group = {group: summarize_bucket(items) for group, items in groups.items()}
    by_difficulty: dict[str, list[dict[str, Any]]] = {}
    by_query_style: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_difficulty.setdefault(str(row.get("difficulty") or "unspecified"), []).append(row)
        by_query_style.setdefault(str(row.get("query_style") or "unspecified"), []).append(row)

    total = len(rows)
    return {
        "total": total,
        "ok": sum(1 for row in rows if row["ok"]),
        "ok_rate": pct(sum(1 for row in rows if row["ok"]), total),
        "intent_ok": sum(1 for row in rows if row["intent_ok"]),
        "intent_ok_rate": pct(sum(1 for row in rows if row["intent_ok"]), total),
        "top1_category_ok": sum(1 for row in rows if row["category_top1_ok"]),
        "top1_category_ok_rate": pct(sum(1 for row in rows if row["category_top1_ok"]), total),
        "top3_category_ok": sum(1 for row in rows if row["category_top3_ok"]),
        "top3_category_ok_rate": pct(sum(1 for row in rows if row["category_top3_ok"]), total),
        "avg_ms": round(sum(row["elapsed_ms"] for row in rows) / total, 1) if total else 0,
        "max_ms": max((row["elapsed_ms"] for row in rows), default=0),
        "groups": summary_by_group,
        "difficulty": {name: summarize_bucket(items) for name, items in by_difficulty.items()},
        "query_style": {name: summarize_bucket(items) for name, items in by_query_style.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run blast furnace RAG test set.")
    parser.add_argument("testset", help="Path to JSON test set.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="兼容旧参数；当前 RAG 固定读取 PostgreSQL bf_assistant.rag_* 表。")
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--mode", choices=["keyword", "vector", "hybrid"], default="hybrid")
    parser.add_argument("--output", choices=["summary", "json"], default="json")
    args = parser.parse_args()

    cases = load_cases(Path(args.testset))
    rows = [run_case(case, Path(args.db_path), args.top_k, args.mode) for case in cases]
    result = {"summary": summarize(rows), "rows": rows}
    payload = result if args.output == "json" else result["summary"]
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2 if args.output == "json" else None)
    print()


if __name__ == "__main__":
    main()

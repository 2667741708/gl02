"""Read-only QA knowledge manifest audit; emits metadata, never document text or secrets."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

DOCUMENT_FIELDS = ('doc_id', 'title', 'knowledge_category', 'version', 'authority_level',
                   'content_hash', 'created_at', 'updated_at', 'text_length')
SAMPLE_FIELDS = ('chunk_id', 'chunk_type', 'content_hash', 'text_length')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--candidate-source", type=Path)
    args = parser.parse_args()
    config = json.loads((args.root / "tools/service_configs/22012_BFV4PreviewProxy8093.json").read_text(encoding="utf-8-sig"))
    for key, value in (config.get("env") or {}).items():
        if key.startswith(("BF_ASSISTANT_PG", "GL02_PG", "PG")):
            os.environ[key] = str(value)
    sys.path.insert(0, str(args.root / "高炉前端数据/智能助手/backend"))
    from qa_readonly_pg import readonly_pg_connect
    with readonly_pg_connect() as conn:
        rows = conn.execute(
            "SELECT doc_id, title, knowledge_category, version, authority_level, "
            "content_hash, created_at, updated_at, length(full_text) AS text_length "
            "FROM rag_document ORDER BY doc_id LIMIT 200"
        ).fetchall()
        counts = conn.execute(
            "SELECT authority_level, count(*) AS chunks FROM rag_chunk GROUP BY authority_level"
        ).fetchall()
        hierarchy = conn.execute("SELECT to_regclass('bf_assistant.rag_hierarchical_chunk') AS relation").fetchone()
        chapters = []
        if hierarchy and hierarchy["relation"]:
            chapters = conn.execute(
                "SELECT chapter_code, chapter_title, regulation_type, granularity, count(*) AS chunks, "
                "sum(length(content)) AS text_length FROM bf_assistant.rag_hierarchical_chunk "
                "GROUP BY chapter_code, chapter_title, regulation_type, granularity "
                "ORDER BY chapter_code, regulation_type, granularity LIMIT 400"
            ).fetchall()
        samples = conn.execute(
            "SELECT chunk_id, chunk_type, content_hash, length(content) AS text_length "
            "FROM rag_chunk WHERE doc_id = %s ORDER BY chunk_id LIMIT 5",
            ("bf_three_rules_two_systems_20260712",)
        ).fetchall()
        document_checks = []
        if args.candidate_source:
            import importlib.util
            spec = importlib.util.spec_from_file_location("qa_document_candidate", args.candidate_source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            from assistant_pg import PgCompatConnection
            for question in ("完整列出高炉工长安全操作规程原文", "列出《三规二制》完整目录", "列出《高炉事故处理》全文"):
                outcome = module.execute_document_question(PgCompatConnection(conn), question, {"intents": ["document_knowledge"]})
                document_checks.append({"completion": {key: outcome['completion'].get(key) for key in ('complete', 'terminal_state', 'reason')},
                                        "answer_chars": len(outcome["answer"])})
        print(json.dumps({"schema": "bf.qa.knowledge-manifest-audit.v1",
            "documents": [{key: r[key] for key in DOCUMENT_FIELDS if key in r} for r in rows], "chunk_counts": [dict(r) for r in counts],
            "hierarchy_exists": bool(hierarchy and hierarchy["relation"]), "chapters": [dict(r) for r in chapters],
            "samples": [{key: r[key] for key in SAMPLE_FIELDS if key in r} for r in samples], "document_checks": document_checks},
            ensure_ascii=False, default=str))
if __name__ == "__main__":
    main()

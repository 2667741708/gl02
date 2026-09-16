"""Check indexed originals against full authority text without publishing either."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

def compact(value): return re.sub(r"\s+", "", str(value or ""))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((args.root / "tools/service_configs/22012_BFV4PreviewProxy8093.json").read_text(encoding="utf-8-sig"))
    for key, value in config.get("env", {}).items():
        if key.startswith(("BF_ASSISTANT_PG", "GL02_PG", "PG")): os.environ[key] = str(value)
    sys.path.insert(0, str(args.root / "高炉前端数据/智能助手/backend"))
    from assistant_pg import raw_pg_connect
    with raw_pg_connect() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        doc = connection.execute("SELECT full_text, content_hash FROM rag_document WHERE doc_id = %s", ("bf_three_rules_two_systems_20260712",)).fetchone()
        rows = connection.execute("SELECT chunk_id, chunk_type, content, enriched_content FROM rag_chunk WHERE doc_id = %s", ("bf_three_rules_two_systems_20260712",)).fetchall()
        full = compact(doc["full_text"])
        counts, missing = {}, []
        for row in rows:
            kind = row["chunk_type"]
            match = compact(row["content"]) in full
            bucket = counts.setdefault(kind, {"total":0, "in_authority_text":0, "all_original_lines_in_authority":0})
            bucket["total"] += 1
            bucket["in_authority_text"] += int(match)
            bucket["all_original_lines_in_authority"] += int(all(compact(line) in full for line in row["content"].splitlines() if compact(line)))
            if not match: missing.append({"chunk_id":row["chunk_id"], "kind":kind, "content_sha256":hashlib.sha256(row["content"].encode("utf-8")).hexdigest()})
        atomic_text = compact("\n".join(row["content"] for row in rows if row["chunk_type"] == "three_rules_atomic"))
        source_lines = [line for line in doc["full_text"].splitlines() if compact(line)]
        uncovered_lines = [{"line_index":i, "sha256":hashlib.sha256(line.encode("utf-8")).hexdigest(), "numbered_leaf":bool(re.match(r"^\s*\d+\.\d+",line))} for i,line in enumerate(source_lines) if compact(line) not in atomic_text]
    print(json.dumps({"schema":"bf.qa.document-provenance-readonly.v1", "source_hash":doc["content_hash"],
                      "counts":counts,"missing":missing, "database_writes":0,"model_calls":0,"question_posts":0,
                      "source_nonempty_lines":len(source_lines),"uncovered_source_lines":uncovered_lines,
                      "scope":"Whitespace-only normalization; membership is not independent index completeness."}, ensure_ascii=False))

if __name__ == "__main__": main()

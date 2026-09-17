"""Evaluate document candidate on actual read-only KB; emit only sanitized coverage."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

def normalize(text):
    return re.sub(r"[\s。．，,；;：:‘’“”\"'\*#]", "", text.replace("<br>", "\n"))

class Rows:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None

class CachedReads:
    def __init__(self, connection): self.connection, self.cache = connection, {}
    def execute(self, sql, args=()):
        if not sql.lstrip().upper().startswith("SELECT "):
            raise ValueError("Only SELECT is allowed")
        key = (sql, tuple(args))
        if key not in self.cache:
            self.cache[key] = self.connection.execute(sql, args).fetchall()
        return Rows(self.cache[key])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--candidate-source", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--summary", action="store_true", help="Emit counts and gaps only, without successful per-case rows")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    config = json.loads((args.root / "tools/service_configs/22012_BFV4PreviewProxy8093.json").read_text(encoding="utf-8-sig"))
    for key, value in (config.get("env") or {}).items():
        if key.startswith(("BF_ASSISTANT_PG", "GL02_PG", "PG")):
            os.environ[key] = str(value)
    sys.path.insert(0, str(args.root / "高炉前端数据/智能助手/backend"))
    from assistant_pg import PgCompatConnection
    from qa_readonly_pg import readonly_pg_connect
    sys.path.insert(0, str(args.candidate_source.parent))
    spec = importlib.util.spec_from_file_location("qa_candidate", args.candidate_source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.offset < 0 or (args.limit is not None and args.limit <= 0):
        raise ValueError("Invalid read-only batch bounds")
    cases = cases[args.offset:None if args.limit is None else args.offset + args.limit]
    results = []
    with readonly_pg_connect() as raw:
        connection = CachedReads(PgCompatConnection(raw))
        for row in cases:
            if row.get("oracle_blocked"):
                results.append({"oracle_id": row["oracle_id"], "state": "oracle_blocked"})
                continue
            outcome = module.execute_document_question(connection, row["question"], {"intents": ["document_knowledge"]})
            normalized = normalize(outcome.get("answer") or "")
            expected_parts = [normalize(part) for part in row["expected"].split("<br>") if normalize(part)]
            missing = [index for index, part in enumerate(expected_parts) if part not in normalized]
            completion = outcome.get("completion") or {}
            results.append({"oracle_id": row["oracle_id"], "state": "coverage_candidate_pass_pending_semantic_review" if not missing and completion.get("terminal_state") == "completed" else "coverage_or_contract_gap", "expected_parts": len(expected_parts), "missing_part_indices": missing, "completion_reason": completion.get("reason"), "terminal_state": completion.get("terminal_state"), "answer_chars": len(outcome.get("answer") or "")})
    counts = {state: sum(row["state"] == state for row in results) for state in sorted({row["state"] for row in results})}
    visible_results = [row for row in results if row["state"] == "coverage_or_contract_gap"] if args.summary else results
    print(json.dumps({"schema":"bf.qa.knowledge-candidate-readonly.v1", "candidate_sha256":hashlib.sha256(args.candidate_source.read_bytes()).hexdigest(), "total":len(results), "counts":counts, "model_calls":0, "question_posts":0, "database_writes":0, "results":visible_results}, ensure_ascii=False))

if __name__ == "__main__": main()

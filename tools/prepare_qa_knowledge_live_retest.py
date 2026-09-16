"""Prepare a fresh knowledge retest round, excluding conflicts and legacy claims."""
import argparse
import json
import re
from pathlib import Path
from audit_qa_knowledge_oracles import parse_cases, inspect, ROOT

LEGACY_EXCLUDED = {"TPL-10C8C8FAF2C694EF", "TPL-342113EAB17420C6", "TPL-6FEC8B7F06A3D59B", "TPL-A5F5920FB3425C53", "TPL-DAA60976527882AB", "TPL-DFAFBFA898C6552F", "TPL-E1C7A67C947531E9", "TPL-F2180C7D419DA198"}

def normalize(text): return re.sub(r"\s+", "", text)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = parse_cases((ROOT / "PT/三规二制高炉长工长知识库测试题库.md").read_text(encoding="utf-8"))
    blocked = {row["oracle_id"] for row in inspect(rows) if row["state"] == "oracle_blocked"}
    inventory = json.loads((ROOT / "tests/qa_regression/templates.v1.json").read_text(encoding="utf-8"))
    entries = inventory.get("cases") or inventory.get("rows") or inventory.get("items")
    if entries is None: raise ValueError("inventory schema requires explicit case rows")
    by_question = {}
    for entry in entries:
        by_question.setdefault(normalize(entry.get("prompt", "")), []).append(entry["case_id"])
    reviews, exclusions = [], []
    for row in rows:
        ids = by_question.get(normalize(row["question"]), [])
        reason = "oracle_conflict" if row["oracle_id"] in blocked else ("legacy_claim_excluded" if LEGACY_EXCLUDED.intersection(ids) else None)
        if reason:
            exclusions.append({"oracle_id": row["oracle_id"], "reason": reason})
            continue
        if not ids: raise ValueError(f"No source inventory match: {row['oracle_id']}")
        reviews.append({"case_id": "TPL-KB-" + row["oracle_id"], "original_case_ids": ids, "oracle_id": row["oracle_id"], "question": row["question"], "expected": {"original_text": row["expected"], "source_reference_id": row["reference_id"], "criteria": ["original source only", "complete expected text", "no live calls", "explicit completion", "exact turn projection"]}})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema":"bf.qa.targeted-cases.v1","requirement_id":"REQ-QA-FULL-ISSUE-INVENTORY-20260916","round":"knowledge-routing-v11-20260916-r1","reviews":reviews,"exclusions":exclusions,"legacy_claims_never_replayed":sorted(LEGACY_EXCLUDED)}, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok":True,"total":len(rows),"fresh_round_cases":len(reviews),"excluded":len(exclusions)}))

if __name__ == "__main__": main()

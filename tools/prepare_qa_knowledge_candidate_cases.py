"""Prepare public document oracles for read-only candidate evaluation, no conversations."""
import argparse
import json
from pathlib import Path
from audit_qa_knowledge_oracles import parse_cases, inspect, ROOT

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = parse_cases((ROOT / "PT/三规二制高炉长工长知识库测试题库.md").read_text(encoding="utf-8"))
    blocked = {row["oracle_id"] for row in inspect(rows) if row["state"] == "oracle_blocked"}
    for row in rows:
        row["oracle_blocked"] = row["oracle_id"] in blocked
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok":True,"cases":len(rows),"oracle_blocked":len(blocked)}))

if __name__ == "__main__": main()

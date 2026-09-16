"""Print a bounded answer and tool metadata for local manual review; never conversations."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    for path in sorted(args.directory.glob("TPL-*.json")):
        row = json.loads(path.read_text(encoding="utf-8-sig"))
        final = row.get("final") or {}
        print(json.dumps({
            "case_id": row["case_id"], "answer": row.get("answer", "")[:5000],
            "error": row.get("error"), "route": final.get("answer_route"),
            "terminated": row.get("terminated"),
            "tools": [{key: item.get(key) for key in ("tool", "name", "ok", "error", "arguments")} for item in row.get("tool_starts", [])],
            "results": [{key: item.get(key) for key in ("tool", "name", "ok", "error", "result", "public_trace")} for item in row.get("tool_results", [])],
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()

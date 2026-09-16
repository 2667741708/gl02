"""Print a bounded answer and tool metadata for local manual review; never conversations."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--max-answer-chars", type=int, default=1800)
    args = parser.parse_args()
    for path in sorted(args.directory.glob("TPL-*.json")):
        row = json.loads(path.read_text(encoding="utf-8-sig"))
        if args.case_id and row["case_id"] not in args.case_id:
            continue
        final = row.get("final") or {}
        print(json.dumps({
            "case_id": row["case_id"], "answer": row.get("answer", "")[:args.max_answer_chars],
            "answer_chars": len(row.get("answer", "")),
            "error": row.get("error"), "route": final.get("answer_route"),
            "completion": final.get("completion"), "model_requests": final.get("model_request_count"),
            "terminated": row.get("terminated"),
            "tools": [{key: item.get(key) for key in ("tool", "name", "ok", "error", "arguments")} for item in row.get("tool_starts", [])],
            "results": [{key: item.get(key) for key in ("tool", "name", "ok", "error")} for item in row.get("tool_results", [])],
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()

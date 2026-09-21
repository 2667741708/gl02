"""Create a sanitized transport receipt for a completed scheduled QA retest."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(plan_path: Path, batch_dir: Path) -> dict:
    plan = read(plan_path)
    cases = plan["cases"]
    prior = [dict(record, source="prior_completed") for record in plan.get("prior_completed_records") or []]
    rows = []
    for case in cases:
        case_id = case["case_id"]
        claim = batch_dir / f"{case_id}.claim"
        result_path = batch_dir / f"{case_id}.json"
        if not claim.exists() or not result_path.exists():
            continue
        result = read(result_path)
        final = result.get("final") or {}
        rows.append({
            "source": "current_collection",
            "case_id": case_id,
            "claim_sha256": sha(claim),
            "result_sha256": sha(result_path),
            "request_count": result.get("request_count"),
            "automatic_retries": result.get("automatic_retries"),
            "http_status": result.get("http_status"),
            "terminated": result.get("terminated") is True,
            "done": result.get("done") is True,
            "has_answer": bool(result.get("answer")),
            "answer_sha256": hashlib.sha256(str(result.get("answer") or "").encode("utf-8")).hexdigest(),
            "answer_route": str(final.get("answer_route") or "unclassified"),
            "model": str(result.get("model") or ""),
            "program_commit": str(result.get("program_commit") or ""),
            "transport_error": str(result.get("transport_error") or ""),
            "error_code": str(result.get("error_code") or ""),
        })
    total = int(plan.get("authorized_case_count") or len(cases))
    prior_valid = all(
        row.get("proven_complete") is True
        and row.get("request_count") == 1
        and row.get("automatic_retries") == 0
        and row.get("http_status") == 200
        and row.get("transport_error") is False
        and row.get("terminated") is True
        and row.get("done") is True
        for row in prior
    )
    transport_passed = (
        len(rows) == len(cases)
        and len(rows) + len(prior) == total
        and prior_valid
        and all(row["request_count"] == 1 for row in rows)
        and all(row["automatic_retries"] == 0 for row in rows)
        and all(row["http_status"] == 200 for row in rows)
        and all(row["terminated"] and row["done"] for row in rows)
        and not any(row["transport_error"] for row in rows)
    )
    return {
        "schema": "bf.qa.v52-scheduled-retest-collection.v1",
        "requirement_id": plan["requirement_id"],
        "execution_id": plan["execution_id"],
        "plan_sha256": sha(plan_path),
        "total": total,
        "current_plan_total": len(cases),
        "prior_completed_count": len(prior),
        "claimed": len(rows) + len(prior),
        "result_count": len(rows) + len(prior),
        "single_request_count": len(prior) + sum(row["request_count"] == 1 for row in rows),
        "automatic_retry_count": sum(int(row["automatic_retries"] or 0) for row in rows),
        "http_200_count": len(prior) + sum(row["http_status"] == 200 for row in rows),
        "terminated_count": len(prior) + sum(row["terminated"] for row in rows),
        "done_count": len(prior) + sum(row["done"] for row in rows),
        "nonempty_answer_count": sum(row["has_answer"] for row in rows),
        "route_counts": dict(sorted(Counter(row["answer_route"] for row in rows).items())),
        "model_labels": sorted({row["model"] for row in rows if row["model"]}),
        "program_commits": sorted({row["program_commit"] for row in rows if row["program_commit"]}),
        "transport_error_counts": dict(sorted(Counter(row["transport_error"] for row in rows if row["transport_error"]).items())),
        "error_code_counts": dict(sorted(Counter(row["error_code"] for row in rows if row["error_code"]).items())),
        "transport_gate_passed": transport_passed,
        "semantic_acceptance": "pending_full_answer_review",
        "nonempty_answer_is_not_semantic_pass": True,
        "records": prior + rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = summarize(args.plan, args.batch)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: value[key] for key in (
        "total", "result_count", "transport_gate_passed", "semantic_acceptance"
    )}, ensure_ascii=False))
    return 0 if value["transport_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

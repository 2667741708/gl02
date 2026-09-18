"""Audit once-only production knowledge results; publish no raw conversation data."""
import argparse
import hashlib
import json
from pathlib import Path
from check_qa_knowledge_candidate_readonly import normalize


def review(row, case):
    final = row.get("final") or {}
    expected = case["expected"]
    answer = row.get("answer") or ""
    missing = [i for i, part in enumerate(expected["original_text"].split("<br>"))
               if normalize(part) and normalize(part) not in normalize(answer)]
    reasons = []
    if missing: reasons.append("expected_original_text_missing")
    if row.get("request_count") != 1: reasons.append("request_count_not_one")
    if row.get("http_status") != 200 or not row.get("terminated") or "done" not in row.get("events", []):
        reasons.append("transport_incomplete")
    if final.get("answer_route") != "verified_document_knowledge": reasons.append("wrong_route")
    if row.get("tool_starts") or final.get("tool_used"): reasons.append("unexpected_external_tools")
    if (final.get("completion") or {}).get("terminal_state") != "completed": reasons.append("not_completed")
    messages = final.get("messages") or []
    if final.get("messages_projection") != "turn" or len(messages) != 2:
        reasons.append("turn_projection_invalid")
    elif ([m.get("role") for m in messages] != ["user", "assistant"]
          or messages[0].get("content") != case["question"] or messages[1].get("content") != answer):
        reasons.append("turn_content_mismatch")
    manifest = final.get("knowledge_manifest") or []
    if (len(manifest) != 1 or manifest[0].get("doc_id") != "bf_three_rules_two_systems_20260712"
        or manifest[0].get("title") != "冀钢炼铁三规二制"
        or manifest[0].get("version") != "v1.0-hierarchical"
        or manifest[0].get("content_hash") != "96fdc3f9ec0a39c226667247ef16295bfa9707e56438c162a7958db96a127b6e"
        or not expected["source_reference_id"].startswith(manifest[0].get("doc_id", "") + "_")):
        reasons.append("source_authority_or_version_invalid")
    return {"case_id": case["case_id"], "oracle_id": case["oracle_id"],
            "state": "contract_and_original_coverage_verified" if not reasons else "failed_review",
            "reasons": reasons, "missing_part_indices": missing, "answer_chars": len(answer),
            "manifest_present": bool(manifest), "request_count": row.get("request_count"),
            "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    progress = json.loads((args.directory / "progress.json").read_text(encoding="utf-8"))
    results = []
    for case in plan["reviews"]:
        path = args.directory / (case["case_id"] + ".json")
        if not path.exists():
            results.append({"case_id": case["case_id"], "oracle_id": case["oracle_id"], "state": "missing_or_uncertain", "reasons": ["do_not_replay"]})
        else:
            results.append(review(json.loads(path.read_text(encoding="utf-8")), case))
    counts = {state: sum(r["state"] == state for r in results) for state in sorted({r["state"] for r in results})}
    report = {"schema": "bf.qa.knowledge-live-review.v1", "checked_at": "2026-09-16",
              "requirement_id": "REQ-QA-FULL-ISSUE-INVENTORY-20260916",
              "production_commit": "9c52d69e2d027bc1dccc42cfd94c65254ee6e803",
              "round": plan["round"], "source_total": len(results) + len(plan["exclusions"]),
              "requests": progress["requests"], "automatic_retries": progress["automatic_retries"],
              "state": progress["state"], "counts": counts, "oracle_blocked": plan["exclusions"],
              "scope": "Original-text coverage and route/transport/completion/turn contracts. Full independent source-boundary semantic review remains separate.",
              "results": results}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("source_total", "requests", "automatic_retries", "state", "counts")}, ensure_ascii=False))


if __name__ == "__main__": main()

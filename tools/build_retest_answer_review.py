#!/usr/bin/env python3
"""Build a sanitized, hash-bound review index for one completed QA retest.

Private prompts, answers, tool payloads and production identifiers are inputs only.
The output contains review decisions and hashes, so it is safe to commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA = "bf.qa.retest-answer-review.v1"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"manual decision line {line_no} is not an object")
        rows.append(value)
    return rows


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _single_route(row: dict[str, Any]) -> str:
    final = row.get("final")
    if not isinstance(final, dict):
        return "unclassified"
    route = final.get("answer_route")
    return str(route) if route else "unclassified"


def _knowledge_status(contract: dict[str, Any], scope: dict[str, Any]) -> tuple[str, list[str]]:
    contract_state = str(contract.get("state") or "missing_contract_state")
    scope_state = str(scope.get("independent_source_scope_state") or "missing_scope_state")
    reasons = sorted({str(item) for item in scope.get("scope_reasons", []) if item})
    if contract_state == "oracle_blocked":
        return "oracle_blocked", ["conflicting_original_oracle"]
    if scope_state == "scope_contract_mismatch":
        return "scope_contract_alert", reasons or ["scope_contract_mismatch"]
    if scope_state != "scope_contract_verified_pending_semantic_review":
        return "scope_contract_alert", [scope_state]
    return "pending_semantic_review", []


def build_review(
    results_path: Path,
    manual_path: Path,
    knowledge_contract_path: Path,
    knowledge_scope_path: Path,
) -> dict[str, Any]:
    payload = _read_json(results_path)
    results = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results:
        raise ValueError("results must contain a non-empty rows array")

    manual_rows = _read_jsonl(manual_path)
    contract_rows = _read_json(knowledge_contract_path)
    scope_rows = _read_json(knowledge_scope_path)
    if not isinstance(contract_rows, list) or not isinstance(scope_rows, list):
        raise ValueError("knowledge inputs must be arrays")

    manual = {int(item["index"]): item for item in manual_rows}
    contract = {int(item["index"]): item for item in contract_rows}
    scope = {int(item["index"]): item for item in scope_rows}
    if len(manual) != len(manual_rows):
        raise ValueError("duplicate manual review index")
    if len(contract) != len(contract_rows) or len(scope) != len(scope_rows):
        raise ValueError("duplicate knowledge review index")
    if set(contract) != set(scope):
        raise ValueError("knowledge contract and scope indexes differ")
    if set(manual) & set(contract):
        raise ValueError("manual and knowledge review indexes overlap")
    expected = set(range(len(results)))
    reviewed = set(manual) | set(contract)
    if reviewed != expected:
        missing = sorted(expected - reviewed)
        extra = sorted(reviewed - expected)
        raise ValueError(f"review coverage mismatch missing={missing[:5]} extra={extra[:5]}")

    records: list[dict[str, Any]] = []
    for index, row in enumerate(results):
        if not isinstance(row, dict):
            raise ValueError(f"result {index} is not an object")
        case_id = str(row.get("case_id") or "")
        answer = str(row.get("answer") or "")
        result_sha = str(row.get("result_file_sha256") or "")
        if not case_id or not answer or len(result_sha) != 64:
            raise ValueError(f"result {index} lacks case id, answer or result hash")
        if row.get("request_count") != 1 or row.get("automatic_retries") != 0:
            raise ValueError(f"result {index} was replayed or retried")
        if row.get("http_status") != 200 or not row.get("done"):
            raise ValueError(f"result {index} did not complete successfully")
        answer_sha = _sha256_text(answer)
        base = {
            "index": index,
            "case_id": case_id,
            "result_sha256": result_sha,
            "answer_sha256": answer_sha,
            "answer_route": _single_route(row),
        }
        if index in manual:
            decision = manual[index]
            if (decision.get("case_id") != case_id
                    or decision.get("result_sha256") != result_sha
                    or decision.get("answer_sha256") != answer_sha
                    or decision.get("full_answer_read") is not True):
                raise ValueError(f"manual decision {index} is not bound to the full result")
            base.update({
                "review_basis": "full_answer_manual_review",
                "review_status": str(decision.get("status") or "missing_status"),
                "issue_class": str(decision.get("issue_class") or "unclassified"),
                "reason_codes": [],
            })
        else:
            contract_item = contract[index]
            scope_item = scope[index]
            if (contract_item.get("case_id") != case_id
                    or scope_item.get("case_id") != case_id
                    or contract_item.get("answer_sha256") != answer_sha
                    or scope_item.get("answer_sha256") != answer_sha):
                raise ValueError(f"knowledge review {index} is not bound to the full answer")
            status, reasons = _knowledge_status(contract_item, scope_item)
            base.update({
                "review_basis": "exact_source_coverage_and_scope_contract",
                "review_status": status,
                "issue_class": "knowledge_source_governance" if status != "pending_semantic_review" else "none_recorded",
                "reason_codes": reasons,
            })
        records.append(base)

    model_names = sorted({str(row.get("model") or "") for row in results})
    if len(model_names) != 1 or not model_names[0]:
        raise ValueError(f"expected one locked model label, got {model_names}")
    manual_status = Counter(item["review_status"] for item in records if item["review_basis"] == "full_answer_manual_review")
    knowledge_status = Counter(item["review_status"] for item in records if item["review_basis"] != "full_answer_manual_review")
    issue_classes = Counter(item["issue_class"] for item in records if item["issue_class"] not in {"none", "none_recorded"})
    routes = Counter(item["answer_route"] for item in records)
    return {
        "schema": SCHEMA,
        "requirement_id": "REQ-QA-RETEST-ANSWER-ROUTING-20260921",
        "transport": {
            "result_count": len(results),
            "http_200_count": sum(row.get("http_status") == 200 for row in results),
            "completed_count": sum(bool(row.get("done")) for row in results),
            "single_request_count": sum(row.get("request_count") == 1 for row in results),
            "automatic_retry_count": sum(int(row.get("automatic_retries") or 0) for row in results),
            "locked_model_label_sha256": _sha256_text(model_names[0]),
            "model_label_count": 1,
        },
        "review_coverage": {
            "per_answer_records": len(records),
            "full_answer_manual_review": len(manual),
            "knowledge_exact_source_contract_review": len(contract),
            "semantic_pass_must_not_be_inferred_from_transport_or_nonempty_answer": True,
        },
        "manual_status_counts": dict(sorted(manual_status.items())),
        "knowledge_status_counts": dict(sorted(knowledge_status.items())),
        "issue_class_counts": dict(sorted(issue_classes.items(), key=lambda item: (-item[1], item[0]))),
        "answer_route_counts": dict(sorted(routes.items(), key=lambda item: (-item[1], item[0]))),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--manual", type=Path, required=True)
    parser.add_argument("--knowledge-contract", type=Path, required=True)
    parser.add_argument("--knowledge-scope", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = build_review(args.results, args.manual, args.knowledge_contract, args.knowledge_scope)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "output": str(args.output),
        "records": review["review_coverage"]["per_answer_records"],
        "manual_status_counts": review["manual_status_counts"],
        "knowledge_status_counts": review["knowledge_status_counts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

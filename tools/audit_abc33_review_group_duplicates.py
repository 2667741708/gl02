"""Audit repeated sensor variables across ABC33 operator review groups."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any


GROUPS = ("main_metrics", "body_metrics", "cooling_metrics", "other_metrics")


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def audit(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    latest = get_json(f"{base}/api/furnace-rules/latest")
    rules = latest.get("rules") or []
    errors: list[dict[str, str]] = []
    affected: dict[str, dict[str, list[str]]] = {}
    occurrence_count = 0
    semantic_count = 0
    missing_semantics: list[dict[str, str]] = []
    longest_semantic = {"rule_id": "", "variable_name": "", "length": 0}

    for rule in rules:
        rule_id = str(rule.get("rule_id") or "")
        try:
            payload = get_json(
                f"{base}/api/furnace-rules/{urllib.parse.quote(rule_id)}/detail"
            )
        except Exception as exc:  # pragma: no cover - production audit path
            errors.append({"rule_id": rule_id, "error": str(exc)})
            continue
        review = payload.get("sensor_review") or {}
        groups_by_variable: dict[str, list[str]] = defaultdict(list)
        for group in GROUPS:
            for metric in review.get(group) or []:
                variable = str(metric.get("variable_name") or "").strip()
                if variable:
                    groups_by_variable[variable].append(group)
                    occurrence_count += 1
                    semantic = str(metric.get("semantic_summary") or "").strip()
                    if semantic:
                        semantic_count += 1
                        if len(semantic) > int(longest_semantic["length"]):
                            longest_semantic = {
                                "rule_id": rule_id,
                                "variable_name": variable,
                                "length": len(semantic),
                            }
                    else:
                        missing_semantics.append(
                            {"rule_id": rule_id, "variable_name": variable, "group": group}
                        )
        duplicates = {
            variable: group_names
            for variable, group_names in sorted(groups_by_variable.items())
            if len(group_names) > 1
        }
        if duplicates:
            affected[rule_id] = duplicates

    duplicate_variables = {
        variable
        for duplicates in affected.values()
        for variable in duplicates
    }
    return {
        "schema_version": "abc33.review_group_duplicate_audit.v1",
        "base_url": base,
        "rule_count": len(rules),
        "detail_error_count": len(errors),
        "detail_errors": errors,
        "metric_occurrence_count": occurrence_count,
        "semantic_count": semantic_count,
        "missing_semantic_count": len(missing_semantics),
        "missing_semantics": missing_semantics,
        "longest_semantic": longest_semantic,
        "affected_rule_count": len(affected),
        "duplicate_variable_count": len(duplicate_variables),
        "duplicate_occurrence_count": sum(
            len(groups) - 1
            for duplicates in affected.values()
            for groups in duplicates.values()
        ),
        "affected_rules": affected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default="http://10.30.220.12:8093", help="8093 base URL"
    )
    parser.add_argument("--output", help="Optional UTF-8 JSON output file")
    parser.add_argument(
        "--require-clean", action="store_true", help="Fail when any duplicate remains"
    )
    args = parser.parse_args()
    result = audit(args.base_url)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)
    if result["rule_count"] != 33 or result["detail_error_count"]:
        return 1
    if args.require_clean and (
        result["affected_rule_count"] or result["missing_semantic_count"]
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

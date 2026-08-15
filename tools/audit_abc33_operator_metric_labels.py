"""Audit operator-visible sensor labels across all 33 ABC furnace-rule details."""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any


GROUPS = ("main_metrics", "body_metrics", "cooling_metrics", "other_metrics")


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def has_chinese(value: object) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(value or "")))


def audit(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    latest = get_json(f"{base}/api/furnace-rules/latest")
    rules = latest.get("rules") or []
    observed: dict[str, dict[str, Any]] = {}
    affected_rules: dict[str, set[str]] = defaultdict(set)
    errors: list[dict[str, str]] = []

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
        for group in GROUPS:
            for metric in review.get(group) or []:
                variable = str(metric.get("variable_name") or "").strip()
                label = str(metric.get("label") or "").strip()
                if not variable:
                    continue
                row = observed.setdefault(
                    variable,
                    {
                        "variable_name": variable,
                        "labels": set(),
                        "groups": set(),
                        "rule_ids": set(),
                    },
                )
                if label:
                    row["labels"].add(label)
                row["groups"].add(group)
                row["rule_ids"].add(rule_id)
                if not has_chinese(label) or label == variable:
                    affected_rules[rule_id].add(variable)

    rows = []
    for variable, row in sorted(observed.items()):
        labels = sorted(row["labels"])
        rows.append(
            {
                "variable_name": variable,
                "labels": labels,
                "groups": sorted(row["groups"]),
                "rule_ids": sorted(row["rule_ids"]),
                "operator_label_issue": not labels
                or all((not has_chinese(label) or label == variable) for label in labels),
            }
        )

    return {
        "schema_version": "abc33.operator_metric_label_audit.v1",
        "base_url": base,
        "rule_count": len(rules),
        "detail_error_count": len(errors),
        "detail_errors": errors,
        "unique_metric_count": len(rows),
        "issue_metric_count": sum(row["operator_label_issue"] for row in rows),
        "issue_metrics": [row for row in rows if row["operator_label_issue"]],
        "affected_rule_count": len(affected_rules),
        "affected_rules": {
            key: sorted(value) for key, value in sorted(affected_rules.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default="http://10.30.220.12:8093", help="8093 base URL"
    )
    parser.add_argument("--output", help="Optional UTF-8 JSON output file")
    args = parser.parse_args()
    result = audit(args.base_url)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)
    return 0 if result["rule_count"] == 33 and not result["detail_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

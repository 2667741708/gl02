from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def load_evaluator(root: Path):
    path = root / ".codex" / "skills" / "agent-tool-capability-evaluation" / "scripts" / "evaluate_mcp_gold_tasks.py"
    spec = importlib.util.spec_from_file_location("evaluate_mcp_gold_tasks", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load evaluator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-score a stored MCP gold live report without issuing another request.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    evaluator = load_evaluator(root)
    catalog = evaluator.load_catalog(root / "PT" / "智能体工具能力金标任务清单.v1.json")
    cases = {case["case_id"]: case for case in catalog["cases"]}
    report = json.loads(args.input.read_text(encoding="utf-8"))
    for row in report.get("rows") or []:
        case = cases[str(row["case_id"])]
        raw = row.get("raw") or {}
        checks = evaluator.evaluate_live_contract(case, raw)
        row["checks"] = checks
        row["status"] = evaluator.live_status(case, raw, checks)
        row["rescored_from"] = str(args.input)
        row["network_request_count_during_rescore"] = 0
    statuses = [str(row.get("status")) for row in report.get("rows") or []]
    report["summary"] = {
        "runs": len(statuses),
        "passed": statuses.count("passed"),
        "failed": statuses.count("failed"),
        "errors": statuses.count("error"),
        "not_supported": statuses.count("not_supported"),
        "oracle_invalid": statuses.count("oracle_invalid"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(evaluator.report_markdown(report), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(args.output), "summary": report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

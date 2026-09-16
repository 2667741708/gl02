"""Validate deterministic routing against public-template and synthetic contracts."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "tests" / "qa_regression" / "task_plan_contracts_20260916.json"
LEDGER_PATH = ROOT / "tests" / "qa_regression" / "question_ledger_20260916.json"
MODULE_PATH = ROOT / "高炉前端数据" / "智能助手" / "backend" / "qa_task_plan.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("qa_task_plan_contract_eval", MODULE_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("qa_task_plan module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate() -> dict[str, object]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    rows = {item["case_id"]: item for item in ledger["rows"]}
    planner = _load_module()
    failures: list[dict[str, object]] = []
    checked = 0
    for case in contract["cases"]:
        prompt = rows[case["case_id"]]["prompt"] if case.get("prompt_from_ledger") else case["prompt"]
        plan = planner.build_task_plan(prompt)
        mismatches = {}
        for field in ("primary_intent", "search_knowledge", "allow_prefetch", "allowed_tool_domains"):
            if plan[field] != case[field]:
                mismatches[field] = {"expected": case[field], "actual": plan[field]}
        if mismatches:
            failures.append({"case_id": case["case_id"], "mismatches": mismatches})
        checked += 1
    return {
        "ok": not failures,
        "requirement_id": contract["requirement_id"],
        "checked": checked,
        "failures": failures,
        "production_verified": False,
    }


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)

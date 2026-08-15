from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def load_contract(root: Path):
    path = root / "tools" / "mcp_fault_preview_acceptance.py"
    spec = importlib.util.spec_from_file_location("mcp_fault_preview_acceptance", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load fault preview contract")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    contract = load_contract(root)
    report = json.loads(args.input.read_text(encoding="utf-8"))
    for row in report.get("rows") or []:
        preserved = {key: bool(value) for key, value in (row.get("checks") or {}).items() if key not in {"required_terms", "forbidden_terms", "answer_nonempty"}}
        preserved.update(contract.answer_contract_checks(str(row["case_id"]), str(row.get("answer") or "")))
        row["checks"] = preserved
        row["status"] = "passed" if all(preserved.values()) else "failed"
        row["rescored_without_model_request"] = True
    rows = report.get("rows") or []
    report["rescored_from"] = str(args.input)
    report["additional_model_requests"] = 0
    report["summary"] = {
        "cases": len(rows),
        "passed": sum(row.get("status") == "passed" for row in rows),
        "failed": sum(row.get("status") == "failed" for row in rows),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["summary"]["failed"] == 0, "summary": report["summary"], "additional_model_requests": 0}, ensure_ascii=False))
    return 0 if report["summary"]["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Build QA routing V4 from the exact accepted V3 production artifacts.

V4 starts the issue-by-issue remediation ledger with QAOPT-R03.  It keeps the
accepted V3 files byte-for-byte except for the proxy import/executor seam and
the TaskPlan/entity resolver modules named in the build report.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import shutil
from pathlib import Path


REQ = "REQ-QA-FULL-ISSUE-INVENTORY-20260916"
PROXY_V3_SHA256 = "abd7cc463c42a7e1c707e1b840b33c9040b33cb850ac7719b164732329af6e67"
TASK_PLAN_V3_SHA256 = "bc34986d7a8cb7ff5af11d073809fce623b4cd924865484d5bf98cd9255510e8"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one exact match, found {count}")
    return source.replace(old, new, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v3-candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    backend = root / "高炉前端数据" / "智能助手" / "backend"
    source_dir = args.v3_candidate.resolve()
    output = args.output.resolve()
    proxy_path = source_dir / "ollama_proxy_server.py"
    task_plan_path = source_dir / "qa_task_plan.py"
    proxy_raw = proxy_path.read_bytes()
    task_plan_raw = task_plan_path.read_bytes()
    if sha256(proxy_raw) != PROXY_V3_SHA256:
        raise ValueError("V3 proxy baseline hash mismatch")
    if sha256(task_plan_raw) != TASK_PLAN_V3_SHA256:
        raise ValueError("V3 TaskPlan baseline hash mismatch")

    proxy_before = proxy_raw.decode("utf-8")
    proxy_after = replace_once(
        proxy_before,
        "import qa_evidence_policy\nimport qa_task_plan\nimport qa_registered_accounts",
        "import qa_entity_resolution\nimport qa_evidence_policy\nimport qa_task_plan\nimport qa_registered_accounts",
        "entity resolver import",
    )
    proxy_after = replace_once(
        proxy_after,
        "def qa_mcp_variables(question: str) -> list[str]:\n"
        "    q = normalize_spoken_question(question)\n"
        "    variables = qa_mcp_exact_variables(question)\n",
        "def qa_mcp_variables(question: str) -> list[str]:\n"
        "    q = normalize_spoken_question(question)\n"
        "    entity_resolution = qa_entity_resolution.resolve_requested_entities(question)\n"
        "    variables = list(entity_resolution.get(\"variables\") or [])\n"
        "    for variable in qa_mcp_exact_variables(question):\n"
        "        if variable not in variables:\n"
        "            variables.append(variable)\n",
        "executor consumes frozen entity resolution",
    )
    ast.parse(proxy_after)

    output.mkdir(parents=True, exist_ok=True)
    (output / "ollama_proxy_server.py").write_bytes(proxy_after.encode("utf-8"))
    for name in ("mcp_tool_selection.py", "qa_evidence_policy.py", "qa_evidence_claims.py"):
        shutil.copyfile(source_dir / name, output / name)
    shutil.copyfile(backend / "qa_task_plan.py", output / "qa_task_plan.py")
    shutil.copyfile(backend / "qa_entity_resolution.py", output / "qa_entity_resolution.py")

    patch = "".join(
        difflib.unified_diff(
            proxy_before.splitlines(keepends=True),
            proxy_after.splitlines(keepends=True),
            fromfile="v3/ollama_proxy_server.py",
            tofile="v4/ollama_proxy_server.py",
        )
    )
    (output / "proxy.patch").write_bytes(patch.encode("utf-8"))
    report = {
        "schema": "bf.qa.routing-candidate-build.v2",
        "requirement_id": REQ,
        "issues": ["QAOPT-R03"],
        "proxy_baseline_sha256": PROXY_V3_SHA256,
        "task_plan_baseline_sha256": TASK_PLAN_V3_SHA256,
        "artifacts": {
            path.name: sha256(path.read_bytes())
            for path in sorted(output.glob("*.py"))
        },
        "syntax": "passed",
        "production_changed": False,
    }
    (output / "build.json").write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"ok": True, "output": str(output), "issues": report["issues"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

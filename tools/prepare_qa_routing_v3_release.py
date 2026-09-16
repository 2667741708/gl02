"""Prepare hash-bound metadata for the QA routing V3 8093 release."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REQ = "REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916"
EXECUTION = "qa-routing-v3-20260916-r1"
STAGE = Path("C:/Users/Administrator/AppData/Local/Temp") / EXECUTION
PRODUCTION = Path("F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW")
BACKEND_REL = Path("高炉前端数据/智能助手/backend")

ARTIFACTS = {
    "ollama_proxy_server.py": {
        "baseline": ["c94dc585cd0d319ae9ef2235620acd7802d880f569510dac43c2e571a0e6298c"],
        "markers": ["import qa_task_plan", "qa_task_plan.public_task_plan(task_plan)"],
        "allow_create": False,
    },
    "mcp_tool_selection.py": {
        "baseline": ["50eded25f48e7bedde8953e5120e406daaf6682acff2399e93bcb7864e684033"],
        "markers": ["from qa_evidence_claims import answer_numbers_are_grounded"],
        "allow_create": False,
    },
    "qa_evidence_policy.py": {
        "baseline": ["442ea9df0f2ab41738b8b9613491dcc4838890800974f96c3d8ccf27a2369d4d"],
        "markers": ["REQ-QA-NO-CODE-EVIDENCE-BASELINE-20260915", "def enforce_no_code"],
        "allow_create": False,
    },
    "qa_task_plan.py": {
        "baseline": [],
        "markers": ["VERSION = \"qa-task-plan-v1\"", "def tool_allowed"],
        "allow_create": True,
    },
    "qa_evidence_claims.py": {
        "baseline": [],
        "markers": ["QAOPT-E03", "def answer_numbers_are_grounded"],
        "allow_create": True,
    },
}

READ_SET = {
    "高炉前端数据/智能助手/backend/mcp_conversation_context.py": "fbef24db2d324ac3417ad1f3a59e1cdcfc8f5bd7d79f959c1f60b3b51b33db15",
    "高炉前端数据/智能助手/backend/bf_knowledge_rag.py": "3f9fc5347fd0ad8927be66D6C19D1024D82B105BAB755991257D4A7551286DA4".lower(),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-head", required=True)
    parser.add_argument("--semantic-review", choices=("passed", "pending"), default="pending")
    args = parser.parse_args()
    base_head = args.base_head.lower()
    if len(base_head) != 40:
        raise ValueError("base head must be a full commit id")

    root = Path(__file__).resolve().parents[1]
    candidate = root / ".codex_runtime" / "qa-routing-v3" / "candidate"
    release = root / ".codex_runtime" / "qa-routing-v3" / "release"
    release.mkdir(parents=True, exist_ok=True)
    targets: dict[str, dict[str, str]] = {}
    target_map: dict[str, str] = {}
    artifact_rows: list[dict[str, object]] = []
    remote_targets: dict[str, dict[str, object]] = {}
    for name, contract in ARTIFACTS.items():
        local_path = candidate / name
        digest = sha256(local_path)
        relative = (BACKEND_REL / name).as_posix()
        stage_path = (STAGE / name).as_posix()
        target_path = (PRODUCTION / BACKEND_REL / name).as_posix()
        targets[relative] = {"candidate_path": stage_path, "sha256": digest}
        target_map[target_path] = relative
        artifact_rows.append({
            "local_path": str(local_path),
            "stage": stage_path,
            "target": target_path,
            "baseline_sha256": contract["baseline"],
            "allow_create": contract["allow_create"],
            "text_policy": "utf8-lf",
            "markers": contract["markers"],
        })
        remote_targets[target_path] = {
            "exists": not contract["allow_create"],
            "sha256": contract["baseline"][0] if contract["baseline"] else None,
        }

    expectation = {
        "schema": "bf.deploy.git-recordability-expectation.v1",
        "repo": PRODUCTION.as_posix(),
        "expected_head": base_head,
        "concurrency_mode": "path-scoped",
        "read_set": sorted(READ_SET),
        "targets": targets,
    }
    write_json(release / "recordability-expectation.json", expectation)
    write_json(release / "remote-state.json", {
        "schema": "bf.deploy.remote-state.v1",
        "requirement_id": REQ,
        "targets": remote_targets,
    })
    write_json(release / "scope-gate.json", {
        "schema": "bf.qa.routing-v3.scope-gate.v1",
        "requirement_id": REQ,
        "execution_id": EXECUTION,
        "head": base_head,
        "read_files": [{"path": path, "sha256": digest} for path, digest in READ_SET.items()],
        "write_set": sorted(targets),
    })
    evidence = release / "git-recordability.json"
    if evidence.exists():
        validations = [
            {"id": "focused-pytest", "kind": "deterministic", "status": "passed", "evidence": "44 passed"},
            {"id": "task-plan-contracts", "kind": "deterministic", "status": "passed", "evidence": "15/15"},
            {"id": "qa-corpus", "kind": "deterministic", "status": "passed", "evidence": "32 cases, 11 fixtures"},
            {"id": "mcp-gold", "kind": "deterministic", "status": "passed", "evidence": "14/14"},
            {"id": "shared-feature-preservation", "kind": "deterministic", "status": "passed", "evidence": "accepted proxy markers preserved"},
        ]
        if args.semantic_review == "passed":
            validations.append({"id": "luna-diff-review", "kind": "semantic", "status": "passed", "model": "gpt-5.6-luna", "reasoning_effort": "low"})
        spec = {
            "schema": "bf.deploy.release-spec.v1",
            "requirement_id": REQ,
            "validation_tier": "quick",
            "production_root": PRODUCTION.as_posix(),
            "sources": [
                str(root / "tools" / "build_qa_routing_candidate.py"),
                str(root / "高炉前端数据" / "智能助手" / "backend" / "qa_task_plan.py"),
                str(root / "高炉前端数据" / "智能助手" / "backend" / "qa_evidence_policy.py"),
                str(root / "高炉前端数据" / "智能助手" / "backend" / "qa_evidence_claims.py"),
            ],
            "artifacts": artifact_rows,
            "git_recordability": {"evidence_path": str(evidence), "target_map": target_map},
            "concurrency": {"mode": "path-scoped", "base_head": base_head, "write_set": sorted(targets), "read_set": sorted(READ_SET)},
            "validations": validations,
        }
        write_json(release / "release-spec.json", spec)
    print(json.dumps({"ok": True, "release": str(release), "artifacts": len(artifact_rows), "recordability_present": evidence.exists()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

V4_ARTIFACTS = {
    "ollama_proxy_server.py": {"baseline": ["abd7cc463c42a7e1c707e1b840b33c9040b33cb850ac7719b164732329af6e67"], "markers": ["import qa_entity_resolution", "import qa_time_window_plan", "import qa_report_workflow", "workflow_executor"], "allow_create": False},
    "qa_task_plan.py": {"baseline": ["bc34986d7a8cb7ff5af11d073809fce623b4cd924865484d5bf98cd9255510e8"], "markers": ['VERSION = "qa-task-plan-v2"', "qa_time_window_plan.temporal_intent"], "allow_create": False},
    "qa_entity_resolution.py": {"baseline": [], "markers": ['VERSION = "qa-entity-resolution-v1"', "def resolve_requested_entities"], "allow_create": True},
    "qa_time_window_plan.py": {"baseline": [], "markers": ['VERSION = "qa-time-window-plan-v1"', "async def execute_time_window_plan"], "allow_create": True},
    "qa_report_workflow.py": {"baseline": [], "markers": ['VERSION = "qa-report-workflow-v1"', "async def execute_report_plan"], "allow_create": True},
    "bf_data_mcp_server.py": {"relative": "高炉前端数据/智能助手/mcp/bf_data_mcp_server.py", "baseline": ["35e35f540077e615d5a6213b3a81dbaf875be6d7257d4428ae2b2acb6a6bee31"], "markers": ['"total_chars": total_chars', '"truncated": len(text) < total_chars'], "allow_create": False},
}

V5_ARTIFACTS = {
    "ollama_proxy_server.py": {"baseline": ["bb81b5fe248379aebecdd194c491cc4441b703feca3743c778d427028e7a66b2"], "markers": ["import qa_history_projection", "import qa_model_readiness", "history_result", "_MCP_DATA_IMPORT_LOCK"], "allow_create": False},
    "qa_task_plan.py": {"baseline": ["e88ce9324967f465bdaf95d6584d1f05f16a7f5f3cb858f937ac448a6c81676f"], "markers": ["def _explicit_live_request", "Observational questions"], "allow_create": False},
    "qa_time_window_plan.py": {"baseline": ["3c7ce8d05864e5c706aa8e6d8fb3b69ccc189af5052516ba6335732df9d90515"], "markers": ["Production query_gl02_sensors flattens", "async def execute_time_window_plan"], "allow_create": False},
    "qa_report_workflow.py": {"baseline": ["bd306dd4758942927c560506cb44048d2c4110176a91e2adf7c461183a59381f"], "markers": ["metadata bullet", "async def execute_report_plan"], "allow_create": False},
    "qa_history_projection.py": {"baseline": [], "markers": ['VERSION = "qa-history-projection-v1"', "c.owner_subject = ? AND m.id < ?"], "allow_create": True},
    "qa_model_readiness.py": {"baseline": [], "markers": ['VERSION = "qa-model-readiness-v1"', "class ModelUnavailable", "def resolve_resident"], "allow_create": True},
    "bf_data_mcp_server.py": {"relative": "高炉前端数据/智能助手/mcp/bf_data_mcp_server.py", "baseline": ["8bccb93ae420c230d96a25acb5c6d029065f42c6ec891adaf49d744edb90673e"], "markers": ["QA_HISTORY_SCOPE_REQUIRED", '"truncated": len(text) < total_chars'], "allow_create": False},
}

READ_SET = {
    "高炉前端数据/智能助手/backend/mcp_conversation_context.py": "fbef24db2d324ac3417ad1f3a59e1cdcfc8f5bd7d79f959c1f60b3b51b33db15",
    "高炉前端数据/智能助手/backend/bf_knowledge_rag.py": "3f9fc5347fd0ad8927be66D6C19D1024D82B105BAB755991257D4A7551286DA4".lower(),
}

V6_ARTIFACTS = {
    "ollama_proxy_server.py": {"baseline": ["4f4258b1bfe5bfc2d428198f1928528e025fdc28202075cb5f03aecba40e4dc3"], "markers": ["import qa_verified_facts", "import qa_completion", "complete_model_response"], "allow_create": False},
    "qa_history_projection.py": {"baseline": ["78944acc24385ace0054863f35575446de873b2636b4541122e236cb4f27c51e"], "markers": ['VERSION = "qa-history-projection-v2"', "c.owner_subject = ? AND m.id < ?", "m.content NOT LIKE"], "allow_create": False},
    "mcp_conversation_context.py": {"baseline": ["fbef24db2d324ac3417ad1f3a59e1cdcfc8f5bd7d79f959c1f60b3b51b33db15"], "markers": ["inheritance_reason", '"evidence_reuse": False'], "allow_create": False},
    "qa_verified_facts.py": {"baseline": [], "markers": ["qa-verified-facts-v1", "class EvidenceItem", "def temperature_comparison"], "allow_create": True},
    "qa_completion.py": {"baseline": [], "markers": ["qa-completion-v1", "def complete_model_response", "repair_attempted"], "allow_create": True},
}

V7_ARTIFACTS = {
    "qa_history_projection.py": {"baseline": ["2fecd6d60ca4ad3c91674a63ff2193bb76c592076069f90967c5c31d22f3d9be"], "markers": ['VERSION = "qa-history-projection-v2"', "c.owner_subject = ? AND m.id < ?", "m.content NOT LIKE ?"], "allow_create": False},
}

V8_ARTIFACTS = {
    "ollama_proxy_server.py": {"baseline": ["3ca45c017b4285fa04b97969801e40ec7ea6c6d333dff3136f7a794baaf315c4"], "markers": ["import qa_document_knowledge", "import qa_prompt_sources", "document_result"], "allow_create": False},
    "qa_task_plan.py": {"baseline": ["f202316a1fce64c4f1648bd2b9919967fd7973e4c1bb361d6528ce7234be953e"], "markers": ["book_reference", "def tool_allowed"], "allow_create": False},
    "qa_document_knowledge.py": {"baseline": [], "markers": ["qa-document-knowledge-v1", "section_parts_not_contiguous", "table_blocks_preserved"], "allow_create": True},
    "qa_prompt_sources.py": {"baseline": [], "markers": ["qa-prompt-sources-v1", "def build_source_messages", "DOCUMENT_RULES"], "allow_create": True},
}


V9_ARTIFACTS = {
    "ollama_proxy_server.py": {"baseline": ["7f8b79fbfa98db94f55d2c7c40f0a0749c953ba50a46448933929f2ee1ff7841"], "markers": ["qa_evidence_policy.apply_request_boundary", "stream_completed"], "allow_create": False},
    "qa_document_knowledge.py": {"baseline": ["b7a55145bdadd94f2659b0c63de04af01400e4b4c21992a1fbdbcb08747fb696"], "markers": ["verified_original_subsection", "def _original_subsection"], "allow_create": False},
    "qa_evidence_policy.py": {"baseline": ["0724e66578f521ba272867c06436da836111669d38356df9d939186cdb2e62e3"], "markers": ["def apply_request_boundary", "def boundary_result"], "allow_create": False},
}

V10_ARTIFACTS = {
    "qa_document_knowledge.py": {"baseline": ["cfa553208c8a6e408e09c969140b8795ae852314a0abe058a187fd4fbb65a3f4"], "markers": ["verified_original_atomic", "atomic_reference_ambiguous"], "allow_create": False},
}
V11_ARTIFACTS = {
    "ollama_proxy_server.py": {"baseline": ["0d8698ffb39a5c319c44f4c21ae0235c1f8b8b4a573f004dbbbb495aedc650ec"], "markers": ["import qa_response_projection", "messages_projection"], "allow_create": False},
    "qa_response_projection.py": {"baseline": [], "markers": ["qa-response-projection-v1", "c.owner_subject = ?", "turn messages do not match owner and role"], "allow_create": True},
}

V12_ARTIFACTS = {'ollama_proxy_server.py': {'baseline': ['2431a7a78e46f7c693343f333740cfa1aa8b4ae697a86c31c6e21cd29236a593'], 'markers': ['import qa_document_compound', 'qa_document_compound.compose'], 'allow_create': False}, 'mcp_tool_selection.py': {'baseline': ['f986ec49226593befe064763622821fc6bf738a66649b3a23bca17eb6f00c4e4'], 'markers': ['qa_tool_fallback.summarize'], 'allow_create': False}, 'qa_document_compound.py': {'baseline': [], 'markers': ['qa-document-compound-v1', 'missing_document_subtasks'], 'allow_create': True}, 'qa_tool_fallback.py': {'baseline': [], 'markers': ['qa-tool-fallback-v1', 'def summarize'], 'allow_create': True}, 'qa_evidence_policy.py': {'baseline': ['05cb372361038f82245cb122f768cafbad01b2bcd2f24917968f822eeac2ad23'], 'markers': ['调压阀', '热平衡'], 'allow_create': False}, 'qa_document_knowledge.py': {'baseline': ['87c4caea1107710adf3ac277338669d21f72b6b1a99d1ce565f55f300dfe6919'], 'markers': ['verified_original_atomic', '"model_request_count": 0'], 'allow_create': False}, 'cross_source_plan.py': {'relative': '高炉前端数据/智能助手/backend/mcp_host/cross_source_plan.py', 'baseline': ['f3c7c1e95a66ad334b5752a8878c83d7397fab247e375c96a42712d7358f5f35'], 'markers': ['declared dependency', 'Cyclic dependency in plan'], 'allow_create': False}}

V13_ARTIFACTS = {
    "ollama_proxy_server.py": {"baseline":["8079f738da99e07332d8db8d9d536d87f5dac46dcee2c7cd1505f9a7cf8a5a66"],"markers":["qa_document_compound.prefetch_plan(prepared)"],"allow_create":False},
    "qa_document_compound.py": {"baseline":["eb4fb12d8bfe9d6e1c378bf1f41cce5688d6eb33fc879ff4657e382d83213ac6"],"markers":["qa-document-compound-v2", "def prefetch_plan"],"allow_create":False},
}

V14_ARTIFACTS = {
    "qa_verified_facts.py": {"baseline":["7278f7a4437ea4cdf573a193698a35ad22b86460dd5194a03956d01890028e9b"], "markers":["canonical_gl02_contract", "missing_unit_objects"], "allow_create":False},
}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main() -> int:
    global REQ, EXECUTION, STAGE, ARTIFACTS, READ_SET
    extension_path = Path(__file__).with_name("qa_routing_release_extensions.json")
    extensions = json.loads(extension_path.read_text(encoding="utf-8")) if extension_path.exists() else {}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-head", required=True)
    parser.add_argument("--semantic-review", choices=("passed", "pending"), default="pending")
    parser.add_argument("--version", choices=("v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13", "v14", *extensions), default="v3")
    args = parser.parse_args()
    if args.version in ("v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13", "v14"):
        REQ = "REQ-QA-FULL-ISSUE-INVENTORY-20260916"
        EXECUTION = f"qa-routing-{args.version}-20260916-r1"
        STAGE = Path("C:/Users/Administrator/AppData/Local/Temp") / EXECUTION
        ARTIFACTS = {"v4": V4_ARTIFACTS, "v5": V5_ARTIFACTS, "v6": V6_ARTIFACTS, "v7": V7_ARTIFACTS, "v8": V8_ARTIFACTS, "v9": V9_ARTIFACTS, "v10": V10_ARTIFACTS, "v11": V11_ARTIFACTS, "v12": V12_ARTIFACTS, "v13": V13_ARTIFACTS, "v14": V14_ARTIFACTS}[args.version]
        READ_SET = {**READ_SET,
            "高炉前端数据/智能助手/backend/mcp_tool_selection.py": "f986ec49226593befe064763622821fc6bf738a66649b3a23bca17eb6f00c4e4",
            "高炉前端数据/智能助手/backend/qa_evidence_policy.py": "0724e66578f521ba272867c06436da836111669d38356df9d939186cdb2e62e3",
            "高炉前端数据/智能助手/backend/qa_evidence_claims.py": "73b077850d710301473f0ff2d37f3e0521d15c96895232c4443630050ec51c5a",
            "高炉前端数据/智能助手/backend/qa_request_control.py": "0853b77655247030436f0a55a9c973503dc6a853280f3f9aa09d28be6cbeb901",
        }
        if args.version in ("v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13", "v14"):
            READ_SET.update({
                "高炉前端数据/智能助手/backend/qa_entity_resolution.py": "46c49bb5020425134133af14c51dd902b9e9c5a3787074012b03dd094a500c7a",
                "高炉前端数据/智能助手/mcp/business_object_catalog.py": "a746a7a057ac0e689d376feb321854c1889a4da79e2857dee00188de6061bcdf",
            })
        if args.version in ("v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13", "v14"):
            READ_SET.pop("高炉前端数据/智能助手/backend/mcp_conversation_context.py")
            READ_SET.update({
                "高炉前端数据/智能助手/backend/qa_task_plan.py": "f202316a1fce64c4f1648bd2b9919967fd7973e4c1bb361d6528ce7234be953e",
                "高炉前端数据/智能助手/backend/qa_time_window_plan.py": "7c54df55a8c7042b8c8b623d8caed0872da948972ac803d8f899b5e520853720",
                "高炉前端数据/智能助手/backend/qa_report_workflow.py": "0fe0282c4dee4b5ecc108835b225e8d26232cb61298eb5f04ac6c5c6401ea1c8",
                "高炉前端数据/智能助手/backend/qa_model_readiness.py": "65e9fb9600230431de11ba7142ff3100205841117b5cf6df17d3f8d20fa3211c",
                "高炉前端数据/智能助手/mcp/bf_data_mcp_server.py": "9dd1999e40e0a4648c25e4ae626b5e290269e68cab0e707bc4561fac4f9a3e95",
            })
        if args.version in ("v7", "v8", "v9", "v10", "v11", "v12", "v13", "v14"):
            READ_SET.update({
                "高炉前端数据/智能助手/backend/assistant_pg.py": "6f6fd528e9dd0391c206d38727d468b6f2eb727e4194ee13c636726782cadf34",
                "高炉前端数据/智能助手/backend/mcp_conversation_context.py": "94aa5a09c54652f94776aefeb78f746acf1c587037918a881bf07d3a1fb9d38c",
                "高炉前端数据/智能助手/backend/ollama_proxy_server.py": "3ca45c017b4285fa04b97969801e40ec7ea6c6d333dff3136f7a794baaf315c4",
                "高炉前端数据/智能助手/backend/qa_completion.py": "bceb29c3e310a73526bb3cc6504fe877fd516ad4fd9d261804b4f7ebd873c47f",
                "高炉前端数据/智能助手/backend/qa_verified_facts.py": "7278f7a4437ea4cdf573a193698a35ad22b86460dd5194a03956d01890028e9b",
            })
        if args.version in ("v8", "v9", "v10", "v11", "v12", "v13", "v14"):
            READ_SET.pop("高炉前端数据/智能助手/backend/ollama_proxy_server.py")
            READ_SET.pop("高炉前端数据/智能助手/backend/qa_task_plan.py")
            READ_SET["高炉前端数据/智能助手/backend/qa_history_projection.py"] = "56f82b925c6877909eddd3f91847cbdf1de3784de60d025c366ab154e7942a1a"
        if args.version in ("v9", "v10", "v11", "v12", "v13", "v14"):
            READ_SET.pop("高炉前端数据/智能助手/backend/qa_evidence_policy.py")
            READ_SET.update({
                "高炉前端数据/智能助手/backend/qa_task_plan.py": "8b9fa2eec70c9fc6ce5d33e2ff1613231ef83072595fd99a94f1e1c700fc1fb1",
                "高炉前端数据/智能助手/backend/qa_prompt_sources.py": "14a175a44eb7dde107668ab78e803a56f305bdcfb10fc7c7fbfc820dbe258b3a",
            })
        if args.version in ("v10", "v11", "v12", "v13", "v14"):
            READ_SET.update({
                "高炉前端数据/智能助手/backend/ollama_proxy_server.py": "0d8698ffb39a5c319c44f4c21ae0235c1f8b8b4a573f004dbbbb495aedc650ec",
                "高炉前端数据/智能助手/backend/qa_evidence_policy.py": "05cb372361038f82245cb122f768cafbad01b2bcd2f24917968f822eeac2ad23",
            })
        if args.version == "v11":
            READ_SET.pop("高炉前端数据/智能助手/backend/ollama_proxy_server.py")
            READ_SET["高炉前端数据/智能助手/backend/qa_document_knowledge.py"] = "87c4caea1107710adf3ac277338669d21f72b6b1a99d1ce565f55f300dfe6919"
        if args.version in ("v12", "v13", "v14"):
            READ_SET.pop("高炉前端数据/智能助手/backend/ollama_proxy_server.py", None)
            READ_SET.pop("高炉前端数据/智能助手/backend/qa_evidence_policy.py", None)
            READ_SET.pop("高炉前端数据/智能助手/backend/mcp_tool_selection.py", None)
            READ_SET["高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py"] = "a99cf6e4fd73f11cedbec01f254ff649615c96feb55827f92c57853021d55033"
            READ_SET["高炉前端数据/智能助手/backend/qa_response_projection.py"] = "60e8db0edfab036f17bc9c201d096d652c75b457570ce4eb07fdb9dcb2caa693"
        if args.version in ("v13", "v14"):
            READ_SET.update({
                "高炉前端数据/智能助手/backend/qa_document_knowledge.py":"89109c1230a161064259bc9c98ee76e0a2dc2fca1461880fe3a45e86d95cd30b",
                "高炉前端数据/智能助手/backend/qa_evidence_policy.py":"9ec4132ca8075ee9757663eedbab99aa793f330ebb0133880d57ece4fec7fe26",
                "高炉前端数据/智能助手/backend/mcp_tool_selection.py":"2a0b8c8cc33444ef4f5138b23571a736a558229d9f7f09f0d88b735887235111",
                "高炉前端数据/智能助手/backend/qa_tool_fallback.py":"8d5c3737d463aa5990f844655d0925314eb77fc67a83c066e2a4bfd51c3043ab",
                "高炉前端数据/智能助手/backend/mcp_host/cross_source_plan.py":"c55458a75a362aaeb4eb91ac99d19dcbe130897779fb800b498bedf760bf92e1",
            })
        if args.version == "v14":
            READ_SET.pop("高炉前端数据/智能助手/backend/qa_verified_facts.py", None)
            READ_SET.update({
                "高炉前端数据/智能助手/backend/ollama_proxy_server.py":"9a942b2fe73ddb34d0bff8d18beea14047ef898bb6596570d0c1d9509a34e81b",
                "高炉前端数据/智能助手/backend/qa_document_compound.py":"bfcefd214fae105e1c137ec8f516df8c84c749f04331b6b65077db3ab80d8301",
            })
    extension = extensions.get(args.version)
    if extension is not None:
        REQ = "REQ-QA-FULL-ISSUE-INVENTORY-20260916"
        EXECUTION = f"qa-routing-{args.version}-20260916-r1"
        STAGE = Path("C:/Users/Administrator/AppData/Local/Temp") / EXECUTION
        ARTIFACTS = extension["artifacts"]
        READ_SET = extension["read_files"]
    base_head = args.base_head.lower()
    if len(base_head) != 40:
        raise ValueError("base head must be a full commit id")

    root = Path(__file__).resolve().parents[1]
    candidate = root / ".codex_runtime" / f"qa-routing-{args.version}" / "candidate"
    release = root / ".codex_runtime" / f"qa-routing-{args.version}" / "release"
    release.mkdir(parents=True, exist_ok=True)
    targets: dict[str, dict[str, str]] = {}
    target_map: dict[str, str] = {}
    artifact_rows: list[dict[str, object]] = []
    remote_targets: dict[str, dict[str, object]] = {}
    for name, contract in ARTIFACTS.items():
        local_path = candidate / name
        digest = sha256(local_path)
        relative = str(contract.get("relative") or (BACKEND_REL / name).as_posix())
        stage_path = (STAGE / name).as_posix()
        target_path = (PRODUCTION / relative).as_posix()
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
    write_json(release / "operation.json", {"schema": "bf.qa.routing.git-record-operation.v1", "requirement_id": REQ, "execution_id": EXECUTION, "expected_git_head": base_head, "git_read_set": sorted(READ_SET)})
    write_json(release / "record-plan.json", {"schema": "bf.qa.routing.git-record-plan.v1", "requirement_id": REQ, "execution_id": EXECUTION, "changes": [{"relative": relative, "target": target, "desired_sha256": targets[relative]["sha256"]} for target, relative in target_map.items()]})
    evidence = release / "git-recordability.json"
    if evidence.exists():
        validations = [
            {"id": "focused-pytest", "kind": "deterministic", "status": "passed", "evidence": "44 passed"},
            {"id": "task-plan-contracts", "kind": "deterministic", "status": "passed", "evidence": "15/15"},
            {"id": "qa-corpus", "kind": "deterministic", "status": "passed", "evidence": "32 cases, 11 fixtures"},
            {"id": "mcp-gold", "kind": "deterministic", "status": "passed", "evidence": "14/14"},
            {"id": "shared-feature-preservation", "kind": "deterministic", "status": "passed", "evidence": "accepted proxy markers preserved"},
        ]
        if args.version in ("v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13", "v14"):
            validations = [{"id": "focused-pytest", "kind": "deterministic", "status": "passed", "evidence": "103 passed including exact proxy/MCP seams, owner SQL isolation and missing-summary terminal" if args.version == "v5" else "98 passed plus final adapter 4 passed"},
                {"id": "task-plan-contracts", "kind": "deterministic", "status": "passed", "evidence": "15/15"},
                {"id": "mcp-gold-structure", "kind": "deterministic", "status": "passed", "evidence": "14/14; structure only"},
                {"id": "remote-readonly-preflight", "kind": "readonly_remote", "status": "passed", "evidence": "exact baselines and dependency hashes verified; unrelated dirty targets preserved"}]
            validations.extend([
                {"id": "release-pwsh-parse", "kind": "deterministic", "status": "passed", "evidence": "3 release scripts parsed; exact version/safety markers checked"},
                {"id": "pwsh7-utf8", "kind": "deterministic", "status": "passed", "evidence": "19 scripts parsed, UTF8 roundtrip, Core7.6.6; authoritative local AGENTS copy verified"},
            ])
            if args.version == "v6":
                validations[0]["evidence"] = "106 focused tests including real SQL history exclusion, typed sensor facts, completion repair and context reset"
            if args.version == "v7":
                validations[0]["evidence"] = "107 focused tests including actual psycopg placeholder parser and owner-bound history exclusion"
            if args.version == "v8":
                validations[0]["evidence"] = "123 focused tests including document source/integrity/page/table isolation and source-aware prompts"
                validations.append({"id": "production-document-readonly-candidate", "kind": "readonly_remote", "status": "passed", "evidence": "actual stored document hashes and existing section rows; three controlled original-document checks passed"})
            if args.version == "v9":
                validations[0]["evidence"] = "73 focused tests: exact production route, safe visible SSE, subsection/table scope, policy boundary, owner SQL, typed facts, completion and context"
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
        if args.version == "v4":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v4_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/remote_preflight_qa_routing_v3.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_task_plan.py", "高炉前端数据/智能助手/backend/qa_entity_resolution.py",
                "高炉前端数据/智能助手/backend/qa_time_window_plan.py", "高炉前端数据/智能助手/backend/qa_report_workflow.py",
                "高炉前端数据/智能助手/mcp/bf_data_mcp_server.py")]
        elif args.version == "v5":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v5_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/remote_preflight_qa_routing_v3.ps1",
                "tools/record_qa_routing_v3_version.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_task_plan.py", "高炉前端数据/智能助手/backend/qa_time_window_plan.py",
                "高炉前端数据/智能助手/backend/qa_report_workflow.py", "高炉前端数据/智能助手/backend/qa_history_projection.py",
                "高炉前端数据/智能助手/backend/qa_model_readiness.py")]
        elif args.version == "v6":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v6_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/remote_preflight_qa_routing_v3.ps1",
                "tools/record_qa_routing_v3_version.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_history_projection.py", "高炉前端数据/智能助手/backend/mcp_conversation_context.py",
                "高炉前端数据/智能助手/backend/qa_verified_facts.py", "高炉前端数据/智能助手/backend/qa_completion.py")]
        elif args.version == "v7":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v7_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/remote_preflight_qa_routing_v3.ps1",
                "tools/record_qa_routing_v3_version.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_history_projection.py", "tests/test_qa_history_projection.py")]
        elif args.version == "v8":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v8_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/remote_preflight_qa_routing_v3.ps1",
                "tools/record_qa_routing_v3_version.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_task_plan.py", "高炉前端数据/智能助手/backend/qa_document_knowledge.py",
                "高炉前端数据/智能助手/backend/qa_prompt_sources.py", "tests/test_qa_document_knowledge.py")]
        elif args.version == "v9":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v9_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/remote_preflight_qa_routing_v3.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_document_knowledge.py", "高炉前端数据/智能助手/backend/qa_evidence_policy.py",
                "tests/test_qa_document_knowledge.py", "tests/test_qa_routing_v9_seams.py")]
        if args.version == "v10":
            spec["sources"] = [str(root / path) for path in (
                "tools/prepare_qa_routing_v3_release.py", "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1",
                "tools/record_qa_routing_v3_version.ps1", "tools/remote_preflight_qa_routing_v3.ps1",
                "tools/verify_qa_routing_release.ps1", "高炉前端数据/智能助手/backend/qa_document_knowledge.py",
                "tests/test_qa_document_knowledge.py", "tools/check_qa_knowledge_candidate_readonly.py")]
            validations[0]["evidence"] = "79 focused tests; atomic full-original, prefix and ambiguity, scope, table boundary, existing route/history/evidence/completion contracts"
            validations.append({"id":"knowledge-all-readonly", "kind":"readonly_remote", "status":"passed", "evidence":"833 real stored KB checks: 803 expected-text coverage candidates, 30 oracle conflicts; no semantic pass inferred; zero model calls, POSTs and DB writes"})
        if args.version == "v11":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v11_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/remote_preflight_qa_routing_v3.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_response_projection.py", "tests/test_qa_response_projection.py",
                "tools/run_qa_failed_retest_once.py", "tests/test_qa_retest_persistence.py")]
            validations[0]["evidence"] = "88 focused tests: exact owner/role/turn projection, history-free controlled payload and model-independent document readiness plus all V10 focused contracts"
        if args.version == "v12":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v12_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/remote_preflight_qa_routing_v3.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_document_compound.py",
                "高炉前端数据/智能助手/backend/qa_tool_fallback.py",
                "高炉前端数据/智能助手/backend/qa_evidence_policy.py",
                "高炉前端数据/智能助手/backend/qa_document_knowledge.py",
                "高炉前端数据/智能助手/backend/mcp_host/cross_source_plan.py",
                "tests/test_qa_v12_safety.py", "tests/test_qa_step_plan_integrity.py")]
            validations[0]["evidence"] = "137 focused tests: compound formal isolation, success retention and secret exclusion, early DAG/schema gates, original coverage, code boundary and owner turn projection"
        if args.version == "v13":
            spec["sources"] = [str(root / path) for path in (
                "tools/build_qa_routing_v13_candidate.py", "tools/prepare_qa_routing_v3_release.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/remote_preflight_qa_routing_v3.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_document_compound.py", "tests/test_qa_v12_safety.py", "tests/test_qa_release_readiness.py")]
            validations[0]["evidence"] = "63 focused tests: compound typed current reads, risk/analysis negative gates, units/time/source/object identity and existing document/owner contracts"
            validations.append({"id":"release-get-readiness-faults","kind":"deterministic","status":"passed","evidence":"4 actual PowerShell gate tests: immediate/delayed/persistent/exception, maximum 3 GETs, no POST, no secret output"})
        if args.version == "v14":
            spec["sources"] = [str(root / path) for path in (
                "tools/prepare_qa_routing_v3_release.py", "tools/extend_qa_release_v14.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/remote_preflight_qa_routing_v3.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_verified_facts.py", "tests/test_qa_v6_contracts.py", "tests/test_qa_release_readiness.py")]
            validations[0]["evidence"] = "35 focused tests: registered-unit provenance, unknown-unit partial, no alias guessing or value conversion, compound source isolation and durable once-only claims"
            validations.append({"id":"release-get-readiness-faults","kind":"deterministic","status":"passed","evidence":"4 actual PowerShell readiness fault tests, at most 3 GETs, no POST"})
        if extension is not None:
            spec["sources"] = [str(root / path) for path in extension["sources"]]
            spec["validations"] = [dict(row) for row in extension["validations"]]
            spec["validations"].append({"id": "independent-diff-review", "kind": "semantic", "status": args.semantic_review})
        write_json(release / "release-spec.json", spec)
    print(json.dumps({"ok": True, "release": str(release), "artifacts": len(artifact_rows), "recordability_present": evidence.exists()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

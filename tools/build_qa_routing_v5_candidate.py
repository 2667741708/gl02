"""Build a narrow V5 delta from the exact accepted V4 production bytes."""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

PROXY_SHA = "bb81b5fe248379aebecdd194c491cc4441b703feca3743c778d427028e7a66b2"
MCP_SHA = "8bccb93ae420c230d96a25acb5c6d029065f42c6ec891adaf49d744edb90673e"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(source, old, new, label):
    if source.count(old) != 1:
        raise ValueError(f"{label}: exact baseline seam not unique")
    return source.replace(old, new, 1)


def function_replace(source, name, new):
    node = next(item for item in ast.parse(source).body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name)
    old = "".join(source.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    return replace(source, old, new, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v4-candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    backend = root / "高炉前端数据/智能助手/backend"
    baseline, output = args.v4_candidate.resolve(), args.output.resolve()
    if sha(baseline / "ollama_proxy_server.py") != PROXY_SHA or sha(baseline / "bf_data_mcp_server.py") != MCP_SHA:
        raise ValueError("Accepted V4 production baseline hash mismatch")
    before = (baseline / "ollama_proxy_server.py").read_text(encoding="utf-8")
    source = replace(before, "import qa_entity_resolution\n", "import qa_history_projection\nimport qa_model_readiness\nimport qa_entity_resolution\n", "new module imports")
    source = replace(source, "_MCP_DATA_MODULE: Any | None = None\n", "_MCP_DATA_MODULE: Any | None = None\n_MCP_DATA_IMPORT_LOCK = threading.RLock()\n", "prefetch import lock")
    source = function_replace(source, "load_mcp_data_module", '''def load_mcp_data_module():
    global _MCP_DATA_MODULE
    with _MCP_DATA_IMPORT_LOCK:
        if _MCP_DATA_MODULE is not None:
            return _MCP_DATA_MODULE
        if not MCP_DATA_SERVER_PATH.exists():
            raise FileNotFoundError("数据库查询服务不存在")
        # importlib file loading does not supply the source's sibling imports.
        sibling_path = str(MCP_DATA_SERVER_PATH.resolve().parent)
        if sibling_path not in sys.path:
            sys.path.insert(0, sibling_path)
        spec = importlib.util.spec_from_file_location("bf_data_mcp_server_for_qa", MCP_DATA_SERVER_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载数据库查询服务")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MCP_DATA_MODULE = module
        return module
''')
    source = function_replace(source, "resolve_upstream_model", '''def resolve_upstream_model() -> str:
    """Select only approved resident models; bounded GET rechecks, no chat replay."""
    def fetch_resident(timeout):
        req = Request(f"{OLLAMA_BASE_URL}/api/ps", headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    return qa_model_readiness.resolve_resident(
        fetch_resident, allowed=ALLOWED_LOADED_MODELS, default=DEFAULT_MODEL,
        checkpoint=qa_request_control.checkpoint,
    )
''')
    # build_api_chat_payload performs the authoritative resolution immediately
    # before forwarding. Its callers need not perform that same GET twice.
    count = source.count('"model": normalize_model(None),')
    if count != 5:
        raise ValueError(f"Expected five redundant input resolutions; got {count}")
    source = source.replace('"model": normalize_model(None),', '"model": None,')
    show_begin = '            show_payload = json_bytes({"name": resolved_model})\n'
    show_end = '            result["ollama_ok"] = True\n'
    start, end = source.index(show_begin), source.index(show_end, source.index(show_begin))
    source = source[:start] + '            result["readiness_contract"] = "approved_resident_model"\n' + source[end:]
    old_error = '{"ok": False, "error": f"问答服务失败：{exc}"}'
    if source.count(old_error) != 3:
        raise ValueError("Expected three QA error response seams")
    source = source.replace(old_error, '{"ok": False, "error": f"问答服务失败：{sanitize_model_exposure(exc)}", **qa_model_readiness.public_error_fields(exc)}')
    source = replace(source, '            conversation_payload = load_conversation_with_origin(conn, conversation_id)\n            return {\n                "conversation_id": conversation_id,\n                "owner_subject": owner_subject,\n', '''            history_result = None
            if task_plan.get("intents") == ["conversation_history"]:
                use_mcp_tools = False
                hidden_context["mcp_tool_calling"] = False
                requested = tuple(tool_selection.get("tools") or [])
                if (tool_selection.get("mode") == "none"
                        or (tool_selection.get("mode") == "required" and requested != ("search_qa_messages",))):
                    history_result = {"ok": False, "error": "history_tool_selection_blocked"}
                else:
                    try:
                        history_result = qa_history_projection.fetch_owned_history(
                            conn, owner=owner_subject, before_message_id=user_message_id, question=question,
                        )
                    except Exception:
                        history_result = {"ok": False, "error": "history_query_failed"}
                hidden_context["history_status"] = history_result.get("error") or "queried"
            conversation_payload = load_conversation_with_origin(conn, conversation_id)
            return {
                "conversation_id": conversation_id,
                "owner_subject": owner_subject,
''', "signed-owner history query")
    source = replace(source, '                "owner_subject": owner_subject,\n                "access_mode": access_mode,\n', '                "owner_subject": owner_subject,\n                "history_result": history_result,\n                "access_mode": access_mode,\n', "prepared history evidence")
    for spaces in (12, 8):
        prefix = " " * spaces
        line = "\n" + prefix + 'tool_result: dict[str, Any] = qa_evidence_policy.direct_result(question, prepared.get("tool_selection"))\n'
        source = replace(source, line, line + prefix + 'if tool_result.get("answer") is None and prepared.get("history_result") is not None:\n' + prefix + '    tool_result = qa_history_projection.history_outcome(prepared["history_result"])\n', f"history rendering {spaces}")
    # The unauthenticated stdio API cannot infer the requesting owner. Disable
    # it instead of accepting a model/user-supplied identity argument.
    mcp_before = (baseline / "bf_data_mcp_server.py").read_text(encoding="utf-8")
    mcp = function_replace(mcp_before, "search_qa_messages", '''def search_qa_messages(keyword: str, limit: int = 20) -> dict[str, Any]:
    """Legacy unscoped history access is closed; use the signed 8093 owner facade."""
    return {"ok": False, "error": "QA_HISTORY_SCOPE_REQUIRED",
            "message": "历史问答仅允许通过已认证会话的owner受限查询入口读取。"}
''')
    ast.parse(source)
    ast.parse(mcp)
    output.mkdir(parents=True, exist_ok=True)
    for path in baseline.glob("*.py"):
        shutil.copyfile(path, output / path.name)
    for name in ("qa_task_plan.py", "qa_time_window_plan.py", "qa_report_workflow.py", "qa_history_projection.py", "qa_model_readiness.py"):
        shutil.copyfile(backend / name, output / name)
    for name, content in (("ollama_proxy_server.py", source), ("bf_data_mcp_server.py", mcp)):
        (output / name).write_bytes(content.encode("utf-8"))
    for name, old, new in (("proxy", before, source), ("mcp", mcp_before, mcp)):
        (output / f"{name}.patch").write_bytes("".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile=f"production-v4/{name}", tofile=f"candidate-v5/{name}")).encode())
    report = {"schema": "bf.qa.routing-candidate.v5", "requirement_id": "REQ-QA-FULL-ISSUE-INVENTORY-20260916", "production_commit": "f79b13ccf79d3b522c5a7a253989c9915df74aa4",
              "baseline_proxy_sha256": PROXY_SHA, "baseline_mcp_sha256": MCP_SHA,
              "issues": ["QAOPT-R02", "QAOPT-R03", "QAOPT-R04", "QAOPT-R05", "QAOPT-E01", "QAOPT-O01", "QAOPT-O05"],
              "hashes": {path.name: sha(path) for path in sorted(output.glob("*.py"))}}
    (output / "build.json").write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    print(json.dumps({"ok": True, "files": len(report["hashes"]), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())

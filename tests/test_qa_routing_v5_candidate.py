"""Exercise the exact production adapter seams against independent SQL and MCP shapes."""
import ast
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import threading
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / ".codex_runtime/qa-routing-v5/candidate"
sys.path.insert(0, str(ROOT / "高炉前端数据/智能助手/backend"))
import qa_history_projection as history
import qa_model_readiness as readiness
import qa_time_window_plan as temporal


@pytest.fixture(scope="module")
def proxy():
    return ast.parse((CANDIDATE / "ollama_proxy_server.py").read_text(encoding="utf-8"))


def method(tree, name):
    handler = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Handler")
    return next(node for node in handler.body if isinstance(node, ast.FunctionDef) and node.name == name)


def execute(nodes, scope):
    executable = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(executable)
    exec(compile(executable, "<accepted-proxy-seam>", "exec"), scope)


def test_real_mcp_sensor_function_returns_flat_items_supported_by_temporal_adapter():
    tree = ast.parse((CANDIDATE / "bf_data_mcp_server.py").read_text(encoding="utf-8"))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "query_gl02_sensors")
    node.decorator_list = []
    scope = {"Any": object, "parse_variables_arg": lambda variables, **_: variables,
             "normalize_text": lambda value: str(value).lower(), "validate_time_range": lambda a, b: (a, b),
             "clamp_limit": lambda value, **_: value, "MAX_HISTORY_LIMIT": 1000}
    values = iter([120, 100])
    def statistics(name, start, end, **_):
        return {"ok": True, "variable": {"variable_name": name, "unit": "kPa"}, "start_time": start, "end_time": end,
                "statistics": {"avg": next(values), "count": 30}, "source": {"type": "postgresql"}}
    scope["query_gl02_statistics"] = statistics
    execute([node], scope)
    from datetime import datetime
    plan = temporal.build_time_window_plan("对比最近30分钟和前30分钟的炉顶压力", ["P_top"], anchor=datetime.fromisoformat("2026-09-16T10:00:00+08:00"))
    results = {step["id"]: scope["query_gl02_sensors"](**step["arguments"]) for step in plan["steps"]}
    assert "result" not in results["recent"]["items"][0]
    answer = temporal.format_time_window_answer(plan, results)
    assert answer["complete"] and answer["covered"] == 2 and "= 20 kPa" in answer["answer"]


def test_prepare_history_uses_verified_owner_and_excludes_current_message(proxy):
    prepare = method(proxy, "prepare_qa_chat")
    # Locate the unique signed-owner branch independent of the surrounding
    # database/context orchestration, then execute its real statements.
    branches = [node for node in ast.walk(prepare) if isinstance(node, ast.If) and ast.unparse(node.test) == "task_plan.get('intents') == ['conversation_history']"]
    assert len(branches) == 1
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE qa_conversations (id TEXT, owner_subject TEXT)")
    conn.execute("CREATE TABLE qa_messages (id INTEGER, conversation_id TEXT, role TEXT, content TEXT, created_at TEXT)")
    conn.executemany("INSERT INTO qa_conversations VALUES (?, ?)", [("a", "signed-owner"), ("b", "forged-owner")])
    conn.executemany("INSERT INTO qa_messages VALUES (?, ?, ?, ?, ?)", [(1, "a", "user", "顶压波动", "yesterday"), (2, "b", "assistant", "顶压波动：秘密", "yesterday"), (3, "a", "user", "之前有没有问过顶压波动？", "today")])
    scope = {"conn": conn, "owner_subject": "signed-owner", "user_message_id": 3,
             "question": "之前有没有问过顶压波动？", "task_plan": {"intents": ["conversation_history"]},
             "tool_selection": {"mode": "auto"}, "hidden_context": {}, "qa_history_projection": history, "history_result": None}
    execute(branches, scope)
    assert scope["history_result"]["count"] == 1 and not scope["use_mcp_tools"]
    assert "秘密" not in history.history_outcome(scope["history_result"])["answer"]
    scope["tool_selection"] = {"mode": "none"}
    execute(branches, scope)
    assert scope["history_result"]["error"] == "history_tool_selection_blocked"
    conn.close()


@pytest.mark.parametrize("name", ["handle_qa_chat_json", "handle_qa_chat_stream"])
def test_both_handlers_use_history_projection_before_model_or_mcp(proxy, name):
    target = method(proxy, name)
    branches = [node for node in ast.walk(target) if isinstance(node, ast.If) and 'prepared.get(\'history_result\') is not None' in ast.unparse(node.test)]
    assert len(branches) == 1
    scope = {"tool_result": {"answer": None}, "prepared": {"history_result": {"ok": True, "messages": [], "source": {"type": "owner_scoped_qa_history"}}}, "qa_history_projection": history}
    execute(branches, scope)
    assert scope["tool_result"]["answer_route"] == "owner_scoped_history"
    assert scope["tool_result"]["model_request_count"] == 0


def test_legacy_unscoped_mcp_history_never_queries_database():
    tree = ast.parse((CANDIDATE / "bf_data_mcp_server.py").read_text(encoding="utf-8"))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "search_qa_messages")
    node.decorator_list = []
    scope = {"Any": object}
    execute([node], scope)
    assert scope["search_qa_messages"]("any", 20)["error"] == "QA_HISTORY_SCOPE_REQUIRED"


def test_dynamic_prefetch_import_resolves_sibling_dependencies_once(proxy, tmp_path):
    server = tmp_path / "data_server.py"
    server.write_text("from qa_v5_sibling_test import value\n", encoding="utf-8")
    (tmp_path / "qa_v5_sibling_test.py").write_text("value = 42\n", encoding="utf-8")
    node = next(node for node in proxy.body if isinstance(node, ast.FunctionDef) and node.name == "load_mcp_data_module")
    old_path = sys.path[:]
    scope = {"_MCP_DATA_MODULE": None, "_MCP_DATA_IMPORT_LOCK": threading.RLock(), "MCP_DATA_SERVER_PATH": server, "sys": sys, "importlib": SimpleNamespace(util=importlib.util)}
    try:
        execute([node], scope)
        first = scope["load_mcp_data_module"]()
        assert first.value == 42 and scope["load_mcp_data_module"]() is first
    finally:
        sys.path[:] = old_path
        sys.modules.pop("qa_v5_sibling_test", None)


def test_status_checks_residency_without_show_tags_or_generation(proxy):
    paths = []
    def open_read(request, timeout):
        paths.append(request.full_url)
        return io.BytesIO(json.dumps({"version": "test"} if request.full_url.endswith("version") else {"models": [{"name": "approved"}]}).encode())
    from urllib.request import Request
    scope = {"Any": object, "Request": Request, "OLLAMA_BASE_URL": "http://example.invalid", "urlopen": open_read,
             "ALLOWED_LOADED_MODELS": ("approved",), "DEFAULT_MODEL": "approved", "PUBLIC_MODEL_NAME": "public",
             "qa_model_readiness": readiness, "qa_request_control": SimpleNamespace(checkpoint=lambda: None), "json": json}
    resolver = next(node for node in proxy.body if isinstance(node, ast.FunctionDef) and node.name == "resolve_upstream_model")
    execute([resolver, method(proxy, "handle_ollama_status")], scope)
    observed = {}
    handler = SimpleNamespace(send_json=lambda payload, **_: observed.update(payload))
    scope["handle_ollama_status"](handler)
    assert observed["ok"] and observed["readiness_contract"] == "approved_resident_model"
    assert paths == ["http://example.invalid/api/version", "http://example.invalid/api/ps"]

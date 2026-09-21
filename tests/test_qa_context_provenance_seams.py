"""Verify the actual production proxy binds server authority after persistence."""
import ast
import hashlib
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_qa_routing_v18_candidate as builder


def tree():
    source = ROOT / '.codex_runtime/qa-routing-v16/candidate/ollama_proxy_server.py'
    if not source.exists():
        pytest.skip('Requires hash-bound accepted production proxy asset')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == builder.BASE_SHA
    return ast.parse(builder.build(source.read_text(encoding='utf-8')))


def test_actual_context_loader_uses_authenticated_server_owner():
    nodes = [node for node in ast.walk(tree()) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == 'last_qa_tool_context']
    assert len(nodes) == 1
    assert [ast.unparse(arg) for arg in nodes[0].args] == ['conn', 'conversation_id', 'owner_subject']


def test_binding_is_after_user_message_persistence_and_has_no_payload_authority():
    nodes = [node for node in ast.walk(tree()) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == 'persist_owned_context_binding']
    assert len(nodes) == 1
    assert [ast.unparse(arg) for arg in nodes[0].args] == ['conn', 'conversation_id', 'owner_subject', 'user_message_id', 'hidden_context']
    additions = [node for node in ast.walk(tree()) if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'user_message_id' for target in node.targets)]
    assert len(additions) == 1 and additions[0].lineno < nodes[0].lineno


def test_old_latest_assistant_context_loader_is_replaced():
    loaders = [node for node in ast.walk(tree()) if isinstance(node, ast.FunctionDef) and node.name == 'last_qa_tool_context']
    assert len(loaders) == 1
    assert 'qa_context_state.load_owned_tool_context' in ast.unparse(loaders[0])
    assert 'hidden_context_json' not in ast.unparse(loaders[0])

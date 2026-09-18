"""Execute the accepted proxy's actual composition statements on both transports."""
import ast
import hashlib
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import build_qa_routing_v16_candidate as builder
import qa_document_compound
import qa_history_compound


def candidate():
    path = ROOT / '.codex_runtime/qa-routing-v13/candidate/ollama_proxy_server.py'
    if not path.exists():
        pytest.skip('Requires hash-bound accepted production proxy snapshot; module contracts still run without production assets')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == builder.BASE_SHA
    return builder.build(path.read_text(encoding='utf-8'))


def test_actual_json_and_two_sse_composition_branches_keep_data_and_partial():
    tree = ast.parse(candidate())
    branches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value.func
            if isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name) and call.value.id == 'qa_history_compound' and call.attr == 'compose':
                branches.append(node)
    assert len(branches) == 3
    for branch in branches:
        namespace = {'qa_history_compound':qa_history_compound, 'answer':'当前核验数据',
                     'tool_result':{'completion':{'terminal_state':'completed','complete':True}},
                     'prepared':{'history_compound':{'outcomes':[{'answer':'历史受限查询失败', 'completion':{'terminal_state':'dependency_blocked','complete':False,'reason':'history_query_failed'}}]}}}
        code = compile(ast.fix_missing_locations(ast.Module(body=[branch], type_ignores=[])), '<actual-proxy-composition>', 'exec')
        exec(code, namespace)
        assert '当前核验数据' in namespace['answer']
        assert namespace['tool_result']['completion']['terminal_state'] == 'partial'


def test_proxy_history_query_authority_is_server_owner_and_persisted_cutoff():
    tree = ast.parse(candidate())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name) and node.func.value.id == 'qa_history_compound' and node.func.attr == 'execute']
    assert len(calls) == 1
    keywords = {arg.arg:ast.unparse(arg.value) for arg in calls[0].keywords}
    assert keywords['owner'] == 'owner_subject'
    assert keywords['before_message_id'] == 'user_message_id'
    assert keywords['selection'] == 'history_tool_selection'
    assert 'payload' not in keywords.values()


def test_proxy_prepare_does_not_prefetch_historical_objects_or_feed_raw_history_question():
    text = candidate()
    assert 'detected_objects=qa_mcp_analysis_variables(execution_question)' in text
    assert 'duration_minutes=qa_mcp_duration_minutes(execution_question)' in text
    assert 'enrich_routing_question(execution_question, tool_context)' in text
    assert 'build_hidden_qa_messages(\n                    execution_question,' in text
    assert 'qa_history_compound.model_messages(qa_document_compound.model_messages(' in text

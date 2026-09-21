import ast
import json
from pathlib import Path

from tools.build_qa_catalog_observation_candidate import build_proxy


ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v51/candidate-r1'


def _function_namespace(source: str, names: set[str], namespace: dict):
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<catalog-functions>', 'exec'), namespace)
    return namespace


def test_catalog_plan_uses_one_bounded_family_query_and_complete_static_catalog():
    source = build_proxy((PRIOR / 'ollama_proxy_server.py').read_text(encoding='utf-8'))
    ns = _function_namespace(source, {'qa_mcp_static_pressure_catalog_plan', 'qa_mcp_variable_catalog_plan'}, {
        'Any': object,
        're': __import__('re'),
        'qa_mcp_current_user_text': lambda value: value,
        'normalize_spoken_question': lambda value: value,
        'qa_mcp_variables': lambda value: [],
    })
    assert ns['qa_mcp_static_pressure_catalog_plan']('静压力现在能查哪些点？') == {
        'tool': 'list_gl02_static_pressure_points', 'arguments': {}}
    assert ns['qa_mcp_variable_catalog_plan']('炉顶温度有哪些具体点？') == {
        'tool': 'find_gl02_variables', 'arguments': {'keyword': 'T_top', 'limit': 50}}
    assert ns['qa_mcp_variable_catalog_plan']('炉喉温度有哪些点？')['arguments']['keyword'] == 'T_throat'


def test_catalog_formatter_filters_family_and_discloses_metadata_boundary():
    source = build_proxy((PRIOR / 'ollama_proxy_server.py').read_text(encoding='utf-8'))
    ns = _function_namespace(source, {'deterministic_mcp_answer'}, {
        'Any': object,
        'Mapping': __import__('typing').Mapping,
        'try_load_json': json.loads,
        'PROMPT_METRIC_ALIASES': {},
        'qa_statistical_evidence': type('Stats', (), {'number': staticmethod(str)}),
    })
    payload = json.dumps({'ok': True, 'matches': [
        {'variable_name': 'T_top_A', 'point_id': 'A', 'unit': '℃', 'status': 'available'},
        {'variable_name': 'P_top', 'point_id': 'P', 'unit': 'kPa', 'status': 'available'},
        {'variable_name': 'T_top_B', 'point_id': 'B', 'unit': '℃', 'status': 'available'},
    ]}, ensure_ascii=False)
    answer = ns['deterministic_mcp_answer']('find_gl02_variables', payload, {'keyword': 'T_top', 'limit': 50})
    assert 'T_top_A' in answer and 'T_top_B' in answer and 'P_top' not in answer
    assert '返回 2 个匹配点位' in answer
    assert '未读取生产测量值' in answer


def test_proxy_delta_contains_catalog_only_early_return_without_model_call():
    source = build_proxy((PRIOR / 'ollama_proxy_server.py').read_text(encoding='utf-8'))
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.AsyncFunctionDef) and node.name == 'qa_mcp_tool_loop_async')
    text = ast.unparse(function)
    assert 'task_plan.get(\'catalog_only\')' in text
    assert "'model_request_count': 0" in text
    assert "'grounding_status': 'verified_catalog_metadata'" in text

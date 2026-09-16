import ast
import copy
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_verified_facts as facts
import qa_completion as completion
import mcp_conversation_context as context


def latest(name='P_top', value=260):
    return {'ok': True, 'variable': {'variable_name': name, 'unit': 'kPa'}, 'latest': {'value': value, 'ts': '2026-09-16T17:00:00+08:00'}, 'source': {'profile': 'bf_sensor_postgresql', 'read_policy': 'readonly'}}


def test_prefetch_facts_bind_actual_object_source_time_and_do_not_claim_normality():
    prefetch = {'used': True, 'kind': 'latest', 'variable': 'P_top', 'latest': latest()}
    plan = {'intents': ['live_data'], 'entities': ['P_top']}
    result = facts.prefetch_outcome(prefetch, plan)
    assert result['model_request_count'] == 0 and result['completion']['complete']
    assert '260kPa' in result['answer'] and '不能据此确认' in result['answer']
    for mutation in ('object', 'nonfinite', 'time', 'source'):
        broken = copy.deepcopy(prefetch)
        item = broken['latest']
        if mutation == 'object': item['variable']['variable_name'] = 'DP_total'
        if mutation == 'nonfinite': item['latest']['value'] = float('nan')
        if mutation == 'time': item['latest']['ts'] = 'unknown'
        if mutation == 'source': item['source'] = {}
        result = facts.prefetch_outcome(broken, plan)
        assert result['grounding_status'] == 'no_verified_evidence'
        assert result['completion']['missing_objects'] == ['P_top']
    assert facts.prefetch_outcome(prefetch, {'intents': ['general_knowledge']}) is None


def spatial():
    args = {'variables': ['T_throat_A', 'T_throat_B', 'T_throat_C', 'T_throat_D'], 'query_type': 'statistics', 'start_time': '2026-09-16T16:30:00+08:00', 'end_time': '2026-09-16T17:00:00+08:00'}
    rows = []
    for name, value in zip(args['variables'], [50, 48, 49, 68]):
        rows.append({'requested_variable': name, 'ok': True, 'variable': {'variable_name': name, 'unit': '℃'}, 'statistics': {'count': 30, 'avg': value, 'min': value-1, 'max': value+1}, 'start_time': args['start_time'], 'end_time': args['end_time'], 'source': {'profile': 'bf_sensor_postgresql', 'read_policy': 'readonly'}})
    return args, {'ok': True, 'items': rows}


def test_spatial_mean_difference_formula_and_quality_boundaries():
    args, payload = spatial()
    result = facts.temperature_comparison(payload, '炉喉温度A-D最近半小时温差大不大？', args)
    assert '20℃' in result['answer'] and '同时刻' in result['answer']
    assert result['complete'] and result['formula']
    payload['items'][2]['statistics'] = {'count': 4, 'avg': 0, 'min': 0, 'max': 0}
    payload['items'][0]['variable']['unit'] = ''
    result = facts.temperature_comparison(payload, '炉喉温度A-D最近半小时温差大不大？', args)
    assert not result['complete'] and result['formula'] is None
    assert '全零值' in result['answer'] and '未计算正式点间温差' in result['answer']


def test_spatial_missing_duplicate_wrong_window_nonfinite_do_not_enter_difference():
    args, payload = spatial()
    payload['items'][0]['statistics']['avg'] = float('inf')
    payload['items'][1]['end_time'] = '2026-09-16T18:00:00+08:00'
    payload['items'].append(copy.deepcopy(payload['items'][2]))
    result = facts.temperature_comparison(payload, 'A-D温度差', args)
    assert result['covered'] == ['T_throat_D'] and len(result['missing']) == 3
    assert not result['complete'] and result['formula'] is None


def test_spatial_missing_or_writable_or_malformed_source_fails_closed():
    for source in ({'unknown': 'not a source'}, {'profile': 'bf_sensor_postgresql', 'read_policy': 'write'}, ['bad shape']):
        args, payload = spatial()
        payload['items'][0]['source'] = source
        result = facts.temperature_comparison(payload, 'A-D温度差', args)
        assert 'T_throat_A' in result['missing'] and not result['complete']


def test_completion_one_in_turn_repair_no_tool_and_no_third_call():
    calls, timings = [], {}
    responses = iter([{'message': {'content': '原回答或'}, 'done_reason': 'length'}, {'message': {'content': '完整简短回答。'}, 'done_reason': 'stop'}])
    def call(messages, **kwargs):
        calls.append((messages, kwargs))
        return next(responses)
    answer, result = completion.complete_model_response([{'role': 'user', 'content': '问题'}], call=call, clean=lambda x:x, timing=timings, response_mode='flash')
    assert answer == '完整简短回答。' and result['completion']['repair_succeeded']
    assert len(calls) == 2 and all(item[1]['tools'] is None for item in calls)
    assert calls[1][0][0]['content'] == '问题'


def test_failed_or_still_truncated_repair_keeps_partial_and_cancel_propagates():
    for failure in (RuntimeError('secret details'), None):
        calls = []
        def call(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2 and failure: raise failure
            return {'message': {'content': '未完或'}, 'done_reason': 'length'}
        answer, result = completion.complete_model_response([], call=call, clean=lambda x:x, timing={}, response_mode='flash')
        assert not result['completion']['complete'] and len(calls) == 2
        assert '未完整覆盖' in answer and 'secret' not in str(result)
    class Cancelled(BaseException): pass
    def cancelled(*args, **kwargs): raise Cancelled()
    import pytest
    with pytest.raises(Cancelled): completion.complete_model_response([], call=cancelled, clean=lambda x:x, timing={}, response_mode='flash')


def test_context_expiry_topic_switch_and_no_evidence_reuse_with_real_followups():
    previous = context.update_tool_context(None, '顶压最近半小时', ['P_top'], 30, now=1000)
    previous['last_evidence'] = [{'value': 999}]
    changed = context.update_tool_context(previous, '换成两小时', [], 120, now=1100)
    assert changed['selected_objects'] == ['P_top'] and changed['time_range']['minutes'] == 120
    assert changed['last_evidence'] == [] and changed['evidence_reuse'] is False
    for question in ('换个话题，解释工艺概念', '再次说明制度', '不看刚才的数据', '不要查询实时数据，解释顶压通常升高的原因'):
        current = context.update_tool_context(previous, question, [], None, now=1100)
        assert current['selected_objects'] == [] and current['time_range'] is None
    expired = context.update_tool_context(previous, '画出来', [], None, now=1701)
    assert expired['selected_objects'] == [] and expired['inheritance_reason'] == 'expired'
    new = context.update_tool_context(previous, '再解释风温变化', ['T_blast'], None, now=1100)
    assert new['selected_objects'] == ['T_blast'] and new['time_range'] is None
    merged = context.update_tool_context(previous, '再加上总压差一起看', ['DP_total'], None, now=1100)
    assert merged['selected_objects'] == ['P_top', 'DP_total'] and merged['time_range']['minutes'] == 30


def test_v6_proxy_integration_exact_handlers_and_grounding_seams():
    path = ROOT / '.codex_runtime/qa-routing-v6/candidate/ollama_proxy_server.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    server = next(node for node in tree.body if isinstance(node, ast.ClassDef) and any(isinstance(item, ast.FunctionDef) and item.name == 'handle_qa_chat_stream' for item in node.body))
    for name in ('handle_qa_chat_json', 'handle_qa_chat_stream'):
        method = next(item for item in server.body if isinstance(item, ast.FunctionDef) and item.name == name)
        attrs = [node.func.attr for node in ast.walk(method) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        assert 'complete_model_response' in attrs and 'prefetch_outcome' in attrs and 'public_completion' in attrs

"""Counterexamples for the V16 production completion aggregation failures."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '高炉前端数据/智能助手/backend'))
import qa_history_compound as compound


def pack(question='查询现在炉顶压力的最新值是多少'):
    return {'remainder_question': question, 'tools_disabled': False,
            'outcomes': [{'answer': '已查询，没有匹配历史。',
                          'completion': {'terminal_state': 'completed', 'complete': True,
                                         'reason': 'verified_owner_history_query', 'history_status': 'no_match'}}]}


def latest():
    return {'ok': True, 'model_request_count': 0,
            'completion': {'schema': 'qa-completion-v1', 'terminal_state': 'answered_pending_review', 'complete': None},
            'tool_trace': [{'tool': 'query_gl02_sensors', 'arguments': {'variables': ['P_top'], 'query_type': 'latest'},
                           'result': {'ok': True, 'query_type': 'latest', 'items': [
                               {'requested_variable': 'P_top', 'ok': True,
                                'variable': {'variable_name': 'P_top', 'unit': 'kPa'},
                                'latest': {'value': 12.0, 'ts': '2026-09-16T12:00:00',
                                           'quality': 'good', 'collected_at': '2026-09-16T12:00:01'},
                                'source': {'service': 'test_sensor', 'read_policy': 'readonly'}}]}}]}


def prepared(request):
    return {'history_compound': request,
            'hidden_context': {'mcp_conversation_context': {'selected_objects': ['P_top']}}}


def test_verified_legacy_document_completion_without_boolean_is_recognized():
    result = {'completion': {'schema': 'qa-document-knowledge-v1', 'terminal_state': 'completed',
                             'reason': 'verified_original_subsection'}, 'knowledge_manifest': [{'sha256': 'test'}]}
    answer, out = compound.compose('测试原文', result, {'history_compound': pack('完整说明《三规二制》高炉工长1工作前全部规定')})
    assert out['completion']['terminal_state'] == 'completed'
    assert out['completion']['complete'] is True and '测试原文' in answer


def test_no_match_history_and_revalidated_latest_both_complete():
    answer, out = compound.compose('旧格式答案', latest(), prepared(pack()))
    assert out['completion']['complete'] is True
    assert out['completion']['terminal_state'] == 'completed'
    assert out['completion']['history_subtasks'][0]['history_status'] == 'no_match'
    assert '12kPa' in answer and '旧格式答案' not in answer
    assert '2026-09-16T12:00:00' in answer and 'test_sensor' in answer


@pytest.mark.parametrize('mutation,missing', [
 ('missing_quality', 'quality_meaning'), ('unknown_quality', 'quality_meaning'),
 ('missing_collection', 'collection_time'), ('missing_read_policy', 'readonly_policy'),
])
def test_saved_value_without_quality_provenance_remains_partial(mutation, missing):
    result = latest()
    row = result['tool_trace'][0]['result']['items'][0]
    if mutation == 'missing_quality': row['latest'].pop('quality')
    elif mutation == 'unknown_quality': row['latest']['quality'] = 'unmapped'
    elif mutation == 'missing_collection': row['latest'].pop('collected_at')
    else: row['source'].pop('read_policy')
    answer, out = compound.compose('旧格式答案', result, prepared(pack()))
    assert out['completion']['complete'] is False
    assert out['completion']['terminal_state'] == 'partial'
    assert missing in out['completion']['missing_evidence_fields']['P_top']
    assert '12kPa' in answer and 'test_sensor' in answer


@pytest.mark.parametrize('mutation', ['failed', 'nonfinite', 'wrong_object', 'missing_time', 'missing_source',
                                    'duplicate', 'wrong_type', 'wrong_args', 'explicit_failed', 'needs_final'])
def test_incomplete_or_wrong_scope_tool_never_becomes_completed(mutation):
    result = latest()
    trace = result['tool_trace'][0]
    row = trace['result']['items'][0]
    if mutation == 'failed': row['ok'] = False
    elif mutation == 'nonfinite': row['latest']['value'] = float('nan')
    elif mutation == 'wrong_object': row['variable']['variable_name'] = 'T_hotblast'
    elif mutation == 'missing_time': row['latest'].pop('ts')
    elif mutation == 'missing_source': row['source'] = {}
    elif mutation == 'duplicate': trace['result']['items'].append(row.copy())
    elif mutation == 'wrong_type': trace['arguments']['query_type'] = 'statistics'
    elif mutation == 'wrong_args': trace['arguments']['variables'] = ['T_hotblast']
    elif mutation == 'explicit_failed': result['completion']['complete'] = False
    else: result['needs_final'] = True
    _, out = compound.compose('可见答案', result, prepared(pack()))
    assert out['completion']['terminal_state'] == 'partial'
    assert out['completion']['complete'] is False


@pytest.mark.parametrize('question', ['分析现在炉顶压力是否正常', '查询炉顶压力趋势', '统计炉顶压力平均值'])
def test_single_point_cannot_complete_analysis(question):
    _, out = compound.compose('单点不是完整分析', latest(), prepared(pack(question)))
    assert out['completion']['complete'] is False


@pytest.mark.parametrize('mutation', ['false', 'missing_manifest', 'unknown_reason', 'wrong_schema', 'partial'])
def test_document_text_alone_never_proves_completion(mutation):
    result = {'completion': {'schema': 'qa-document-knowledge-v1', 'terminal_state': 'completed',
                             'reason': 'verified_original_subsection'}, 'knowledge_manifest': [{'sha256': 'test'}]}
    if mutation == 'false': result['completion']['complete'] = False
    elif mutation == 'missing_manifest': result.pop('knowledge_manifest')
    elif mutation == 'unknown_reason': result['completion']['reason'] = 'some_answer'
    elif mutation == 'wrong_schema': result['completion']['schema'] = 'unknown'
    else: result['completion']['terminal_state'] = 'partial'
    _, out = compound.compose('非空原文', result, {'history_compound': pack('制度原文')})
    assert out['completion']['complete'] is False


def test_global_tool_prohibition_blocks_revalidation():
    request = dict(pack(), tools_disabled=True)
    _, out = compound.compose('未查询', latest(), prepared(request))
    assert out['completion']['complete'] is False

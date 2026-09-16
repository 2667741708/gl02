"""Synthetic regression checks against the actual production-derived V22 renderer."""
import ast
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / '.codex_runtime/qa-routing-v22/candidate'
BACKEND = ROOT / '高炉前端数据/智能助手/backend'
sys.path.insert(0, str(BACKEND))
import qa_evidence_policy
import qa_verified_facts as facts


def statistics(**changes):
    return {'avg': 4.0, 'stddev': math.sqrt(8 / 3), 'min': 2.0, 'max': 6.0,
            'count': 3, **changes}


@pytest.mark.parametrize('changes,unit,fragment', [
    ({'avg': -4, 'min': -6, 'max': -2}, 'kPa', '非正'),
    ({'avg': 0, 'min': -1}, 'kPa', '非正'),
    ({'avg': 1e-16}, 'kPa', '接近'),
    ({}, '℃', '比例尺度'), ({}, '°F', '比例尺度'),
    ({}, '', '未登记'), ({'stddev': float('nan')}, 'kPa', '无效'),
    ({'stddev': -1}, 'kPa', '无效'), ({'avg': True}, 'kPa', '无效'),
    ({'min': -1}, 'kPa', '负值'),
])
def test_cv_invalid_domain_is_explicit_without_changing_raw_values(changes, unit, fragment):
    source = statistics(**changes)
    original = dict(source)
    contract = facts.cv_contract(source, unit)
    assert contract['value'] is None and fragment in contract['reason']
    assert source == original


def test_population_cv_recomputed_independently_for_positive_data():
    values = [2, 4, 6]
    mean = sum(values) / len(values)
    population_std = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    contract = facts.cv_contract(statistics(), 'kPa')
    assert contract['value'] == pytest.approx(population_std / mean * 100)
    assert '零点未另行核实' in contract['reason']


def test_trend_names_two_signal_scope_and_exposes_recent_reversal():
    source = {'endpoint_direction': '下降', 'regression_direction': '下降',
              'recent_direction': '上升', 'recent_delta': 2, 'trend_consistency': 'consistent'}
    text = facts.trend_context(source, 'kPa', lambda value: str(value))
    assert '首末与回归一致性 consistent' in text
    assert '存在时间尺度差异' in text and '最近15分钟方向 上升' in text
    assert source['trend_consistency'] == 'consistent'


def test_trend_rejects_unknown_typed_labels_and_false_upstream_agreement():
    text = facts.trend_context({'endpoint_direction': '下降', 'regression_direction': '上升',
                               'recent_direction': {}, 'trend_consistency': 'consistent'}, 'kPa', str)
    assert '首末与回归一致性 conflicting' in text
    assert '证据不足' in text and '变化量 无法判断；' in text


def renderer(path):
    if not path.is_file():
        if os.environ.get('BF_QA_RELEASE_CANDIDATE_REQUIRED') == '1':
            pytest.fail('Release gate requires the captured production-derived candidate')
        pytest.skip('Production-derived renderer integration requires the private prepared candidate')
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in {'deterministic_mcp_answer', 'try_load_json'}]
    namespace = {'json': json, 'Any': Any, 'qa_verified_facts': facts,
                 'PROMPT_METRIC_ALIASES': {'P_top': '顶压'},
                 'PROMPT_METRIC_UNIT_FALLBACKS': {'P_top': 'kPa'}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['deterministic_mcp_answer']


def payload(stats, unit='kPa'):
    return json.dumps({'ok': True, 'items': [{
        'requested_variable': 'P_top', 'ok': True,
        'variable': {'variable_name': 'P_top', 'unit': unit},
        'source': {'profile': 'synthetic_fixture', 'read_policy': 'readonly'},
        'start_time': '2026-01-01T00:00:00', 'end_time': '2026-01-01T00:30:00',
        'statistics': stats}]})


def test_actual_candidate_renderer_preserves_fields_and_corrects_scope():
    source = statistics(endpoint_direction='下降', regression_direction='下降',
                        recent_direction='上升', recent_delta=2, trend='下降', trend_consistency='consistent')
    answer = renderer(CANDIDATE / 'ollama_proxy_server.py')('query_gl02_sensors', payload(source))
    assert '总体标准差 STDDEV_POP' in answer and '样本数 3' in answer
    assert '全窗口趋势 下降' in answer and '存在时间尺度差异' in answer
    assert '来源：synthetic_fixture / readonly' in answer
    assert 'CV = STDDEV_POP ÷ 均值 × 100%' in answer


def test_original_production_renderer_reproduces_unsigned_domain_failure():
    source = statistics(avg=-4, min=-6, max=-2)
    before = renderer(CANDIDATE.parent / 'baseline/ollama_proxy_server.py')('query_gl02_sensors', payload(source))
    after = renderer(CANDIDATE / 'ollama_proxy_server.py')('query_gl02_sensors', payload(source))
    assert '= -40.825%' in before
    assert 'CV未提供' in after and '非正' in after
    assert '均值 -4' in before and '均值 -4' in after


def test_mcp_prompt_retains_goals_and_assigns_security_to_implementation():
    assert '协议本身自动保障安全' in qa_evidence_policy.PROMPT
    assert '信息充分时直接回答' in qa_evidence_policy.PROMPT
    assert '不生成任何代码' in qa_evidence_policy.PROMPT

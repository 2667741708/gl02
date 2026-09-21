"""QAOPT-R10: actual multi-turn routing state, distinct from reusable evidence."""
import math
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '高炉前端数据/智能助手/backend'))
import mcp_conversation_context as context

def previous():
    state = context.update_tool_context(None, '最近两小时顶压趋势', ['P_top'], 120, now=1000)
    state['last_evidence'] = [{'value': 999, 'data_time': 'old'}]
    return state

@pytest.mark.parametrize('question', ['它现在是多少', '继续看当前实时值', '这个最新值是多少'])
def test_explicit_latest_followup_keeps_object_but_drops_historical_window(question):
    state = context.update_tool_context(previous(), question, [], None, now=1100)
    assert state['selected_objects'] == ['P_top']
    assert state['time_range'] is None and state['analysis_goal'] == 'latest'
    assert not state['inheritance']['time_range']
    routing = context.enrich_routing_question(question, state)
    assert '最近120分钟' not in routing and '查询最新值' in routing
    assert state['last_evidence'] == [] and state['evidence_reuse'] is False

@pytest.mark.parametrize('stamp', [None, True, math.nan, math.inf, '1000'])
def test_unverifiable_clock_cannot_authorize_inheritance(stamp):
    old = previous()
    old['updated_at'] = stamp
    state = context.update_tool_context(old, '画出来', [], None, now=1100)
    assert state['selected_objects'] == [] and state['time_range'] is None

@pytest.mark.parametrize('minutes', [True, 0, -30, '120', math.nan])
def test_corrupt_prior_window_is_not_routed_as_history(minutes):
    old = previous()
    old['time_range']['minutes'] = minutes
    state = context.update_tool_context(old, '画出来', [], None, now=1100)
    assert state['time_range'] is None

def test_explicit_historical_followup_keeps_requested_window_even_with_current_word():
    state = context.update_tool_context(previous(), '这个当前最近30分钟趋势', [], 30, now=1100)
    assert state['selected_objects'] == ['P_top'] and state['time_range']['minutes'] == 30

def test_topic_switch_and_user_supplied_data_do_not_inherit_live_objects():
    for question in ['新问题，请解释三规二制', '不要查询实时数据，分析我提供的数据', '换个话题，通常风温如何影响热平衡']:
        state = context.update_tool_context(previous(), question, [], None, now=1100)
        assert state['selected_objects'] == [] and state['time_range'] is None

def test_adding_object_inherits_valid_window_without_reusing_measurements():
    state = context.update_tool_context(previous(), '再加上总压差比较', ['DP_total'], None, now=1100)
    assert state['selected_objects'] == ['P_top', 'DP_total']
    assert state['time_range']['minutes'] == 120 and state['last_evidence'] == []

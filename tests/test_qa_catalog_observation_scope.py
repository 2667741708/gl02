"""Route point catalogs and colloquial observations without widening reads."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_task_plan as planner


CATALOG = [
    '炉顶温度有哪些具体点？',
    '炉喉温度有哪些点？',
    '静压力现在能查哪些点？',
    '帮我列出当前可用的炉顶相关点位',
]


@pytest.mark.parametrize('question', CATALOG)
def test_catalog_question_has_metadata_only_permission(question):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['live_data']
    assert plan['catalog_only'] is True
    assert plan['allow_mcp_tools'] is True
    assert plan['allow_prefetch'] is False
    assert planner.sensor_context_policy(plan)['enabled'] is False
    for tool in ('find_gl02_variables', 'get_gl02_variable_info', 'list_gl02_available_variables',
                 'list_gl02_static_pressure_points'):
        assert planner.tool_allowed(tool, plan)
    for tool in ('get_latest_gl02_value', 'query_gl02_sensors', 'plot_gl02_trends',
                 'get_latest_furnace_snapshot', 'imes__query_current_heat_chemistry'):
        assert not planner.tool_allowed(tool, plan)


@pytest.mark.parametrize('question', [
    '当前可用的炉顶相关点位和最近一小时趋势一起查',
    '列出炉顶温度点位，并查询现在的数值',
])
def test_catalog_plus_measurement_keeps_explicit_measurement_scope(question):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['live_data']
    assert plan['catalog_only'] is False
    assert plan['allow_prefetch'] and planner.tool_allowed('query_gl02_sensors', plan)


@pytest.mark.parametrize('question', [
    '全炉压差最近一小时升了还是降了？',
    '13层F温度最近是不是升高了？',
    '画出CO、CO2、H2最近一小时趋势图。',
    '最近半小时炉顶压力如何？',
    '炉顶压力近况，带上起止时间和当前值。',
])
def test_colloquial_observation_authorizes_live_read(question):
    plan = planner.build_task_plan(question)
    assert 'live_data' in plan['intents']
    assert not plan['catalog_only']
    assert plan['allow_prefetch'] and plan['allow_mcp_tools']


@pytest.mark.parametrize('question', [
    '不要查询实时数据，说明炉顶温度有哪些影响因素。',
    '请解释“炉顶温度有哪些具体点”这句话。',
    '《三规二制》中有哪些点需要记住？',
    '一般炉顶压力上升有哪些原因？',
])
def test_catalog_and_observation_words_do_not_widen_restricted_or_conceptual_scope(question):
    plan = planner.build_task_plan(question)
    assert not plan.get('catalog_only')
    assert not plan['allow_prefetch']
    assert not planner.tool_allowed('query_gl02_sensors', plan)


def test_supplied_values_and_independent_catalog_remain_separate():
    plan = planner.build_task_plan('风温=[1000,1010]，计算平均值；炉顶温度有哪些点？')
    assert set(plan['intents']) == {'user_supplied_data', 'live_data'}
    assert plan['catalog_only'] is True
    assert plan['allowed_sources'] == ['live_readonly_data', 'user_message']
    assert not plan['allow_prefetch']


def test_catalog_flag_is_in_public_audit_without_question_text():
    public = planner.public_task_plan(planner.build_task_plan(CATALOG[0]))
    assert public['schema'] == 'qa-task-plan-v11-catalog-observation-scope'
    assert public['catalog_only'] is True
    assert 'instruction_text' not in public


def test_chinese_comma_between_chapter_numbers_is_not_an_instruction_separator():
    question = '完整列出《三规二制》第27，28章原文'
    assert planner.instruction_clauses(question) == [question]
    assert planner.active_source_clauses(question) == [question]

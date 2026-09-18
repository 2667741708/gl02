"""Exercise actual proxy planner seam rather than only context state helpers."""
import ast
from datetime import datetime, timedelta
from functools import lru_cache
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v20_builder', ROOT / 'tools/build_qa_routing_v20_candidate.py')
import sys
sys.path.insert(0, str(ROOT / 'tools'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


SOURCE = ROOT / 'tests/qa_regression/fixtures/planner_seam_v18.py.txt'


@lru_cache(maxsize=1)
def planner():
    source = SOURCE
    tree = ast.parse(builder.build(source.read_text(encoding='utf-8')))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
        and node.name in ('qa_mcp_current_user_text', 'qa_mcp_planning_question')]
    namespace = {'qa_mcp_variables':lambda text: ['P_top'] if '顶压' in text else [],
        'qa_mcp_imes_plan':lambda text: None, '_detect_heat_reference':lambda text: None}
    exec(compile(ast.Module(body=functions, type_ignores=[]), '<actual-proxy-seam>', 'exec'), namespace)
    return namespace['qa_mcp_planning_question']


@pytest.mark.parametrize('question', ['这个最近30分钟趋势','那个过去一小时的走势','它们现在是多少',
    '这些平均是多少','上面的最近30分钟统计','刚才那个变化如何'])
def test_pronoun_followup_keeps_owner_resolved_private_routing_context(question):
    raw=question+'\n[服务端对话状态：标准变量：DP_total；最近30分钟；查询意图：history；查询历史趋势]'
    assert planner()(raw)==raw


@pytest.mark.parametrize('question', ['查询当前顶压','新问题查询顶压最近30分钟趋势',
    '这个顶压现在是多少','只用我给的10、20、30计算平均值','解释压力控制原理'])
def test_explicit_object_or_unrelated_new_question_drops_old_routing_suffix(question):
    raw=question+'\n[服务端对话状态：标准变量：DP_total；最近30分钟；查询意图：history]'
    assert planner()(raw)==question


def test_real_planner_followup_enters_deterministic_statistics_with_exact_window():
    tree=ast.parse(builder.build(SOURCE.read_text(encoding='utf-8')))
    functions=[node for node in tree.body if isinstance(node,ast.FunctionDef)
        and node.name in ('qa_mcp_current_user_text','qa_mcp_planning_question','qa_mcp_sensor_query_plan')]
    from types import SimpleNamespace
    namespace={'Any':object,'datetime':datetime,'timedelta':timedelta,'re':__import__('re'),
        'QA_ANSWER_ROUTE_CODE':'code','QA_ANSWER_ROUTE_ANALYSIS':'analysis','qa_answer_route':lambda text:'general',
        'qa_mcp_variables':lambda text:['DP_total'] if 'DP_total' in text else [],
        'qa_mcp_analysis_variables':lambda text:['DP_total'] if 'DP_total' in text else [],
        'qa_mcp_imes_plan':lambda text:None,'_detect_heat_reference':lambda text:None,
        'qa_mcp_body_temperature_statistics_plan':lambda text:None,'qa_mcp_duration_minutes':lambda text:30,
        'qa_evidence_policy':SimpleNamespace(no_live_lookup=lambda text:False)}
    exec(compile(ast.Module(body=functions,type_ignores=[]),'<actual-planner-sensor-seam>','exec'),namespace)
    raw='这个最近30分钟趋势\n[服务端对话状态：标准变量：DP_total；最近30分钟；查询意图：history；查询历史趋势]'
    plan=namespace['qa_mcp_sensor_query_plan'](namespace['qa_mcp_planning_question'](raw))
    assert plan['tool']=='query_gl02_sensors'
    assert plan['arguments']['variables']==['DP_total'] and plan['arguments']['query_type']=='statistics'
    start=datetime.fromisoformat(plan['arguments']['start_time'])
    end=datetime.fromisoformat(plan['arguments']['end_time'])
    assert end-start==timedelta(minutes=30)

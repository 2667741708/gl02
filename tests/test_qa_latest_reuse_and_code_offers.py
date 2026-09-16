"""Boundary regressions reproduced by the V23 online original questions."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / '高炉前端数据/智能助手/backend'
sys.path.insert(0, str(BACKEND))
import qa_task_plan as planner
import qa_verified_facts as facts
import qa_evidence_policy as policy


def latest(name='P_top', value=250):
    return {'ok':True, 'variable':{'variable_name':name,'unit':'kPa'},
            'latest':{'value':value,'ts':'2030-01-01T10:00:00+08:00'},
            'source':{'engine':'fixture_readonly','read_policy':'readonly'}}


def pack(name='P_top'):
    return {'used':True,'kind':'latest','variable':name,'latest':latest(name)}


@pytest.mark.parametrize('question,name', [
    ('给我说一下炉顶的压力','P_top'),('告诉我一下炉顶的温度','T_top'),
    ('现在顶压是多少','P_top'),('顶压','P_top')])
def test_original_simple_latest_is_reused(question, name):
    assert facts.reusable_latest_read(question, pack(name), planner.build_task_plan(question))


@pytest.mark.parametrize('question', [
    '最近两小时顶压趋势','顶压正常吗','当前顶压风险分析','当前顶压和风量匹配吗',
    '顶压的原理是什么','昨晚顶压数据','读取日报摘要','之前问过顶压吗',
    '不要查现场数据，告诉我顶压原理','只用我给的数据分析顶压',
    '把顶压最近两小时画出来','顶压与历史基线比较','当前顶压变化量',
    '当前顶压均值和标准差','根据《高炉规程》解释顶压','当前顶压有什么作用',
    '当前炉顶温差','查顶压8:00至9:00','查顶压八点 至 九点'])
def test_point_cannot_complete_other_tasks(question):
    assert not facts.reusable_latest_read(question, pack(), planner.build_task_plan(question))


@pytest.mark.parametrize('bad', [True, float('nan'), float('inf')])
def test_invalid_value_not_reused(bad):
    payload=pack();payload['latest']['latest']['value']=bad
    assert not facts.reusable_latest_read('当前顶压',payload,planner.build_task_plan('当前顶压'))


def test_wrong_object_missing_point_and_write_source_not_reused():
    plan=planner.build_task_plan('当前顶压')
    payload=pack();payload['latest']['variable']['variable_name']='Q_blast'
    assert not facts.reusable_latest_read('当前顶压',payload,plan)
    payload=pack();payload['latest']['source']['read_policy']='write'
    assert not facts.reusable_latest_read('当前顶压',payload,plan)
    payload={'used':True,'kind':'multi_latest','latest_by_variable':{'P_top':latest()}}
    assert not facts.reusable_latest_read('当前顶压和风量',payload,{**plan,'entities':['P_top','Q_blast']})


def test_production_ui_enable_flag_does_not_replan_completed_read():
    path=ROOT/'.codex_runtime/qa-routing-v24/candidate/ollama_proxy_server.py'
    if not path.exists():
        if os.environ.get('BF_QA_RELEASE_CANDIDATE_REQUIRED') == '1':
            pytest.fail('Required V24 production-derived candidate missing')
        pytest.skip('Prepare V24 production-derived candidate for integration seam')
    node=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='qa_mcp_should_use_tools')
    scope={'Any':object,'QA_MCP_TOOLS_ENABLED':True,'QA_MCP_TOOL_MODE':'auto',
           'qa_evidence_policy':policy,'qa_verified_facts':facts,'qa_task_plan':planner,
           'qa_answer_route':lambda _: 'direct','QA_ANSWER_ROUTE_CODE':'code_generation'}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<production-seam>','exec'),scope)
    assert scope['qa_mcp_should_use_tools']('给我说一下炉顶的压力',{'use_mcp_tools':True},pack()) is False
    assert scope['qa_mcp_should_use_tools']('当前顶压趋势',{'use_mcp_tools':True},pack()) is True


@pytest.mark.parametrize('offer', [
    '我可以提供绘图代码。','3. 生成绘图代码（需您自行运行）。',
    '可以给出 SQL语句。','我将提供Python示例。','需要时能编写伪代码。',
    '我可以运行这个脚本。'])
def test_offers_removed_without_erasing_valid_facts(offer):
    result=policy.enforce_no_code('均值为4。\n'+offer)
    assert '均值为4' in result
    assert offer not in result
    assert policy.NO_CODE in result


def test_mixed_negative_clause_cannot_hide_positive_offer():
    result=policy.enforce_no_code('均值为4，我不生成代码，但我可以提供伪代码。')
    assert '均值为4' in result
    assert '但我可以提供伪代码' not in result


@pytest.mark.parametrize('text', [
    '暂不生成代码。可以查询授权数据并生成界面图表。',
    '可以解释MCP和SQL的概念。','均值=(2+4+6)/3=4。',
    '不提供代码或脚本示例。','避免生成代码，使用中文步骤说明。'])
def test_allowed_concepts_math_queries_and_chart_kept(text):
    assert policy.enforce_no_code(text)==text

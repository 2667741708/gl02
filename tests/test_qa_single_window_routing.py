"""Single-window observations must reach the existing reviewed read-only resolver."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '高炉前端数据/智能助手/backend'))
import qa_task_plan


@pytest.mark.parametrize('question', [
    '上部压差、下部压差、全炉压差最近半小时对比一下',
    '10层D炉体温度最近半小时稳不稳',
    '10层D温度最近半小时稳不稳',
    '第10层 D 温度过去30分钟稳不稳',
    '最近半小时炉顶压力有没有波动？',
    '最近30分钟炉体温度稳不稳',
    '当前铁口温度高不高',
])
def test_live_observation_enables_reviewed_read_only_execution(question):
    plan = qa_task_plan.build_task_plan(question)
    assert 'live_data' in plan['intents']
    assert plan['allow_prefetch'] and plan['allow_mcp_tools']
    assert qa_task_plan.tool_allowed('query_gl02_sensors', plan)


@pytest.mark.parametrize('question', [
    '上部压差最近半小时对比一下，不要查询现场数据',
    '10层D炉体温度最近半小时稳不稳，不需要查实时数据',
    '只根据我提供的假设顶压数据判断最近半小时稳不稳',
    '通常炉体温度稳不稳如何判断',
    '一般压差比较的原理是什么',
    '解释“10层D炉体温度最近半小时稳不稳”这句话的含义',
    '最近半小时对比一下两个小说角色',
    '根据《操作制度》说明最近半小时压差对比的方法',
])
def test_no_live_and_explanatory_boundaries_remain_closed(question):
    plan = qa_task_plan.build_task_plan(question)
    assert not plan['allow_prefetch'] and not plan['allow_mcp_tools']

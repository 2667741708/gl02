"""Mathematical functions remain available under the no-code policy."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_evidence_policy as policy


@pytest.mark.parametrize('question', [
 '给出一次函数y=2x+1在x=3时的值',
 '给出二次函数y=x²-4x+3的极小值',
 '写出反比例函数y=6/x的定义域',
 '给出数学函数f(x)=x²的导数',
 '输出函数f(x)=2x+1在x=3时的值',
 '给出函数的斜率和截距，已知y=2x+1',
 '给出函数值，已知f(x)=x²，x=2',
 '写出三角函数sin(x)的周期',
 '给出指数函数y=2^x在x=3时的值',
 '给出对数函数y=ln(x)的定义域',
])
def test_math_function_is_not_disabled_code(question):
    assert not policy.code_requested(question)
    assert policy.direct_result(question) == {}
    assert not policy.boundary_result(question, {'completion': {'terminal_state': 'completed'}})['completion'].get('policy_limited')


@pytest.mark.parametrize('question', [
 '写一个计算均值的函数', '生成一个函数', '提供Python函数示例',
 '写出一次函数求值的Python代码', '给出数学函数f(x)=x²的伪代码',
 '输出函数f(x)=2x+1的JavaScript实现', '给出二次函数绘图脚本',
 '运行函数f(x)=2x+1的代码', '展示一个SQL函数实现',
 '运行函数f(x)', '实现一次函数', '给出数学函数的Python示例',
])
def test_code_function_requests_remain_disabled(question):
    assert policy.code_requested(question)
    result = policy.direct_result(question)
    assert result['answer_route'] == 'code_disabled'
    assert result['model_request_count'] == 0 and not result['tool_used']


def test_mixed_math_and_code_preserves_math_subtask():
    question = '给出一次函数y=2x+1的斜率；再写Python代码'
    assert policy.code_requested(question)
    assert not policy.code_request_only(question)
    assert policy.direct_result(question) == {}
    answer = policy.apply_request_boundary(question, '斜率为2。')
    assert '斜率为2' in answer and policy.NO_CODE in answer
    result = policy.boundary_result(question, {'completion': {'terminal_state': 'completed'}})
    assert result['completion']['terminal_state'] == 'partial'
    assert result['completion']['blocked_subtasks'] == ['code_generation_or_execution']


@pytest.mark.parametrize('answer', ['f(x)=2x+1，f(3)=7。', '一次函数的斜率为2，截距为1。'])
def test_mathematical_notation_survives_output_guard(answer):
    assert policy.enforce_no_code(answer) == answer


def test_frozen_candidate_preserves_fixed_base_and_actual_policy():
    candidate = ROOT / '.codex_runtime/qa-routing-v38/candidate-r2'
    manifest = json.loads((candidate / 'package_manifest.private.json').read_bytes())
    assert len(manifest['files']) == 15
    assert manifest['model_name'] == 'chiqiongblastfuenace:latest'
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not manifest['model_switch_allowed'] and not manifest['fallback_model_allowed']
    prior = ROOT / '.codex_runtime/qa-routing-v37/candidate-r2'
    for name, item in manifest['files'].items():
        assert hashlib.sha256((candidate / name).read_bytes()).hexdigest() == item['sha256']
    for name in manifest['inherited_v37_files_byte_identical']:
        assert (candidate / name).read_bytes() == (prior / name).read_bytes()
    assert manifest['additional_runtime_read_set'] == json.loads((prior / 'package_manifest.private.json').read_bytes())['additional_runtime_read_set']
    spec = importlib.util.spec_from_file_location('qa_math_function_frozen_policy', candidate / 'qa_evidence_policy.py')
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    assert frozen.direct_result('给出一次函数y=2x+1的斜率') == {}
    assert frozen.direct_result('写出一次函数求值的Python代码')['answer_route'] == 'code_disabled'


@pytest.mark.parametrize('question,code_route', [
 ('给出一次函数y=2x+1的斜率', False),
 ('给出一次函数y=2x+1的斜率；再写Python代码', False),
 ('写出一次函数求值的Python代码', True),
])
def test_actual_proxy_route_distinguishes_math_and_code(question, code_route):
    source = (ROOT / '.codex_runtime/qa-routing-v38/candidate-r2/ollama_proxy_server.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_answer_route')
    scope = {'qa_evidence_policy': policy, 'normalize_spoken_question': lambda text: text,
     'qa_mcp_variables': lambda text: [],
     'QA_ANSWER_ROUTE_CODE': 'code_generation', 'QA_ANSWER_ROUTE_ANALYSIS': 'analysis',
     'QA_ANSWER_ROUTE_FACT_ONLY': 'fact', 'QA_ANSWER_ROUTE_GENERAL': 'general'}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-candidate-route>', 'exec'), scope)
    assert (scope['qa_answer_route'](question) == 'code_generation') is code_route

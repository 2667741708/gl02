"""Reproduce unfinished analyses and validate real production-derived exit seams."""
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import re
import sys
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_completion as completion
import qa_evidence_policy

spec = importlib.util.spec_from_file_location('completion_builder', ROOT / 'tools/build_qa_v29_completion_candidate.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
BASE = ROOT / '.codex_runtime/qa-routing-v28/candidate-r4/ollama_proxy_server.py'


def response(content='完整解释。', reason='stop', **changes):
    obj = {'message': {'content': content}, 'done': True, 'done_reason': reason}
    obj.update(changes)
    return obj


@pytest.mark.parametrize('reason', ['length', 'max_tokens', 'token_limit'])
@pytest.mark.parametrize('key', ['done_reason', 'finish_reason'])
def test_all_limit_causes_are_partial_even_with_explicit_completed_contract(reason, key):
    result = {'answer': '答复未完', 'model_timing': {key: reason},
        'completion': {'terminal_state': 'completed', 'complete': True}}
    original = deepcopy(result)
    contract = completion.public_completion(result)
    assert contract['terminal_state'] == 'partial' and not contract['complete']
    assert contract['incomplete_reasons'] == ['output_limit'] and result == original


@pytest.mark.parametrize('obj', [{'done': False, 'done_reason': 'stop'}, {'done': True, 'done_reason': 'error'},
    {'done': True, 'done_reason': 'length'}, {'done': True, 'done_reason': ['stop']}, {}, {'done': 1}])
def test_eof_unknown_or_malformed_termination_cannot_be_transport_completed(obj):
    assert not completion.stream_finished(obj)


@pytest.mark.parametrize('reason', [None, 'stop', 'eos', 'end_turn'])
def test_real_normal_terminal_events_remain_accepted(reason):
    assert completion.stream_finished({'done': True, 'done_reason': reason})


@pytest.mark.parametrize('tail', ['待核实项', '待核实事项：', '## 结论', '仍需核对的指标:', '建议'])
def test_unfinished_heading_is_detected_before_composition_can_hide_it(tail):
    answer = '已有核实事实。\n' + tail
    assert completion.incomplete_response(response(answer), answer)
    contract = completion.public_completion({'completion': {'complete': True, 'terminal_state': 'completed'}}, answer=answer)
    assert contract['terminal_state'] == 'partial' and 'unfinished_heading' in contract['incomplete_reasons']


@pytest.mark.parametrize('answer', ['结论：尚不能确认风险。', '待核实项：采样覆盖率。',
    '建议核对来源；端点质量不代表整窗。', '制度原文中出现“待核实项”，完整引用如下。'])
def test_complete_sentences_containing_heading_words_are_not_false_positives(answer):
    assert not completion.incomplete_response(response(answer), answer)


def test_composed_actual_answer_is_audited_instead_of_stale_tool_text():
    result = {'answer': '待核实项', 'completion': {'terminal_state': 'completed', 'complete': True}}
    contract = completion.public_completion(result, answer='待核实项：覆盖率。\n制度子任务已完成。')
    assert contract['complete'] is True


@pytest.mark.parametrize('status', ['incomplete', 'incomplete_factual_fallback'])
def test_preserved_facts_do_not_hide_missing_model_analysis(status):
    result = {'answer': '保留的事实。', 'model_explanation': {'status': status},
        'completion': {'terminal_state': 'completed', 'complete': True}}
    contract = completion.public_completion(result)
    assert not contract['complete'] and 'model_analysis_incomplete' in contract['incomplete_reasons']


def test_chart_or_document_suffix_cannot_hide_recorded_unfinished_heading():
    result = {'completion': {'terminal_state': 'answered_pending_review', 'complete': False,
        'incomplete_reasons': ['unfinished_heading']}}
    contract = completion.public_completion(result, answer='待核实项\n图表链接已保留。\n制度原文已附。')
    assert contract['terminal_state'] == 'partial' and 'unfinished_heading' in contract['incomplete_reasons']


@pytest.mark.parametrize('first', [response('事实。\n待核实项'), response('', 'stop'), response('未完', 'max_tokens'), response('未完', None, done=False)])
def test_bounded_repair_uses_same_inputs_no_tools_and_only_one_additional_call(first):
    calls = []
    responses = iter([first, response('完整且简短的答复。')])
    messages = [{'role': 'user', 'content': '合成问题'}]
    original = deepcopy(messages)
    def call(items, **kwargs):
        calls.append((items, kwargs))
        return next(responses)
    answer, result = completion.complete_model_response(messages, call=call, clean=str.strip, timing={}, response_mode='flash')
    assert answer == '完整且简短的答复。' and result['completion']['complete']
    assert result['model_request_count'] == 2 and result['completion']['repair_succeeded']
    assert len(calls) == 2 and all(kw['tools'] is None for _, kw in calls)
    assert calls[1][0][0] == messages[0] and messages == original


def test_failed_or_unfinished_repair_keeps_original_and_partial_without_third_call():
    calls = []
    def call(*args, **kwargs):
        calls.append(1)
        return response('已有事实。\n待核实项')
    answer, result = completion.complete_model_response([], call=call, clean=str.strip, timing={}, response_mode='flash')
    assert len(calls) == 2 and not result['completion']['complete']
    assert answer.startswith('已有事实。') and 'unfinished_heading' in result['completion']['incomplete_reasons']


def namespace(after, obj):
    raw = BASE.read_bytes()
    text = builder.transform(raw).decode() if after else raw.decode()
    names = {'qa_grounded_mcp_analysis', 'qa_body_temperature_model_explanation'}
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name in names]
    calls = []
    def call(*args, **kwargs):
        calls.append(kwargs)
        return obj
    scope = {'Any': Any, 're': re, 'QA_RESPONSE_MODE_FLASH': 'flash', 'qa_completion': completion,
        'qa_evidence_policy': qa_evidence_policy, 'call_ollama_chat_obj': call,
        'clean_llm_output': str.strip, 'ollama_response_timing': lambda r: {'done_reason': r.get('done_reason')},
        'llm_output_is_empty': lambda s: not s.strip(), 'answer_is_grounded': lambda *a: True,
        'emit_host_log': lambda *a, **kw: None}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual-completion-seams>', 'exec'), scope)
    return scope, calls


@pytest.mark.parametrize('obj', [response('解释未完', 'length'), response('已有解释。\n待核实项')])
def test_actual_grounded_analysis_reproduces_false_success_then_preserves_facts(obj):
    before, _ = namespace(False, obj)
    old = before['qa_grounded_mcp_analysis']('合成问题', '已核验事实。', [])
    assert old[1] == 'succeeded'
    after, calls = namespace(True, obj)
    answer, status, timing = after['qa_grounded_mcp_analysis']('合成问题', '已核验事实。', [])
    assert status == 'incomplete_factual_fallback' and answer.startswith('已核验事实。')
    assert obj['message']['content'] not in answer and len(calls) == 1 and calls[0]['tools'] is None


def test_actual_body_explanation_discards_truncation_without_dropping_deterministic_facts():
    before, _ = namespace(False, response('伴随变化', 'max_tokens'))
    assert before['qa_body_temperature_model_explanation']('问题', '已核验事实。')[1] == 'succeeded'
    after, calls = namespace(True, response('伴随变化', 'max_tokens'))
    assert after['qa_body_temperature_model_explanation']('问题', '已核验事实。') == ('', 'incomplete')
    assert len(calls) == 1


def test_actual_successful_grounded_response_remains_usable():
    scope, calls = namespace(True, response())
    assert scope['qa_grounded_mcp_analysis']('问题', '已核验事实。', [])[1] == 'succeeded'
    assert len(calls) == 1


def test_all_public_handler_exits_audit_actual_answer_and_stream_uses_shared_finish_gate():
    tree = ast.parse(builder.transform(BASE.read_bytes()))
    methods = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in {'handle_qa_chat_json', 'handle_qa_chat_stream'}}
    calls = [n for method in methods.values() for n in ast.walk(method) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
        and n.func.value.id == 'qa_completion' and n.func.attr == 'public_completion']
    assert len(calls) == 3 and all(any(kw.arg == 'answer' and isinstance(kw.value, ast.Name) and kw.value.id == 'answer' for kw in call.keywords) for call in calls)
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'stream_finished' for n in ast.walk(methods['handle_qa_chat_stream']))


def test_cancel_during_repair_propagates_instead_of_being_marked_success():
    class Cancelled(BaseException): pass
    calls = []
    def call(*a, **kw):
        calls.append(1)
        if len(calls) == 2: raise Cancelled()
        return response('未完', 'length')
    with pytest.raises(Cancelled):
        completion.complete_model_response([], call=call, clean=str.strip, timing={}, response_mode='flash')
    assert len(calls) == 2

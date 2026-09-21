"""One bounded in-request completion repair and honest public terminal state."""
from __future__ import annotations
import re

VERSION = 'qa-completion-v2'
LIMIT_REASONS = frozenset(('length', 'max_tokens', 'token_limit'))
STOP_REASONS = frozenset(('stop', 'eos', 'end_turn'))
_EMPTY_HEADING = re.compile(r'(?:^|\n)\s*(?:#{1,6}\s*)?(?:待核实项|待核实事项|仍需核对的指标|后续核对项|结论|总结|建议)\s*[：:]?\s*$')


def response_text(response: dict) -> str:
    return str((response.get('message') or {}).get('content') or response.get('response') or '').strip()


def truncated(response: dict) -> bool:
    return any(isinstance(response.get(key), str) and response[key] in LIMIT_REASONS for key in ('done_reason', 'finish_reason'))


def unfinished_heading(answer: str) -> bool:
    return bool(_EMPTY_HEADING.search(str(answer or '').strip()))


def stream_finished(response: dict) -> bool:
    """A transport EOF or an unknown finish reason is not normal termination."""
    reason = response.get('done_reason') or response.get('finish_reason')
    return response.get('done') is True and (reason is None or isinstance(reason, str) and reason in STOP_REASONS)


def response_issues(response: dict, answer: str) -> list[str]:
    reasons = []
    reason = response.get('done_reason') or response.get('finish_reason')
    if truncated(response):
        reasons.append('output_limit')
    elif response.get('done') is False or not (isinstance(reason, str) and reason in STOP_REASONS) and not stream_finished(response):
        reasons.append('termination_unverified')
    if not str(answer or '').strip():
        reasons.append('empty_answer')
    elif unfinished_heading(answer):
        reasons.append('unfinished_heading')
    return reasons


def incomplete_response(response: dict, answer: str) -> bool:
    return bool(response_issues(response, answer))


def complete_model_response(messages, *, call, clean, timing, response_mode):
    response = call(messages, tools=None, max_tokens=720, response_mode=response_mode)
    timing.update(response)
    answer, calls, repaired = clean(response_text(response)), 1, False
    still_truncated = truncated(response)
    issues = response_issues(response, answer)
    repair_error = None
    if issues:
        # The original POST is not replayed. One new model item in this turn
        # asks for a shorter complete answer based on the same original inputs.
        repair_messages = [*messages, {'role': 'system', 'content': '上次回答未完整结束、为空或留下没有正文的标题。现在重新组织一个完整且简短的回答，最多250个汉字，优先回答原问题所有必要部分，最后一句必须完整。不新增示例、代码、数值、阈值或无证据结论；保留必要的数据与来源限制。'}]
        calls += 1
        try:
            second = call(repair_messages, tools=None, max_tokens=720, response_mode=response_mode)
            candidate = clean(response_text(second))
            timing.update(second)
            second_issues = response_issues(second, candidate)
            if not second_issues:
                answer, still_truncated, repaired, issues = candidate, False, True, []
        except Exception as exc:
            repair_error = type(exc).__name__
    complete = bool(answer) and not issues
    if still_truncated:
        answer += '\n\n回答达到长度上限，未完整覆盖问题；本轮补答未完成，不应视为完整答案。'
    elif not answer:
        answer = '本轮没有取得可展示的回答，未完成问题。'
    elif issues:
        answer += '\n\n回答未完整结束或存在没有正文的标题；本轮未完整覆盖问题。'
    return answer, {'answer_route': 'evidence_without_tools', 'model_request_count': calls,
                    'completion': {'schema': VERSION, 'terminal_state': 'completed' if complete else 'partial', 'complete': complete, 'truncated': still_truncated, 'incomplete_reasons': issues, 'repair_attempted': calls == 2, 'repair_succeeded': repaired, 'repair_error_type': repair_error, 'semantic_review_required': True}}


def public_completion(result: dict, *, answer: str | None = None) -> dict:
    explicit = result.get('completion')
    state = 'partial' if result.get('complete') is False or result.get('ok') is False or result.get('needs_final') else 'answered_pending_review'
    contract = dict(explicit) if isinstance(explicit, dict) else {'schema': VERSION, 'terminal_state': state, 'complete': False if state == 'partial' else None, 'semantic_review_required': True}
    reasons = list(contract.get('incomplete_reasons') or [])
    timing = result.get('model_timing')
    if (isinstance(timing, dict) and truncated(timing)) or contract.get('truncated') is True:
        reasons.append('output_limit')
    actual = answer if answer is not None else result.get('answer')
    if actual is not None and not str(actual).strip():
        reasons.append('empty_answer')
    elif actual is not None and unfinished_heading(str(actual)):
        reasons.append('unfinished_heading')
    if contract.get('stream_completed') is False:
        reasons.append('stream_incomplete')
    explanation = result.get('model_explanation')
    if result.get('grounding_status') == 'incomplete_factual_fallback' or (isinstance(explanation, dict) and explanation.get('status') in ('incomplete', 'incomplete_factual_fallback')):
        reasons.append('model_analysis_incomplete')
    if reasons:
        contract.update(terminal_state='partial', complete=False, incomplete_reasons=list(dict.fromkeys(reasons)), semantic_review_required=True)
    return contract

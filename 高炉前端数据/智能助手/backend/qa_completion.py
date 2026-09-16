"""One bounded in-request completion repair and honest public terminal state."""
from __future__ import annotations

VERSION = 'qa-completion-v1'


def response_text(response: dict) -> str:
    return str((response.get('message') or {}).get('content') or response.get('response') or '').strip()


def truncated(response: dict) -> bool:
    return response.get('done_reason') in ('length', 'max_tokens', 'token_limit')


def complete_model_response(messages, *, call, clean, timing, response_mode):
    response = call(messages, tools=None, max_tokens=720, response_mode=response_mode)
    timing.update(response)
    answer, calls, repaired = clean(response_text(response)), 1, False
    still_truncated = truncated(response)
    repair_error = None
    if still_truncated:
        # The original POST is not replayed. One new model item in this turn
        # asks for a shorter complete answer based on the same original inputs.
        repair_messages = [*messages, {'role': 'system', 'content': '上次回答因输出长度限制被截断。现在重新组织一个完整且简短的回答，最多250个汉字，优先回答原问题所有必要部分，最后一句必须完整。不新增示例、代码、数值、阈值或无证据结论；保留必要的数据与来源限制。'}]
        calls += 1
        try:
            second = call(repair_messages, tools=None, max_tokens=720, response_mode=response_mode)
            candidate = clean(response_text(second))
            timing.update(second)
            if candidate and not truncated(second):
                answer, still_truncated, repaired = candidate, False, True
        except Exception as exc:
            repair_error = type(exc).__name__
    complete = bool(answer) and not still_truncated
    if still_truncated:
        answer += '\n\n回答达到长度上限，未完整覆盖问题；本轮补答未完成，不应视为完整答案。'
    elif not answer:
        answer = '本轮没有取得可展示的回答，未完成问题。'
    return answer, {'answer_route': 'evidence_without_tools', 'model_request_count': calls,
                    'completion': {'schema': VERSION, 'terminal_state': 'completed' if complete else 'partial', 'complete': complete, 'truncated': still_truncated, 'repair_attempted': calls == 2, 'repair_succeeded': repaired, 'repair_error_type': repair_error, 'semantic_review_required': True}}


def public_completion(result: dict) -> dict:
    explicit = result.get('completion')
    if isinstance(explicit, dict):
        return explicit
    state = 'partial' if result.get('complete') is False or result.get('ok') is False or result.get('needs_final') else 'answered_pending_review'
    return {'schema': VERSION, 'terminal_state': state, 'complete': False if state == 'partial' else None, 'semantic_review_required': True}

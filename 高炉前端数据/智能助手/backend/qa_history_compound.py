"""Execute owner-bound history separately from present-data subtasks (QAOPT-R02).

Historical answers never enter the model or current-data evidence. Server owner
and persisted message cutoff are the only query authority, never client IDs.
"""
import qa_document_compound
import qa_evidence_policy
import qa_history_projection
import qa_task_plan
import qa_verified_facts
import re

VERSION = 'qa-history-compound-v2'
MAX_HISTORY_TASKS = 4


def split_request(question, plan):
    if 'conversation_history' not in plan.get('intents', []) or len(plan['intents']) < 2:
        return None
    history, remainder, blocked = [], [], []
    for clause in qa_document_compound.clauses(question):
        child = qa_task_plan.build_task_plan(clause)
        if child['intents'] == ['conversation_history']:
            history.append(clause)
        elif 'conversation_history' in child['intents']:
            blocked.append('history_clause_scope_ambiguous')
        else:
            remainder.append(clause)
    if not history and not blocked:
        blocked.append('history_clause_scope_missing')
    if len(history) > MAX_HISTORY_TASKS:
        history = []
        blocked.append('history_subtask_limit')
    return {'version': VERSION, 'history_questions': history, 'blocked': blocked,
            'tools_disabled': plan.get('no_live_lookup') is True,
            'remainder_question': '；'.join(remainder) or '请提示用户单独说明非历史问题的对象和时间范围，不猜测或查询。'}


def data_tool_selection(selection, request):
    if request and request.get('tools_disabled'):
        return {'mode': 'none', 'tools': [], 'reason': 'source_plan_disallows_tools'}
    if not request or selection.get('mode') != 'required':
        return dict(selection)
    result = dict(selection)
    result['tools'] = [name for name in selection.get('tools', []) if name != 'search_qa_messages']
    if not result['tools']:
        result.update(mode='none', reason='only_history_tool_requested')
    return result


def execution_plan(question, request):
    plan = qa_task_plan.build_task_plan(question)
    if request and request.get('tools_disabled'):
        plan.update(allow_mcp_tools=False, allow_prefetch=False, no_live_lookup=True, allowed_tool_domains=[])
    return plan


def execute(request, conn, *, owner, before_message_id, selection):
    if not request:
        return None
    outcomes = []
    blocked = list(request['blocked'])
    allowed = not request.get('tools_disabled') and selection.get('mode') != 'none' and (
        selection.get('mode') != 'required' or 'search_qa_messages' in selection.get('tools', []))
    for question in request['history_questions']:
        if not allowed:
            payload = {'ok': False, 'error': 'history_tool_selection_blocked'}
        else:
            try:
                payload = qa_history_projection.fetch_owned_history(
                    conn, owner=owner, before_message_id=before_message_id, question=question)
            except Exception:
                payload = {'ok': False, 'error': 'history_query_failed'}
        outcome = qa_history_projection.history_outcome(payload)
        outcome['answer'] = qa_evidence_policy.enforce_no_code(outcome['answer'])
        success = payload.get('ok') is True and payload.get('source', {}).get('type') == 'owner_scoped_qa_history'
        outcome['completion'] = {'terminal_state': 'completed' if success else 'dependency_blocked',
                                 'complete': success, 'reason': 'verified_owner_history_query' if success else payload.get('error', 'history_query_failed'),
                                 'source_type': 'owner_scoped_qa_history', 'history_status': outcome.get('history_status')}
        outcomes.append(outcome)
    for reason in blocked:
        outcomes.append({'answer': '历史要求未能独立确认范围，请将历史关键词和当前数据问题分开说明；未检索其他身份会话。',
                         'completion': {'terminal_state': 'needs_clarification', 'complete': False, 'reason': reason}})
    return {**request, 'outcomes': outcomes}


def model_messages(messages, prepared):
    pack = prepared.get('history_compound')
    if not pack:
        return messages
    question = (prepared.get('document_compound') or {}).get('remainder_question') or pack['remainder_question']
    systems = [dict(message) for message in messages if message.get('role') == 'system']
    systems.append({'role': 'system', 'content': '历史检索由独立身份受限执行器回答。只回答下列非历史问题；不补写历史记录，不将旧聊天答案当作当前读数、制度原文或新分析证据。'})
    return [*systems, {'role': 'user', 'content': question}]


def normalize_present(answer, result, pack, prepared):
    """Recognize verified legacy contracts; never infer completion from text."""
    out = dict(result or {})
    contract = dict(out.get('completion') or {})
    if (contract.get('schema') == 'qa-document-knowledge-v1'
        and contract.get('terminal_state') == 'completed'
        and 'complete' not in contract
        and contract.get('reason') in {'verified_original_atomic', 'verified_original_subsection',
                                      'verified_original_subsections', 'verified_original_document', 'verified_original_page'}
        and out.get('knowledge_manifest')):
        contract['complete'] = True
        contract['completion_basis'] = 'verified_document_executor_contract'
        out['completion'] = contract
    # An old deterministic latest-reading branch exposes pending completion.
    # Revalidate its actual tool payload and render typed facts before upgrading.
    if contract.get('terminal_state') not in (None, 'answered_pending_review'):
        return answer, out
    if contract.get('complete') is False or out.get('ok') is False or out.get('needs_final'):
        return answer, out
    question = pack['remainder_question']
    plan = execution_plan(question, pack)
    if (plan.get('intents') != ['live_data'] or not plan.get('allow_mcp_tools')
        or re.search(r'分析|判断|是否|正常|异常|风险|趋势|变化|原因|为什么|匹配|对比|比较|统计|平均|最高|最低', question)):
        return answer, out
    expected = list(plan.get('entities') or [])
    context_objects = ((prepared.get('hidden_context') or {}).get('mcp_conversation_context') or {}).get('selected_objects')
    if not expected and isinstance(context_objects, list):
        expected = list(context_objects)
    if any(not isinstance(name, str) or not name for name in expected) or len(set(expected)) != len(expected):
        return answer, out
    traces = out.get('tool_trace') or []
    if not expected or len(traces) != 1:
        return answer, out
    trace = traces[0]
    args, payload = trace.get('arguments') or {}, trace.get('result') or {}
    if (trace.get('tool') != 'query_gl02_sensors' or args.get('query_type') != 'latest'
        or args.get('variables') != expected or payload.get('ok') is not True
        or payload.get('query_type') != 'latest'):
        return answer, out
    rows = payload.get('items')
    if not isinstance(rows, list) or len(rows) != len(expected):
        return answer, out
    names = [row.get('requested_variable') for row in rows if isinstance(row, dict)]
    if len(names) != len(rows) or len(set(names)) != len(names) or set(names) != set(expected):
        return answer, out
    values = {row['requested_variable']: row.get('result', row) for row in rows}
    verified = qa_verified_facts.prefetch_outcome({'used': True, 'kind': 'multi_latest',
                                                'latest_by_variable': values}, plan)
    if verified is None:
        return answer, out
    out.update(completion={**verified['completion'], 'completion_basis': 'revalidated_latest_tool_payload'},
               grounding_status=verified['grounding_status'])
    return verified['answer'], out


def compose(answer, result, prepared):
    pack = prepared.get('history_compound')
    if not pack:
        return answer, result
    answer, out = normalize_present(answer, result, pack, prepared)
    contract = dict(out.get('completion') or {})
    subtasks = [item['completion'] for item in pack['outcomes']]
    failed = [item['reason'] for item in subtasks if item['terminal_state'] != 'completed']
    # Keep the established generated-history prefix so subsequent owner queries
    # exclude this composed excerpt rather than recursively quoting it.
    answer = '在当前会话身份可访问的历史中，本轮复合回答如下：\n【历史记录子任务】\n' + '\n\n'.join(item['answer'] for item in pack['outcomes']) + '\n\n【非历史子任务】\n' + str(answer or '')
    contract.update(history_subtasks=subtasks, semantic_review_required=True)
    if failed or contract.get('terminal_state') != 'completed' or contract.get('complete') is not True:
        contract.update(terminal_state='partial', complete=False, missing_history_subtasks=failed)
    out.update(completion=contract, answer_route='isolated_history_compound')
    return answer, out

"""Bind mixed history to the owner and isolate present-data execution from V13."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = '9a942b2fe73ddb34d0bff8d18beea14047ef898bb6596570d0c1d9509a34e81b'


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Accepted production preparation seam changed: ' + old[:80])
    return text.replace(old, new)


def build(text):
    text = replace_one(text, 'import qa_history_projection\n', 'import qa_history_projection\nimport qa_history_compound\n')
    text = replace_one(text, '            task_plan = qa_task_plan.build_task_plan(question)\n',
        '            source_task_plan = qa_task_plan.build_task_plan(question)\n'
        '            history_request = (qa_history_compound.split_request(question, source_task_plan)\n'
        '                               if str(payload.get("analysis_mode") or "") != "initial_context_explanation" else None)\n'
        '            execution_question = history_request["remainder_question"] if history_request else question\n'
        '            task_plan = qa_history_compound.execution_plan(execution_question, history_request)\n')
    start = text.index('            source_task_plan = ')
    end = text.index('            hidden_context = {', start)
    block = text[start:end]
    for old, new in (
        ('previous_tool_context,\n                question,', 'previous_tool_context,\n                execution_question,'),
        ('detected_objects=qa_mcp_analysis_variables(question)', 'detected_objects=qa_mcp_analysis_variables(execution_question)'),
        ('duration_minutes=qa_mcp_duration_minutes(question)', 'duration_minutes=qa_mcp_duration_minutes(execution_question)'),
        ('enrich_routing_question(question, tool_context)', 'enrich_routing_question(execution_question, tool_context)'),
        ('                else question\n', '                else execution_question\n'),
        ('answer_route = qa_answer_route(question)', 'answer_route = qa_answer_route(execution_question)'),
        ('qa_document_knowledge.execute_document_question(conn, question, task_plan)', 'qa_document_knowledge.execute_document_question(conn, execution_question, task_plan)'),
        ('qa_document_compound.prepare(conn, question, task_plan)', 'qa_document_compound.prepare(conn, execution_question, task_plan)'),
        ('else qa_search_knowledge(\n                question,', 'else qa_search_knowledge(\n                execution_question,'),
        ('            if tool_selection.get("mode") == "required":\n',
         '            history_tool_selection = dict(tool_selection)\n'
         '            tool_selection = qa_history_compound.data_tool_selection(tool_selection, history_request)\n'
         '            if tool_selection.get("mode") == "required":\n'),
    ):
        if old.startswith('            if tool_selection'):
            if block.count(old) != 2: raise ValueError('Two preparation selection branches required')
            block = block.replace(old, new, 1)
        else:
            block = replace_one(block, old, new)
    text = text[:start] + block + text[end:]
    text = replace_one(text, '                "qa_task_plan": qa_task_plan.public_task_plan(task_plan),\n',
        '                "qa_task_plan": qa_task_plan.public_task_plan(task_plan),\n'
        '                "qa_source_task_plan": qa_task_plan.public_task_plan(source_task_plan),\n')
    text = replace_one(text, '                hidden_context["history_status"] = history_result.get("error") or "queried"\n            conversation_payload = load_conversation_with_origin(conn, conversation_id)\n',
        '                hidden_context["history_status"] = history_result.get("error") or "queried"\n'
        '            history_compound = qa_history_compound.execute(\n'
        '                history_request, conn, owner=owner_subject, before_message_id=user_message_id, selection=history_tool_selection)\n'
        '            conversation_payload = load_conversation_with_origin(conn, conversation_id)\n')
    text = replace_one(text, '                "history_result": history_result,\n',
        '                "history_result": history_result,\n                "history_compound": history_compound,\n')
    text = replace_one(text, '"messages": qa_document_compound.model_messages(build_hidden_qa_messages(',
        '"messages": qa_history_compound.model_messages(qa_document_compound.model_messages(build_hidden_qa_messages(')
    text = replace_one(text, 'build_hidden_qa_messages(\n                    question,',
        'build_hidden_qa_messages(\n                    execution_question,')
    text = replace_one(text, '), {"document_compound": document_compound}),',
        '), {"document_compound": document_compound}), {"history_compound": history_compound, "document_compound": document_compound}),')
    pattern = r'^( +)answer, tool_result = qa_document_compound\.compose\(answer, tool_result, prepared\)$'
    text, count = re.subn(pattern, lambda match: match.group(0) + '\n' + match.group(1) + 'answer, tool_result = qa_history_compound.compose(answer, tool_result, prepared)', text, flags=re.M)
    if count != 3: raise ValueError('JSON and both SSE composition branches required')
    ast.parse(text)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    proxy = ROOT / '.codex_runtime/qa-routing-v13/candidate/ollama_proxy_server.py'
    if hashlib.sha256(proxy.read_bytes()).hexdigest() != BASE_SHA:
        raise ValueError('Accepted production proxy changed')
    text = build(proxy.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'ollama_proxy_server.py').write_text(text, encoding='utf-8', newline='\n')
    shutil.copyfile(ROOT / '高炉前端数据/智能助手/backend/qa_history_compound.py', args.output / 'qa_history_compound.py')
    print(json.dumps({'ok':True, 'hashes':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in args.output.glob('*.py')}}))


if __name__ == '__main__': main()

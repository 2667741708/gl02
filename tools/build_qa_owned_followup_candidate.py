"""Carry owned referential objects through the full frozen request and clarification path."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path

from probe_qa_shared_proxy_delta_readonly import stable_ast_dump

if not __debug__:
    raise RuntimeError('Owned followup candidate requires assertions enabled')
ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v48/candidate-r1'
PRIOR_SHA = 'ff6667172cdaac42f9335f5b28fbf382863ea2f39d9ce07a01584dc5b5abb3b8'
FUNCTIONS = {'prepare_qa_chat', 'build_hidden_qa_messages', 'qa_mcp_planning_question',
    'run_qa_mcp_tool_loop', 'qa_mcp_tool_loop_async', 'handle_qa_chat_json', 'handle_qa_chat_stream'}


def build_proxy(text):
    before = ast.parse(text)
    replacements = [
        ('        temporal_question, qa_mcp_variables(temporal_question)\n',
         '        temporal_question, (list(task_plan.get("entities") or [])\n'
         '            if task_plan.get("reason") == "owned_referential_followup"\n'
         '            else qa_mcp_variables(temporal_question))\n', 1),
        ('            sensor_context_enabled = sensor_policy["enabled"]\n',
         '            if (sensor_policy["enabled"] and not source_task_plan.get("entities")\n'
         '                    and re.match(r"^\\s*(?:刚才|上面|那个|这个|它们?|这些|继续|再看|画出来|画一下|来张图|换成|改成|换散点)",\n'
         '                        str(source_task_plan.get("instruction_text") or ""))):\n'
         '                sensor_policy.update(enabled=False, skipped=True, reason="referential_object_resolution_before_source_read")\n'
         '            sensor_context_enabled = sensor_policy["enabled"]\n', 1),
        ('    has_reference = any(term in current for term in (\n',
         '    has_reference = bool(re.match(r"^\\s*(?:继续|再看|画出来|画一下|来张图|换散点|换成|改成)", current)) or any(term in current for term in (\n', 1),
        ('    response_mode: str = QA_RESPONSE_MODE_FLASH,\n) -> dict[str, Any]:\n    evidence_sink: list[dict[str, Any]] = []\n',
         '    response_mode: str = QA_RESPONSE_MODE_FLASH,\n    task_plan: dict[str, Any] | None = None,\n) -> dict[str, Any]:\n    evidence_sink: list[dict[str, Any]] = []\n', 1),
        ('                evidence_sink=evidence_sink,\n            )\n        )\n    except (KeyboardInterrupt, SystemExit):\n',
         '                evidence_sink=evidence_sink,\n                task_plan=task_plan,\n            )\n        )\n    except (KeyboardInterrupt, SystemExit):\n', 1),
        ('    analysis_mode: str = "",\n) -> list[dict[str, str]]:\n    source_messages = qa_prompt_sources.build_source_messages(question, history, knowledge_context, analysis_mode)\n',
         '    analysis_mode: str = "",\n    task_plan: dict[str, Any] | None = None,\n) -> list[dict[str, str]]:\n'
         '    source_messages = (None if (task_plan or {}).get("reason") == "owned_referential_followup"\n'
         '        else qa_prompt_sources.build_source_messages(question, history, knowledge_context, analysis_mode))\n', 1),
        ('            tool_context = update_tool_context(\n                previous_tool_context,\n                execution_question,\n                detected_objects=qa_mcp_analysis_variables(execution_question),\n                duration_minutes=qa_mcp_duration_minutes(execution_question),\n            )\n',
         '            # Only the active instruction and owner-loaded ancestry may resolve a referential read.\n'
         '            context_instruction = str(task_plan.get("instruction_text") or "")\n'
         '            exclusive_context = (bool(set(task_plan.get("intents") or []) & {"user_supplied_data", "document_knowledge", "conversation_history", "period_report"})\n'
         '                and "live_data" not in (task_plan.get("intents") or []))\n'
         '            context_forbidden = bool(task_plan.get("no_live_lookup") or task_plan.get("all_tools_disabled") or exclusive_context\n'
         '                or qa_evidence_policy.code_request_only(execution_question))\n'
         '            tool_context = update_tool_context(\n'
         '                None if context_forbidden else previous_tool_context,\n'
         '                context_instruction,\n'
         '                detected_objects=[] if context_forbidden else qa_mcp_analysis_variables(context_instruction),\n'
         '                duration_minutes=None if context_forbidden else qa_mcp_duration_minutes(context_instruction),\n'
         '            )\n'
         '            followup_resolution = qa_task_plan.resolve_owned_followup(\n'
         '                execution_question, task_plan, tool_context,\n'
         '                qa_mcp_variables(" ".join(tool_context.get("selected_objects") or [])),\n'
         '                code_only=qa_evidence_policy.code_request_only(execution_question))\n'
         '            task_plan = followup_resolution["task_plan"]\n', 1),
        ('                "sensor_context_policy": dict(sensor_policy),\n',
         '                "sensor_context_policy": dict(sensor_policy),\n'
         '                "followup_resolution_state": followup_resolution["state"],\n', 1),
        ('                "document_result": document_result,\n',
         '                "context_resolution_result": followup_resolution["outcome"],\n'
         '                "execution_task_plan": task_plan,\n'
         '                "document_result": document_result,\n', 1),
        ('                    assistant_rule_context=bound_assistant_context,\n',
         '                    assistant_rule_context=bound_assistant_context,\n                    task_plan=task_plan,\n', 1),
        ('                    response_mode=prepared.get("response_mode") or QA_RESPONSE_MODE_FLASH,\n                )\n                tool_result = qa_mcp_result_with_fallback(\n',
         '                    response_mode=prepared.get("response_mode") or QA_RESPONSE_MODE_FLASH,\n'
         '                    task_plan=prepared.get("execution_task_plan"),\n'
         '                )\n                tool_result = qa_mcp_result_with_fallback(\n', 2),
    ]
    changed = text
    for old,new,count in replacements:
        assert changed.count(old) == count, 'Expected exact frozen patch count: ' + old[:80]
        changed = changed.replace(old,new)
    for indent in ('            ', '        '):
        old = '\n'+indent+'if tool_result.get("answer") is None and prepared.get("document_result") is not None:\n'
        assert changed.count(old) == 1
        new = '\n'+indent+'if tool_result.get("answer") is None and prepared.get("context_resolution_result") is not None:\n'+\
            indent+'    tool_result = prepared["context_resolution_result"]'+old
        changed = changed.replace(old,new)
    after = ast.parse(changed)
    original = {n.name:n for n in ast.walk(before) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in FUNCTIONS}
    assert set(original) == FUNCTIONS
    seen = set()
    class Restore(ast.NodeTransformer):
        def visit_FunctionDef(self,node):
            if node.name in original:
                assert node.name not in seen
                seen.add(node.name)
                return copy.deepcopy(original[node.name])
            return self.generic_visit(node)
        visit_AsyncFunctionDef = visit_FunctionDef
    normalized = Restore().visit(after)
    assert seen == FUNCTIONS and stable_ast_dump(before) == stable_ast_dump(normalized)
    return changed


def validate_planner(before,after):
    a,b = ast.parse(before),ast.parse(after)
    added = [n for n in b.body if isinstance(n,ast.FunctionDef) and n.name == 'resolve_owned_followup']
    assert len(added) == 1 and not any(isinstance(n,ast.FunctionDef) and n.name == 'resolve_owned_followup' for n in a.body)
    b.body.remove(added[0])
    assert stable_ast_dump(a) == stable_ast_dump(b), 'Existing planner semantics changed'


def main(revision):
    target = ROOT/'.codex_runtime/qa-routing-v49'/('candidate-'+revision)
    assert not target.exists()
    raw = (PRIOR/'package_manifest.private.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PRIOR_SHA
    prior = json.loads(raw)
    payloads = {name:(PRIOR/name).read_bytes() for name in prior['files']}
    assert all(hashlib.sha256(raw).hexdigest() == prior['files'][name]['sha256'] for name,raw in payloads.items())
    planner = (ROOT/'高炉前端数据/智能助手/backend/qa_task_plan.py').read_bytes()
    validate_planner(payloads['qa_task_plan.py'],planner)
    payloads['qa_task_plan.py'] = planner
    payloads['ollama_proxy_server.py'] = build_proxy(payloads['ollama_proxy_server.py'].decode('utf-8')).encode('utf-8')
    for name,raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw.decode('utf-8'),filename=name)
    inherited = sorted(set(payloads)-{'qa_task_plan.py','ollama_proxy_server.py'})
    assert len(payloads) == 16 and len(inherited) == 14
    manifest = {**prior,'candidate':'v49-'+revision,'prior_manifest_sha256':PRIOR_SHA,
        'files':{name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in sorted(payloads.items())},
        'inherited_v48_files_byte_identical':inherited,'owned_followup_plan_propagated':True,
        'missing_followup_object_deterministic_clarification':True,'production_writes':0,'model_operations':0}
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert all(manifest[key] is False for key in ('model_switch_allowed','fallback_model_allowed','same_name_weight_replacement_allowed'))
    target.mkdir(parents=True)
    for name,raw in payloads.items():
        with (target/name).open('xb') as f:f.write(raw)
    raw = (json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    with (target/'package_manifest.private.json').open('xb') as f:f.write(raw)
    print(json.dumps({'ok':True,'candidate':manifest['candidate'],'files':16,'inherited':14,
        'manifest_sha256':hashlib.sha256(raw).hexdigest(),'production_sealed':False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision',choices=tuple('r'+str(i) for i in range(1,21)),default='r1')
    main(parser.parse_args().revision)

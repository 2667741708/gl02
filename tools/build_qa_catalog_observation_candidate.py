"""Freeze V52 catalog and observation routing on V51 without production/model operations."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path

try:
    from tools.probe_qa_shared_proxy_delta_readonly import stable_ast_dump
except ModuleNotFoundError:  # Script execution places tools/ itself on sys.path.
    from probe_qa_shared_proxy_delta_readonly import stable_ast_dump

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v51/candidate-r1'
PRIOR_SHA = '6dc360c9aec932498e19c638ba4756ba668a8140b0b348ca04a9f1509b275a60'
PLANNER_CHANGED_FUNCTIONS = {
    'instruction_clauses', 'user_data_scope', '_explicit_live_request', 'build_task_plan',
    'public_task_plan', 'tool_allowed', 'resolve_owned_followup',
}
PLANNER_ADDED_FUNCTIONS = {'_catalog_request', '_catalog_only_request'}
PLANNER_CHANGED_BINDINGS = {'VERSION', '_LIVE_ACTIONS', '_LIVE_READONLY_TOOL_NAMES'}
PLANNER_ADDED_BINDINGS = {'_CATALOG_TOOL_NAMES', '_CHAPTER_LIST_PATTERN'}
PROXY_CHANGED_FUNCTIONS = {
    'qa_mcp_static_pressure_catalog_plan', 'qa_mcp_variable_catalog_plan',
    'deterministic_mcp_answer', 'qa_mcp_tool_loop_async',
}


STATIC_PLAN = '''def qa_mcp_static_pressure_catalog_plan(question: str) -> dict[str, Any] | None:
    """Return the complete registered static-pressure point family."""

    text = normalize_spoken_question(qa_mcp_current_user_text(question))
    if (re.search(r"(?:静压力|静压)[^；。\\n]{0,18}(?:哪些(?:具体)?点|有哪些点|点位|测点|目录)", text)
            and not re.search(r"(?:当前|现在|目前|最新|实时)[^；。\\n]{0,12}(?:值|数值|多少)", text)):
        return {"tool": "list_gl02_static_pressure_points", "arguments": {}}
    return None
'''


VARIABLE_PLAN = '''def qa_mcp_variable_catalog_plan(question: str) -> dict[str, Any] | None:
    """Resolve point-family inventories through one bounded metadata query."""

    text = normalize_spoken_question(qa_mcp_current_user_text(question))
    catalog_intent = bool(re.search(
        r"(?:点位|测点|传感器|变量)[^；。\\n]{0,16}(?:目录|列表|有哪些|可用|可查)"
        r"|(?:有哪些|哪些|列出|列一下|可查|可用)[^；。\\n]{0,20}(?:点位|测点|传感器|变量|具体点)"
        r"|(?:对应哪个传感器|对应哪个点位|点位是什么|点位是哪个|在系统里叫什么变量|系统变量是什么)"
        r"|(?:炉顶|炉喉|顶温|炉体温度)[^；。\\n]{0,16}(?:哪些(?:具体)?点|有哪些点)", text))
    if not catalog_intent:
        return None
    family_keyword = next((keyword for aliases, keyword in (
        (("炉顶温度", "顶温", "上升管煤气温度"), "T_top"),
        (("炉喉温度", "炉喉"), "T_throat"),
        (("炉体温度", "炉身温度"), "T_body"),
    ) if any(alias in text for alias in aliases)), "")
    if family_keyword:
        return {"tool": "find_gl02_variables", "arguments": {"keyword": family_keyword, "limit": 50}}
    variables = qa_mcp_variables(question)
    inventory = bool(re.search(r"有哪些|哪些|列出|列一下|列表|目录|可用|可查", text))
    if len(variables) == 1 and not inventory:
        return {"tool": "get_gl02_variable_info", "arguments": {"variable": variables[0]}}
    return {"tool": "find_gl02_variables", "arguments": {"keyword": text.strip(), "limit": 50}}
'''


def _node_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name)
    lines = source.splitlines(keepends=True)
    return ''.join(lines[node.lineno - 1:node.end_lineno])


def _replace_function(source: str, name: str, replacement: str) -> str:
    old = _node_source(source, name)
    assert source.count(old) == 1
    return source.replace(old, replacement.rstrip() + '\n', 1)


def build_proxy(before: str) -> str:
    after = _replace_function(before, 'qa_mcp_static_pressure_catalog_plan', STATIC_PLAN)
    after = _replace_function(after, 'qa_mcp_variable_catalog_plan', VARIABLE_PLAN)
    old_find = '''    if tool_name == "find_gl02_variables":
        matches = [item for item in payload.get("matches") or [] if isinstance(item, Mapping)]
        if not matches:
            return "GL02 只读变量语义目录没有找到匹配点位。"
        lines = ["GL02 只读变量语义目录匹配结果："]
        for item in matches[:10]:
            variable_name = str(item.get("variable_name") or "未知")
            lines.append(
                f"- {label(variable_name)}：变量 `{variable_name}`；"
                f"点位 ID {item.get('point_id') or '未登记'}；"
                f"单位 {item.get('unit') or '未登记'}。"
            )
        return "\\n".join(lines)
'''
    new_find = '''    if tool_name == "find_gl02_variables":
        matches = [item for item in payload.get("matches") or [] if isinstance(item, Mapping)]
        keyword = str((arguments or {}).get("keyword") or "")
        if keyword in {"T_top", "T_throat", "T_body"}:
            matches = [item for item in matches if str(item.get("variable_name") or "") == keyword
                       or str(item.get("variable_name") or "").startswith(keyword + "_")]
        if not matches:
            return "GL02 只读变量语义目录没有找到匹配点位。"
        lines = [f"GL02 只读变量语义目录返回 {len(matches)} 个匹配点位："]
        for item in matches:
            variable_name = str(item.get("variable_name") or "未知")
            lines.append(
                f"- {label(variable_name)}：变量 `{variable_name}`；"
                f"点位 ID {item.get('point_id') or '未登记'}；"
                f"单位 {item.get('unit') or '未登记'}；"
                f"状态 {item.get('status') or '未知'}。"
            )
        if len(matches) >= int((arguments or {}).get("limit") or 50):
            lines.append("结果已达到单次目录上限；如需完整大类目录，请继续按层号或方位缩小范围。")
        lines.append("来源：GL02 只读变量语义目录；本回答未读取生产测量值。")
        return "\\n".join(lines)
'''
    assert after.count(old_find) == 1
    after = after.replace(old_find, new_find, 1)
    marker = '''                if direct_answer:
                    verified_tool_result = tool_result_is_grounding_evidence(
                        name, result_text, question=question
                    )
'''
    catalog_return = '''                if direct_answer:
                    if task_plan.get("catalog_only"):
                        return {
                            "ok": True,
                            "tool_used": True,
                            "answer": direct_answer,
                            "messages": working_messages,
                            "tool_trace": trace,
                            "answer_route": route,
                            "grounding_status": "verified_catalog_metadata",
                            "model_explanation": {"status": "not_applicable"},
                            "model_request_count": 0,
                            "model_timing": {},
                            "termination_reason": "catalog_metadata_complete",
                            "requested_tools": [name],
                            "executed_tools": [name],
                        }
                    verified_tool_result = tool_result_is_grounding_evidence(
                        name, result_text, question=question
                    )
'''
    assert after.count(marker) == 1
    return after.replace(marker, catalog_return, 1)


def validate_planner(before: bytes, after: bytes) -> None:
    old, current = ast.parse(before), ast.parse(after)
    old_functions = {node.name: node for node in old.body if isinstance(node, ast.FunctionDef)}
    old_bindings = {}
    for node in old.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            old_bindings[node.targets[0].id] = node
    restored, added_functions, added_bindings = [], set(), set()
    for node in current.body:
        if isinstance(node, ast.FunctionDef) and node.name in PLANNER_ADDED_FUNCTIONS:
            added_functions.add(node.name)
            continue
        if isinstance(node, ast.FunctionDef) and node.name in PLANNER_CHANGED_FUNCTIONS:
            restored.append(copy.deepcopy(old_functions[node.name]))
            continue
        name = (node.targets[0].id if isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) else None)
        if name in PLANNER_ADDED_BINDINGS:
            added_bindings.add(name)
            continue
        if name in PLANNER_CHANGED_BINDINGS:
            restored.append(copy.deepcopy(old_bindings[name]))
            continue
        restored.append(node)
    current.body = restored
    assert added_functions == PLANNER_ADDED_FUNCTIONS
    assert added_bindings == PLANNER_ADDED_BINDINGS
    assert stable_ast_dump(old) == stable_ast_dump(current), 'Unreviewed planner change'


def validate_proxy(before: str, after: str) -> None:
    old, current = ast.parse(before), ast.parse(after)
    old_functions = {node.name: node for node in old.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    restored = []
    seen = set()
    for node in current.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in PROXY_CHANGED_FUNCTIONS:
            restored.append(copy.deepcopy(old_functions[node.name]))
            seen.add(node.name)
        else:
            restored.append(node)
    current.body = restored
    assert seen == PROXY_CHANGED_FUNCTIONS
    assert stable_ast_dump(old) == stable_ast_dump(current), 'Unreviewed proxy change'


def main(revision: str) -> None:
    if not __debug__:
        raise RuntimeError('Candidate assertions must be enabled')
    target = ROOT / '.codex_runtime/qa-routing-v52' / ('candidate-' + revision)
    assert not target.exists(), 'Never overwrite a frozen candidate'
    raw_manifest = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert hashlib.sha256(raw_manifest).hexdigest() == PRIOR_SHA
    previous = json.loads(raw_manifest)
    payloads = {name: (PRIOR / name).read_bytes() for name in previous['files']}
    assert len(payloads) == 16
    for name, raw in payloads.items():
        assert hashlib.sha256(raw).hexdigest() == previous['files'][name]['sha256']
    planner = (ROOT / '高炉前端数据/智能助手/backend/qa_task_plan.py').read_bytes()
    validate_planner(payloads['qa_task_plan.py'], planner)
    proxy = build_proxy(payloads['ollama_proxy_server.py'].decode('utf-8')).encode('utf-8')
    validate_proxy(payloads['ollama_proxy_server.py'].decode('utf-8'), proxy.decode('utf-8'))
    payloads['qa_task_plan.py'] = planner
    payloads['ollama_proxy_server.py'] = proxy
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw, filename=name)
    inherited = sorted(set(payloads) - {'qa_task_plan.py', 'ollama_proxy_server.py'})
    manifest = {
        **previous,
        'candidate': 'v52-' + revision,
        'prior_manifest_sha256': PRIOR_SHA,
        'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                  for name, raw in sorted(payloads.items())},
        'inherited_v51_files_byte_identical': inherited,
        'catalog_observation_scope': True,
        'catalog_metadata_no_model_round': True,
        'catalog_changed_planner_functions': sorted(PLANNER_CHANGED_FUNCTIONS | PLANNER_ADDED_FUNCTIONS),
        'catalog_changed_proxy_functions': sorted(PROXY_CHANGED_FUNCTIONS),
        'production_writes': 0,
        'model_operations': 0,
    }
    assert len(inherited) == 14
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert all(manifest[key] is False for key in ('model_switch_allowed', 'fallback_model_allowed', 'same_name_weight_replacement_allowed'))
    target.mkdir(parents=True)
    for name, raw in payloads.items():
        with (target / name).open('xb') as stream:
            stream.write(raw)
    frozen = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with (target / 'package_manifest.private.json').open('xb') as stream:
        stream.write(frozen)
    print(json.dumps({'ok': True, 'candidate': manifest['candidate'], 'files': len(payloads),
                      'inherited': len(inherited), 'manifest_sha256': hashlib.sha256(frozen).hexdigest(),
                      'production_sealed': False, 'model_operations': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=tuple('r' + str(i) for i in range(1, 21)), default='r1')
    main(parser.parse_args().revision)

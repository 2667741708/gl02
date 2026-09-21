"""Build exact historical windows and registered chart objects from V24 bytes."""
import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = '2ba8dc4e6118490b6e6f2683314520bbfbc92fb47404ee9e8953769eb8dfd888'
CHANGED = {
    'qa_mcp_explicit_time_range', 'qa_mcp_prefetch', 'qa_mcp_chart_plan',
    'qa_mcp_standard_analysis_plan', 'qa_mcp_sensor_query_plan',
    'qa_mcp_body_temperature_statistics_plan', 'qa_mcp_preflight_answer',
    'deterministic_mcp_answer',
}


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unique seam required: ' + old[:100])
    return text.replace(old, new)


def build():
    raw = (ROOT / '.codex_runtime/qa-routing-v24/candidate/ollama_proxy_server.py').read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('Current production-derived baseline changed')
    text = raw.decode('utf-8')
    replacements = {}
    for node in ast.parse(text).body:
        if not isinstance(node, ast.FunctionDef) or node.name not in CHANGED:
            continue
        old = ast.get_source_segment(text, node)
        new = old
        if node.name == 'qa_mcp_explicit_time_range':
            new = '''def qa_mcp_explicit_time_range(question: str, now: datetime | None = None) -> tuple[datetime, datetime] | None:
    """REQ-QA-EXPLICIT-CLOCK-AND-CHART-20260917: never guess a last-hour window."""
    clock = qa_time_window_plan.parse_explicit_clock_range(question, anchor=now)
    return (clock['start'], clock['end']) if clock and clock['ok'] else None'''
        elif node.name == 'qa_mcp_prefetch':
            seam = '    if not QA_MCP_PREFETCH_ENABLED:\n'
            new = replace_one(new, seam,
                "    if qa_time_window_plan.explicit_clock_intent(question):\n"
                "        return {'used': False, 'reason': 'requires_explicit_clock_workflow'}\n"
                "    if qa_entity_resolution.resolve_requested_entities(question)['unresolved']:\n"
                "        return {'used': False, 'reason': 'requires_object_clarification'}\n"
                "    if qa_mcp_chart_plan(question) is not None:\n"
                "        return {'used': False, 'reason': 'requires_chart_workflow'}\n" + seam)
        elif node.name in {'qa_mcp_chart_plan', 'qa_mcp_standard_analysis_plan'}:
            seam = '    text = str(question or "")\n'
            new = replace_one(new, seam, seam +
                "    if qa_evidence_policy.no_live_lookup(text):\n        return None\n"
                "    clock = qa_time_window_plan.parse_explicit_clock_range(text)\n"
                "    if clock and not clock['ok']:\n        return None\n")
            seam = '    end_dt = datetime.now().astimezone().replace(second=0, microsecond=0)\n    start_dt = end_dt - timedelta(minutes=duration_minutes)\n'
            new = replace_one(new, seam,
                "    end_dt = clock['end'] if clock else datetime.now(LOCAL_TZ).replace(second=0, microsecond=0)\n"
                "    start_dt = clock['start'] if clock else end_dt - timedelta(minutes=duration_minutes)\n"
                "    if clock:\n        duration_minutes = int((end_dt - start_dt).total_seconds() / 60)\n")
            if node.name == 'qa_mcp_chart_plan':
                new = replace_one(new, '("小图", "small_multiples"),', '("小图", "small_multiples"),\n        ("分别画", "small_multiples"),')
                new = replace_one(new, '        "moving_average_points": moving_average_points,',
                    '        "max_points_per_variable": min(5000, max(120, duration_minutes + 5)),\n        "moving_average_points": moving_average_points,')
        elif node.name == 'qa_mcp_sensor_query_plan':
            seam = '    text = str(question or "")\n'
            new = replace_one(new, seam, seam +
                "    if qa_evidence_policy.no_live_lookup(text):\n        return None\n"
                "    clock = qa_time_window_plan.parse_explicit_clock_range(text)\n"
                "    if clock and not clock['ok']:\n        return None\n")
            new = replace_one(new, '    if answer_route == QA_ANSWER_ROUTE_ANALYSIS:\n        intent = "statistics"',
                "    if clock:\n        intent = 'statistics' if answer_route == QA_ANSWER_ROUTE_ANALYSIS or any(term in user_text for term in ('平均', '最高', '最低', '统计', '波动', '稳不稳')) else 'history'\n"
                '    elif answer_route == QA_ANSWER_ROUTE_ANALYSIS:\n        intent = "statistics"')
            new = replace_one(new, '        "query_type": "latest" if intent == "latest" else "statistics",',
                '        "query_type": "history" if clock and intent == "history" else "latest" if intent == "latest" else "statistics",')
            new = replace_one(new, '        end_dt = datetime.now().astimezone().replace(second=0, microsecond=0)\n        start_dt = end_dt - timedelta(minutes=duration_minutes)',
                "        end_dt = clock['end'] if clock else datetime.now(LOCAL_TZ).replace(second=0, microsecond=0)\n"
                "        start_dt = clock['start'] if clock else end_dt - timedelta(minutes=duration_minutes)")
            new = replace_one(new, '    return {"tool": "query_gl02_sensors", "arguments": arguments}',
                "    if arguments['query_type'] == 'history':\n"
                "        arguments.pop('agg', None)\n        arguments['max_points_per_variable'] = 5000\n"
                '    return {"tool": "query_gl02_sensors", "arguments": arguments}')
        elif node.name == 'qa_mcp_body_temperature_statistics_plan':
            new = replace_one(new, '    text = str(question or "")\n',
                '    text = str(question or "")\n'
                '    if qa_evidence_policy.no_live_lookup(text):\n        return None\n'
                "    clock = qa_time_window_plan.parse_explicit_clock_range(text)\n"
                "    if clock and not clock['ok']:\n        return None\n")
        elif node.name == 'qa_mcp_preflight_answer':
            new = replace_one(new, '    ambiguous_pressure = ',
                "    clock = qa_time_window_plan.parse_explicit_clock_range(current)\n"
                "    if clock and not clock['ok'] and not qa_evidence_policy.no_live_lookup(current):\n"
                "        return clock['blocked_reason'] + '本次未调用任何数据工具。'\n"
                "    unresolved = qa_entity_resolution.resolve_requested_entities(current)['unresolved']\n"
                "    if unresolved and not qa_evidence_policy.no_live_lookup(current):\n"
                "        return '；'.join(unresolved) + '。本次未调用任何数据工具。'\n\n"
                '    ambiguous_pressure = ')
        elif node.name == 'deterministic_mcp_answer':
            new = replace_one(new, '    if tool_name == "query_gl02_sensors":\n        lines = []',
                '    if tool_name == "query_gl02_sensors":\n'
                '        if payload.get("query_type") == "history":\n'
                '            return qa_time_window_plan.format_history_answer(payload)\n        lines = []')
        if old == new:
            raise ValueError('Requested seam unchanged: ' + node.name)
        replacements[node.name] = new
    if set(replacements) != CHANGED:
        raise ValueError('Missing candidate symbol')
    desired = text
    for node in reversed(ast.parse(text).body):
        if isinstance(node, ast.FunctionDef) and node.name in replacements:
            old = ast.get_source_segment(text, node)
            start = sum(len(line) for line in text.splitlines(True)[:node.lineno - 1])
            desired = desired[:start] + replacements[node.name] + desired[start + len(old):]
    def preserved(value):
        return [ast.dump(n, include_attributes=False) for n in ast.parse(value).body
                if not (isinstance(n, ast.FunctionDef) and n.name in CHANGED)]
    if preserved(text) != preserved(desired):
        raise ValueError('Unrequested production proxy AST change')
    target = ROOT / '.codex_runtime/qa-routing-v25/candidate'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'ollama_proxy_server.py').write_bytes(desired.encode('utf-8'))
    for name in ['qa_time_window_plan.py', 'qa_task_plan.py', 'qa_entity_resolution.py']:
        raw = (ROOT / '高炉前端数据/智能助手/backend' / name).read_bytes()
        ast.parse(raw)
        (target / name).write_bytes(raw)
    print({'ok': True, 'protected_ast_nodes': len(preserved(text)), 'changed_functions': sorted(CHANGED),
           'proxy_sha256': hashlib.sha256(desired.encode()).hexdigest()})


if __name__ == '__main__':
    build()

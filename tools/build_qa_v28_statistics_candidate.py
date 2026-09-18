"""Preserve V27 single-base constraints while repairing lossy statistics evidence."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = '79849e555560655cc12bda7c58a2617e47765106b266735d102524a2992b969e'
CHANGED = {'qa_mcp_prefetch', 'qa_mcp_prefetch_is_complete', 'deterministic_mcp_answer'}


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unique statistics seam required')
    return text.replace(old, new)


def transform(raw):
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('Frozen V27 baseline changed')
    text = raw.decode('utf-8')
    nodes = ast.parse(text).body
    edits = {}
    for node in nodes:
        if not isinstance(node, ast.FunctionDef) or node.name not in CHANGED:
            continue
        old = ast.get_source_segment(text, node)
        new = old
        if node.name == 'qa_mcp_prefetch':
            begin = new.index('            summaries[item] = {\n')
            end = new.index('\n        if len(variables) > 1:', begin)
            new = new[:begin] + '            summaries[item] = qa_statistical_evidence.prefetch_summary(item, start_text, end_text, stats)' + new[end:]
        elif node.name == 'qa_mcp_prefetch_is_complete':
            begin = new.index('        summary = pack.get("summary") or {}\n')
            end = new.index('\n    if kind == "multi_latest":', begin)
            new = new[:begin] + ('        summary = pack.get("summary")\n'
                '        return bool(qa_statistical_evidence.summary_has_data(summary)\n'
                '                    and summary.get("variable") == pack["variable"])') + new[end:]
            begin = new.index('        return bool(\n', new.index('    if kind == "multi_statistics":'))
            end = new.index('\n    return False', begin)
            new = new[:begin] + ('        return bool(variables and isinstance(summaries, dict)\n'
                '                    and all(qa_statistical_evidence.summary_has_data(summaries.get(item))\n'
                '                            and summaries[item].get("variable") == item for item in variables))') + new[end:]
        else:
            new = once(new, '''        try:
            return f"{float(value):.3f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return str(value if value is not None else "无")''', '        return qa_statistical_evidence.number(value)')
            new = once(new, '            unit = str(variable.get("unit") or PROMPT_METRIC_UNIT_FALLBACKS.get(str(requested)) or "").strip()',
                '            unit_info = qa_statistical_evidence.unit_contract(variable, str(requested), PROMPT_METRIC_UNIT_FALLBACKS)\n'
                '            unit = unit_info["unit"]')
            new = once(new, 'f"采集时间 {latest.get(\'collected_at\') or \'未知\'}；来源：{source_text}。"',
                'f"采集时间 {latest.get(\'collected_at\') or \'未知\'}；来源：{source_text}。{unit_info[\'disclosure\']}"')
            new = once(new, '+ qa_verified_facts.render_cv(statistics, unit, number)\n',
                '+ qa_verified_facts.render_cv(statistics, unit, number)\n'
                '                    + qa_statistical_evidence.quality_context(statistics)\n'
                '                    + unit_info["disclosure"]\n')
            new = once(new, '            elif isinstance(statistics, dict) and statistics:\n',
                '            elif isinstance(statistics, dict) and statistics:\n'
                '                if not qa_statistical_evidence.valid_count(statistics.get("count")):\n'
                '                    lines.append(f"{label(requested)}（{requested}）：无有效样本或样本数量未核实；未输出正式统计与稳定性结论。")\n'
                '                    continue\n'
                '                if not qa_statistical_evidence.renderer_statistics_ready(item, payload, arguments):\n'
                '                    lines.append(f"{label(requested)}（{requested}）：统计证据的对象、来源或时间窗未核实；未输出正式统计与稳定性结论。来源：{source_text}。")\n'
                '                    continue\n')
            new = once(new, 'str(source.get("profile") or source.get("engine") or "gl02-data")',
                'str(source.get("profile") or source.get("engine") or source.get("service") or "来源未核实")')
            new = once(new, 'str(source.get("read_policy") or "readonly")',
                'str(source.get("read_policy") or "只读策略字段未提供")')
        edits[node.name] = new
    if set(edits) != CHANGED:
        raise ValueError('Statistics function inventory changed')
    desired = text
    lines = text.splitlines(True)
    for node in reversed(nodes):
        if isinstance(node, ast.FunctionDef) and node.name in edits:
            start = sum(len(line) for line in lines[:node.lineno-1])
            end = sum(len(line) for line in lines[:node.end_lineno])
            desired = desired[:start] + edits[node.name] + '\n' + desired[end:]
    desired = once(desired, 'import qa_verified_facts\n', 'import qa_verified_facts\nimport qa_statistical_evidence\n')
    def preserved(source):
        return [ast.dump(node, include_attributes=False) for node in ast.parse(source).body
            if not (isinstance(node, ast.FunctionDef) and node.name in CHANGED)
            and not (isinstance(node, ast.Import) and [alias.name for alias in node.names] == ['qa_statistical_evidence'])]
    if preserved(text) != preserved(desired):
        raise ValueError('Unrelated accepted feature or fixed-base guard changed')
    return desired.encode('utf-8')


def main():
    base = (ROOT / '.codex_runtime/qa-routing-v27/candidate/ollama_proxy_server.py').read_bytes()
    result = transform(base)
    output = ROOT / '.codex_runtime/qa-routing-v28/candidate-r4'
    if output.exists():
        raise ValueError('Frozen candidate exists; no overwrite')
    output.mkdir(parents=True)
    (output / 'ollama_proxy_server.py').write_bytes(result)
    module = (ROOT / '高炉前端数据/智能助手/backend/qa_statistical_evidence.py').read_bytes()
    ast.parse(module)
    (output / 'qa_statistical_evidence.py').write_bytes(module)
    fixed = (ROOT / '.codex_runtime/qa-routing-v27/candidate/qa_fixed_model_identity.py').read_bytes()
    (output / 'qa_fixed_model_identity.py').write_bytes(fixed)
    print(json.dumps({'ok': True, 'baseline_sha256': BASE_SHA, 'changed_functions': sorted(CHANGED),
        'proxy_sha256': hashlib.sha256(result).hexdigest(), 'module_sha256': hashlib.sha256(module).hexdigest(),
        'fixed_module_sha256': hashlib.sha256(fixed).hexdigest(), 'remote_execution': False}))


if __name__ == '__main__':
    main()

"""Bind latest answers and completion to typed source/time/quality evidence on V31."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY_SHA = 'bb3aae24828a85cba91dc1a24b7455f29c37d4b885b815bca069c379837c0679'
FACTS_SHA = '15a43e3909e6528faa71456a4a6ec97b8a9ad2e758d2863ae5d7b1b8ba64cfeb'
CHANGED = {'deterministic_mcp_answer', 'qa_mcp_tool_loop_async'}
TARGET_NAME = 'candidate-r2'


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unique latest evidence seam required')
    return text.replace(old, new)


def transform(raw):
    if hashlib.sha256(raw).hexdigest() != PROXY_SHA:
        raise ValueError('Frozen V31 proxy changed')
    text = raw.decode('utf-8')
    nodes, edits = ast.parse(text).body, {}
    for node in nodes:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name not in CHANGED:
            continue
        old = ast.get_source_segment(text, node)
        if node.name == 'deterministic_mcp_answer':
            begin = '            if isinstance(latest, dict) and latest.get("value") is not None:\n'
            end = '            elif isinstance(statistics, dict) and statistics:\n'
            if old.count(begin) != 1 or old.count(end) != 1:
                raise ValueError('Latest renderer boundary changed')
            first, last = old.index(begin), old.index(end)
            new = old[:first] + begin + (
                '                if not qa_statistical_evidence.renderer_latest_ready(item, payload, arguments):\n'
                '                    lines.append(f"{label(requested)}（{requested}）：最新值的对象、来源、数值或数据时间未核实；未输出该项正式事实。")\n'
                '                    continue\n'
                '                details = qa_statistical_evidence.latest_details(item, unit)\n'
                '                lines.append(\n'
                '                    f"{label(requested)}（{requested}）：最近一次已保存值 {number(latest.get(\'value\'))}{unit_text}；"\n'
                '                    f"数据时间 {latest.get(\'ts\')}；来源：{source_text}。"\n'
                '                    + details["text"] + unit_info["disclosure"]\n'
                '                )\n') + old[last:]
        else:
            seam = '                direct_answer = deterministic_mcp_answer(name, result_text, args)\n'
            new = once(old, seam, seam +
                '                latest_completion = qa_statistical_evidence.sensor_latest_completion(try_load_json(result_text), args, PROMPT_METRIC_UNIT_FALLBACKS) if name == "query_gl02_sensors" else None\n')
            seam = 'if comparison is not None else qa_completion.public_completion({}),'
            new = once(new, seam, 'if comparison is not None else (latest_completion if latest_completion is not None and (not latest_completion["complete"] or final_answer_route == "grounded_fact_only") else qa_completion.public_completion({})),')
        edits[node.name] = new
    if set(edits) != CHANGED:
        raise ValueError('Latest evidence function inventory changed')
    result, lines = text, text.splitlines(True)
    for node in reversed(nodes):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in edits:
            start = sum(len(v) for v in lines[:node.lineno - 1])
            end = sum(len(v) for v in lines[:node.end_lineno])
            result = result[:start] + edits[node.name] + '\n' + result[end:]
    def protected(source):
        return [ast.dump(n, include_attributes=False) for n in ast.parse(source).body
            if not (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in CHANGED)]
    if protected(text) != protected(result):
        raise ValueError('Unrelated V31 routing or fixed identity changed')
    return result.encode('utf-8')


def main():
    source = ROOT / '.codex_runtime/qa-routing-v31/candidate'
    target = ROOT / '.codex_runtime/qa-routing-v32' / TARGET_NAME
    if target.exists():
        raise ValueError('Frozen candidate exists; no overwrite')
    baseline = ROOT / '.codex_runtime/qa-routing-v32/baseline/qa_verified_facts.py'
    if hashlib.sha256(baseline.read_bytes()).hexdigest() != FACTS_SHA:
        raise ValueError('Accepted production facts baseline changed')
    backend = ROOT / '高炉前端数据/智能助手/backend'
    facts = (backend / 'qa_verified_facts.py').read_bytes()
    changed = {'finite', 'latest_item', 'prefetch_outcome'}
    def facts_protected(raw):
        return [ast.dump(n, include_attributes=False) for n in ast.parse(raw).body
            if not (isinstance(n, ast.FunctionDef) and n.name in changed)]
    if facts_protected(baseline.read_bytes()) != facts_protected(facts):
        raise ValueError('Unrelated production facts AST changed')
    files = {name: (source / name).read_bytes() for name in
        ('bf_data_mcp_server.py', 'qa_window_quality.py', 'qa_completion.py', 'qa_fixed_model_identity.py')}
    files['ollama_proxy_server.py'] = transform((source / 'ollama_proxy_server.py').read_bytes())
    files['qa_statistical_evidence.py'] = (backend / 'qa_statistical_evidence.py').read_bytes()
    files['qa_verified_facts.py'] = facts
    for raw in files.values(): ast.parse(raw)
    target.mkdir(parents=True)
    for name, raw in files.items(): (target / name).write_bytes(raw)
    print(json.dumps({'ok': True, 'sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}, 'remote_execution': False}))


if __name__ == '__main__':
    main()

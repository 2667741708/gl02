"""REQ-QA-RENDERER-CONTRACT-20260917: repair response handling on the frozen V30 base."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY_SHA = '92e628b65d373504cdc3b2a73962b7cf3b53d3f6c024f34094b9d97700f497d1'
MCP_SHA = '2d85a74658db4efe5e241cf4158aa926a363957acf2689b916da0f18475d9e87'


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unique renderer contract seam required')
    return text.replace(old, new)


def transform(raw):
    if hashlib.sha256(raw).hexdigest() != PROXY_SHA:
        raise ValueError('Frozen V30 r2 proxy changed')
    text = raw.decode('utf-8')
    nodes = ast.parse(text).body
    node = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == 'deterministic_mcp_answer')
    old = ast.get_source_segment(text, node)
    new = once(old, '        lines = []\n        for item in payload.get("items") or []:\n            if not isinstance(item, dict):\n                continue',
        '        lines = []\n        items = payload.get("items")\n'
        '        if not isinstance(items, list):\n'
        '            return "工具返回的传感器结果列表结构无效；未输出正式统计与稳定性结论。"\n'
        '        for item in items:\n'
        '            if not isinstance(item, dict):\n'
        '                lines.append("工具返回项结构无效；未输出该项正式统计与稳定性结论。")\n'
        '                continue')
    seam = '            variable = item.get("variable") or {}\n            unit_info = qa_statistical_evidence.unit_contract(variable, str(requested), PROMPT_METRIC_UNIT_FALLBACKS)'
    new = once(new, seam,
        '            if not qa_statistical_evidence.renderer_item_shape_ready(item):\n'
        '                lines.append(f"{label(requested)}（{requested}）：工具返回字段结构无效；未输出该项正式统计与稳定性结论。")\n'
        '                continue\n'
        '            variable = item.get("variable") or {}\n'
        '            unit_info = qa_statistical_evidence.request_unit_contract(variable, requested, PROMPT_METRIC_UNIT_FALLBACKS)')
    lines = text.splitlines(True)
    start = sum(len(v) for v in lines[:node.lineno - 1])
    end = sum(len(v) for v in lines[:node.end_lineno])
    result = text[:start] + new + '\n' + text[end:]
    def protected(source):
        return [ast.dump(n, include_attributes=False) for n in ast.parse(source).body
            if not (isinstance(n, ast.FunctionDef) and n.name == 'deterministic_mcp_answer')]
    if protected(text) != protected(result):
        raise ValueError('Unrelated routing or fixed base guard changed')
    return result.encode('utf-8')


def main():
    source = ROOT / '.codex_runtime/qa-routing-v30/candidate-r2'
    target = ROOT / '.codex_runtime/qa-routing-v31/candidate'
    if target.exists():
        raise ValueError('Frozen candidate exists; no overwrite')
    if hashlib.sha256((source / 'bf_data_mcp_server.py').read_bytes()).hexdigest() != MCP_SHA:
        raise ValueError('Frozen V30 MCP changed')
    files = {name: (source / name).read_bytes() for name in
        ('bf_data_mcp_server.py', 'qa_window_quality.py', 'qa_completion.py', 'qa_fixed_model_identity.py')}
    files['ollama_proxy_server.py'] = transform((source / 'ollama_proxy_server.py').read_bytes())
    files['qa_statistical_evidence.py'] = (ROOT / '高炉前端数据/智能助手/backend/qa_statistical_evidence.py').read_bytes()
    for raw in files.values():
        ast.parse(raw)
    target.mkdir(parents=True)
    for name, raw in files.items():
        (target / name).write_bytes(raw)
    print(json.dumps({'ok': True, 'sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
        'remote_execution': False}))


if __name__ == '__main__':
    main()

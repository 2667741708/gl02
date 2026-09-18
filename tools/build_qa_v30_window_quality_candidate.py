"""Add measured quality distributions, preserving V29 and the single immutable base."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY_SHA = '464e866fca464beffc10aaea1c8536cf8483270970550b13f88bbfe0425f84d0'
MCP_SHA = '42d81acb60a0d3b28897c55e5c692e71f75ca5cf262dc8088fa4d1dcc6817884'


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unique window-quality seam required')
    return text.replace(old, new)


def transform_mcp(raw):
    if hashlib.sha256(raw).hexdigest() != MCP_SHA:
        raise ValueError('Accepted V26 MCP changed')
    text = raw.decode('utf-8')
    nodes = ast.parse(text).body
    changed = {'query_postgres_statistics', 'statistics_from_rows'}
    edits = {}
    for node in nodes:
        if not isinstance(node, ast.FunctionDef) or node.name not in changed:
            continue
        old = ast.get_source_segment(text, node)
        if node.name == 'query_postgres_statistics':
            new = once(old, '        stats_sql = """', '        stats_sql = f"""')
            new = once(new, 'REGR_SLOPE(value, EXTRACT(EPOCH FROM ts) / 60.0) AS slope_per_min',
                'REGR_SLOPE(value, EXTRACT(EPOCH FROM ts) / 60.0) AS slope_per_min\n'
                '                   {qa_window_quality.sql_projection("value")}')
            new = once(new, 'REGR_SLOPE(one_minute_average_value, EXTRACT(EPOCH FROM ts) / 60.0) AS slope_per_min',
                'REGR_SLOPE(one_minute_average_value, EXTRACT(EPOCH FROM ts) / 60.0) AS slope_per_min\n'
                '               {qa_window_quality.sql_projection("one_minute_average_value")}')
            seam = 'return enrich_statistics_trend(stats, first, last, recent_first, recent_last)'
            if new.count(seam) != 2:
                raise ValueError('Both database result seams required')
            new = once(new, '\n        ' + seam,
                '\n        stats["quality_summary"] = qa_window_quality.from_counts(stats, start_time, end_time)\n        ' + seam)
            new = once(new, '\n    ' + seam,
                '\n    stats["quality_summary"] = qa_window_quality.from_counts(stats, start_time, end_time)\n    ' + seam)
        else:
            new = once(old, '        "count": len(values),',
                '        "count": len(values),\n        "quality_summary": qa_window_quality.from_rows(usable),')
        edits[node.name] = new
    if set(edits) != changed:
        raise ValueError('MCP quality inventory changed')
    result = text
    lines = text.splitlines(True)
    for node in reversed(nodes):
        if isinstance(node, ast.FunctionDef) and node.name in edits:
            start = sum(len(v) for v in lines[:node.lineno-1])
            end = sum(len(v) for v in lines[:node.end_lineno])
            result = result[:start] + edits[node.name] + '\n' + result[end:]
    seam = 'from assistant_pg import ensure_assistant_schema, raw_pg_connect, schema_name  # noqa: E402\n'
    result = once(result, seam, seam + 'import qa_window_quality  # noqa: E402\n')
    def preserved(source):
        return [ast.dump(n, include_attributes=False) for n in ast.parse(source).body
            if not (isinstance(n, ast.FunctionDef) and n.name in changed)
            and not (isinstance(n, ast.Import) and [a.name for a in n.names] == ['qa_window_quality'])]
    if preserved(text) != preserved(result):
        raise ValueError('Unrelated accepted MCP changed')
    return result.encode('utf-8')


def transform_proxy(raw):
    if hashlib.sha256(raw).hexdigest() != PROXY_SHA:
        raise ValueError('Frozen V29 r2 proxy changed')
    result = once(raw.decode('utf-8'), 'qa_statistical_evidence.quality_context(statistics)',
        'qa_statistical_evidence.quality_context(statistics, item.get("start_time"), item.get("end_time"))')
    def preserved(source):
        class Mask(ast.NodeTransformer):
            def visit_FunctionDef(self, node):
                return None if node.name == 'deterministic_mcp_answer' else self.generic_visit(node)
        return ast.dump(Mask().visit(ast.parse(source)), include_attributes=False)
    if preserved(raw.decode('utf-8')) != preserved(result):
        raise ValueError('Unrelated V29 feature or fixed base guard changed')
    return result.encode('utf-8')


def main():
    proxy_dir = ROOT / '.codex_runtime/qa-routing-v29/candidate-r2'
    mcp_dir = ROOT / '.codex_runtime/qa-routing-v26/candidate'
    target = ROOT / '.codex_runtime/qa-routing-v30/candidate-r2'
    if target.exists():
        raise ValueError('Frozen candidate exists; no overwrite')
    files = {'ollama_proxy_server.py': transform_proxy((proxy_dir / 'ollama_proxy_server.py').read_bytes()),
        'bf_data_mcp_server.py': transform_mcp((mcp_dir / 'bf_data_mcp_server.py').read_bytes())}
    for name in ('qa_window_quality.py', 'qa_statistical_evidence.py'):
        files[name] = (ROOT / '高炉前端数据/智能助手/backend' / name).read_bytes()
    for name in ('qa_completion.py', 'qa_fixed_model_identity.py'):
        files[name] = (proxy_dir / name).read_bytes()
    for raw in files.values():
        ast.parse(raw)
    target.mkdir(parents=True)
    for name, raw in files.items():
        (target / name).write_bytes(raw)
    print(json.dumps({'ok': True, 'sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}, 'remote_execution': False}))


if __name__ == '__main__':
    main()

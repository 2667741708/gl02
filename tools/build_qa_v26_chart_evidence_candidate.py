"""Apply typed chart evidence repair to the accepted production V25 bytes."""
import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'ef7b970caf748d8965eabdfbd308b988ebd1d47ba4c6b4a9cc8dbfb38db7ecf9'
CHANGED = {'deterministic_mcp_answer', 'qa_mcp_tool_loop_async', 'qa_mcp_execute_parallel_batch', 'qa_mcp_execute_forced_tools'}


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unique seam required: ' + old[:100])
    return text.replace(old, new)


def build():
    raw = (ROOT / '.codex_runtime/qa-routing-v25/candidate/ollama_proxy_server.py').read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('Accepted production baseline mismatch')
    text = raw.decode('utf-8')
    # Resolve actual batch/forced function names from their reviewed seams.
    nodes = ast.parse(text).body
    replacements = {}
    allowed = set()
    for node in nodes:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        old = ast.get_source_segment(text, node)
        new = old
        if node.name == 'deterministic_mcp_answer':
            new = once(new, 'def deterministic_mcp_answer(tool_name: str, result_text: str) -> str:',
                'def deterministic_mcp_answer(tool_name: str, result_text: str, arguments: Mapping[str, Any] | None = None) -> str:')
            seam = '    if tool_name in {"plot_gl02_trends", "plot_gl02_analysis", "plot_gl02_body_temperature_matrix"}:'
            new = once(new, seam,
                '    if tool_name == "plot_gl02_trends":\n'
                '        return qa_tool_fallback.trend_chart_answer(payload, arguments, PROMPT_METRIC_ALIASES)\n\n' + seam)
        if 'result_text = mcp_result_to_text(result)\n' in new and 'async def execute_one(' in new:
            new = once(new, 'result_text = mcp_result_to_text(result)',
                'result_text = mcp_result_to_text(result, max_chars=None if name in {"plot_gl02_trends", "query_gl02_sensors"} else QA_MCP_MAX_RESULT_CHARS)')
        if node.name == 'qa_mcp_tool_loop_async':
            new = once(new, 'if name == "gl02ext__query_body_temperature_statistics"\n',
                'if name in {"gl02ext__query_body_temperature_statistics", "plot_gl02_trends", "query_gl02_sensors"}\n')
            new = once(new, 'working_messages.append({"role": "tool", "name": name, "content": result_text})',
                'working_messages.append({"role": "tool", "name": name, "content": qa_tool_fallback.model_result_text(name, result_text, args, QA_MCP_MAX_RESULT_CHARS)})')
            new = once(new, 'evidence_sink.append({"name": name, "result_text": result_text})',
                'evidence_sink.append({"name": name, "arguments": args, "result_text": result_text})')
            new = once(new, 'direct_answer = deterministic_mcp_answer(name, result_text)',
                'direct_answer = deterministic_mcp_answer(name, result_text, args)')
        # Every batch consumer gets full ledger evidence and a separate bounded transcript.
        if 'evidence_sink.append({"name": item["name"], "result_text": item["result_text"]})' in new:
            new = new.replace('evidence_sink.append({"name": item["name"], "result_text": item["result_text"]})',
                'evidence_sink.append({"name": item["name"], "arguments": item["trace"].get("arguments", {}), "result_text": item["result_text"]})')
            new = new.replace('{"role": "tool", "name": item["name"], "content": item["result_text"]}',
                '{"role": "tool", "name": item["name"], "content": qa_tool_fallback.model_result_text(item["name"], item["result_text"], item["trace"].get("arguments", {}), QA_MCP_MAX_RESULT_CHARS)}')
            new = new.replace('deterministic_mcp_answer(item["name"], item["result_text"])',
                'deterministic_mcp_answer(item["name"], item["result_text"], item["trace"].get("arguments", {}))')
        if old != new:
            allowed.add(node.name)
            replacements[node.name] = new
    if allowed != CHANGED:
        raise ValueError('Unexpected changed symbols: ' + str(allowed))
    desired = text
    for node in reversed(nodes):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in replacements:
            old = ast.get_source_segment(text, node)
            start = sum(len(line) for line in text.splitlines(True)[:node.lineno - 1])
            desired = desired[:start] + replacements[node.name] + desired[start + len(old):]
    desired = once(desired, 'import qa_evidence_policy\n', 'import qa_evidence_policy\nimport qa_tool_fallback\n')
    def protected(source):
        return [ast.dump(n, include_attributes=False) for n in ast.parse(source).body
                if not (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in allowed)
                and not (isinstance(n, ast.Import) and [a.name for a in n.names] == ['qa_tool_fallback'])]
    if protected(text) != protected(desired):
        raise ValueError('Unrequested proxy AST changes')
    out = ROOT / '.codex_runtime/qa-routing-v26/candidate'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'ollama_proxy_server.py').write_bytes(desired.encode('utf-8'))
    for name, prefix in [('qa_tool_fallback.py', 'backend'), ('bf_data_mcp_server.py', 'mcp')]:
        data = (ROOT / '高炉前端数据/智能助手' / prefix / name).read_bytes()
        ast.parse(data)
        if name == 'bf_data_mcp_server.py':
            base = (out.parent / 'production-bf_data_mcp_server.py').read_bytes()
            if hashlib.sha256(base).hexdigest() != '9dd1999e40e0a4648c25e4ae626b5e290269e68cab0e707bc4561fac4f9a3e95':
                raise ValueError('Current production MCP baseline mismatch')
            target_names = {'parse_variables_arg', 'plot_gl02_trends'}
            source = data.decode('utf-8')
            replace = {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body
                       if isinstance(n, ast.FunctionDef) and n.name in target_names}
            base_text = base.decode('utf-8')
            merged = base_text
            for n in reversed(ast.parse(base_text).body):
                if isinstance(n, ast.FunctionDef) and n.name in target_names:
                    old = ast.get_source_segment(base_text, n)
                    index = sum(len(line) for line in base_text.splitlines(True)[:n.lineno-1])
                    merged = merged[:index]+replace[n.name]+merged[index+len(old):]
            def preserved_mcp(value):
                return [ast.dump(n, include_attributes=False) for n in ast.parse(value).body
                        if not (isinstance(n, ast.FunctionDef) and n.name in target_names)]
            if preserved_mcp(base_text) != preserved_mcp(merged):
                raise ValueError('Unrequested production MCP AST change')
            data = merged.encode('utf-8')
        (out / name).write_bytes(data)
    print({'ok': True, 'changed_functions': sorted(allowed), 'protected_ast_nodes': len(protected(text)),
           'proxy_sha256': hashlib.sha256(desired.encode('utf-8')).hexdigest()})


if __name__ == '__main__':
    build()

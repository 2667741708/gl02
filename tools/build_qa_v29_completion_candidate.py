"""REQ-QA-FINAL-COMPLETION-20260917: retain V28 and the immutable base guard."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'bc815f53bb5242b762eaf6d5071bf8cf6481a1ecdf356884026e8b2a5108cfd3'
CHANGED = {'qa_body_temperature_model_explanation', 'qa_grounded_mcp_analysis',
    'handle_qa_chat_json', 'handle_qa_chat_stream'}


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Unique completion seam required')
    return text.replace(before, after)


def transform(raw):
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('Frozen V28 r4 baseline changed')
    text = raw.decode('utf-8')
    tree = ast.parse(text)
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in CHANGED]
    if len(nodes) != len(CHANGED):
        raise ValueError('Completion seam inventory changed')
    edits = {}
    for node in nodes:
        old = ast.get_source_segment(text, node)
        if node.name == 'qa_grounded_mcp_analysis':
            new = once(old, '    if llm_output_is_empty(answer):',
                '    if qa_completion.incomplete_response(response, answer):\n'
                '        fallback = f"{factual_answer}\\n\\n模型综合未完整结束，以上仅保留已核验的只读查询事实；本轮分析部分未完成。"\n'
                '        return fallback, "incomplete_factual_fallback", timing\n'
                '    if llm_output_is_empty(answer):')
        elif node.name == 'qa_body_temperature_model_explanation':
            new = once(old, '    if not explanation:',
                '    if qa_completion.incomplete_response(response, explanation):\n'
                '        return "", "incomplete"\n'
                '    if not explanation:')
        else:
            expected = 1 if node.name == 'handle_qa_chat_json' else 2
            seam = 'qa_completion.public_completion(tool_result)'
            if old.count(seam) != expected:
                raise ValueError('Public completion exits changed')
            new = old.replace(seam, 'qa_completion.public_completion(tool_result, answer=answer)')
            if node.name == 'handle_qa_chat_stream':
                new = once(new, 'stream_completed = obj.get("done_reason") != "length"',
                    'stream_completed = qa_completion.stream_finished(obj)')
                seam = '            answer = qa_evidence_policy.apply_request_boundary(question, clean_llm_output("".join(answer_parts)))'
                new = once(new, seam, seam + '\n'
                    '            stream_answer_issues = ["unfinished_heading"] if qa_completion.unfinished_heading(answer) else []')
                new = once(new, '                "stream_completed": stream_completed,',
                    '                "stream_completed": stream_completed,\n'
                    '                "incomplete_reasons": stream_answer_issues,')
        edits[node.name] = new
    result = text
    lines = text.splitlines(True)
    for node in sorted(nodes, key=lambda n: n.lineno, reverse=True):
        start = sum(len(v) for v in lines[:node.lineno-1])
        end = sum(len(v) for v in lines[:node.end_lineno])
        # ast source begins at def, while its remaining method lines retain indentation.
        replacement = ' ' * node.col_offset + edits[node.name] + '\n'
        result = result[:start] + replacement + result[end:]
    def preserved(source):
        parsed = ast.parse(source)
        class Mask(ast.NodeTransformer):
            def visit_FunctionDef(self, node):
                return None if node.name in CHANGED else self.generic_visit(node)
        return ast.dump(Mask().visit(parsed), include_attributes=False)
    if preserved(text) != preserved(result):
        raise ValueError('Unrelated feature or fixed identity guard changed')
    return result.encode('utf-8')


def main():
    source = ROOT / '.codex_runtime/qa-routing-v28/candidate-r4'
    target = ROOT / '.codex_runtime/qa-routing-v29/candidate-r2'
    if target.exists():
        raise ValueError('Frozen candidate exists; no overwrite')
    result = transform((source / 'ollama_proxy_server.py').read_bytes())
    module = (ROOT / '高炉前端数据/智能助手/backend/qa_completion.py').read_bytes()
    ast.parse(module)
    target.mkdir(parents=True)
    (target / 'ollama_proxy_server.py').write_bytes(result)
    (target / 'qa_completion.py').write_bytes(module)
    for name in ('qa_statistical_evidence.py', 'qa_fixed_model_identity.py'):
        (target / name).write_bytes((source / name).read_bytes())
    print(json.dumps({'ok': True, 'baseline_sha256': BASE_SHA,
        'proxy_sha256': hashlib.sha256(result).hexdigest(),
        'completion_sha256': hashlib.sha256(module).hexdigest(),
        'changed_functions': sorted(CHANGED), 'remote_execution': False}))


if __name__ == '__main__':
    main()

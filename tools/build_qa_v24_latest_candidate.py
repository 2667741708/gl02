"""Build V24 latest-fact reuse from verified V23 production bytes."""
import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'c90f82cf2466bf4004efed330d21a252fdd8c847605f966909102a9c7653aefc'


def main():
    baseline = ROOT / '.codex_runtime/qa-routing-v22/candidate/ollama_proxy_server.py'
    raw = baseline.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('Production-derived baseline changed')
    text = raw.decode('utf-8')
    tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'qa_mcp_should_use_tools')
    old = ast.get_source_segment(text, node)
    seam = '    forced = payload.get("use_mcp_tools")\n'
    if old.count(seam) != 1:
        raise ValueError('Unique tool-enable seam required')
    insertion = ('    # REQ-QA-LATEST-PREFETCH-REUSE-20260917: the UI enables tools; it\n'
                 '    # does not require redundant planning after a valid simple read.\n'
                 '    if qa_verified_facts.reusable_latest_read(\n'
                 '        question, mcp_prefetch, qa_task_plan.build_task_plan(question)\n'
                 '    ):\n'
                 '        return False\n')
    new = old.replace(seam, insertion + seam)
    start = sum(len(line) for line in text.splitlines(True)[:node.lineno-1])
    end = start + len(old)
    desired = text[:start] + new + text[end:]
    def preserved(value):
        return [ast.dump(n, include_attributes=False) for n in ast.parse(value).body
                if not (isinstance(n, ast.FunctionDef) and n.name == node.name)]
    if preserved(text) != preserved(desired):
        raise ValueError('Unrequested proxy AST change')
    candidate = ROOT / '.codex_runtime/qa-routing-v24/candidate'
    candidate.mkdir(parents=True, exist_ok=True)
    (candidate / 'ollama_proxy_server.py').write_bytes(desired.encode('utf-8'))
    for name in ['qa_verified_facts.py', 'qa_evidence_policy.py']:
        raw = (ROOT / '高炉前端数据/智能助手/backend' / name).read_bytes()
        ast.parse(raw)
        (candidate / name).write_bytes(raw)
    print({'ok': True, 'proxy_other_ast_nodes_unchanged': len(preserved(text)), 'proxy_sha256': hashlib.sha256(desired.encode()).hexdigest()})


if __name__ == '__main__':
    main()

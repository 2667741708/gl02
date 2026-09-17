"""REQ-QA-SINGLE-BASE-MODEL-20260917: preserve accepted V26, pin every model POST."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = '47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431'
CHANGED = {'resolve_upstream_model', 'build_ollama_request', 'handle_ollama_status'}
RESOLVE = '''def resolve_upstream_model() -> str:
    """Only the immutable base; GET checks never load or switch a model."""
    def fetch(path, timeout):
        req = Request(f"{OLLAMA_BASE_URL}{path}", headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    return qa_fixed_model_identity.resolve(
        lambda timeout: fetch("/api/tags", timeout),
        lambda timeout: fetch("/api/ps", timeout),
        checkpoint=qa_request_control.checkpoint,
    )'''
REQUEST = '''def build_ollama_request(path: str, body: bytes | None = None, stream: bool = False) -> Request:
    headers = {
        "Accept": "text/event-stream" if stream else "application/json",
        "Content-Type": "application/json",
    }
    if body is not None:
        if path != "/api/chat":
            raise qa_fixed_model_identity.FixedModelUnavailable("固定底座策略禁止其他模型写入接口。")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Model request must be an object")
        # Recheck immediately before every turn, including tools=None fallback.
        payload["model"] = resolve_upstream_model()
        body = json_bytes(payload)
    return Request(f"{OLLAMA_BASE_URL}{path}", data=body, headers=headers, method="POST" if body is not None else "GET")'''
STATUS = '''def handle_ollama_status(self) -> None:
    result: dict[str, Any] = {
        "ok": False, "proxy_ok": True, "ollama_ok": False, "model_ok": False,
        "target_model": PUBLIC_MODEL_NAME, "error": "",
        "readiness_contract": "fixed_model_digest",
        "identity_locked": True, "model_switch_allowed": False,
        "required_model_identity_sha256": qa_fixed_model_identity.MODEL_DIGEST,
    }
    try:
        req = Request(f"{OLLAMA_BASE_URL}/api/version", headers={"Accept": "application/json"})
        with urlopen(req, timeout=6) as resp:
            json.loads(resp.read().decode("utf-8", errors="replace"))
        result["ollama_ok"] = True
        resolve_upstream_model()
        result["model_identity_sha256"] = qa_fixed_model_identity.MODEL_DIGEST
        result["model_ok"] = True
        result["ok"] = True
    except URLError as exc:
        result["error"] = f"高炉大模型服务不可达：{sanitize_model_exposure(exc.reason)}"
    except qa_fixed_model_identity.FixedModelUnavailable as exc:
        result["error"] = str(exc)
        result.update(qa_model_readiness.public_error_fields(exc))
    except Exception:
        result["error"] = "固定问答底座身份尚未核实。"
    self.send_json(result, status=200)'''


def transform(raw):
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('Accepted V26 baseline changed')
    text = raw.decode('utf-8')
    tree = ast.parse(text)
    nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in CHANGED]
    if len(nodes) != 3 or {n.name for n in nodes} != CHANGED:
        raise ValueError('Unique seams required')
    result = text
    values = {'resolve_upstream_model': RESOLVE, 'build_ollama_request': REQUEST, 'handle_ollama_status': STATUS}
    lines = text.splitlines(True)
    for node in sorted(nodes, key=lambda n: n.lineno, reverse=True):
        # Include full indentation of methods; leave the following blank lines intact.
        start = sum(len(v) for v in lines[:node.lineno - 1])
        end = sum(len(v) for v in lines[:node.end_lineno])
        replacement = '\n'.join(' ' * node.col_offset + v if v else '' for v in values[node.name].splitlines()) + '\n'
        result = result[:start] + replacement + result[end:]
    seam = 'import qa_model_readiness\n'
    if result.count(seam) != 1:
        raise ValueError('Readiness import seam changed')
    result = result.replace(seam, seam + 'import qa_fixed_model_identity\n')
    def preserved(value):
        parsed = ast.parse(value)
        class Mask(ast.NodeTransformer):
            def visit_FunctionDef(self, node):
                if node.name in CHANGED:
                    return None
                return self.generic_visit(node)
            def visit_Import(self, node):
                return None if [a.name for a in node.names] == ['qa_fixed_model_identity'] else node
        return ast.dump(Mask().visit(parsed), include_attributes=False)
    if preserved(text) != preserved(result):
        raise ValueError('Unrelated accepted feature changed')
    return result.encode('utf-8')


def main():
    raw = (ROOT / '.codex_runtime/qa-routing-v26/candidate/ollama_proxy_server.py').read_bytes()
    target = ROOT / '.codex_runtime/qa-routing-v27/candidate'
    if target.exists():
        raise ValueError('Frozen candidate exists; no overwrite')
    result = transform(raw)
    module = (ROOT / '高炉前端数据/智能助手/backend/qa_fixed_model_identity.py').read_bytes()
    ast.parse(module)
    target.mkdir(parents=True)
    (target / 'ollama_proxy_server.py').write_bytes(result)
    (target / 'qa_fixed_model_identity.py').write_bytes(module)
    print(json.dumps({'ok': True, 'baseline_sha256': BASE_SHA, 'changed_functions': sorted(CHANGED),
        'proxy_sha256': hashlib.sha256(result).hexdigest(), 'module_sha256': hashlib.sha256(module).hexdigest(),
        'remote_execution': False}))


if __name__ == '__main__':
    main()

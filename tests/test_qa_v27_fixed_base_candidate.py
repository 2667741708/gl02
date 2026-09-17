"""Exercise the actual three proxy replacements without importing production I/O."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.request import Request

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_fixed_model_identity as fixed
import qa_model_readiness

spec = importlib.util.spec_from_file_location('v27_builder', ROOT / 'tools/build_qa_v27_fixed_base_candidate.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def namespace():
    raw = (ROOT / '.codex_runtime/qa-routing-v26/candidate/ollama_proxy_server.py').read_bytes()
    candidate = builder.transform(raw).decode()
    nodes = [n for n in ast.walk(ast.parse(candidate)) if isinstance(n, ast.FunctionDef) and n.name in builder.CHANGED]
    scope = {'qa_fixed_model_identity': fixed, 'qa_model_readiness': qa_model_readiness,
             'qa_request_control': SimpleNamespace(checkpoint=lambda: None),
             'json': json, 'json_bytes': lambda v: json.dumps(v).encode(), 'Request': Request,
             'OLLAMA_BASE_URL': 'http://127.0.0.1:11434', 'PUBLIC_MODEL_NAME': '业务模型',
             'sanitize_model_exposure': str, 'URLError': __import__('urllib.error', fromlist=['URLError']).URLError,
             'Any': object}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual-v27-functions>', 'exec'), scope)
    return scope


def test_every_model_turn_and_fallback_revalidates_and_replaces_caller_model():
    scope = namespace()
    calls = []
    def resolve():
        calls.append('identity')
        return fixed.MODEL_NAME
    scope['resolve_upstream_model'] = resolve
    for tools in [None, [{'name': 'read_only_query'}], None]:
        req = scope['build_ollama_request']('/api/chat', json.dumps({'model': 'other:version', 'tools': tools}).encode())
        assert req.method == 'POST'
        assert json.loads(req.data)['model'] == fixed.MODEL_NAME
        assert json.loads(req.data)['tools'] == tools
    assert len(calls) == 3


def test_mismatch_blocks_request_construction_before_post():
    scope = namespace()
    def reject():
        raise fixed.FixedModelUnavailable('mismatch')
    scope['resolve_upstream_model'] = reject
    with pytest.raises(fixed.FixedModelUnavailable):
        scope['build_ollama_request']('/api/chat', b'{"model":"other"}')


@pytest.mark.parametrize('path', ['/api/generate', '/api/embed', '/api/create', '/api/delete'])
def test_other_model_mutation_paths_forbidden(path):
    scope = namespace()
    scope['resolve_upstream_model'] = lambda: pytest.fail('No model operation')
    with pytest.raises(fixed.FixedModelUnavailable):
        scope['build_ollama_request'](path, b'{}')


@pytest.mark.parametrize('ready', [True, False])
def test_status_does_not_claim_verified_actual_digest_on_mismatch(ready):
    scope = namespace()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{}'
    scope['urlopen'] = lambda *a, **kw: Response()
    def resolve():
        if not ready: raise fixed.FixedModelUnavailable('mismatch')
        return fixed.MODEL_NAME
    scope['resolve_upstream_model'] = resolve
    output = []
    scope['handle_ollama_status'](SimpleNamespace(send_json=lambda value, status: output.append(value)))
    result = output[0]
    assert result['ok'] == ready
    assert result['identity_locked'] and not result['model_switch_allowed']
    assert result['required_model_identity_sha256'] == fixed.MODEL_DIGEST
    assert ('model_identity_sha256' in result) == ready

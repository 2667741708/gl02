"""Build a hash-bound, credential-free, RAM-only QA import/request probe script."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from qa_frozen_candidate import latest_frozen_candidate


def build(dependency_root, output_script):
    candidate, manifest = latest_frozen_candidate(ROOT)
    probe = (ROOT / 'tools/qa_full_candidate_probe.py').read_bytes()
    payload = {'dependency_root': str(dependency_root), 'request_contracts': True,
        'candidate': manifest['candidate'],
        'manifest_sha256': hashlib.sha256((candidate / 'package_manifest.private.json').read_bytes()).hexdigest(),
        'probe_sha256': hashlib.sha256(probe).hexdigest(),
        'model_name': manifest['model_name'], 'model_digest': manifest['model_digest'],
        'sources': {name: base64.b64encode((candidate / name).read_bytes()).decode('ascii') for name in manifest['files']},
        'sha256': {name: item['sha256'] for name, item in manifest['files'].items()}}
    packed = base64.b64encode(zlib.compress(json.dumps(payload, ensure_ascii=False).encode('utf-8'))).decode('ascii')
    script = ('import base64,json,zlib\nnamespace={"__name__":"qa_readonly_probe"}\n'
        + 'exec(compile(base64.b64decode(' + repr(base64.b64encode(probe).decode('ascii')) + '),"<qa_full_candidate_probe>","exec"),namespace)\n'
        + 'payload=json.loads(zlib.decompress(base64.b64decode(' + repr(packed) + ')))\n'
        + 'result=namespace["run"](payload)\nprint(json.dumps(result,ensure_ascii=False))\n'
        + 'raise SystemExit(0 if result["ok"] else 1)\n')
    ast.parse(script)
    target = Path(output_script).resolve()
    if not target.is_relative_to(ROOT / '.codex_runtime'):
        raise ValueError('Probe script must stay in ignored private runtime directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = script.encode('utf-8')
    # An existing receipt/script is never silently overwritten.
    with target.open('xb') as stream:
        stream.write(raw)
    return {'candidate': manifest['candidate'], 'manifest_sha256': payload['manifest_sha256'],
        'probe_sha256': payload['probe_sha256'], 'script_sha256': hashlib.sha256(raw).hexdigest(),
        'characters': len(script), 'production_writes': 0, 'model_operations': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dependency-root', required=True)
    parser.add_argument('--output-script', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.dependency_root, args.output_script)))

"""Capture scoped hashes and prove the immutable base using metadata GETs only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

MODEL_NAME = 'chiqiongblastfuenace:latest'
MODEL_DIGEST = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'


def scoped_paths(root, scope):
    paths = [row['path'] for row in scope['read_files']] + scope['write_set']
    result = {}
    for relative in dict.fromkeys(paths):
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or not (root / path).resolve().is_relative_to(root.resolve()):
            raise ValueError('Scope must stay inside the reviewed repository')
        result[relative] = (root / path).resolve()
    return result


def pin_status(tags_before, resident, tags_after):
    def alias(rows):
        if not isinstance(rows, list): return False
        selected = [row for row in rows if isinstance(row, dict) and (row.get('name') or row.get('model')) == MODEL_NAME]
        return len(selected) == 1 and selected[0].get('digest') == MODEL_DIGEST
    resident_ready = (isinstance(resident, list) and len(resident) == 1
                      and isinstance(resident[0], dict)
                      and (resident[0].get('name') or resident[0].get('model')) == MODEL_NAME
                      and resident[0].get('digest') == MODEL_DIGEST)
    return {'alias_before_fixed': alias(tags_before), 'resident_fixed': resident_ready,
            'alias_after_fixed': alias(tags_after)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--scope-file', type=Path, help='Reviewed exact-path scope gate')
    group.add_argument('--scope-json', help='Same reviewed gate, transported as structured argv without a remote file')
    args = parser.parse_args()
    # Loopback metadata must not pass through system/user network proxies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    metadata_errors = []
    def request(path, port):
        try:
            with opener.open(f'http://127.0.0.1:{port}{path}', timeout=3) as response:
                payload = json.load(response)
            if not isinstance(payload, dict): raise ValueError('Metadata is not an object')
            return payload
        except (OSError, ValueError, TimeoutError) as error:
            metadata_errors.append({'port': port, 'endpoint': path, 'error_type': type(error).__name__})
            return {}
    scope = json.loads(args.scope_json) if args.scope_json is not None else json.loads(args.scope_file.read_text(encoding='utf-8'))
    paths = scoped_paths(args.root, scope)
    hashes = {relative: hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
              for relative, path in paths.items()}
    missing_reads = [row['path'] for row in scope['read_files'] if hashes[row['path']] is None]
    head = subprocess.check_output(['C:/Program Files/Git/cmd/git.exe', '-C', str(args.root),
                                    'rev-parse', 'HEAD'], text=True).strip()
    status = request('/api/ollama/status', 8093)
    tags = request('/api/tags', 11434).get('models', [])
    resident = request('/api/ps', 11434).get('models', [])
    tags_after = request('/api/tags', 11434).get('models', [])
    identity = pin_status(tags, resident, tags_after)
    ready = all(identity.values())
    result = {'ok': bool(status.get('ok') and ready and not missing_reads and not metadata_errors), 'head': head, 'runtime_hashes': hashes,
              'missing_read_files': missing_reads,
              'catalog_sha256': hashlib.sha256((args.root / '数据库同步和存取/config/点位语义目录.json').read_bytes()).hexdigest(),
              'expected_model_identity': {'name': MODEL_NAME, 'digest': MODEL_DIGEST},
              'model_identity': {'name': MODEL_NAME, 'digest': MODEL_DIGEST,
                                 'family': resident[0].get('details', {}).get('family')} if ready else None,
              'fixed_identity_checks': identity, 'fixed_identity_ready': ready,
              'status': status, 'single_resident_matches_alias': ready,
              'metadata_errors': metadata_errors, 'loopback_proxy_disabled': True,
              'question_posts': 0, 'model_calls': 0, 'database_writes': 0, 'production_writes': 0}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())

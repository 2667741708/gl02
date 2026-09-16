"""Capture version hashes and a matching single resident model without generation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--scope-file', type=Path, required=True, help='Reviewed exact-path scope gate')
    args = parser.parse_args()
    def request(path, port):
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=8) as response:
            return json.load(response)
    scope = json.loads(args.scope_file.read_text(encoding='utf-8'))
    paths = [row['path'] for row in scope['read_files']] + scope['write_set']
    hashes = {path: hashlib.sha256((args.root / path).read_bytes()).hexdigest() for path in paths}
    head = subprocess.check_output(['C:/Program Files/Git/cmd/git.exe', '-C', str(args.root),
                                    'rev-parse', 'HEAD'], text=True).strip()
    status = request('/api/ollama/status', 8093)
    tags = request('/api/tags', 11434).get('models', [])
    resident = request('/api/ps', 11434).get('models', [])
    selected = [row for row in tags if row.get('name') == 'chiqiongblastfuenace:latest']
    matching = len(selected) == len(resident) == 1 and selected[0]['digest'] == resident[0]['digest']
    result = {'ok': bool(status.get('ok') and matching), 'head': head, 'runtime_hashes': hashes,
              'catalog_sha256': hashlib.sha256((args.root / '数据库同步和存取/config/点位语义目录.json').read_bytes()).hexdigest(),
              'model_identity': {'name': selected[0]['name'], 'digest': selected[0]['digest'],
                                 'family': resident[0].get('details', {}).get('family')} if matching else None,
              'status': status, 'single_resident_matches_alias': matching}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())

"""Audit exact staged QA JSON evidence for private payloads before publication."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_KEYS = {'answer', 'messages', 'hidden_context', 'hidden_context_json', 'full_text',
                'result_text', 'tool_results', 'tool_starts', 'owner_subject',
                'authorization', 'cookie', 'password', 'access_token', 'connection_string', 'dsn'}

def private_keys(value):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in PRIVATE_KEYS: found.add(key)
            found.update(private_keys(item))
    elif isinstance(value, list):
        for item in value: found.update(private_keys(item))
    return found

def main():
    paths = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    issues, checked = [], 0
    for path in filter(None, paths):
        raw = subprocess.check_output(['git', 'show', ':' + path], cwd=ROOT)
        text = raw.decode('utf-8')
        if re.search(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bsk-[A-Za-z0-9]{32,}\b', text):
            issues.append({'path': path, 'reason': 'credential_pattern'})
        if path.startswith('tests/qa_regression/') and path.endswith('.json'):
            checked += 1
            found = private_keys(json.loads(text))
            if found: issues.append({'path': path, 'reason': 'private_json_fields', 'fields': sorted(found)})
    print(json.dumps({'ok': not issues, 'staged_paths': len(list(filter(None, paths))),
                      'qa_json_checked': checked, 'issues': issues}, ensure_ascii=False))
    return int(bool(issues))

if __name__ == '__main__': raise SystemExit(main())

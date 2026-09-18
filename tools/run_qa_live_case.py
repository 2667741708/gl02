"""Execute one authorized live QA case, with a fresh private session and no replay.

Run on the verified server using stdin. Credentials and cookies stay in memory;
only allowlisted response evidence is returned. No runtime files are modified.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


def source_accounts(root, process_env):
    backend = root / '高炉前端数据/智能助手/backend'
    source = (backend / 'ollama_proxy_server.py').read_text(encoding='utf-8-sig')
    names = {'parse_dotenv_file', 'auth_env_values', 'safe_env_account_key',
             'first_env_value', 'configured_login_accounts'}
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    if {n.name for n in nodes} != names:
        raise RuntimeError('auth source contract changed')
    namespace = dict(Path=Path, os=os, re=re, Any=Any, PROJECT_ROOT=root,
                     BASE_DIR=root / '高炉前端数据', ASSISTANT_DIR=backend.parent,
                     ASSISTANT_BACKEND_DIR=backend)
    original = dict(os.environ)
    try:
        os.environ.update(process_env)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<auth-readonly>', 'exec'), namespace)
        return namespace['configured_login_accounts']()
    finally:
        os.environ.clear()
        os.environ.update(original)


def json_request(path, payload=None, cookie=''):
    connection = http.client.HTTPConnection('127.0.0.1', 8093, timeout=25)
    headers = {'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:8093',
               'X-BF-Controlled-Client': '1', 'X-BF-Acceptance-ID': 'Q-QA-LIVE-BASELINE-20260915'}
    if cookie:
        headers['Cookie'] = cookie
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    try:
        connection.request('GET' if payload is None else 'POST', path, body, headers)
        response = connection.getresponse()
        data = json.loads(response.read())
        cookies = '; '.join(v.split(';', 1)[0] for k, v in response.getheaders() if k.lower() == 'set-cookie')
        if response.status != 200 or data.get('ok') is False:
            raise RuntimeError(f'API HTTP {response.status} at {path}')
        return data, cookies
    finally:
        connection.close()


def run(args):
    import psutil
    root = args.root.resolve()
    case = json.loads(args.case_json)
    question = case['prompt']
    catalog_path = root / '数据库同步和存取/config/点位语义目录.json'
    catalog_bytes = catalog_path.read_bytes()
    catalog = json.loads(catalog_bytes.decode('utf-8-sig'))
    objects = catalog['objects']
    forbidden = [str(o['object_id']) for o in objects if re.search(r'[A-Za-z_]', str(o['object_id']))]
    if case.get('prompt_mode', 'spoken') == 'spoken' and any(re.search(r'(?<![A-Za-z0-9_])' + re.escape(v) + r'(?![A-Za-z0-9_])', question) for v in forbidden):
        raise RuntimeError('oracle_invalid: internal catalog ID in prompt')
    listeners = {c.pid for c in psutil.net_connections(kind='tcp')
                 if c.status == 'LISTEN' and c.laddr.port == 8093}
    if len(listeners) != 1:
        raise RuntimeError('ambiguous 8093 listener')
    pid = listeners.pop()
    process = psutil.Process(pid)
    command = process.cmdline()
    if not any(str(root).casefold() in v.casefold() for v in command):
        raise RuntimeError('unexpected runtime root')
    env = process.environ()
    accounts = source_accounts(root, env)
    if not accounts:
        raise RuntimeError('configured login unavailable')
    # Prefer the existing lower-privilege account; never create an account.
    username = min(accounts, key=lambda n: 0 if 'operator' in accounts[n]['role'].lower() else 1)
    login, cookie = json_request('/api/auth/login', {'username': username, 'password': accounts[username]['password']})
    accounts.clear()
    if not cookie:
        raise RuntimeError('login did not issue session')
    conversation_id = args.conversation_id
    if args.inspect_only:
        if not conversation_id:
            raise RuntimeError('inspection requires an existing conversation')
        data, _ = json_request('/api/qa/conversation?id=' + conversation_id, cookie=cookie)
        messages = [{k: m.get(k) for k in ('id', 'role', 'content', 'created_at', 'hidden_context')}
                    for m in data['messages']]
        print(json.dumps({'case_id': case['case_id'], 'request_count': 0,
                          'recovered_from_persistence': True, 'messages': messages}, ensure_ascii=False, default=str))
        return
    if not conversation_id:
        created, _ = json_request('/api/qa/conversations', {'title': '回归基线 ' + case['case_id']}, cookie)
        conversation_id = created['conversation']['id']
    backend = root / '高炉前端数据/智能助手/backend'
    files = ['ollama_proxy_server.py', 'qa_evidence_policy.py', 'mcp_tool_selection.py', 'mcp_tool_policy.py',
             'qa_request_control.py', 'mcp_host/server_registry.json']
    hashes = {name: hashlib.sha256((backend / name).read_bytes()).hexdigest() for name in files}
    result = {'schema': 'bf.qa.live.case.v1', 'case_id': case['case_id'], 'question': question,
              'phase': args.phase, 'execution_kind': 'live_production', 'conversation_id': conversation_id,
              'program_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
              'runtime_hashes': hashes, 'catalog_sha256': hashlib.sha256(catalog_bytes).hexdigest(),
              'catalog_object_count': len(objects), 'pid': pid, 'role': login['role'],
              'model': env.get('BF_LLM_MODEL'), 'request_count': 0, 'automatic_retries': 0,
              'events': [], 'tool_starts': [], 'tool_results': [], 'traces': [], 'final': {}, 'answer': ''}
    connection = http.client.HTTPConnection('127.0.0.1', 8093, timeout=args.timeout)
    started = time.monotonic()
    chunks = []
    full_stream_content = None
    final_answer = None
    try:
        payload = {'conversation_id': conversation_id, 'message': question, 'stream': True,
                   'use_mcp_tools': True, 'response_projection': 'turn'}
        headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream',
                   'Origin': 'http://127.0.0.1:8093', 'Cookie': cookie,
                   'X-BF-Controlled-Client': '1', 'X-BF-Acceptance-ID': case['case_id']}
        result['request_count'] = 1
        connection.request('POST', '/api/qa/chat', json.dumps(payload, ensure_ascii=False).encode('utf-8'), headers)
        response = connection.getresponse()
        result['http_status'] = response.status
        if response.status != 200 or 'text/event-stream' not in (response.getheader('Content-Type') or ''):
            raise RuntimeError(f'chat HTTP {response.status}')
        event = 'message'
        while time.monotonic() - started < args.timeout:
            raw = response.readline()
            if not raw:
                result['eof'] = True
                break
            line = raw.decode('utf-8').rstrip('\r\n')
            if line.startswith('event:'):
                event = line[6:].strip()
                result['events'].append({'event': event, 'seconds': round(time.monotonic() - started, 3)})
            elif line.startswith('data:'):
                data = json.loads(line[5:])
                if event == 'delta':
                    chunks.append(str(data.get('delta') or ''))
                    if isinstance(data.get('content'), str):
                        full_stream_content = data['content']
                elif event == 'tool_start':
                    result['tool_starts'].append(data)
                elif event == 'tool_result':
                    result['tool_results'].append(data)
                elif event == 'trace':
                    result['traces'].append(data)
                elif event == 'final':
                    final_answer = data.get('answer')
                    keys = ('ok', 'answer_route', 'grounding_status', 'model_request_count', 'mcp_tool_trace',
                            'termination_reason', 'request_id', 'qa_request_id', 'mcp_request_budget', 'metrics',
                            'completion', 'knowledge_manifest', 'messages_projection', 'messages', 'task_plan')
                    result['final'] = {k: data[k] for k in keys if k in data}
                elif event == 'error':
                    result['error_code'] = data.get('error') or data.get('code') or 'sse_error'
                elif event == 'done':
                    result['done'] = True
                    break
        result['terminated'] = bool(result.get('done') or result.get('eof'))
    except Exception as exc:
        result['transport_error'] = type(exc).__name__
        result['terminated'] = False
    finally:
        connection.close()
        cookie = ''
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    result['delta_concatenation'] = ''.join(chunks)
    result['last_stream_content'] = full_stream_content
    result['answer'] = final_answer if isinstance(final_answer, str) else (full_stream_content or ''.join(chunks))
    print(json.dumps(result, ensure_ascii=False, default=str))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--case-json', required=True)
    parser.add_argument('--phase', default='before')
    parser.add_argument('--conversation-id')
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        parser.error('--execute required; no request sent')
    run(args)


if __name__ == '__main__':
    main()

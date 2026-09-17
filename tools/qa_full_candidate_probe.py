"""Read-only, in-memory import of an exact frozen QA closure; no service switch.

REQ-QA-FULL-CANDIDATE-RUNTIME-20260917. Run in a fresh Python process with -B.
The caller supplies verified source bytes, not production configuration or data.
"""
import base64
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import io
import json
import os
import platform
from pathlib import Path
import sys
import threading

BASE_FILES = {'bf_data_mcp_server.py', 'ollama_proxy_server.py', 'qa_completion.py',
    'qa_document_compound.py', 'qa_document_knowledge.py', 'qa_evidence_policy.py',
    'qa_fixed_model_identity.py', 'qa_history_compound.py', 'qa_history_projection.py',
    'qa_knowledge_reader_source_gate.py', 'qa_knowledge_source_binding.py',
    'qa_statistical_evidence.py', 'qa_task_plan.py', 'qa_verified_facts.py',
    'qa_window_quality.py', 'qa_prompt_binding.py'}
FIXED_NAME = 'chiqiongblastfuenace:latest'
FIXED_DIGEST = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'


class SideEffectDenied(RuntimeError):
    pass


def run(payload):
    """Import actual complete modules under native dependencies, rejecting I/O."""
    if payload.get('model_name') != FIXED_NAME or payload.get('model_digest') != FIXED_DIGEST:
        raise ValueError('Frozen model identity mismatch')
    sources = payload['sources']
    hashes = payload['sha256']
    if set(sources) != BASE_FILES or set(hashes) != BASE_FILES:
        raise ValueError('Frozen module set mismatch')
    decoded = {name: base64.b64decode(data, validate=True) for name, data in sources.items()}
    for name, raw in decoded.items():
        if hashlib.sha256(raw).hexdigest() != hashes[name]:
            raise ValueError('Frozen module hash mismatch: ' + name)
        if name[:-3] in sys.modules:
            raise ValueError('Fresh interpreter required: ' + name)
    root = Path(payload['dependency_root']).resolve()
    backend = root / '高炉前端数据/智能助手/backend'
    mcp = root / '高炉前端数据/智能助手/mcp'
    service = root / '自动诊断服务'
    if not backend.is_dir() or not service.is_dir():
        raise ValueError('Reviewed dependency root unavailable')
    sys.dont_write_bytecode = True
    for key in list(os.environ):
        if key.startswith(('BF_', 'OLLAMA_', 'PG')):
            del os.environ[key]
    os.environ.update({'BF_FRONTEND_DIR': str(root / '高炉前端数据'),
        'OLLAMA_BASE_URL': 'http://synthetic.invalid:11434',
        'BF_QA_KNOWLEDGE_SEARCH_MODE': 'keyword', 'BF_SKIP_ASSISTANT_STARTUP': '1',
        'BF_DIAGNOSIS_AI_ANALYSIS_ENABLED': '0'})
    sys.path[:0] = [str(backend), str(mcp), str(service)]
    # On Windows, stdlib platform.machine() may run the read-only `ver` command.
    # Prepare its OS metadata before the guarded candidate import, rather than
    # allowing candidate code to spawn processes or misclassifying it as a write.
    platform.uname()
    attempted = []
    attempt_frames = []
    dependency_hashes = {}

    def denied(kind):
        attempted.append(kind)
        frames = []
        frame = sys._getframe(1)
        for _ in range(10):
            if frame is None:
                break
            frames.append({'file': Path(frame.f_code.co_filename).name,
                'function': frame.f_code.co_name, 'line': frame.f_lineno})
            frame = frame.f_back
        attempt_frames.append({'kind': kind, 'frames': frames})
        raise SideEffectDenied('Read-only full import rejected side effect: ' + kind)

    def audit(event, args):
        if event in {'socket.connect', 'socket.connect_ex', 'socket.bind', 'socket.getaddrinfo',
                'subprocess.Popen', 'os.system', 'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir',
                'os.truncate', 'os.chmod', 'os.link', 'os.symlink'}:
            denied(event)
        if event == 'open':
            mode, flags = args[1:3]
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                    isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                denied('open_write')

    sys.addaudithook(audit)
    threading.Thread.start = lambda self: denied('thread_start')
    # Native DB drivers do not necessarily use Python socket auditing.
    for driver in ('psycopg', 'psycopg2', 'sqlite3'):
        try:
            module = importlib.import_module(driver)
        except ModuleNotFoundError as exc:
            if exc.name != driver:
                raise
        else:
            module.connect = lambda *args, **kwargs: denied('database_connect')

    class Loader(importlib.abc.Loader):
        def __init__(self, name, raw, path=None):
            self.name, self.raw = name, raw
            self.path = path or (mcp if name == 'bf_data_mcp_server' else backend) / (name + '.py')
        def create_module(self, spec):
            return None
        def get_source(self, name):
            return self.raw.decode('utf-8')
        def exec_module(self, module):
            module.__file__ = str(self.path)
            exec(compile(self.raw, str(self.path), 'exec'), module.__dict__)

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            raw = decoded.get(fullname + '.py')
            if raw is not None:
                return importlib.util.spec_from_loader(fullname, Loader(fullname, raw))
            # Capture and execute actual project source, avoiding stale .pyc or
            # hashing a later replacement instead of the bytes that executed.
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is not None and spec.origin and spec.origin.endswith('.py'):
                origin = Path(spec.origin).resolve()
                if origin.is_relative_to(root):
                    raw = origin.read_bytes()
                    dependency_hashes[origin.relative_to(root).as_posix()] = hashlib.sha256(raw).hexdigest()
                    return importlib.util.spec_from_file_location(fullname, str(origin),
                        loader=Loader(fullname, raw, origin),
                        submodule_search_locations=spec.submodule_search_locations)
            return None

    sys.meta_path.insert(0, Finder())
    log = io.StringIO()
    prior_stdout = sys.stdout
    imported = []
    importing = None
    contracts = None
    error = None
    try:
        sys.stdout = log
        # No missing import is stubbed. Both full application entry modules execute.
        for name in ('ollama_proxy_server', 'bf_data_mcp_server'):
            importing = name
            importlib.import_module(name)
            imported.append(name)
        for name in sorted(BASE_FILES):
            importing = name[:-3]
            importlib.import_module(importing)
        if payload.get('request_contracts') is True:
            contracts = request_contracts(sys.modules['ollama_proxy_server'])
    except Exception as exc:
        error = {'type': type(exc).__name__, 'missing_module': getattr(exc, 'name', None), 'importing': importing}
    finally:
        sys.stdout = prior_stdout
    loaded = {}
    changed_dependencies = []
    for name, module in sorted(sys.modules.items()):
        file = getattr(module, '__file__', None)
        if not file:
            continue
        path = Path(file).resolve()
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if name + '.py' in decoded:
            loaded[relative] = {'sha256': hashes[name + '.py'], 'source': 'frozen_in_memory'}
        elif path.suffix == '.py' and path.is_file():
            executed_sha = dependency_hashes.get(relative)
            current_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if executed_sha is None or executed_sha != current_sha:
                changed_dependencies.append(relative)
            loaded[relative] = {'sha256': executed_sha, 'source': 'dependency_readonly_source'}
    return {'schema': 'bf.qa.full-candidate-readonly-import.v1',
        'candidate': payload.get('candidate'), 'manifest_sha256': payload.get('manifest_sha256'),
        'probe_sha256': payload.get('probe_sha256'),
        'fixed_identity': {'name': FIXED_NAME, 'digest': FIXED_DIGEST},
        'ok': imported == ['ollama_proxy_server', 'bf_data_mcp_server'] and error is None and not attempted and not changed_dependencies
            and (contracts is None or all(row['passed'] for row in contracts['cases'])),
        'native_python': '.'.join(str(x) for x in sys.version_info[:3]),
        'stdlib_platform_metadata_prepared': True,
        'imported_entries': imported, 'error': error,
        'frozen_modules_loaded': sum(name[:-3] in sys.modules for name in BASE_FILES),
        'module_hashes': loaded, 'side_effect_attempts': attempted,
        'changed_or_unbound_dependencies': changed_dependencies,
        'project_dependencies_executed_from_source': True,
        'side_effect_frames': attempt_frames,
        'request_contracts': contracts,
        'model_calls': 0, 'question_posts': 0, 'production_writes': 0,
        'service_started': False, 'semantic_accuracy_inferred': False}


def request_contracts(proxy):
    """Exercise full imported handlers with synthetic I/O, not real QA requests."""
    owner = 'synthetic-owner'
    conversation_id = 'synthetic-conversation'
    timestamp = '2026-01-01T00:00:00+00:00'
    conversation = {'id': conversation_id, 'owner_subject': owner, 'title': 'synthetic-title',
        'created_at': timestamp, 'updated_at': timestamp, 'last_user_at': timestamp}
    state = {'messages': [], 'calls': [], 'digest': FIXED_DIGEST, 'cancel_after_chat': False,
        'sensor_context_reads': [], 'page_archives': []}

    class Cursor:
        def __init__(self, rows=(), lastrowid=None):
            self.rows, self.lastrowid = list(rows), lastrowid
        def fetchone(self): return self.rows[0] if self.rows else None
        def fetchall(self): return self.rows

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def close(self): pass
        def commit(self): pass
        def execute(self, sql, params=()):
            text = ' '.join(sql.lower().split())
            if text.startswith('select') and 'from furnace_snapshots' in text:
                state['sensor_context_reads'].append('assistant_snapshot_read')
            if text.startswith('insert into furnace_snapshots('):
                state['page_archives'].append('synthetic_page_archive')
                return Cursor(lastrowid=len(state['page_archives']))
            if text.startswith('insert into qa_messages('):
                message = dict(zip(('conversation_id', 'role', 'content', 'created_at', 'snapshot_id', 'hidden_context_json'), params))
                message['id'] = len(state['messages']) + 1
                state['messages'].append(message)
                return Cursor(lastrowid=message['id'])
            if text.startswith('update qa_messages set hidden_context_json'):
                hidden, message_id, room, subject = params
                matches = [row for row in state['messages'] if row['id'] == message_id and row['conversation_id'] == room and row['role'] == 'user' and subject == owner]
                for row in matches: row['hidden_context_json'] = hidden
                return Cursor([{'id': row['id']} for row in matches])
            if text.startswith('update qa_conversations set'):
                return Cursor()
            if text.startswith('select owner_subject from qa_conversations'):
                return Cursor([{'owner_subject': owner}] if params[0] == conversation_id else [])
            if text.startswith('select * from qa_conversations where id'):
                matches = params[0] == conversation_id and (len(params) == 1 or params[1] == owner)
                return Cursor([conversation] if matches else [])
            if text.startswith('select c.*') and 'from qa_conversations c' in text:
                return Cursor([conversation] if 'where c.id = ?' in text else [])
            if text.startswith('select m.id from qa_messages m join qa_conversations c'):
                room, subject, *ids = params
                return Cursor([{'id': row['id']} for row in state['messages'] if row['conversation_id'] == room and subject == owner and row['role'] == 'user' and row['id'] in ids])
            if text.startswith('select id, conversation_id, role, content, created_at, snapshot_id from qa_messages'):
                return Cursor(state['messages'])
            if text.startswith('select') and any(part in text for part in ('from furnace_snapshots', 'from qa_messages', 'from qa_conversation_origins')):
                return Cursor()
            raise RuntimeError('Synthetic database does not implement this query')

    def transport(request, **kwargs):
        path = proxy.urlparse(request.full_url).path
        if request.get_method() == 'GET' and path in ('/api/tags', '/api/ps'):
            return io.BytesIO(json.dumps({'models': [{'name': FIXED_NAME, 'digest': state['digest']}]}).encode())
        if path != '/api/chat' or request.get_method() != 'POST':
            raise RuntimeError('Unexpected synthetic transport path')
        body = json.loads(request.data)
        state['calls'].append(body)
        if state['cancel_after_chat']:
            proxy.qa_request_control._local.state.stop()
        return io.BytesIO(json.dumps({'message': {'content': '三个给定样本的平均值为223.33，极差为6；只反映给定样本。'},
            'done': True, 'done_reason': 'stop'}).encode('utf-8'))

    class Probe(proxy.Handler):
        def __init__(self, question, *, subject=owner, stream=False, request_id=None):
            self.headers = {'Host': 'synthetic.invalid', 'Origin': 'http://synthetic.invalid', 'Content-Type': 'application/json'}
            self.path, self.command = '/api/qa/chat', 'POST'
            self.client_address = ('127.0.0.1', 1)
            self.wfile = io.BytesIO()
            self.statuses = []
            self.session = {'sub': subject, 'role': 'operator', 'access_mode': 'authenticated'}
            body = {'message': question, 'conversation_id': conversation_id, 'stream': stream,
                'client_request_id': request_id or 'synthetic_request_' + proxy.uuid.uuid4().hex,
                'current_snapshot': {'source_time': timestamp,
                    'values': {'synthetic_page_marker': 'PAGE_ARCHIVE_IS_NOT_ANALYSIS_EVIDENCE'}}}
            raw = json.dumps(body).encode('utf-8')
            self.headers['Content-Length'] = str(len(raw))
            self.rfile = io.BytesIO(raw)
        def qa_session_required(self): return self.session
        def send_response(self, status): self.statuses.append(status)
        def send_header(self, *args): pass
        def end_headers(self): pass
        def add_cors(self): pass
        def latest_pg_snapshot_for_qa(self, conn):
            state['sensor_context_reads'].append('latest_sensor_provider')
            return None
        def recent_pg_diagnosis_snapshots_for_qa(self, **kwargs):
            state['sensor_context_reads'].append('trend_sensor_provider')
            return [], {}

    # Keep actual DB/control wrapper, ownership, preparation, prompt, request,
    # completion, persistence and reply methods. Only external seams are fake.
    proxy._assistant_pg_connect = Connection
    proxy._QA_DB_BOOTSTRAPPED = True
    proxy.urlopen = transport
    proxy.qa_request_control._requests.clear()
    class SourceBoundCases(list):
        def append(self, row):
            # All questions below explicitly restrict external data or request
            # disabled code. Functional success alone does not prove no reads.
            row['functional_contract_passed'] = bool(row['passed'])
            row['sensor_context_read_count'] = len(state['sensor_context_reads'])
            row['sensor_context_read_kinds'] = list(state['sensor_context_reads'])
            row['mock_page_archives'] = len(state['page_archives'])
            expected_archives = 0 if row['id'] in {'full_json_cross_owner_denied', 'full_json_single_user_busy'} else 1
            isolated = all(message.get('snapshot_id') is None
                and not (json.loads(message.get('hidden_context_json') or '{}').get('snapshot_ids') or [])
                and json.loads(message.get('hidden_context_json') or '{}').get('latest_snapshot_id') is None
                for message in state['messages'])
            isolated = isolated and all('PAGE_ARCHIVE_IS_NOT_ANALYSIS_EVIDENCE' not in json.dumps(body)
                for body in state['calls'])
            row['page_archive_isolated_from_evidence'] = bool(isolated)
            row['passed'] = bool(row['passed'] and not state['sensor_context_reads']
                and row['mock_page_archives'] == expected_archives and isolated)
            super().append(row)

    cases = SourceBoundCases()
    data_question = '仅基于我提供的数据：风压=[220,224,226]，计算平均值并说明波动，不查数据库。'

    def reset():
        state['messages'], state['calls'], state['digest'] = [], [], FIXED_DIGEST
        state['cancel_after_chat'] = False
        state['sensor_context_reads'] = []
        state['page_archives'] = []

    def response(handler):
        return json.loads(handler.wfile.getvalue())

    reset()
    handler = Probe(data_question)
    handler.handle_qa_chat()
    result = response(handler)
    stored = [row for row in state['messages'] if row['role'] == 'assistant']
    persisted = json.loads(stored[0]['hidden_context_json']) if stored else {}
    bound = result.get('prompt_binding') or {}
    cases.append({'id': 'full_json_supplied_data', 'passed': result.get('ok') is True
        and len(state['calls']) == 1 and bound.get('requests_built') == 1
        and persisted.get('prompt_binding') == bound and not result.get('mcp_tool_calling'),
        'status': handler.statuses[-1], 'mock_requests': len(state['calls']),
        'error_code': result.get('error') if not result.get('ok') else None})

    reset()
    handler = Probe('写一个Python示例读取数据库。')
    handler.handle_qa_chat()
    result = response(handler)
    cases.append({'id': 'full_json_code_disabled', 'passed': result.get('ok') is True
        and not state['calls'] and '```' not in result.get('answer', ''),
        'status': handler.statuses[-1], 'mock_requests': len(state['calls']),
        'error_code': result.get('error') if not result.get('ok') else None})

    reset()
    handler = Probe(data_question, subject='synthetic-other-owner')
    handler.handle_qa_chat()
    result = response(handler)
    cases.append({'id': 'full_json_cross_owner_denied', 'passed': handler.statuses == [404]
        and result.get('error') == 'conversation_not_found' and not state['messages'] and not state['calls'],
        'status': handler.statuses[-1], 'mock_requests': len(state['calls'])})

    reset()
    state['digest'] = 'f' * 64
    handler = Probe(data_question)
    handler.handle_qa_chat()
    result = response(handler)
    cases.append({'id': 'full_json_wrong_weight_denied', 'passed': result.get('ok') is False
        and result.get('code') == 'fixed_model_identity_not_ready' and not state['calls']
        and not any(row['role'] == 'assistant' for row in state['messages'])
        and (result.get('prompt_binding') or {}).get('requests_built') == 0,
        'status': handler.statuses[-1], 'mock_requests': len(state['calls']),
        'error_code': result.get('code')})

    reset()
    active = proxy.qa_request_control.RequestState('synthetic_other_active', 'synthetic-other-owner', 'synthetic-other-conversation')
    proxy.qa_request_control._requests[active.id] = active
    handler = Probe(data_question)
    handler.handle_qa_chat()
    result = response(handler)
    cases.append({'id': 'full_json_single_user_busy', 'passed': handler.statuses == [409]
        and result.get('error') == 'assistant_in_use' and result.get('automatic_replay') is False
        and not state['messages'] and not state['calls'], 'status': handler.statuses[-1],
        'mock_requests': len(state['calls'])})
    active.finished.set()
    active.state = 'completed'

    reset()
    duplicate_id = 'synthetic_duplicate_request'
    first = Probe('写一个Python示例读取数据库。', request_id=duplicate_id)
    first.handle_qa_chat()
    first_result = response(first)
    count = len(state['messages'])
    repeated = Probe(data_question, request_id=duplicate_id)
    repeated.handle_qa_chat()
    result = response(repeated)
    cases.append({'id': 'full_json_duplicate_id_denied', 'passed': first_result.get('ok') is True
        and repeated.statuses == [409] and result.get('error') == 'request_already_exists'
        and len(state['messages']) == count and not state['calls'],
        'status': repeated.statuses[-1], 'mock_requests': len(state['calls'])})

    reset()
    state['cancel_after_chat'] = True
    handler = Probe(data_question)
    handler.handle_qa_chat()
    result = response(handler)
    cases.append({'id': 'full_json_cancel_before_persist', 'passed': handler.statuses == [409]
        and result.get('error') == 'request_cancelled' and len(state['calls']) == 1
        and not any(row['role'] == 'assistant' for row in state['messages']),
        'status': handler.statuses[-1], 'mock_requests': len(state['calls'])})

    # Heartbeat scheduling is an explicit synthetic seam: do not start a thread
    # on the production host. Event wrapping and finalization still execute.
    start_thread = proxy.threading.Thread.start
    heartbeat_schedules = []
    proxy.threading.Thread.start = lambda self: heartbeat_schedules.append(self.name)
    try:
        for identifier, question, digest, expected_calls in [
                ('full_sse_supplied_data', data_question, FIXED_DIGEST, 1),
                ('full_sse_code_disabled', '写一个Python示例读取数据库。', FIXED_DIGEST, 0),
                ('full_sse_wrong_weight_denied', data_question, 'f' * 64, 0)]:
            reset()
            state['digest'] = digest
            handler = Probe(question, stream=True)
            handler.handle_qa_chat()
            events = []
            for block in handler.wfile.getvalue().decode('utf-8').split('\n\n'):
                lines = block.splitlines()
                if lines:
                    events.append((lines[0].removeprefix('event: '), json.loads(lines[1].removeprefix('data: '))))
            names = [name for name, _ in events]
            final = next((value for name, value in events if name == 'final'), None)
            errors = [value for name, value in events if name == 'error']
            if digest == FIXED_DIGEST:
                stored = [row for row in state['messages'] if row['role'] == 'assistant']
                persisted = json.loads(stored[0]['hidden_context_json']) if stored else {}
                passed = final is not None and final.get('ok') is True and not errors
                passed = passed and names[0] == 'start' and names[-2:] == ['final', 'done'] and 'delta' in names
                passed = passed and len(state['calls']) == expected_calls
                passed = passed and persisted.get('prompt_binding') == final.get('prompt_binding')
            else:
                passed = final is None and bool(errors) and errors[-1].get('code') == 'fixed_model_identity_not_ready'
                passed = passed and not state['calls'] and not any(row['role'] == 'assistant' for row in state['messages'])
                passed = passed and (errors[-1].get('prompt_binding') or {}).get('requests_built') == 0
            cases.append({'id': identifier, 'passed': bool(passed), 'status': handler.statuses[-1],
                'events': names, 'mock_requests': len(state['calls'])})
    finally:
        proxy.threading.Thread.start = start_thread

    return {'state': 'synthetic_contract_only', 'cases': cases,
        'mocked_boundaries': ['authentication_session', 'database_connection', 'sensor_snapshot_provider', 'ollama_transport', 'heartbeat_thread_start'],
        'heartbeat_schedules_mocked': len(heartbeat_schedules), 'real_concurrency_verified': False,
        'full_prepare_executed': True, 'real_database_verified': False,
        'real_model_answer_verified': False, 'production_accuracy_inferred': False}


if __name__ == '__main__':
    result = run(json.load(sys.stdin))
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['ok'] else 1)

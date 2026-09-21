"""Bind actual frozen proxy request, persistence, cache and response boundaries."""
import ast
from contextlib import nullcontext
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from typing import Any, Mapping
from urllib.request import Request

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_prompt_binding as binding
from qa_frozen_candidate import latest_frozen_candidate

VERSIONS = {'sources': 'sources-v1', 'evidence': 'evidence-v1', 'task_plan': 'plan-v1', 'abc_initial': 'abc.v1'}
MESSAGES = [{'role': 'system', 'content': 'synthetic-private-prompt'},
            {'role': 'user', 'content': 'synthetic-private-question'}]


@pytest.mark.parametrize('base', ['abc.v1', 'custom.v2', 'abc.v1.fixed-pin-binding.v1'])
def test_actual_cache_namespace_appends_exactly_one_suffix(monkeypatch, base):
    candidate, _ = latest_frozen_candidate(ROOT)
    tree = ast.parse((candidate / 'ollama_proxy_server.py').read_bytes())
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'ABC_RULE_ASSISTANT_PROMPT_VERSION')
    monkeypatch.setenv('BF_ABC_RULE_ASSISTANT_PROMPT_VERSION', base)
    namespace = {'os': os, 'qa_prompt_binding': binding}
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), str(candidate), 'exec'), namespace)
    expected = base if base.endswith('.fixed-pin-binding.v1') else base + '.fixed-pin-binding.v1'
    assert namespace['ABC_RULE_ASSISTANT_PROMPT_VERSION'] == expected


def prepared(messages=None):
    return {'messages': messages or MESSAGES, 'response_mode': 'flash', 'use_mcp_tools': False,
            'tool_selection': {'mode': 'none'}, 'analysis_mode': '', 'qa_answer_route': 'analysis'}


def scope():
    candidate, manifest = latest_frozen_candidate(ROOT)
    tree = ast.parse((candidate / 'ollama_proxy_server.py').read_bytes())
    names = {'build_ollama_request', 'add_message', 'cache_abc_rule_analysis', '_abc_rule_cached_analysis',
             'send_json', 'write_qa_event', 'handle_qa_chat', 'send_cached_abc_initial_analysis'}
    selected = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {'Any': Any, 'Mapping': Mapping, 'Request': Request, 'json': json,
        'qa_prompt_binding': binding, 'qa_fixed_model_identity': binding.qa_fixed_model_identity,
        'resolve_upstream_model': lambda: binding.qa_fixed_model_identity.MODEL_NAME,
        'OLLAMA_BASE_URL': 'http://synthetic-model', 'json_bytes': lambda obj: json.dumps(obj).encode(),
        'iso_now': lambda: 'synthetic-time', 'title_from_question': lambda text: 'synthetic-title',
        'ABC_RULE_ASSISTANT_PROMPT_VERSION': 'abc.v1',
        'load_json': lambda text, default: json.loads(text) if isinstance(text, str) else text or default,
        'compress_static_payload': lambda data, *args: (data, None),
        'qa_sse_event': lambda event, obj: json.dumps({'event': event, 'payload': obj}).encode(),
        'QA_RESPONSE_MODE_FLASH': 'flash', 'normalize_qa_response_mode': lambda value: value or 'flash',
        'parse_tool_selection': lambda value, **kwargs: value or {'mode': 'auto'},
        'QA_MCP_MAX_TOOL_CALLS': 4, 'ToolSelectionError': ValueError,
        'db_connect': lambda: nullcontext(object()), 'finish_abc_rule_initial_analysis': lambda ticket: None}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(candidate), 'exec'), namespace)
    return namespace, manifest


def start_prepared():
    binding.record_prepared(prepared(), template='synthetic-template', versions=VERSIONS)


@pytest.mark.parametrize('stream,tools,output_format', [(False, None, None), (True, None, None),
    (False, [{'type': 'function', 'function': {'name': 'synthetic_read'}}], {'type': 'object'})])
def test_actual_request_boundary_records_exact_outbound_body_after_pin_check(stream, tools, output_format):
    namespace, _ = scope()
    @binding.trace_turn
    def turn():
        start_prepared()
        payload = {'model': 'untrusted-override', 'messages': MESSAGES, 'stream': stream,
                   'tools': tools, 'format': output_format, 'options': {'temperature': 0.1}}
        request = namespace['build_ollama_request']('/api/chat', json.dumps(payload).encode(), stream=stream)
        result = binding.snapshot()
        assert result['requests_built'] == 1
        row = result['requests'][0]
        assert row['outbound_body_sha256'] == hashlib.sha256(request.data).hexdigest()
        assert row['state'] == 'request_built' and row['stream'] is stream
        assert json.loads(request.data)['model'] == binding.qa_fixed_model_identity.MODEL_NAME
        assert 'prompt_binding' not in json.loads(request.data)
        assert row['system_prompt_sha256'] == result['prepared']['system_prompt_sha256']
        assert not result['completion_or_accuracy_inferred']
    turn()
    assert binding.snapshot() is None


def test_actual_pin_failure_records_no_request_and_never_builds_post():
    namespace, _ = scope()
    def unavailable():
        raise binding.qa_fixed_model_identity.FixedModelUnavailable('synthetic-pin-error')
    namespace['resolve_upstream_model'] = unavailable
    @binding.trace_turn
    def turn():
        start_prepared()
        with pytest.raises(binding.qa_fixed_model_identity.FixedModelUnavailable):
            namespace['build_ollama_request']('/api/chat', json.dumps({'messages': MESSAGES}).encode())
        assert binding.snapshot()['requests_built'] == 0
    turn()


def test_actual_assistant_message_persists_binding_without_mutating_user_context():
    namespace, _ = scope()
    writes = []
    connection = SimpleNamespace(execute=lambda sql, params: writes.append((sql, params)) or SimpleNamespace(lastrowid=4), commit=lambda: None)
    context = {'synthetic_fact_reference': 1}
    @binding.trace_turn
    def turn():
        start_prepared()
        namespace['add_message'](connection, 'synthetic-room', 'assistant', 'synthetic-answer', hidden_context=context)
        stored = json.loads(writes[0][1][-1])
        assert stored['prompt_binding']['requests_built'] == 0
        assert stored['prompt_binding']['prepared']['system_prompt_sha256']
        assert context == {'synthetic_fact_reference': 1}
    turn()


class Output:
    def __init__(self):
        self.wfile = io.BytesIO()
        self.headers = {}
    def send_response(self, status): pass
    def send_header(self, *args): pass
    def add_cors(self): pass
    def end_headers(self): pass


@pytest.mark.parametrize('transport', ['json', 'sse_final', 'sse_error'])
def test_actual_response_boundary_includes_current_binding(transport):
    namespace, _ = scope()
    @binding.trace_turn
    def turn():
        start_prepared()
        output = Output()
        payload = {'ok': True, 'answer': 'synthetic-answer'}
        if transport == 'json':
            namespace['send_json'](output, payload)
            result = json.loads(output.wfile.getvalue())
        else:
            namespace['write_qa_event'](output, 'final' if transport == 'sse_final' else 'error', payload)
            result = json.loads(output.wfile.getvalue())['payload']
        assert result['prompt_binding']['prepared']['system_prompt_sha256']
        assert result['prompt_binding']['requests_built'] == 0
        assert 'prompt_binding' not in payload
    turn()


def test_actual_cache_reader_rejects_legacy_same_name_without_fixed_digest_proof():
    namespace, _ = scope()
    row = {'analysis_text': 'synthetic-answer', 'analysis_json': '{}', 'context_hash': 'synthetic-context',
           'generation_state': 'completed', 'context_snapshot_id': 2, 'prompt_version': 'abc.v1', 'model_name': binding.qa_fixed_model_identity.MODEL_NAME}
    conn = SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchone=lambda: row))
    assert namespace['_abc_rule_cached_analysis'](conn, 2, row['model_name']) is None


def captured_envelope():
    @binding.trace_turn
    def turn():
        start_prepared()
        body = json.dumps({'model': binding.qa_fixed_model_identity.MODEL_NAME, 'messages': MESSAGES}).encode()
        binding.record_request(body)
        return binding.cache_envelope({'synthetic_analysis': 1})
    return turn()


def test_actual_cache_write_read_preserves_generation_binding():
    namespace, _ = scope()
    writes = []
    source = {'rule_id': 'synthetic-rule', 'evaluation_id': 2, 'context_hash': 'synthetic-context',
              'operator_explanation_json': '{}', 'assistant_context_json': '{}'}
    conn = SimpleNamespace(execute=lambda sql, params: writes.append((sql, params)) or SimpleNamespace(fetchone=lambda: source), commit=lambda: None)
    @binding.trace_turn
    def turn():
        start_prepared()
        binding.record_request(json.dumps({'model': binding.qa_fixed_model_identity.MODEL_NAME, 'messages': MESSAGES}).encode())
        namespace['cache_abc_rule_analysis'](conn, 2, 'synthetic-answer', model_name=binding.qa_fixed_model_identity.MODEL_NAME, analysis_payload={'synthetic_analysis': 1}, claim_token='synthetic-claim')
        envelope = json.loads(writes[-1][1][6])
        assert envelope['analysis'] == {'synthetic_analysis': 1}
        row = {'analysis_text': 'synthetic-answer', 'analysis_json': json.dumps(envelope), 'context_hash': 'synthetic-context',
               'generation_state': 'completed', 'context_snapshot_id': 2, 'prompt_version': 'abc.v1', 'model_name': binding.qa_fixed_model_identity.MODEL_NAME}
        reader = SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchone=lambda: row))
        cached = namespace['_abc_rule_cached_analysis'](reader, 2, row['model_name'])
        assert cached['prompt_binding']['requests_built'] == 1
        assert binding.cache_reply_binding(cached['prompt_binding'])['current_requests_built'] == 0
    turn()


@pytest.mark.parametrize('transport,owned', [('json', True), ('sse', True), ('json', False), ('sse', False)])
def test_actual_cached_reply_preserves_original_binding_and_owner_gate(transport, owned):
    namespace, _ = scope()
    original = binding.cached_binding(captured_envelope())
    cached = {'answer': 'synthetic-answer', 'prompt_binding': original, 'context_snapshot_id': 2}
    namespace.update(load_conversation_with_origin=lambda *args: {}, load_messages=lambda *args: [])
    replies = []
    output = Output()
    output.qa_conversation_owned = lambda *args: owned
    output.send_json = lambda payload, **kwargs: replies.append(payload)
    output.write_qa_event = lambda event, payload: replies.append(payload) if event == 'final' else None
    namespace['send_cached_abc_initial_analysis'](output, 'synthetic-room', cached, stream=transport == 'sse', session={'sub': 'synthetic-owner'})
    if not owned:
        assert replies == []
        return
    result = replies[0]['prompt_binding']
    assert result['delivery'] == 'cache' and result['current_requests_built'] == 0
    assert result['requests'][0]['outbound_body_sha256'] == original['requests'][0]['outbound_body_sha256']
    assert original['delivery'] == 'current_turn' and 'current_requests_built' not in original


@pytest.mark.parametrize('method', ['handle_qa_chat_json', 'handle_qa_chat_stream'])
def test_actual_prepare_hook_hashes_final_prepared_messages(method):
    candidate, _ = latest_frozen_candidate(ROOT)
    tree = ast.parse((candidate / 'ollama_proxy_server.py').read_bytes())
    node = next(item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == method)
    assignment = next(item for item in ast.walk(node) if isinstance(item, ast.Assign)
        and isinstance(item.targets[0], ast.Name) and item.targets[0].id == 'prepared'
        and isinstance(item.value, ast.Call) and isinstance(item.value.func, ast.Attribute) and item.value.func.attr == 'prepare_qa_chat')
    capture = next(item for item in ast.walk(node) if isinstance(item, ast.Expr) and isinstance(item.value, ast.Call)
        and isinstance(item.value.func, ast.Attribute) and item.value.func.attr == 'record_prepared')
    namespace = {'self': SimpleNamespace(prepare_qa_chat=lambda *args, **kwargs: prepared()),
        'payload': {}, 'question': 'synthetic-question', 'qa_prompt_binding': binding,
        'QA_SYSTEM_PROMPT_TEMPLATE': 'synthetic-template', 'ABC_RULE_ASSISTANT_PROMPT_VERSION': 'abc.v1',
        'qa_prompt_sources': SimpleNamespace(VERSION=VERSIONS['sources']),
        'qa_evidence_policy': SimpleNamespace(VERSION=VERSIONS['evidence']),
        'qa_task_plan': SimpleNamespace(VERSION=VERSIONS['task_plan'])}
    @binding.trace_turn
    def turn():
        exec(compile(ast.Module(body=[assignment, capture], type_ignores=[]), str(candidate), 'exec'), namespace)
        assert binding.snapshot()['versions'] == VERSIONS
        assert binding.snapshot()['prepared']['system_messages'] == 1
    turn()


@pytest.mark.parametrize('mutation', ['retired_digest', 'no_requests', 'wrong_name', 'raw_request', 'raw_version', 'invalid_hash', 'bool_count'])
def test_cache_binding_rejects_unknown_or_untrusted_provenance(mutation):
    envelope = captured_envelope()
    current = envelope['prompt_binding']
    if mutation == 'retired_digest': current['requests'][0]['model_digest'] = '9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb'
    if mutation == 'no_requests': current['requests'] = []; current['requests_built'] = 0
    if mutation == 'wrong_name': current['requests'][0]['model_name'] = 'other:latest'
    if mutation == 'raw_request': current['requests'][0]['raw_prompt'] = 'private-material'
    if mutation == 'raw_version': current['versions']['owner'] = 'private-identity'
    if mutation == 'invalid_hash': current['requests'][0]['system_prompt_sha256'] = 'private-material'
    if mutation == 'bool_count': current['requests_built'] = True
    assert binding.cached_binding(envelope) is None


def test_planner_fallback_and_repair_keep_distinct_effective_system_hashes():
    @binding.trace_turn
    def turn():
        start_prepared()
        for stage in ('planner', 'fallback', 'repair'):
            messages = [*MESSAGES, {'role': 'system', 'content': 'synthetic-' + stage}]
            binding.record_request(json.dumps({'model': binding.qa_fixed_model_identity.MODEL_NAME, 'messages': messages}).encode())
        result = binding.snapshot()
        assert result['requests_built'] == 3
        assert len({row['system_prompt_sha256'] for row in result['requests']}) == 3
        assert [row['ordinal'] for row in result['requests']] == [1, 2, 3]
        rendered = json.dumps(result)
        assert 'synthetic-private-prompt' not in rendered and 'synthetic-private-question' not in rendered
        assert 'synthetic-template' not in rendered and 'untrusted-override' not in rendered
    turn()


def test_turn_context_isolated_across_threads_and_reset_after_failure():
    barrier = threading.Barrier(2)
    results = []
    failures = []
    @binding.trace_turn
    def turn(index):
        start_prepared()
        binding.record_request(json.dumps({'model': binding.qa_fixed_model_identity.MODEL_NAME,
            'messages': [{'role': 'system', 'content': 'synthetic-' + str(index)}]}).encode())
        barrier.wait(timeout=5)
        results.append(binding.snapshot())
        if index: raise RuntimeError('synthetic-failure')
    def worker(index):
        try: turn(index)
        except RuntimeError: failures.append(index)
        assert binding.snapshot() is None
    threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 2 and failures == [1]
    assert all(row['requests_built'] == 1 for row in results)
    assert len({row['requests'][0]['system_prompt_sha256'] for row in results}) == 2


@pytest.mark.parametrize('stream', [False, True])
def test_actual_outer_chat_dispatch_has_turn_context_and_preserves_owner_gate(stream):
    namespace, _ = scope()
    session = {'sub': 'synthetic-owner', 'role': 'operator'}
    calls = []
    def execute(payload, question):
        assert binding.snapshot() is not None
        assert payload['_qa_owner_subject'] == 'synthetic-owner'
        calls.append(('stream' if stream else 'json', question))
    handler = SimpleNamespace(qa_session_required=lambda: session,
        read_json_body=lambda: {'message': 'synthetic-question', 'stream': stream}, headers={},
        qa_chat_conversation_id=lambda conn, requested, actor: 'synthetic-room',
        handle_qa_chat_json=execute, handle_qa_chat_stream=execute)
    namespace['handle_qa_chat'](handler)
    assert calls == [('stream' if stream else 'json', 'synthetic-question')]
    assert binding.snapshot() is None

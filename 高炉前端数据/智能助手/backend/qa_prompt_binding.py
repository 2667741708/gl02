"""Hash actual QA request bodies without retaining prompts, facts, or identities."""
from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
import hashlib
import json
import re

import qa_fixed_model_identity

VERSION = 'qa-prompt-binding-v1'
SCHEMA = 'bf.qa.prompt-binding.v1'
CACHE_SCHEMA = 'bf.qa.cached-analysis-envelope.v1'
_CACHE_SUFFIX = '.fixed-pin-binding.v1'
_turn = ContextVar('qa_prompt_binding_turn', default=None)


def cache_version(base):
    base = str(base).strip()
    while base.endswith(_CACHE_SUFFIX):
        base = base[:-len(_CACHE_SUFFIX)]
    version = base + _CACHE_SUFFIX
    if not base or not re.fullmatch('[A-Za-z0-9_.-]{1,100}', version):
        raise ValueError('Invalid QA cache version')
    return version


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _message_hashes(messages):
    if not isinstance(messages, list) or any(not isinstance(row, dict) for row in messages):
        raise ValueError('QA messages must be an array of objects')
    systems = [{'index': index, 'content': row.get('content')} for index, row in enumerate(messages)
               if row.get('role') == 'system']
    return {'messages_sha256': _hash(messages), 'system_prompt_sha256': _hash(systems),
            'system_messages': len(systems)}


def trace_turn(function):
    """Isolate each synchronous HTTP turn and reset even on failure/cancellation."""
    @wraps(function)
    def traced(*args, **kwargs):
        token = _turn.set({'versions': {}, 'prepared': None, 'requests': []})
        try:
            return function(*args, **kwargs)
        finally:
            _turn.reset(token)
    return traced


def record_prepared(prepared, *, template, versions):
    trace = _turn.get()
    if trace is None:
        return
    policy = {key: prepared.get(key) for key in
              ('analysis_mode', 'response_mode', 'use_mcp_tools', 'tool_selection', 'qa_answer_route')}
    trace['versions'] = dict(versions)
    trace['prepared'] = {**_message_hashes(prepared['messages']),
                         'template_sha256': _hash(template), 'request_policy_sha256': _hash(policy)}


def record_request(body):
    """Called after the fixed pin check and serialization, before constructing Request.

    A recorded body proves request construction, not sending, completion or accuracy.
    No field is added to the upstream body and no model fallback is permitted.
    """
    trace = _turn.get()
    if trace is None:
        return
    payload = json.loads(body.decode('utf-8'))
    if payload.get('model') != qa_fixed_model_identity.MODEL_NAME:
        raise qa_fixed_model_identity.FixedModelUnavailable('固定底座请求名称不一致。')
    trace['requests'].append({
        'ordinal': len(trace['requests']) + 1, 'state': 'request_built',
        'model_name': qa_fixed_model_identity.MODEL_NAME,
        'model_digest': qa_fixed_model_identity.MODEL_DIGEST,
        'outbound_body_sha256': hashlib.sha256(body).hexdigest(),
        **_message_hashes(payload.get('messages') or []),
        'tool_schema_sha256': _hash(payload.get('tools')),
        'options_sha256': _hash(payload.get('options')),
        'output_schema_sha256': _hash(payload.get('format')),
        'stream': bool(payload.get('stream')), 'think': bool(payload.get('think'))})


def snapshot():
    trace = _turn.get()
    if trace is None:
        return None
    return deepcopy({'schema': SCHEMA, 'version': VERSION, 'delivery': 'current_turn',
                     'state': 'captured', 'versions': trace['versions'], 'prepared': trace['prepared'],
                     'requests_built': len(trace['requests']), 'requests': trace['requests'],
                     'completion_or_accuracy_inferred': False})


def with_binding(hidden_context):
    binding = snapshot()
    if binding is None:
        return hidden_context
    return {**(hidden_context or {}), 'prompt_binding': binding}


def public_payload(payload):
    binding = snapshot()
    if binding is None or not isinstance(payload, dict):
        return payload
    # Cache delivery carries the independently validated original generation binding.
    if 'prompt_binding' in payload:
        return payload
    return {**payload, 'prompt_binding': binding}


def cache_envelope(analysis):
    binding = snapshot()
    if binding is None:
        return analysis
    return {'schema': CACHE_SCHEMA, 'analysis': analysis, 'prompt_binding': binding}


def cached_binding(envelope):
    """Legacy or malformed caches never fabricate a same-base provenance proof."""
    if not isinstance(envelope, dict) or envelope.get('schema') != CACHE_SCHEMA:
        return None
    binding = envelope.get('prompt_binding')
    if not isinstance(binding, dict) or binding.get('schema') != SCHEMA or binding.get('version') != VERSION:
        return None
    requests = binding.get('requests')
    if not isinstance(requests, list) or not requests or type(binding.get('requests_built')) is not int or binding['requests_built'] != len(requests):
        return None
    if binding.get('delivery') != 'current_turn' or binding.get('state') != 'captured' or binding.get('completion_or_accuracy_inferred') is not False:
        return None
    hash_keys = ('outbound_body_sha256', 'messages_sha256', 'system_prompt_sha256',
                 'tool_schema_sha256', 'options_sha256', 'output_schema_sha256')
    request_keys = {'ordinal', 'state', 'model_name', 'model_digest', 'stream', 'think', 'system_messages', *hash_keys}
    for ordinal, row in enumerate(requests, 1):
        if not isinstance(row, dict) or set(row) != request_keys or row.get('ordinal') != ordinal or row.get('state') != 'request_built':
            return None
        if row.get('model_name') != qa_fixed_model_identity.MODEL_NAME or row.get('model_digest') != qa_fixed_model_identity.MODEL_DIGEST:
            return None
        if any(not isinstance(row.get(key), str) or not re.fullmatch('[0-9a-f]{64}', row[key]) for key in hash_keys):
            return None
        if any(type(row.get(key)) is not bool for key in ('stream', 'think')) or type(row.get('system_messages')) is not int or row['system_messages'] < 1:
            return None
    prepared = binding.get('prepared')
    prepared_keys = {'messages_sha256', 'system_prompt_sha256', 'system_messages', 'template_sha256', 'request_policy_sha256'}
    if not isinstance(prepared, dict) or set(prepared) != prepared_keys or type(prepared.get('system_messages')) is not int or prepared['system_messages'] < 1:
        return None
    if any(not isinstance(prepared[key], str) or not re.fullmatch('[0-9a-f]{64}', prepared[key]) for key in prepared_keys - {'system_messages'}):
        return None
    versions = binding.get('versions')
    if not isinstance(versions, dict) or set(versions) != {'sources', 'evidence', 'task_plan', 'abc_initial'}:
        return None
    if any(not isinstance(value, str) or not re.fullmatch('[A-Za-z0-9_.-]{1,100}', value) for value in versions.values()):
        return None
    # Return only an exact safe whitelist; arbitrary stored fields cannot reach the browser.
    return deepcopy({key: binding[key] for key in
                     ('schema', 'version', 'delivery', 'state', 'versions', 'prepared', 'requests_built', 'requests', 'completion_or_accuracy_inferred')})


def cache_reply_binding(binding):
    if binding is None:
        return {'schema': SCHEMA, 'state': 'unavailable', 'delivery': 'cache',
                'current_requests_built': 0, 'completion_or_accuracy_inferred': False}
    return {**deepcopy(binding), 'delivery': 'cache', 'current_requests_built': 0}

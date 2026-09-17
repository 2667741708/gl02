"""Reject stale or incomplete full-runtime evidence before release preparation."""
import copy
import hashlib
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]
from qa_frozen_candidate import latest_frozen_candidate
from verify_qa_full_candidate_probe import CASES, SHARED_CASES, ORDINARY_CASES, validate


def evidence():
    candidate, manifest = latest_frozen_candidate(ROOT)
    probe_sha = hashlib.sha256((ROOT / 'tools/qa_full_candidate_probe.py').read_bytes()).hexdigest()
    modules = {}
    for name, item in manifest['files'].items():
        prefix = 'mcp' if name == 'bf_data_mcp_server.py' else 'backend'
        modules['高炉前端数据/智能助手/' + prefix + '/' + name] = {
            'sha256': item['sha256'], 'source': 'frozen_in_memory'}
    for name in ('assistant_pg.py', 'qa_request_control.py', 'qa_prompt_sources.py', 'qa_model_readiness.py'):
        modules['高炉前端数据/智能助手/backend/' + name] = {
            'sha256': 'a' * 64, 'source': 'dependency_readonly_source'}
    for path, digest in manifest.get('runtime_dependency_pins', {}).items():
        modules[path] = {'sha256': digest, 'source': 'dependency_readonly_source'}
    report = {'schema': 'bf.qa.full-candidate-readonly-import.v1', 'ok': True,
        'candidate': manifest['candidate'], 'manifest_sha256': hashlib.sha256((candidate / 'package_manifest.private.json').read_bytes()).hexdigest(),
        'probe_sha256': probe_sha, 'fixed_identity': {'name': manifest['model_name'], 'digest': manifest['model_digest']},
        'native_python': '3.11.9', 'imported_entries': ['ollama_proxy_server', 'bf_data_mcp_server'],
        'frozen_modules_loaded': 16, 'side_effect_attempts': [], 'changed_or_unbound_dependencies': [],
        'project_dependencies_executed_from_source': True, 'model_calls': 0, 'question_posts': 0, 'production_writes': 0,
        'service_started': False, 'semantic_accuracy_inferred': False, 'module_hashes': modules,
        'runtime_dependency_pins': manifest.get('runtime_dependency_pins', {}), 'runtime_dependency_pin_mismatches': [],
        'request_contracts': {'state': 'synthetic_contract_only',
            'cases': [{'id': name, 'passed': True, 'functional_contract_passed': True,
                'sensor_context_read_count': 0, 'sensor_context_read_kinds': [],
                'mock_page_archives': 0 if name in {'full_json_cross_owner_denied', 'full_json_single_user_busy'} else 1,
                'page_archive_isolated_from_evidence': True} for name in sorted(CASES)],
            'full_prepare_executed': True, 'real_database_verified': False,
            'real_model_answer_verified': False, 'real_concurrency_verified': False,
            'production_accuracy_inferred': False,
            'mocked_boundaries': ['authentication_session', 'database_connection', 'sensor_snapshot_provider', 'ollama_transport', 'heartbeat_thread_start'],
            'ordinary_context_mocked_boundaries': ['authentication_session', 'database_connection', 'sensor_snapshot_provider', 'ollama_transport', 'heartbeat_thread_start', 'keyword_knowledge_provider'],
            'ordinary_context_cases': [{'id': key, 'passed': True, 'functional_contract_passed': True,
                'model_answer_generated': False, 'authority_present': values[0], 'authority_expected': values[0],
                'mock_knowledge_provider_queries': values[1], 'sensor_context_read_count': 0,
                'sensor_context_read_kinds': [], 'mock_page_archives': 1,
                'page_archive_isolated_from_evidence': True} for key, values in ORDINARY_CASES.items()]}}
    if manifest.get('shared_proxy_integration'):
        report['shared_abc_contracts'] = {'state': 'synthetic_contract_only',
            'merged_handler_methods_executed': True, 'real_database_verified': False,
            'real_authorization_verified': False, 'real_model_answer_verified': False,
            'production_accuracy_inferred': False,
            'mocked_boundaries': ['abc_configuration_provider', 'abc_database_connection',
                'persisted_sensor_review_provider', 'operator_permission_result', 'http_response_capture'],
            'cases': [{'id': key, 'passed': True, 'status': values[0], 'mock_db_read_count': values[1],
                'mock_operator_checks': values[2]} for key, values in SHARED_CASES.items()]}
    return report, candidate, manifest, probe_sha


def test_valid_evidence_exports_only_dependency_read_scope_without_authorization():
    report, candidate, manifest, probe_sha = evidence()
    scope = validate(report, candidate, manifest, probe_sha)
    assert set(scope['required_reads']) == {
        '高炉前端数据/智能助手/backend/' + name for name in
        ('assistant_pg.py', 'qa_request_control.py', 'qa_prompt_sources.py', 'qa_model_readiness.py')
    } | set(manifest.get('runtime_dependency_pins', {}))
    assert scope['native_contracts_passed'] == 10
    assert scope['native_ordinary_prepare_contracts_passed'] == 6
    assert scope['production_dependency_refresh_required'] is True
    assert scope['deployment_authorized'] is False
    assert scope['production_model_identity_verified'] is False
    assert scope['semantic_accuracy_inferred'] is False


@pytest.mark.parametrize('mutation', [
    lambda r: r.update(ok=False),
    lambda r: r.update(candidate='stale'),
    lambda r: r.update(manifest_sha256='b' * 64),
    lambda r: r.update(probe_sha256='b' * 64),
    lambda r: r['fixed_identity'].update(digest='f' * 64),
    lambda r: r.update(native_python='3.13.0'),
    lambda r: r.update(frozen_modules_loaded=15),
    lambda r: r.update(side_effect_attempts=['socket.connect']),
    lambda r: r.update(changed_or_unbound_dependencies=['modified.py']),
    lambda r: r.pop('runtime_dependency_pins'),
    lambda r: r.update(runtime_dependency_pins={}),
    lambda r: r.pop('runtime_dependency_pin_mismatches'),
    lambda r: r.update(runtime_dependency_pin_mismatches=['changed.py']),
    lambda r: r['module_hashes'].pop('高炉前端数据/智能助手/backend/furnace_display_policy.py'),
    lambda r: r['module_hashes']['高炉前端数据/智能助手/backend/abc_score_explanation.py'].update(sha256='b' * 64),
    lambda r: r.pop('shared_abc_contracts'),
    lambda r: r['shared_abc_contracts']['cases'].pop(),
    lambda r: r['shared_abc_contracts']['cases'][0].update(passed=False),
    lambda r: r['shared_abc_contracts']['cases'][0].update(mock_db_read_count=0),
    lambda r: r['shared_abc_contracts']['cases'][0].update(status=201),
    lambda r: r['shared_abc_contracts'].update(real_authorization_verified=True),
    lambda r: r['shared_abc_contracts']['mocked_boundaries'].append('unreviewed'),
    lambda r: r.update(model_calls=1),
    lambda r: r.update(production_writes=False),
    lambda r: r.update(semantic_accuracy_inferred=True),
    lambda r: r['request_contracts']['cases'].pop(),
    lambda r: r['request_contracts']['cases'][0].update(passed=False),
    lambda r: r['request_contracts']['cases'][0].update(sensor_context_read_count=5),
    lambda r: r['request_contracts']['cases'][0].update(sensor_context_read_count=False),
    lambda r: r['request_contracts']['cases'][0].pop('sensor_context_read_count'),
    lambda r: r['request_contracts']['cases'][0].update(sensor_context_read_kinds=['latest_sensor_provider']),
    lambda r: r['request_contracts']['cases'][0].update(functional_contract_passed=False),
    lambda r: r['request_contracts']['cases'][0].pop('mock_page_archives'),
    lambda r: r['request_contracts']['cases'][0].update(mock_page_archives=False),
    lambda r: r['request_contracts']['cases'][0].update(mock_page_archives=17),
    lambda r: r['request_contracts']['cases'][0].update(page_archive_isolated_from_evidence=False),
    lambda r: r['request_contracts'].update(real_model_answer_verified=True),
    lambda r: r['request_contracts']['mocked_boundaries'].append('unreviewed'),
    lambda r: r['request_contracts'].pop('ordinary_context_cases'),
    lambda r: r['request_contracts'].pop('ordinary_context_mocked_boundaries'),
    lambda r: r['request_contracts']['ordinary_context_cases'].pop(),
    lambda r: r['request_contracts']['ordinary_context_cases'][0].update(passed=False),
    lambda r: r['request_contracts']['ordinary_context_cases'][0].update(sensor_context_read_count=6),
    lambda r: r['request_contracts']['ordinary_context_cases'][0].update(sensor_context_read_count=False),
    lambda r: r['request_contracts']['ordinary_context_cases'][0].update(authority_present=True),
    lambda r: r['request_contracts']['ordinary_context_cases'][0].update(mock_knowledge_provider_queries=0),
    lambda r: r['request_contracts']['ordinary_context_cases'][0].update(mock_page_archives=0),
    lambda r: r['request_contracts']['ordinary_context_cases'][0].update(model_answer_generated=True),
    lambda r: r['request_contracts']['ordinary_context_cases'][0].update(page_archive_isolated_from_evidence=False),
    lambda r: r['module_hashes'].pop('高炉前端数据/智能助手/backend/qa_prompt_binding.py'),
    lambda r: r['module_hashes']['高炉前端数据/智能助手/backend/qa_prompt_binding.py'].update(sha256='b' * 64),
    lambda r: r['module_hashes']['高炉前端数据/智能助手/backend/qa_request_control.py'].update(source='dependency_readonly'),
    lambda r: r['module_hashes'].update({'../outside.py': {'sha256': 'a' * 64, 'source': 'dependency_readonly_source'}}),
])
def test_stale_or_weakened_probe_report_is_not_release_evidence(mutation):
    report, candidate, manifest, probe_sha = evidence()
    changed = copy.deepcopy(report)
    mutation(changed)
    with pytest.raises(ValueError):
        validate(changed, candidate, manifest, probe_sha)

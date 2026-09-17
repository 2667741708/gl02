"""Validate native full-candidate evidence and export transitive read scope.

This local gate never grants deployment or changes the production model.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from qa_frozen_candidate import latest_frozen_candidate

CASES = {'full_json_supplied_data', 'full_json_code_disabled', 'full_json_cross_owner_denied',
    'full_json_wrong_weight_denied', 'full_json_single_user_busy', 'full_json_duplicate_id_denied',
    'full_json_cancel_before_persist', 'full_sse_supplied_data', 'full_sse_code_disabled',
    'full_sse_wrong_weight_denied'}
SHARED_CASES = {
    'shared_public_breakdown_v2': (200, 2, 0),
    'shared_unavailable_score_not_counted': (200, 2, 0),
    'shared_public_detail_v3': (200, 1, 0),
    'shared_stale_detail_fail_closed': (200, 1, 0),
    'shared_operator_breakdown_denied': (403, 0, 1),
    'shared_invalid_evaluation_denied': (400, 0, 0),
    'shared_unknown_rule_denied': (404, 0, 0),
    'shared_missing_batch_denied': (404, 1, 0),
    'shared_missing_detail_needs_data': (200, 1, 0),
}
ORDINARY_CASES = {
    'ordinary_general_explanation': (False, 1),
    'ordinary_greeting': (False, 0),
    'ordinary_rule_explanation': (False, 1),
    'ordinary_bound_rule_explanation': (True, 1),
    'ordinary_unrelated_bound_topic': (False, 1),
    'ordinary_supplied_data_bound_isolated': (False, 0),
}
FOLLOWUP_CASES = {
    'followup_explicit_window': ('owned_live_followup', 30),
    'followup_inherited_window': ('owned_live_followup', 120),
    'followup_continue': ('owned_live_followup', 120),
    'followup_latest_resets_window': ('owned_live_followup', None),
    'followup_statistics': ('owned_live_followup', 120),
    'followup_missing_object': ('needs_clarification', 30),
    'followup_stale_object': ('needs_clarification', 30),
    'followup_foreign_ancestry': ('needs_clarification', 30),
    'followup_missing_latest': ('needs_clarification', None),
    'followup_stale_latest': ('needs_clarification', None),
    'followup_foreign_latest': ('needs_clarification', None),
    'followup_supplied_data_resets_scope': ('not_applicable', None),
    'followup_disabled_code_scope': ('disabled_code_only', None),
    'followup_clarification_json': None,
    'followup_clarification_sse': None,
}
CONFIRMATION_CASES = {
    'confirmation_bare_history': ('confirmed_data_object', ['DP_total'], 30),
    'confirmation_prefixed_history': ('confirmed_data_object', ['DP_total'], 120),
    'confirmation_latest': ('confirmed_data_object', ['DP_total'], None),
    'confirmation_statistics': ('confirmed_data_object', ['DP_total'], 120),
    'confirmation_boxplot': ('confirmed_data_object', ['DP_total'], 30),
    'confirmation_pair': ('confirmed_data_object', ['DP_total', 'P_top'], 60),
    'confirmation_insufficient_pair': ('needs_clarification', [], 60),
    'confirmation_expired': ('needs_clarification', ['DP_total'], None),
    'confirmation_foreign': ('needs_clarification', ['DP_total'], None),
    'confirmation_no_tools': ('not_applicable', [], None),
    'confirmation_selected_no_tools': ('not_applicable', [], None),
    'confirmation_disabled_code': ('disabled_code_only', [], None),
    'confirmation_supplied_data': ('not_applicable', [], None),
    'confirmation_roundtrip_json': ('confirmed_data_object', ['DP_total'], 30),
    'confirmation_roundtrip_sse': ('confirmed_data_object', ['DP_total'], 30),
}


def validate(report, candidate, manifest, probe_sha256):
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(report.get('schema') == 'bf.qa.full-candidate-readonly-import.v1' and report.get('ok') is True,
        'Native probe did not pass')
    require(report.get('candidate') == manifest['candidate'], 'Stale candidate evidence')
    require(report.get('manifest_sha256') == hashlib.sha256((candidate / 'package_manifest.private.json').read_bytes()).hexdigest(),
        'Frozen manifest mismatch')
    require(report.get('probe_sha256') == probe_sha256, 'Probe implementation changed')
    require(report.get('fixed_identity') == {'name': manifest['model_name'], 'digest': manifest['model_digest']},
        'Fixed base identity mismatch')
    require(re.fullmatch(r'3\.11\.\d+', str(report.get('native_python') or '')) is not None,
        'Native production Python 3.11 evidence required')
    require(report.get('imported_entries') == ['ollama_proxy_server', 'bf_data_mcp_server']
        and type(report.get('frozen_modules_loaded')) is int and report['frozen_modules_loaded'] == 16,
        'Full frozen closure not imported')
    require(report.get('side_effect_attempts') == [] and report.get('changed_or_unbound_dependencies') == []
        and report.get('project_dependencies_executed_from_source') is True, 'Import side effect or unbound dependency')
    require(all(type(report.get(key)) is int and report[key] == 0 for key in ('model_calls', 'question_posts', 'production_writes'))
        and report.get('service_started') is False and report.get('semantic_accuracy_inferred') is False,
        'Read-only or accuracy boundary violated')
    contracts = report.get('request_contracts') or {}
    rows = contracts.get('cases') or []
    require(len(rows) == len(CASES) and {row.get('id') for row in rows} == CASES
        and all(row.get('passed') is True for row in rows), 'Complete handler contract evidence required')
    require(all(row.get('functional_contract_passed') is True
        and type(row.get('sensor_context_read_count')) is int and row['sensor_context_read_count'] == 0
        and row.get('sensor_context_read_kinds') == [] for row in rows),
        'Explicit source restriction sensor reads were not verified')
    require(all(type(row.get('mock_page_archives')) is int
        and row['mock_page_archives'] == (0 if row['id'] in {'full_json_cross_owner_denied', 'full_json_single_user_busy'} else 1)
        and row.get('page_archive_isolated_from_evidence') is True for row in rows),
        'Page archival preservation or evidence isolation not verified')
    require(contracts.get('state') == 'synthetic_contract_only' and contracts.get('full_prepare_executed') is True
        and all(contracts.get(key) is False for key in ('real_database_verified', 'real_model_answer_verified',
            'real_concurrency_verified', 'production_accuracy_inferred')), 'Synthetic scope mislabeled')
    require(contracts.get('mocked_boundaries') == ['authentication_session', 'database_connection',
        'sensor_snapshot_provider', 'ollama_transport', 'heartbeat_thread_start'], 'Unreviewed mocked boundaries')
    require(contracts.get('ordinary_context_mocked_boundaries') == ['authentication_session',
        'database_connection', 'sensor_snapshot_provider', 'ollama_transport',
        'heartbeat_thread_start', 'keyword_knowledge_provider'], 'Unreviewed ordinary mocked boundaries')
    ordinary_rows = contracts.get('ordinary_context_cases') or []
    require(len(ordinary_rows) == len(ORDINARY_CASES)
        and {row.get('id') for row in ordinary_rows} == set(ORDINARY_CASES),
        'Complete ordinary preparation evidence required')
    for row in ordinary_rows:
        authority, queries = ORDINARY_CASES[row['id']]
        require(row.get('passed') is True and row.get('functional_contract_passed') is True
            and row.get('model_answer_generated') is False
            and row.get('authority_present') is authority and row.get('authority_expected') is authority
            and type(row.get('mock_knowledge_provider_queries')) is int
            and row['mock_knowledge_provider_queries'] == queries
            and type(row.get('sensor_context_read_count')) is int and row['sensor_context_read_count'] == 0
            and row.get('sensor_context_read_kinds') == []
            and type(row.get('mock_page_archives')) is int and row['mock_page_archives'] == 1
            and row.get('page_archive_isolated_from_evidence') is True,
            'Ordinary source isolation or bound authority not verified')
    if manifest.get('owned_followup_plan_propagated'):
        followups = contracts.get('owned_followup_cases') or []
        require(len(followups) == len(FOLLOWUP_CASES)
            and {row.get('id') for row in followups} == set(FOLLOWUP_CASES), 'Complete owned followup evidence required')
        require(contracts.get('owned_followup_mocked_boundaries') == ['authentication_session',
            'database_connection', 'sensor_snapshot_provider', 'ollama_transport', 'heartbeat_thread_start',
            'mcp_prefetch_provider', 'mcp_configuration_result'], 'Unreviewed followup mocked boundaries')
        for row in followups:
            require(row.get('passed') is True and row.get('functional_contract_passed') is True
                and row.get('model_answer_generated') is False
                and type(row.get('sensor_context_read_count')) is int and row['sensor_context_read_count'] == 0
                and row.get('sensor_context_read_kinds') == []
                and type(row.get('mock_page_archives')) is int and row['mock_page_archives'] == 1
                and row.get('page_archive_isolated_from_evidence') is True
                and type(row.get('mock_model_requests')) is int and row['mock_model_requests'] == 0
                and type(row.get('mock_prefetch_queries')) is int,
                'Followup source archival or no-model boundary not verified')
            expected = FOLLOWUP_CASES[row['id']]
            if expected is None:
                require(type(row.get('status')) is int and row['status'] == 200
                    and row.get('answer_route') == 'owned_followup_needs_clarification'
                    and row.get('mock_prefetch_queries') == 0
                    and (row.get('events') == [] if row['id'].endswith('_json')
                        else row.get('events') == ['start', 'start', 'delta', 'final', 'done']),
                    'Final deterministic followup clarification not verified')
            else:
                state, minutes = expected
                require(row.get('resolution_state') == state
                    and row.get('selected_objects') == (['DP_total'] if state == 'owned_live_followup' else [])
                    and (row.get('minutes') is None if minutes is None
                        else type(row.get('minutes')) is int and row['minutes'] == minutes)
                    and type(row.get('mock_prefetch_queries')) is int
                    and row['mock_prefetch_queries'] == (1 if state == 'owned_live_followup' else 0)
                    and row.get('fresh_evidence_required') is True,
                    'Owned object window ancestry or fresh-query contract not verified')
    if manifest.get('pending_object_confirmation'):
        confirmations = contracts.get('pending_confirmation_cases') or []
        require(len(confirmations) == len(CONFIRMATION_CASES)
            and {row.get('id') for row in confirmations} == set(CONFIRMATION_CASES),
            'Complete pending confirmation evidence required')
        for row in confirmations:
            state, objects, minutes = CONFIRMATION_CASES[row['id']]
            enabled = state == 'confirmed_data_object'
            roundtrip = row['id'].startswith('confirmation_roundtrip_')
            require(row.get('passed') is True and row.get('functional_contract_passed') is True
                and row.get('resolution_state') == state and row.get('selected_objects') == objects
                and (row.get('minutes') is None if minutes is None else type(row.get('minutes')) is int and row['minutes'] == minutes)
                and row.get('model_answer_generated') is False
                and type(row.get('mock_prefetch_queries')) is int and row['mock_prefetch_queries'] == int(enabled)
                and type(row.get('mock_model_requests')) is int and row['mock_model_requests'] == 0
                and type(row.get('sensor_context_read_count')) is int and row['sensor_context_read_count'] == 0
                and row.get('sensor_context_read_kinds') == []
                and type(row.get('mock_page_archives')) is int and row['mock_page_archives'] == (2 if roundtrip else 1)
                and row.get('page_archive_isolated_from_evidence') is True
                and row.get('fresh_evidence_required') is True
                and row.get('original_user_question_preserved') is True
                and (row.get('current_object_source_bound') is True if enabled else row.get('current_object_source_bound') is None)
                and (not roundtrip or (row.get('pending_created_by_first_handler') is True and row.get('clarification_no_reads') is True)),
                'Pending confirmation owner freshness or source boundary not verified')
    if manifest.get('shared_proxy_integration'):
        shared = report.get('shared_abc_contracts') or {}
        shared_rows = shared.get('cases') or []
        require(len(shared_rows) == len(SHARED_CASES)
            and {row.get('id') for row in shared_rows} == set(SHARED_CASES),
            'Complete merged shared Handler evidence required')
        for row in shared_rows:
            require(row.get('passed') is True and all(type(row.get(key)) is int
                for key in ('status', 'mock_db_read_count', 'mock_operator_checks'))
                and tuple(row[key] for key in ('status', 'mock_db_read_count', 'mock_operator_checks')) == SHARED_CASES[row['id']],
                'Shared public or permission contract failed')
        require(shared.get('state') == 'synthetic_contract_only' and shared.get('merged_handler_methods_executed') is True
            and shared.get('mocked_boundaries') == ['abc_configuration_provider', 'abc_database_connection',
                'persisted_sensor_review_provider', 'operator_permission_result', 'http_response_capture']
            and all(shared.get(key) is False for key in ('real_database_verified', 'real_authorization_verified',
                'real_model_answer_verified', 'production_accuracy_inferred')), 'Shared synthetic scope mislabeled')
    modules = report.get('module_hashes') or {}
    frozen = {}
    dependencies = {}
    for path, row in modules.items():
        parsed = PurePosixPath(path)
        require(not parsed.is_absolute() and '..' not in parsed.parts and '\\' not in path
            and ':' not in path and parsed.as_posix() == path and path.endswith('.py'), 'Invalid project read path')
        require(isinstance(row, dict) and set(row) == {'sha256', 'source'}
            and re.fullmatch(r'[0-9a-f]{64}', str(row.get('sha256') or '')) is not None, 'Invalid module hash evidence')
        if row['source'] == 'frozen_in_memory':
            name = parsed.name
            expected_path = '高炉前端数据/智能助手/' + ('mcp/' if name == 'bf_data_mcp_server.py' else 'backend/') + name
            require(name in manifest['files'] and path == expected_path
                and row['sha256'] == manifest['files'][name]['sha256'] and name not in frozen,
                'Frozen module source mismatch')
            frozen[name] = row['sha256']
        else:
            require(row['source'] == 'dependency_readonly_source', 'Unbound native dependency')
            dependencies[path] = row['sha256']
    require(set(frozen) == set(manifest['files']), 'Missing frozen module provenance')
    require({'高炉前端数据/智能助手/backend/assistant_pg.py',
        '高炉前端数据/智能助手/backend/qa_request_control.py',
        '高炉前端数据/智能助手/backend/qa_prompt_sources.py',
        '高炉前端数据/智能助手/backend/qa_model_readiness.py'} <= set(dependencies), 'Missing core runtime dependencies')
    pins = manifest.get('runtime_dependency_pins', {})
    require(report.get('runtime_dependency_pins') == pins
        and report.get('runtime_dependency_pin_mismatches') == []
        and all(dependencies.get(path) == digest for path, digest in pins.items()),
        'Shared runtime dependency pin mismatch or missing source provenance')
    return {'schema': 'bf.qa.native-transitive-read-scope.v1', 'candidate': manifest['candidate'],
        'manifest_sha256': report['manifest_sha256'], 'probe_sha256': probe_sha256,
        'dependency_hashes': dict(sorted(dependencies.items())),
        'required_reads': sorted(dependencies), 'production_model_identity_verified': False,
        'runtime_dependency_pins': pins,
        'production_dependency_refresh_required': True, 'deployment_authorized': False,
        'native_contracts_passed': len(CASES),
        'native_ordinary_prepare_contracts_passed': len(ORDINARY_CASES),
        'native_shared_contracts_passed': len(SHARED_CASES) if manifest.get('shared_proxy_integration') else 0,
        'native_owned_followup_contracts_passed': len(FOLLOWUP_CASES) if manifest.get('owned_followup_plan_propagated') else 0,
        'native_pending_confirmation_contracts_passed': len(CONFIRMATION_CASES) if manifest.get('pending_object_confirmation') else 0,
        'semantic_accuracy_inferred': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output-read-scope', type=Path, required=True)
    args = parser.parse_args()
    candidate, manifest = latest_frozen_candidate(ROOT)
    probe_sha = hashlib.sha256((ROOT / 'tools/qa_full_candidate_probe.py').read_bytes()).hexdigest()
    scope = validate(json.loads(args.evidence.read_bytes()), candidate, manifest, probe_sha)
    target = args.output_read_scope.resolve()
    if not target.is_relative_to(ROOT / '.codex_runtime'):
        raise ValueError('Read scope must stay in ignored private runtime directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write((json.dumps(scope, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'candidate': scope['candidate'],
        'native_contracts_passed': scope['native_contracts_passed'],
        'native_ordinary_prepare_contracts_passed': scope['native_ordinary_prepare_contracts_passed'],
        'native_shared_contracts_passed': scope['native_shared_contracts_passed'],
        'native_owned_followup_contracts_passed': scope['native_owned_followup_contracts_passed'],
        'transitive_dependencies': len(scope['required_reads']), 'production_ready_inferred': False}))

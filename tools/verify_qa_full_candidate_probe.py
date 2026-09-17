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
        'native_contracts_passed': len(CASES), 'semantic_accuracy_inferred': False}


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
        'transitive_dependencies': len(scope['required_reads']), 'production_ready_inferred': False}))

"""Reject incomplete, cross-owner, stale-window, or hidden-read release proof."""
import copy

import pytest

from test_qa_full_candidate_probe_evidence import evidence, validate


@pytest.mark.parametrize('field,value', [
    ('passed', False), ('functional_contract_passed', False),
    ('sensor_context_read_count', 1), ('sensor_context_read_count', False),
    ('sensor_context_read_kinds', ['latest_sensor_provider']),
    ('mock_model_requests', 1), ('mock_prefetch_queries', 0),
    ('mock_page_archives', 0), ('page_archive_isolated_from_evidence', False),
    ('original_user_question_preserved', False), ('current_object_source_bound', False),
    ('fresh_evidence_required', False), ('minutes', 120),
    ('selected_objects', ['P_top']), ('resolution_state', 'not_applicable'),
])
def test_bad_confirmation_proof_cannot_pass_release_gate(field, value):
    report, candidate, manifest, probe_sha = evidence()
    assert manifest.get('pending_object_confirmation')
    row = report['request_contracts']['pending_confirmation_cases'][0]
    row[field] = value
    with pytest.raises(ValueError, match='Pending confirmation'):
        validate(report, candidate, manifest, probe_sha)


@pytest.mark.parametrize('identifier,field,value', [
    ('confirmation_expired', 'mock_prefetch_queries', 1),
    ('confirmation_foreign', 'mock_prefetch_queries', 1),
    ('confirmation_expired', 'minutes', 30),
    ('confirmation_roundtrip_json', 'pending_created_by_first_handler', False),
    ('confirmation_roundtrip_sse', 'clarification_no_reads', False),
])
def test_failed_owner_or_handler_roundtrip_proof_is_rejected(identifier, field, value):
    report, candidate, manifest, probe_sha = evidence()
    next(row for row in report['request_contracts']['pending_confirmation_cases'] if row['id'] == identifier)[field] = value
    with pytest.raises(ValueError, match='Pending confirmation'):
        validate(report, candidate, manifest, probe_sha)


@pytest.mark.parametrize('duplicate', [False, True])
def test_missing_or_duplicate_confirmation_evidence_is_rejected(duplicate):
    report, candidate, manifest, probe_sha = evidence()
    rows = report['request_contracts']['pending_confirmation_cases']
    if duplicate:
        rows[-1] = copy.deepcopy(rows[0])
    else:
        rows.pop()
    with pytest.raises(ValueError, match='Complete pending confirmation'):
        validate(report, candidate, manifest, probe_sha)

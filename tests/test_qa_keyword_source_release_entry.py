"""Sealed entry gates with genuine isolated PostgreSQL identity and transactions."""
import copy
import hashlib
import json
from pathlib import Path
import platform
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import qa_keyword_source_release_entry as entry
from test_qa_keyword_source_transaction import pg_cluster, prepared, bundle, encode, current, foreign_snapshot


@pytest.fixture
def inputs(prepared, tmp_path):
    conn, plan, manifest, candidate, _, _ = prepared
    root = tmp_path / 'owned-root'
    config_file = root / entry.CONFIG_RELATIVE
    config_file.parent.mkdir(parents=True)
    config = {'env': {'GL02_PGHOST': conn.info.host, 'GL02_PGPORT': str(conn.info.port),
                      'GL02_PGDATABASE': conn.info.dbname, 'GL02_PGUSER': conn.info.user,
                      'GL02_PGPASSWORD': '', 'BF_QA_KNOWLEDGE_SEARCH_MODE': 'keyword'}}
    config_raw = encode(config)
    config_file.write_bytes(config_raw)
    conn.execute('SET LOCAL search_path=bf_assistant,bf_sensor,public')
    identity = dict(conn.execute(entry.IDENTITY_SQL).fetchone())
    conn.rollback()
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'release_plan.private.json').write_bytes(plan)
    (artifacts / 'source_scope_manifest.json').write_bytes(manifest)
    (artifacts / 'document_candidate.private.json').write_bytes(candidate)
    contract = {
        'schema': 'bf.qa.private-source-release-entry.v1', 'root_absolute': str(root),
        'hostname_sha256': entry._digest(platform.node().casefold().encode()),
        'database_identity_sha256': entry.tx.snapshot_hash(identity),
        'service_config_sha256': entry._digest(config_raw), 'action': 'publish',
        'operation_id': 'qa-source-publish-synthetic-1', 'model_name': entry.MODEL_NAME,
        'model_digest': entry.MODEL_DIGEST, 'knowledge_search_mode': 'keyword',
        'embedding_generation': False, 'plan_sha256': entry.tx.PLAN_SHA,
    }
    return root, artifacts, contract, tmp_path


def invoke(inputs, *, action=None, operation_id=None, authorized=True, changes=None):
    root, artifacts, contract, directory = inputs
    contract = copy.deepcopy(contract)
    if action:
        contract['action'] = action
    if operation_id:
        contract['operation_id'] = operation_id
    contract.update(changes or {})
    raw = encode(contract)
    path = directory / (contract['operation_id'] + '-contract.json')
    path.write_bytes(raw)
    return entry.run(root=root, artifact_dir=artifacts, contract_path=path, contract_sha=entry._digest(raw),
                     action=contract['action'], operation_id=contract['operation_id'], authorized=authorized)


def states(inputs, operation_id='qa-source-publish-synthetic-1'):
    path = inputs[0] / 'logs/qa_source_release_operations' / (operation_id + '.jsonl')
    return [json.loads(line)['state'] for line in path.read_text().splitlines()]


def test_plan_has_no_connection_secret_read_or_journal_write(inputs, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Plan attempted a connection or configuration secret read')
    monkeypatch.setattr(entry, '_connection', forbidden)
    monkeypatch.setattr(entry, '_config', forbidden)
    result = invoke(inputs, action='plan', authorized=False)
    assert result['database_connections'] == result['database_writes'] == 0
    assert not (inputs[0] / 'logs').exists()


def test_unauthorized_write_does_not_claim_an_attempt(inputs):
    with pytest.raises(entry.EntryError, match='separate_database_write_authorization_required'):
        invoke(inputs, authorized=False)
    assert not (inputs[0] / 'logs').exists()


@pytest.mark.parametrize('changes', [
    {'model_name': 'replacement-model'}, {'model_digest': '9' * 64},
    {'embedding_generation': True}, {'knowledge_search_mode': 'hybrid'},
    {'plan_sha256': '0' * 64}, {'hostname_sha256': '0' * 64},
    {'root_absolute': str(ROOT)}, {'unexpected_scope': True},
])
def test_mutated_sealed_policy_is_rejected_before_claim(inputs, changes):
    with pytest.raises(entry.EntryError):
        invoke(inputs, changes=changes)
    assert not (inputs[0] / 'logs').exists()


def test_wrong_contract_digest_cannot_read_configuration(inputs):
    root, artifacts, contract, directory = inputs
    raw = encode(contract)
    path = directory / 'contract.json'
    path.write_bytes(raw)
    with pytest.raises(entry.EntryError, match='contract_digest_mismatch'):
        entry.run(root=root, artifact_dir=artifacts, contract_path=path, contract_sha='0' * 64,
                  action='publish', operation_id=contract['operation_id'], authorized=True)
    assert not (root / 'logs').exists()


def test_genuine_identity_publish_recover_rollback_and_foreign_document_isolation(inputs, prepared):
    conn, _, _, _, before, foreign = prepared
    assert invoke(inputs)['state'] == 'applied'
    assert states(inputs) == ['claimed_no_write_yet', 'identity_verified_write_not_started',
                             'write_call_started_outcome_unverified', 'committed']
    assert foreign_snapshot(conn) == foreign
    conn.rollback()
    assert invoke(inputs, action='recover', operation_id='qa-source-recover-synthetic-1',
                  authorized=False)['state'] == 'applied_snapshot_verified'
    assert not (inputs[0] / 'logs/qa_source_release_operations/qa-source-recover-synthetic-1.jsonl').exists()
    assert invoke(inputs, action='rollback', operation_id='qa-source-rollback-synthetic-1')['state'] == 'rolled_back'
    assert current(conn) == before
    assert invoke(inputs, action='recover', operation_id='qa-source-recover-synthetic-2',
                  authorized=False)['state'] == 'rolled_back_snapshot_verified'
    assert foreign_snapshot(conn) == foreign
    conn.rollback()


def test_duplicate_operation_never_reaches_a_second_database_connection(inputs, monkeypatch):
    invoke(inputs)
    def forbidden(*args, **kwargs):
        raise AssertionError('Duplicate attempt connected')
    monkeypatch.setattr(entry, '_connection', forbidden)
    with pytest.raises(entry.EntryError, match='operation_already_claimed'):
        invoke(inputs)


def test_wrong_live_database_identity_blocks_before_any_source_write(inputs, prepared):
    before = current(prepared[0])
    with pytest.raises(entry.EntryError, match='target_database_identity_mismatch'):
        invoke(inputs, changes={'database_identity_sha256': '0' * 64})
    assert states(inputs) == ['claimed_no_write_yet', 'unresolved_or_failed']
    assert current(prepared[0]) == before


def test_configuration_drift_is_sanitized_and_preserves_source(inputs, prepared):
    path = inputs[0] / entry.CONFIG_RELATIVE
    path.write_bytes(path.read_bytes() + b' ')
    before = current(prepared[0])
    with pytest.raises(entry.EntryError, match='service_config_digest_mismatch'):
        invoke(inputs)
    assert current(prepared[0]) == before
    assert states(inputs) == ['claimed_no_write_yet', 'unresolved_or_failed']


def test_precommit_failure_is_persistent_and_same_operation_cannot_replay(inputs, prepared, monkeypatch):
    original = entry.tx._replace
    def failing(connection, snapshot):
        original(connection, snapshot)
        raise RuntimeError('synthetic credential-and-row-value')
    monkeypatch.setattr(entry.tx, '_replace', failing)
    before = current(prepared[0])
    with pytest.raises(entry.EntryError) as error:
        invoke(inputs)
    assert 'credential-and-row-value' not in str(error.value)
    assert states(inputs)[-1] == 'unresolved_or_failed'
    assert current(prepared[0]) == before
    with pytest.raises(entry.EntryError, match='already_claimed'):
        invoke(inputs)
    assert invoke(inputs, action='recover', operation_id='qa-source-recover-failed-1',
                  authorized=False)['state'] == 'not_recorded_unresolved'


@pytest.mark.parametrize('mode', ['absent', 'hybrid', None])
def test_keyword_configuration_must_be_explicit_even_with_a_matching_sealed_hash(inputs, prepared, mode):
    path = inputs[0] / entry.CONFIG_RELATIVE
    config = json.loads(path.read_bytes())
    if mode == 'absent':
        config['env'].pop('BF_QA_KNOWLEDGE_SEARCH_MODE')
    else:
        config['env']['BF_QA_KNOWLEDGE_SEARCH_MODE'] = mode
    raw = encode(config)
    path.write_bytes(raw)
    before = current(prepared[0])
    with pytest.raises(entry.EntryError, match='keyword_service_configuration_required'):
        invoke(inputs, changes={'service_config_sha256': entry._digest(raw)})
    assert current(prepared[0]) == before
    assert states(inputs) == ['claimed_no_write_yet', 'unresolved_or_failed']


def test_postcommit_receipt_failure_recovers_committed_database_without_replay(inputs, prepared, monkeypatch):
    original = entry._record
    def failing(path, value, **kwargs):
        if value['state'] == 'committed':
            raise OSError('synthetic sensitive I/O details')
        return original(path, value, **kwargs)
    monkeypatch.setattr(entry, '_record', failing)
    with pytest.raises(entry.EntryError, match='entry_failed_OSError') as error:
        invoke(inputs)
    assert 'sensitive' not in str(error.value)
    with pytest.raises(entry.EntryError, match='already_claimed'):
        invoke(inputs)
    assert invoke(inputs, action='recover', operation_id='qa-source-recover-commit-1',
                  authorized=False)['state'] == 'applied_snapshot_verified'

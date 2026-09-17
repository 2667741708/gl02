"""Source binding rejects drift/contamination without DB or model operations."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
sys.path.insert(0, str(ROOT / 'tools'))
import qa_knowledge_source_binding as binding
import prepare_qa_keyword_source_release as release


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


@pytest.fixture
def bundle(monkeypatch):
    authority = '1. 合成条款甲。\n2. 合成条款乙。'
    monkeypatch.setattr(binding, 'AUTHORITY_SHA', binding.sha(authority))
    chunks = []
    for i, (kind, text) in enumerate([('atomic', '1. 合成条款甲。'), ('atomic', '2. 合成条款乙。'), ('section', authority)]):
        chunks.append({'chunk_id': f'synthetic-{i}', 'granularity': kind, 'chapter_code': '1',
                       'chapter_title': '合成岗位', 'regulation_type': '安全操作规程',
                       'title': '合成标题', 'section_code': '', 'hierarchy_path': ['合成岗位'],
                       'source_block_start': i if i < 2 else 0, 'source_block_end': i if i < 2 else 1,
                       'content': text, 'content_hash': binding.sha(text),
                       'enriched_content': '合成岗位/安全操作规程\n' + text})
    fingerprints = [{key: chunk[key] for key in ('chunk_id', 'granularity', 'chapter_code', 'regulation_type',
                                                 'source_block_start', 'source_block_end')} for chunk in chunks]
    for row, chunk in zip(fingerprints, chunks):
        row.update(content_sha256=chunk['content_hash'], enriched_content_sha256=binding.sha(chunk['enriched_content']),
                   role_name_sha256=binding.sha(chunk['chapter_title']))
    manifest = {'schema': 'bf.qa.source-scope-manifest.v1', 'source_docx_sha256': binding.SOURCE_SHA,
                'candidate_authority_sha256': binding.AUTHORITY_SHA, 'chunk_fingerprints': fingerprints,
                'item_gate': {'verified': True, 'semantic_verified': False, 'missing_occurrences': 0,
                              'extra_occurrences': 0, 'order_matches': True, 'expected_items': 2, 'actual_items': 2},
                'chunk_gate': {'verified': True, 'semantic_verified': False, 'error_counts': {}, 'chunks': 3,
                               'atomics': 2, 'topic_completeness_verified': False}}
    manifest_raw = encode(manifest)
    monkeypatch.setattr(binding, 'MANIFEST_SHA', hashlib.sha256(manifest_raw).hexdigest())
    candidate = {'schema': 'bf.qa.private-keyword-source-candidate.v1', 'doc_id': binding.DOC_ID,
                 'version': binding.VERSION, 'content_hash': binding.AUTHORITY_SHA, 'full_text': authority,
                 'source_docx_sha256': binding.SOURCE_SHA, 'source_scope_manifest_sha256': binding.MANIFEST_SHA,
                 'knowledge_search_mode': 'keyword', 'embedding_generation': False, 'chunks': chunks}
    candidate_raw = encode(candidate)
    monkeypatch.setattr(binding, 'CANDIDATE_SHA', hashlib.sha256(candidate_raw).hexdigest())
    baseline = {'doc_id': binding.DOC_ID, 'version': release.OLD_VERSION, 'content_hash': release.OLD_AUTHORITY_SHA,
                'canonical_text_sha256': release.OLD_AUTHORITY_SHA, 'chunk_counts': dict(release.OLD_COUNTS),
                'embedding_count': sum(release.OLD_COUNTS.values())}
    return manifest_raw, candidate_raw, baseline


def test_valid_bundle_prepares_target_only_keyword_rows_and_safe_report(bundle):
    manifest, candidate, baseline = bundle
    plan, report = release.build_plan(manifest, candidate, baseline)
    assert report['source_binding_gate']['verified']
    assert len(plan['chunks']) == 3 and all(row['doc_id'] == binding.DOC_ID for row in plan['chunks'])
    assert plan['source_file_policy'] == 'preserve_current_document_and_reuse_for_chunks'
    assert 'complete_embedding_rows_with_vector_text' in plan['archive_required']
    assert plan['commit_uncertainty_policy'].endswith('never_auto_replay')
    assert plan['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert report['model_calls'] == report['database_writes'] == report['question_posts'] == 0
    assert not report['publication_executor_implemented'] and not report['rollback_snapshot_saved']
    assert '合成条款' not in json.dumps(report, ensure_ascii=False)
    document = dict(plan['document_update'], source_file='controlled-source-reference')
    rows = [dict(row, source_file=document['source_file']) for row in plan['chunks']]
    assert binding.verify_database_source(manifest, candidate, document, list(reversed(rows)))['verified']
    assert report['source_binding_gate']['database_snapshot_verified'] is False


@pytest.mark.parametrize('raw', [b'', b'{}', b'changed', 'not-bytes'])
def test_manifest_digest_or_type_drift_rejected(raw):
    with pytest.raises(binding.SourceBindingError):
        binding.load_manifest(raw)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'extra', 'owner', 'kind', 'content', 'metadata', 'stored_hash'])
def test_database_chunk_changes_cannot_be_verified(bundle, change):
    manifest, candidate, baseline = bundle
    plan, _ = release.build_plan(manifest, candidate, baseline)
    rows = copy.deepcopy(plan['chunks'])
    if change == 'missing':
        rows.pop()
    elif change == 'duplicate':
        rows.append(copy.deepcopy(rows[0]))
    elif change == 'extra':
        rows.append(dict(rows[0], chunk_id='foreign-source'))
    else:
        field = {'owner': 'doc_id', 'kind': 'chunk_type', 'content': 'content',
                 'metadata': 'enriched_content', 'stored_hash': 'content_hash'}[change]
        rows[0][field] = 'changed'
    with pytest.raises(binding.SourceBindingError):
        binding.verify_prepared_source(manifest, candidate, plan['document_update'], rows)


@pytest.mark.parametrize('field', ['doc_id', 'version', 'content_hash', 'full_text'])
def test_database_document_identity_changes_are_rejected(bundle, field):
    manifest, candidate, baseline = bundle
    plan, _ = release.build_plan(manifest, candidate, baseline)
    document = dict(plan['document_update'], **{field: 'changed'})
    with pytest.raises(binding.SourceBindingError):
        binding.verify_prepared_source(manifest, candidate, document, plan['chunks'])


@pytest.mark.parametrize('field', ['parent_chunk_id', 'title', 'summary', 'keywords_json', 'entities_json',
                                 'phenomenon_json', 'parameter_names_json', 'token_count', 'knowledge_category',
                                 'task_scope_json', 'authority_level', 'source_priority', 'search_text'])
def test_retrieval_metadata_is_bound_to_frozen_candidate(bundle, field):
    manifest, candidate, baseline = bundle
    plan, _ = release.build_plan(manifest, candidate, baseline)
    rows = copy.deepcopy(plan['chunks'])
    rows[0][field] = 'changed'
    with pytest.raises(binding.SourceBindingError, match='retrieval metadata'):
        binding.verify_prepared_source(manifest, candidate, plan['document_update'], rows)


@pytest.mark.parametrize('field', ['chapter_code', 'chapter_title', 'regulation_type', 'source_block_start', 'source_block_end'])
def test_optional_parsed_source_metadata_cannot_override_manifest(bundle, field):
    manifest, candidate, baseline = bundle
    plan, _ = release.build_plan(manifest, candidate, baseline)
    rows = copy.deepcopy(plan['chunks'])
    rows[0][field] = 'changed'
    with pytest.raises(binding.SourceBindingError, match='Parsed database source'):
        binding.verify_prepared_source(manifest, candidate, plan['document_update'], rows)


@pytest.mark.parametrize('change', ['missing', 'empty', 'foreign_chunk'])
def test_real_database_snapshot_requires_shared_document_source_path(bundle, change):
    manifest, candidate, baseline = bundle
    plan, _ = release.build_plan(manifest, candidate, baseline)
    document = dict(plan['document_update'], source_file='controlled-source-reference')
    rows = [dict(row, source_file=document['source_file']) for row in plan['chunks']]
    if change == 'missing':
        document.pop('source_file')
    elif change == 'empty':
        document['source_file'] = ''
    else:
        rows[0]['source_file'] = 'foreign-source-reference'
    with pytest.raises(binding.SourceBindingError, match='source path'):
        binding.verify_database_source(manifest, candidate, document, rows)


@pytest.mark.parametrize('field', ['doc_id', 'version', 'content_hash', 'canonical_text_sha256', 'chunk_counts', 'embedding_count'])
def test_live_baseline_drift_blocks_release_preparation(bundle, field):
    manifest, candidate, baseline = bundle
    changed = dict(baseline, **{field: True if field == 'embedding_count' else 'changed'})
    with pytest.raises(ValueError, match='baseline changed'):
        release.build_plan(manifest, candidate, changed)


def test_relabelled_or_changed_candidate_bytes_rejected(bundle):
    manifest, candidate, _ = bundle
    with pytest.raises(binding.SourceBindingError, match='digest mismatch'):
        binding.load_candidate(candidate.replace(b'keyword', b'hybrid'), manifest)


def test_untrusted_parsed_manifest_is_not_accepted(bundle):
    manifest, candidate, _ = bundle
    with pytest.raises(binding.SourceBindingError, match='immutable source bytes'):
        binding.load_candidate(candidate, json.loads(manifest))


def test_duplicate_json_key_rejected_even_in_resealed_fixture(monkeypatch):
    raw = b'{"same":1,"same":2}'
    monkeypatch.setattr(binding, 'MANIFEST_SHA', hashlib.sha256(raw).hexdigest())
    with pytest.raises(binding.SourceBindingError, match='Duplicate source JSON'):
        binding.load_manifest(raw)


@pytest.mark.parametrize('place', ['public', 'root', 'existing'])
def test_release_plan_output_cannot_be_public_or_reused(tmp_path, monkeypatch, place):
    monkeypatch.setattr(release, 'ROOT', tmp_path)
    root = tmp_path / '.codex_runtime/qa-source-scope-20260917'
    target = tmp_path / 'public' if place == 'public' else root if place == 'root' else root / 'existing'
    if place == 'existing':
        target.mkdir(parents=True)
    monkeypatch.setattr(release.subprocess, 'run', lambda *a, **k: pytest.fail('Reject path before Git'))
    with pytest.raises(ValueError, match='unused private'):
        release.private_output(target)


def test_nonignored_release_output_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(release, 'ROOT', tmp_path)
    monkeypatch.setattr(release.subprocess, 'run', lambda *a, **k: type('Result', (), {'returncode': 1})())
    with pytest.raises(ValueError, match='Git ignored'):
        release.private_output(tmp_path / '.codex_runtime/qa-source-scope-20260917/new')

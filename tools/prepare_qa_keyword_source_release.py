"""Prepare a sealed private keyword source plan; never connects or publishes to a DB."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_knowledge_source_binding as binding

OLD_AUTHORITY_SHA = '96fdc3f9ec0a39c226667247ef16295bfa9707e56438c162a7958db96a127b6e'
OLD_VERSION = 'v1.0-hierarchical'
OLD_COUNTS = {'three_rules_atomic': 4540, 'three_rules_topic': 805, 'three_rules_section': 109}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def build_plan(manifest_bytes, candidate_bytes, baseline):
    manifest = binding.load_manifest(manifest_bytes)
    candidate = binding.load_candidate(candidate_bytes, manifest_bytes)
    if (not isinstance(baseline, dict) or baseline.get('doc_id') != binding.DOC_ID
            or baseline.get('version') != OLD_VERSION or baseline.get('content_hash') != OLD_AUTHORITY_SHA
            or baseline.get('canonical_text_sha256') != OLD_AUTHORITY_SHA
            or baseline.get('chunk_counts') != OLD_COUNTS
            or type(baseline.get('embedding_count')) is not int or baseline.get('embedding_count') != sum(OLD_COUNTS.values())):
        raise ValueError('Observed production baseline changed; prepare again after readonly review')
    rows = binding.keyword_rows(candidate)
    document = {key: candidate[key] for key in ('doc_id', 'version', 'full_text', 'content_hash')}
    gate = binding.verify_prepared_source(manifest_bytes, candidate_bytes, document, rows)
    plan = {'schema': 'bf.qa.private-keyword-release-plan.v1', 'requirement_id': 'REQ-QA-KEYWORD-SOURCE-RELEASE-20260917',
            'release_id': 'qa-source-keyword-20260917-r2', 'doc_id': binding.DOC_ID,
            'expected_before': baseline, 'document_update': document, 'chunks': rows,
            'manifest_text': manifest_bytes.decode('utf-8'), 'manifest_sha256': binding.MANIFEST_SHA,
            'source_file_policy': 'preserve_current_document_and_reuse_for_chunks',
            'created_at_policy': 'preserve_document_created_at_stamp_new_chunks_at_apply',
            'archive_required': ['complete_document_row', 'complete_chunk_rows_including_search_text',
                                 'complete_embedding_rows_with_vector_text', 'previous_source_binding'],
            'transaction_required': ['nonblocking_doc_advisory_lock', 'lock_document_chunks_embeddings_binding',
                                     'recheck_baseline_and_chunk_id_collisions', 'archive_before_snapshot_in_database',
                                     'update_target_document_without_delete', 'replace_only_target_chunks_and_embeddings',
                                     'persist_source_binding', 'verify_full_after_snapshot_then_commit'],
            'rollback_required': ['matching_release_and_exact_after_snapshot', 'restore_document_chunks_embeddings_and_binding',
                                  'verify_exact_before_snapshot'],
            'commit_uncertainty_policy': 'readonly_recover_exact_release_id_never_auto_replay',
            'required_migration': 'schema/20260917_qa_keyword_source_release.sql',
            'knowledge_search_mode': 'keyword', 'embedding_generation': False,
            'model_name': 'chiqiongblastfuenace:latest',
            'model_digest': 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'}
    report = {'schema': 'bf.qa.keyword-source-release-preparation.v1', 'requirement_id': plan['requirement_id'],
              'release_id': plan['release_id'], 'doc_id': binding.DOC_ID,
              'expected_before': baseline, 'manifest_sha256': binding.MANIFEST_SHA,
              'candidate_sha256': binding.CANDIDATE_SHA, 'authority_sha256': binding.AUTHORITY_SHA,
              'chunk_counts': dict(Counter(row['chunk_type'] for row in rows)), 'source_binding_gate': gate,
              'plan_sha256': hashlib.sha256(encode(plan)).hexdigest(),
              'publication_executor_implemented': False, 'rollback_snapshot_saved': False,
              'migration_applied': False, 'production_applied': False,
              'model_calls': 0, 'database_writes': 0, 'question_posts': 0,
              'semantic_verified': False, 'embedding_generation': False}
    return plan, report


def private_output(target):
    target = target.resolve()
    private_root = (ROOT / '.codex_runtime/qa-source-scope-20260917').resolve()
    if not target.is_relative_to(private_root) or target == private_root or target.exists():
        raise ValueError('Only an unused private source release directory is allowed')
    result = subprocess.run(['git', 'check-ignore', '--stdin'], input=str((target / 'release_plan.private.json').relative_to(ROOT)) + '\n',
                            capture_output=True, text=True, cwd=ROOT, timeout=10)
    if result.returncode != 0:
        raise ValueError('Source release output must be Git ignored')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-dir', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = private_output(args.output)
    if args.baseline.stat().st_size > 10000:
        raise ValueError('Bounded sanitized baseline metadata required')
    baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
    def bounded(name):
        path = args.candidate_dir / name
        if path.stat().st_size > binding.MAX_BYTES:
            raise ValueError('Source artifact size exceeds bound')
        return path.read_bytes()
    plan, report = build_plan(bounded('source_scope_manifest.json'), bounded('document_candidate.private.json'), baseline)
    output.mkdir(parents=True)
    for name, value in [('release_plan.private.json', plan), ('sanitized_report.json', report)]:
        with (output / name).open('xb') as handle:
            handle.write(encode(value))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Append a public triage supplement without changing frozen first-run judgments."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tests/qa_regression'
MAPPING = {
    'TPL-254A275F94B2E4D5': (['QAOPT-E02', 'QAOPT-E03', 'QAOPT-E05'], 'latest_unit_and_collection_provenance',
        'V32 preserves verified values and explicit missing fields; unregistered temperature unit still requires authoritative metadata.'),
    'TPL-4F3E4DA366EA5176': (['QAOPT-R03', 'QAOPT-E01', 'QAOPT-E02', 'QAOPT-E05'], 'directory_without_joint_observations',
        'Resolve both objects and obtain aligned actual sequences; directory data cannot satisfy joint analysis.'),
    'TPL-AC03EBFC7B6DE0C9': (['QAOPT-O02', 'QAOPT-E01', 'QAOPT-E02', 'QAOPT-E05'], 'joint_analysis_timeout_and_prior_evidence_gap',
        'Preserve only verified prior facts, disclose missing DP evidence, and measure the source timeout without replays.'),
    'TPL-BD6C66D1AE3A2397': (['QAOPT-K01', 'QAOPT-K03', 'QAOPT-E05'], 'incomplete_authoritative_clause',
        'Retrieve complete authoritative section with ordered coverage; missing text cannot be filled from general knowledge.'),
    'TPL-0138CEF2A2BA93B3': (['QAOPT-K01', 'QAOPT-K03', 'QAOPT-O02', 'QAOPT-E05'], 'incomplete_chapter_and_history_timeout',
        'Use the authoritative chapter rather than conversation history; disclose gaps and retain the original timeout evidence.'),
    **{case: (['QAOPT-K01', 'QAOPT-K03', 'QAOPT-E05'], 'enterprise_original_missing',
        'Obtain complete approved enterprise original; distinguish generic principles and keep partial until full coverage is verified.')
        for case in ('TPL-DF40C86F676DD002', 'TPL-1AB4BD6D5D30DFFA', 'TPL-B2385F77F4DDF9B9', 'TPL-5FCE8B443C84E4A8')},
}


def main():
    source = OUT / 'initial_semantic_summary_20260917.json'
    raw = source.read_bytes()
    summary = json.loads(raw)
    rows = summary['rows']
    counts = Counter(row['status'] for row in rows)
    if len(rows) != 1233 or counts != Counter({'passed':269, 'partial':186, 'failed':636,
        'oracle_blocked':89, 'insufficient_evidence':53}):
        raise ValueError('Frozen original denominator changed')
    missing = [row for row in rows if row['status'] in ('failed', 'partial') and not row['issue_ids']]
    if {row['case_id'] for row in missing} != set(MAPPING) or len(missing) != 9:
        raise ValueError('Unmapped set changed; independent review required')
    catalog = OUT / 'optimization_issue_catalog_20260916.json'
    catalog_raw = catalog.read_bytes()
    catalog_ids = {row['id'] for row in json.loads(catalog_raw)['issues']}
    supplement = []
    for row in missing:
        ids, reason, gate = MAPPING[row['case_id']]
        if not set(ids) <= catalog_ids or row['case_id'] == 'TPL-10C8C8FAF2C694EF':
            raise ValueError('Unknown issue or forbidden replay case')
        supplement.append({key: row[key] for key in ('case_id', 'status', 'category', 'source_path', 'source_line',
            'original_result_sha256', 'original_prompt_sha256')})
        supplement[-1].update(prior_issue_ids=[], proposed_issue_ids=ids, reason_code=reason,
            acceptance_gate=gate, root_cause_confirmed=False, state='triaged_repair_or_acceptance_open')
    output = {'schema': 'bf.qa.unmapped-triage-supplement.v1',
        'requirement_id': 'REQ-QA-UNMAPPED-TRIAGE-20260917', 'checked_at': '2026-09-17',
        'source_sha256': hashlib.sha256(raw).hexdigest(), 'catalog_sha256': hashlib.sha256(catalog_raw).hexdigest(),
        'classification_basis': 'frozen final-review reasons and existing issue catalog',
        'original_judgments_unchanged': True, 'frozen_unmapped_cases': 9, 'supplemental_triage_cases': 9,
        'category_counts': dict(Counter(row['category'] for row in missing)),
        'status_counts': dict(Counter(row['status'] for row in missing)),
        'unmapped_after_applying_proposed_supplement': 0, 'confirmed_root_causes_or_closed_cases': 0,
        'real_requests': 0, 'sent_unknown_never_replay': ['TPL-10C8C8FAF2C694EF'], 'rows': supplement}
    target = OUT / 'unmapped_triage_supplement_20260917.json'
    if target.exists():
        raise ValueError('Frozen triage supplement exists; no overwrite')
    if source.read_bytes() != raw or catalog.read_bytes() != catalog_raw:
        raise ValueError('Evidence changed during triage')
    target.write_bytes((json.dumps(output, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'triaged': 9, 'closed': 0, 'requests': 0, 'original_evidence_unchanged': True}))


if __name__ == '__main__':
    main()

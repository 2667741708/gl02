"""Freeze a source-only keyword KB candidate in ignored local storage; no DB/model calls."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess

from docx import Document
import build_three_rules_hierarchical_kb as builder
from qa_source_scope_contract import extract_scope, validate_items, validate_chunks, digest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = 'c5f5578616ebfe7bbbfcc10a7710281c3c4e511361572addc47de56e95a8a541'
OLD_AUTHORITY_SHA = '96fdc3f9ec0a39c226667247ef16295bfa9707e56438c162a7958db96a127b6e'
NEW_AUTHORITY_SHA = 'fbf5835be19c6a3dbd8c21489529ed2dd219c3ede634d5729e65d1396f1cb092'


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def private_target(value):
    target = value.resolve()
    private_root = (ROOT / '.codex_runtime/qa-source-scope-20260917').resolve()
    if not target.is_relative_to(private_root) or target == private_root or target.exists():
        raise ValueError('New candidate requires an unused private source-scope directory')
    relative = (target / 'document_candidate.private.json').relative_to(ROOT).as_posix()
    result = subprocess.run(['git', 'check-ignore', '--stdin'], input=relative + '\n', text=True,
                            capture_output=True, cwd=ROOT, timeout=10)
    if result.returncode != 0:
        raise ValueError('Original source candidate must be Git ignored')
    return target


def prepare(document, source_sha):
    if source_sha != SOURCE_SHA:
        raise ValueError('Frozen original DOCX identity changed')
    source_contents = []
    scope = extract_scope(document, builder.REGULATION_HEADING_ALIASES, builder.CHAPTER_HEADING_ALIASES,
                          content_sink=source_contents.append)
    chapters, items = builder.parse_source_items(document)
    item_gate = validate_items(scope, items)
    if not item_gate['verified']:
        raise ValueError('Independent source items failed; no candidate frozen')
    chunks = builder.build_chunks(items)
    chunk_gate = validate_chunks(scope, chunks, source_contents)
    if not chunk_gate['verified']:
        raise ValueError('Independent source chunks failed; no candidate frozen')
    authority = '\n'.join(source_contents)
    if digest(authority) != NEW_AUTHORITY_SHA:
        raise ValueError('Reviewed source authority changed; no candidate frozen')
    fingerprints = [{'chunk_id': chunk.chunk_id, 'granularity': chunk.granularity,
                     'chapter_code': chunk.chapter_code, 'role_name_sha256': digest(chunk.chapter_title),
                     'regulation_type': chunk.regulation_type, 'content_sha256': chunk.content_hash,
                     'enriched_content_sha256': digest(chunk.enriched_content),
                     'source_block_start': chunk.source_block_start, 'source_block_end': chunk.source_block_end}
                    for chunk in chunks]
    manifest = {'schema': 'bf.qa.source-scope-manifest.v1', 'requirement_id': 'REQ-QA-SOURCE-SCOPE-20260917',
                'source_docx_sha256': source_sha, 'legacy_authority_sha256': OLD_AUTHORITY_SHA,
                'candidate_authority_sha256': NEW_AUTHORITY_SHA, 'source_scope': scope,
                'item_gate': item_gate, 'chunk_gate': chunk_gate, 'chunk_fingerprints': fingerprints,
                'semantic_review_required': True, 'production_applied': False}
    candidate = {'schema': 'bf.qa.private-keyword-source-candidate.v1', 'doc_id': builder.DOC_ID,
                 'title': builder.DOC_TITLE, 'version': 'v2.0-source-scope-20260917', 'authority_level': 'knowledge_doc',
                 'expected_current_authority_sha256': OLD_AUTHORITY_SHA, 'content_hash': NEW_AUTHORITY_SHA,
                 'full_text': authority, 'source_docx_sha256': source_sha, 'knowledge_search_mode': 'keyword',
                 'embedding_generation': False, 'chunks': [asdict(chunk) for chunk in chunks],
                 'source_scope_manifest_sha256': hashlib.sha256(encode(manifest)).hexdigest()}
    report = {'schema': 'bf.qa.source-scope-candidate-report.v1', 'requirement_id': 'REQ-QA-SOURCE-SCOPE-20260917',
              'source_docx_sha256': source_sha, 'legacy_authority_sha256': OLD_AUTHORITY_SHA,
              'candidate_authority_sha256': NEW_AUTHORITY_SHA, 'chapters': len(chapters),
              'source_items': len(items), 'scope_groups': len({(item.chapter_code, item.regulation_type) for item in items}),
              'chunk_counts': dict(Counter(chunk.granularity for chunk in chunks)),
              'item_gate': item_gate, 'chunk_gate': chunk_gate, 'semantic_passed': 0,
              'model_name': 'chiqiongblastfuenace:latest',
              'model_digest': 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124',
              'model_calls': 0, 'embedding_generation': False, 'database_writes': 0, 'question_posts': 0,
              'production_applied': False, 'privacy': 'Report contains hashes and counts only; original source candidate is Git ignored.'}
    return manifest, candidate, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docx', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    target = private_target(args.output)
    if not args.docx.is_file() or args.docx.stat().st_size > 25000000:
        raise ValueError('Bounded original DOCX is required')
    raw = args.docx.read_bytes()
    manifest, candidate, report = prepare(Document(BytesIO(raw)), hashlib.sha256(raw).hexdigest())
    files = {'source_scope_manifest.json': encode(manifest), 'document_candidate.private.json': encode(candidate)}
    report['artifact_sha256'] = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    report['generator_sha256'] = {name: hashlib.sha256((ROOT / 'tools' / name).read_bytes()).hexdigest()
                                for name in ('freeze_qa_source_scope_candidate.py', 'qa_source_scope_contract.py', 'build_three_rules_hierarchical_kb.py')}
    files['sanitized_report.json'] = encode(report)
    target.mkdir(parents=True)
    for name, value in files.items():
        with (target / name).open('xb') as handle:
            handle.write(value)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

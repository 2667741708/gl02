"""Pure source-manifest binding gates; no connection, model or mutation capabilities."""
from __future__ import annotations

from collections import Counter
import hashlib
import json

DOC_ID = 'bf_three_rules_two_systems_20260712'
VERSION = 'v2.0-source-scope-20260917'
SOURCE_SHA = 'c5f5578616ebfe7bbbfcc10a7710281c3c4e511361572addc47de56e95a8a541'
AUTHORITY_SHA = 'fbf5835be19c6a3dbd8c21489529ed2dd219c3ede634d5729e65d1396f1cb092'
MANIFEST_SHA = 'e3a0a9b1baffd386800bcbd2795338f16dadd40a859dabd4ad4a5ad5c29dc331'
CANDIDATE_SHA = '95fa4525c35054f20adacf758d52ef7c3de0cecd98a270e30a66d7ce006d8f7c'
MAX_BYTES = 25000000


class SourceBindingError(ValueError):
    """A source identity/binding failed; text must not be marked verified."""


def sha(text):
    if not isinstance(text, str):
        raise SourceBindingError('Source text type invalid')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _decode(raw, expected):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise SourceBindingError('Bounded immutable source bytes required')
    if hashlib.sha256(raw).hexdigest() != expected:
        raise SourceBindingError('Frozen source artifact digest mismatch')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SourceBindingError('Duplicate source JSON field')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                           parse_constant=lambda token: (_ for _ in ()).throw(SourceBindingError('Nonfinite source JSON')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SourceBindingError('Invalid source artifact encoding') from exc
    if not isinstance(value, dict):
        raise SourceBindingError('Source artifact must be an object')
    return value


def load_manifest(raw):
    manifest = _decode(raw, MANIFEST_SHA)
    if (manifest.get('schema') != 'bf.qa.source-scope-manifest.v1'
            or manifest.get('source_docx_sha256') != SOURCE_SHA
            or manifest.get('candidate_authority_sha256') != AUTHORITY_SHA):
        raise SourceBindingError('Original source authority identity mismatch')
    for name in ('item_gate', 'chunk_gate'):
        gate = manifest.get(name)
        if not isinstance(gate, dict) or gate.get('verified') is not True or gate.get('semantic_verified') is not False:
            raise SourceBindingError('Independent source gate missing')
    item_gate, chunk_gate = manifest['item_gate'], manifest['chunk_gate']
    if (item_gate.get('missing_occurrences') != 0 or item_gate.get('extra_occurrences') != 0
            or item_gate.get('order_matches') is not True or chunk_gate.get('error_counts') != {}
            or chunk_gate.get('topic_completeness_verified') is not False):
        raise SourceBindingError('Independent source coverage inconsistent')
    fingerprints = manifest.get('chunk_fingerprints')
    if not isinstance(fingerprints, list) or not fingerprints or len(fingerprints) > 10000:
        raise SourceBindingError('Bounded source chunk fingerprints required')
    seen, counts = set(), Counter()
    for row in fingerprints:
        if not isinstance(row, dict) or row.get('granularity') not in ('atomic', 'topic', 'section'):
            raise SourceBindingError('Source fingerprint kind invalid')
        chunk_id = row.get('chunk_id')
        if not isinstance(chunk_id, str) or not chunk_id or chunk_id in seen:
            raise SourceBindingError('Source fingerprint ID invalid')
        seen.add(chunk_id)
        counts[row['granularity']] += 1
        for name in ('content_sha256', 'enriched_content_sha256', 'role_name_sha256'):
            value = row.get(name)
            if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise SourceBindingError('Source fingerprint digest invalid')
        start, end = row.get('source_block_start'), row.get('source_block_end')
        if type(start) is not int or type(end) is not int or start < 0 or end < start:
            raise SourceBindingError('Source position invalid')
    if (chunk_gate.get('chunks') != len(fingerprints) or chunk_gate.get('atomics') != counts['atomic']
            or item_gate.get('expected_items') != counts['atomic'] or item_gate.get('actual_items') != counts['atomic']):
        raise SourceBindingError('Source fingerprint counts inconsistent')
    return manifest


def _chunk_gate(manifest, rows, *, database):
    if not isinstance(rows, list) or len(rows) > 10000:
        raise SourceBindingError('Bounded source chunk rows required')
    expected = manifest['chunk_fingerprints']
    actual = {}
    for row in rows:
        if not isinstance(row, dict):
            raise SourceBindingError('Source chunk row type invalid')
        chunk_id = row.get('chunk_id')
        if not isinstance(chunk_id, str) or chunk_id in actual:
            raise SourceBindingError('Duplicate or invalid source chunk row')
        actual[chunk_id] = row
    if set(actual) != {row['chunk_id'] for row in expected}:
        raise SourceBindingError('Source chunk set incomplete or contaminated')
    atomics = []
    for fingerprint in expected:
        row = actual[fingerprint['chunk_id']]
        if database:
            if row.get('doc_id') != DOC_ID or row.get('chunk_type') != 'three_rules_' + fingerprint['granularity']:
                raise SourceBindingError('Database source ownership or kind mismatch')
        elif (row.get('granularity') != fingerprint['granularity']
              or row.get('chapter_code') != fingerprint['chapter_code']
              or row.get('regulation_type') != fingerprint['regulation_type']
              or sha(row.get('chapter_title')) != fingerprint['role_name_sha256']
              or row.get('source_block_start') != fingerprint['source_block_start']
              or row.get('source_block_end') != fingerprint['source_block_end']):
            raise SourceBindingError('Candidate source scope mismatch')
        if (sha(row.get('content')) != fingerprint['content_sha256']
                or row.get('content_hash') != fingerprint['content_sha256']
                or sha(row.get('enriched_content')) != fingerprint['enriched_content_sha256']):
            raise SourceBindingError('Source chunk content or metadata digest mismatch')
        if fingerprint['granularity'] == 'atomic':
            atomics.append(row['content'])
    if sha('\n'.join(atomics)) != AUTHORITY_SHA:
        raise SourceBindingError('Ordered source atomic authority mismatch')
    return {'verified': True, 'chunks': len(rows), 'atomics': len(atomics),
            'topic_completeness_verified': False, 'semantic_verified': False}


def load_candidate(raw, manifest_bytes):
    manifest = load_manifest(manifest_bytes)
    candidate = _decode(raw, CANDIDATE_SHA)
    if (candidate.get('schema') != 'bf.qa.private-keyword-source-candidate.v1'
            or candidate.get('doc_id') != DOC_ID or candidate.get('version') != VERSION
            or candidate.get('content_hash') != AUTHORITY_SHA
            or candidate.get('source_docx_sha256') != SOURCE_SHA
            or candidate.get('source_scope_manifest_sha256') != MANIFEST_SHA
            or candidate.get('knowledge_search_mode') != 'keyword'
            or candidate.get('embedding_generation') is not False
            or sha(candidate.get('full_text')) != AUTHORITY_SHA):
        raise SourceBindingError('Frozen keyword candidate contract mismatch')
    _chunk_gate(manifest, candidate.get('chunks'), database=False)
    return candidate


def keyword_rows(candidate):
    """Deterministic projection onto actual RAG columns; path/timestamps added at apply."""
    rows = []
    for chunk in candidate['chunks']:
        keywords = list(dict.fromkeys([chunk['chapter_title'], chunk['regulation_type'],
                                      chunk['section_code'], chunk['granularity'], *chunk['hierarchy_path']]))
        keywords_json = json.dumps(keywords, ensure_ascii=False)
        rows.append({'chunk_id': chunk['chunk_id'], 'doc_id': DOC_ID,
                     'parent_chunk_id': chunk.get('parent_chunk_id'), 'title': chunk['title'],
                     'content': chunk['content'], 'enriched_content': chunk['enriched_content'],
                     'summary': chunk['title'][:300], 'keywords_json': keywords_json,
                     'entities_json': json.dumps([chunk['chapter_title'], chunk['regulation_type']], ensure_ascii=False),
                     'phenomenon_json': '[]', 'parameter_names_json': '[]',
                     'chunk_type': 'three_rules_' + chunk['granularity'], 'token_count': len(chunk['content']),
                     'knowledge_category': '三规二制',
                     'task_scope_json': json.dumps(['process_qa', 'case_analysis', 'condition_diagnosis']),
                     'authority_level': 'knowledge_doc',
                     'source_priority': {'atomic': 110, 'topic': 105, 'section': 95}[chunk['granularity']],
                     'content_hash': chunk['content_hash'],
                     'search_text': '\n'.join([chunk['title'], chunk['content'], chunk['enriched_content'], keywords_json])})
    return rows


def _verify_snapshot(manifest_bytes, candidate_bytes, document, chunks):
    manifest = load_manifest(manifest_bytes)
    candidate = load_candidate(candidate_bytes, manifest_bytes)
    if (not isinstance(document, dict) or document.get('doc_id') != DOC_ID
            or document.get('version') != VERSION or document.get('content_hash') != AUTHORITY_SHA
            or sha(document.get('full_text')) != AUTHORITY_SHA):
        raise SourceBindingError('Database source document identity mismatch')
    gate = _chunk_gate(manifest, chunks, database=True)
    expected = {row['chunk_id']: row for row in keyword_rows(candidate)}
    source = {row['chunk_id']: row for row in candidate['chunks']}
    for row in chunks:
        for key, value in expected[row['chunk_id']].items():
            if key not in row or row[key] != value or type(row[key]) is not type(value):
                raise SourceBindingError('Database retrieval metadata mismatch')
        # These are not physical rag_chunk columns. If a caller supplies parsed
        # source metadata, do not allow it to contradict the signed source map.
        for key in ('chapter_code', 'chapter_title', 'regulation_type', 'source_block_start', 'source_block_end'):
            if key in row and (row[key] != source[row['chunk_id']][key]
                               or type(row[key]) is not type(source[row['chunk_id']][key])):
                raise SourceBindingError('Parsed database source metadata mismatch')
    return gate


def verify_prepared_source(manifest_bytes, candidate_bytes, document, chunks):
    """Check private planned rows; this is not a database publication acceptance."""
    gate = _verify_snapshot(manifest_bytes, candidate_bytes, document, chunks)
    return dict(gate, database_snapshot_verified=False)


def verify_database_source(manifest_bytes, candidate_bytes, document, chunks):
    """Check complete rows fetched from one consistent DB snapshot.

    Source content and all deterministic retrieval metadata are signed by the
    fixed candidate. This does not prove relevance or prescription correctness.
    """
    gate = _verify_snapshot(manifest_bytes, candidate_bytes, document, chunks)
    path = document.get('source_file')
    if not isinstance(path, str) or not path:
        raise SourceBindingError('Database source path policy missing')
    if any(row.get('source_file') != path for row in chunks):
        raise SourceBindingError('Database source path binding mismatch')
    return dict(gate, database_snapshot_verified=True)

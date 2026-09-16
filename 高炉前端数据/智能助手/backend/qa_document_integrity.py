"""Independent authority membership and source-line coverage for original indexes.

QAOPT-K03/K06. This proves original text membership and missing-tail coverage;
it does not infer semantic correctness, role binding, or completeness from part IDs.
"""
from functools import lru_cache
import hashlib
import re

VERSION = 'qa-document-integrity-v1'
MAX_CHUNKS = 15000
MAX_SOURCE_CHARS = 2000000

def compact(text):
    return re.sub(r'\s+', '', str(text or ''))

def inspect(full_text, chunks):
    if not isinstance(full_text, str) or not compact(full_text) or len(full_text) > MAX_SOURCE_CHARS:
        return {'verified': False, 'reason': 'authority_text_bounds'}
    if not chunks or len(chunks) > MAX_CHUNKS:
        return {'verified': False, 'reason': 'original_index_bounds'}
    # Include content, hash, authority and type in the cache key. A document
    # hash alone would hide an index deletion or mutation at the same version.
    key = tuple((str(row.get('chunk_type') or ''), str(row.get('content') or ''),
                 str(row.get('content_hash') or '').lower(), str(row.get('authority_level') or ''))
                for row in chunks)
    return dict(_inspect(full_text, key))

@lru_cache(maxsize=4)
def _inspect(full_text, chunks):
    source = compact(full_text)
    covered_lines, texts = set(), []
    kinds = {'three_rules_atomic', 'three_rules_section', 'three_rules_topic'}
    for kind, text, digest, authority in chunks:
        canonical = text.replace('\r\n', '\n').replace('\r', '\n')
        if (kind not in kinds or authority != 'knowledge_doc' or not compact(text)
            or digest not in {hashlib.sha256(text.encode('utf-8')).hexdigest(), hashlib.sha256(canonical.encode('utf-8')).hexdigest()}):
            return {'verified': False, 'reason': 'original_index_integrity'}
        normalized = compact(text)
        lines = [compact(line) for line in canonical.splitlines() if compact(line)]
        if kind == 'three_rules_atomic':
            if normalized not in source:
                return {'verified': False, 'reason': 'atomic_text_outside_authority'}
        else:
            # Reviewed aggregates omit intervening headings. Verify their
            # original lines in source order without requiring contiguity.
            offset = 0
            for line in lines:
                position = source.find(line, offset)
                if position < 0:
                    return {'verified': False, 'reason': 'aggregate_text_outside_authority'}
                offset = position + len(line)
        covered_lines.update(lines)
        texts.append(normalized)
    source_lines = [compact(line) for line in full_text.splitlines() if compact(line)]
    joined = '\n'.join(texts)  # separator prevents cross-chunk false matches
    missing = sum(line not in covered_lines and line not in joined for line in source_lines)
    return {'verified': missing == 0, 'reason': 'verified_authority_line_coverage' if not missing else 'authority_index_missing_lines',
            'source_nonempty_lines': len(source_lines), 'missing_source_lines': missing,
            'indexed_chunks': len(chunks), 'source_sha256': hashlib.sha256(full_text.encode('utf-8')).hexdigest(),
            'canonical_source_sha256': hashlib.sha256(full_text.replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')).hexdigest(),
            'scope': 'whitespace-normalized original membership and source-line coverage; semantic and role checks remain separate'}


def inspect_selected_scope(selected, indexed):
    """Detect an aggregate page omitting originals retained in another index.

    Call only after inspect() validates source membership and global coverage.
    This checks cross-index consistency within the selected role/regulation;
    it does not independently authenticate the scope metadata itself.
    """
    scopes = {}
    for row in selected:
        key = (str(row['chapter']), str(row['regulation']))
        scopes.setdefault(key, []).append(compact(row['content']))
    texts = {key: '\n'.join(parts) for key, parts in scopes.items()}
    checked, missing = 0, 0
    for row in indexed:
        if row.get('chunk_type') not in {'three_rules_atomic', 'three_rules_topic'}:
            continue
        header = str(row.get('enriched_content') or '')
        role = re.search(r'^【岗位/制度】\d+\.\s*(.+)$', header, re.M)
        regulation = re.search(r'^【规程类型】(.+)$', header, re.M)
        if not role or not regulation:
            return {'verified': False, 'reason': 'original_scope_metadata_unverified'}
        key = (role.group(1).strip(), regulation.group(1).strip())
        if key not in texts:
            continue
        for line in str(row.get('content') or '').splitlines():
            normalized = compact(line)
            if normalized:
                checked += 1
                missing += normalized not in texts[key]
    return {'verified': missing == 0,
            'reason': 'selected_scope_index_consistent' if not missing else 'selected_scope_missing_original_lines',
            'checked_reference_lines': checked, 'missing_reference_lines': missing,
            'scope': 'cross-index selected-role consistency; authority and metadata integrity are separate gates'}

"""Independent source-position oracle; never reads the generated index or its headers."""
from __future__ import annotations

from collections import Counter
import hashlib
import re

from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

VERSION = 'qa-source-scope-contract-v1'
FORMAL_TYPES = {'安全操作规程', '技术操作规程', '设备使用维护规程', '岗位交接班制度', '生产联系确认制'}


class SourceScopeUnverified(ValueError):
    """No raw source text in diagnostics."""


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _clean(value):
    return '\n'.join(filter(None, (re.sub(r'[ \t\u3000]+', ' ', row).strip() for row in value.replace('\r', '\n').split('\n'))))


def _name(value):
    value = re.sub(r'[\s.．、:：·]+', '', value).lower()
    return re.sub(r'(?:“三规[一二]制”|"三规[一二]制"|三规[一二]制)$', '', value)


def _role(value):
    value = _name(value)
    for prefix in ('高炉', '原料', '岗位'):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value


def _blocks(document):
    # Independent OOXML traversal. Do not call the index builder's iter_blocks.
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            text = _clean(Paragraph(child, document).text)
            kind = 'paragraph'
        elif isinstance(child, CT_Tbl):
            rows = []
            for row in Table(child, document).rows:
                values = [_clean(cell.text).replace('\n', ' / ') for cell in row.cells]
                if any(values):
                    rows.append(' | '.join(values))
            # Normalize rendered spacing once more, while preserving every cell
            # delimiter; empty cells must not produce a false content mismatch.
            text, kind = _clean('\n'.join(rows)), 'table'
        else:
            continue
        if text:
            yield kind, text


def extract_scope(document, heading_policy, role_heading_policy=None, *, content_sink=None):
    """Independent ordered content oracle from DOCX, with explicit heading policy.

    The literal heading policy is shared reviewed data, not a second semantic
    adjudication. The oracle validates source positions, boundaries and content,
    not whether the book's prescriptions or historical answer oracle are correct.
    """
    if not heading_policy or any(not isinstance(key, str) or value not in FORMAL_TYPES for key, value in heading_policy.items()):
        raise SourceScopeUnverified('Invalid explicit source heading policy')
    toc = re.compile(r'^\s*(\d+)[.．、]\s*(.+?)(?:…{2,}|\.{4,})\s*\d+\s*$')
    directory = {}
    for paragraph in document.paragraphs[:80]:
        entry = toc.fullmatch(_clean(paragraph.text))
        if entry:
            code, name = int(entry[1]), entry[2].strip()
            if code in directory and directory[code] != name:
                raise SourceScopeUnverified('Conflicting source directory')
            directory[code] = name
    if set(directory) != set(range(1, 29)):
        raise SourceScopeUnverified('Frozen book requires exactly 28 source roles')
    role_heading_policy = role_heading_policy or {}
    for (code, alias), name in role_heading_policy.items():
        if code not in directory or directory[code] != name or not alias:
            raise SourceScopeUnverified('Source role alias is not bound to directory')
    positions, rows, regulation_positions = [], [], []
    current, regulation = None, None
    for block_index, (kind, text) in enumerate(_blocks(document)):
        logical_rows = text.split('\n') if kind == 'paragraph' else [text]
        for line_index, line in enumerate(logical_rows):
            if kind == 'paragraph' and toc.fullmatch(line):
                if current is not None:
                    raise SourceScopeUnverified('Directory occurs inside source body')
                continue
            numbered = re.fullmatch(r'\s*(\d+)[.．、]\s*(.+)', line) if kind == 'paragraph' else None
            code = int(numbered[1]) if numbered else None
            name = _name(numbered[2]) if numbered else None
            name = _name(role_heading_policy.get((code, name), name)) if numbered else None
            if code in directory and (name == _name(directory[code]) or (len(_role(directory[code])) >= 2 and _role(name) == _role(directory[code]))):
                if code != len(positions) + 1:
                    raise SourceScopeUnverified('Source role headings repeated or out of order')
                current = code
                regulation = directory[code] if code >= 27 else '综合规定'
                if code >= 27 and regulation not in FORMAL_TYPES:
                    raise SourceScopeUnverified('System chapter category unresolved')
                positions.append({'chapter_code': str(code), 'block_index': block_index, 'line_index': line_index,
                                  'source_heading_sha256': digest(line), 'role_name_sha256': digest(directory[code])})
                continue
            if current is None:
                continue
            if kind == 'paragraph':
                label = re.sub(r'^\s*(?:[0-9]+(?:\.[0-9]+)*[.．、]*|[一二三四五六七八九十]+[.．、]+|[（(][一二三四五六七八九十0-9]+[）)])\s*', '', line).strip().rstrip(':：').strip()
                name = directory[current]
                if label != name and label.startswith(name):
                    label = label[len(name):].strip()
                if label in heading_policy:
                    regulation = heading_policy[label]
                    regulation_positions.append({'chapter_code': str(current), 'regulation_type': regulation,
                                                 'block_index': block_index, 'line_index': line_index,
                                                 'source_heading_sha256': digest(line)})
                    continue
            if regulation not in FORMAL_TYPES:
                raise SourceScopeUnverified('Source content precedes explicit regulation heading')
            row = {'block_index': block_index, 'line_index': line_index, 'kind': kind,
                   'chapter_code': str(current), 'regulation_type': regulation, 'content_sha256': digest(line),
                   'role_name_sha256': digest(directory[current])}
            rows.append(row)
            if content_sink is not None:
                content_sink(line)
    if len(positions) != 28:
        raise SourceScopeUnverified('Source role body incomplete')
    return {'version': VERSION, 'roles': positions, 'regulation_headings': regulation_positions, 'items': rows,
            'heading_policy_semantic_review': 'shared_reviewed_literal_policy_not_independent_semantic_scoring'}


def validate_items(scope, items):
    expected = [(row['block_index'], row['kind'], row['chapter_code'], row['regulation_type'], row['content_sha256'], row['role_name_sha256']) for row in scope['items']]
    actual = [(item.block_index, item.kind, item.chapter_code, item.regulation_type, digest(item.text), digest(item.chapter_title)) for item in items]
    missing, extra = Counter(expected) - Counter(actual), Counter(actual) - Counter(expected)
    return {'verified': expected == actual, 'reason': 'independent_source_positions_verified' if expected == actual else 'source_position_scope_or_content_mismatch',
            'expected_items': len(expected), 'actual_items': len(actual), 'missing_occurrences': sum(missing.values()),
            'extra_occurrences': sum(extra.values()), 'order_matches': expected == actual,
            'semantic_verified': False, 'model_calls': 0, 'question_posts': 0}


def validate_chunks(scope, chunks, source_contents):
    """Use independent original rows; sections are whole-item contiguous slices.

    Topic aggregates may omit intervening headings/children, so their source
    lines must form an ordered subsequence inside the original role/regulation
    range. This does not prove topic completeness or semantic correctness.
    """
    rows = scope['items']
    if len(rows) != len(source_contents) or any(digest(text) != row['content_sha256'] for row, text in zip(rows, source_contents)):
        raise SourceScopeUnverified('Independent source content binding failed')
    roles = {row['chapter_code']: row for row in scope['roles']}
    atomics = [chunk for chunk in chunks if chunk.granularity == 'atomic']
    expected = [(row['block_index'], row['block_index'], row['chapter_code'], row['regulation_type'], row['role_name_sha256'], row['content_sha256']) for row in rows]
    actual = [(chunk.source_block_start, chunk.source_block_end, chunk.chapter_code, chunk.regulation_type,
               digest(chunk.chapter_title), digest(chunk.content)) for chunk in atomics]
    errors = []
    if expected != actual:
        errors.append('atomic_source_order_scope_or_content_mismatch')
    ids = [chunk.chunk_id for chunk in chunks]
    if len(ids) != len(set(ids)):
        errors.append('duplicate_chunk_id')
    for chunk in chunks:
        code, regulation = chunk.chapter_code, chunk.regulation_type
        start, end = chunk.source_block_start, chunk.source_block_end
        if (code not in roles or regulation not in FORMAL_TYPES or type(start) is not int or type(end) is not int
                or start > end or start < roles[code]['block_index']
                or (str(int(code) + 1) in roles and end > roles[str(int(code) + 1)]['block_index'])):
            errors.append('chunk_source_range_unverified')
            continue
        if digest(chunk.chapter_title) != roles[code]['role_name_sha256'] or digest(chunk.content) != chunk.content_hash:
            errors.append('chunk_role_or_hash_unverified')
            continue
        role_header = re.search(r'^【岗位/制度】(\d+)\.\s*(.+)$', chunk.enriched_content, re.M)
        regulation_header = re.search(r'^【规程类型】(.+)$', chunk.enriched_content, re.M)
        if (not role_header or role_header[1] != code or digest(role_header[2]) != roles[code]['role_name_sha256']
                or not regulation_header or regulation_header[1] != regulation):
            errors.append('chunk_header_scope_mismatch')
            continue
        eligible = [(row, text) for row, text in zip(rows, source_contents)
                    if row['chapter_code'] == code and row['regulation_type'] == regulation and start <= row['block_index'] <= end]
        if not eligible or not any(row['block_index'] == start for row, _ in eligible) or not any(row['block_index'] == end for row, _ in eligible):
            errors.append('chunk_boundary_not_in_source')
            continue
        if chunk.granularity == 'section':
            matched = False
            for offset, (first, _) in enumerate(eligible):
                if first['block_index'] != start:
                    continue
                pieces = []
                for last, text in eligible[offset:]:
                    pieces.append(text)
                    combined = '\n'.join(pieces)
                    if combined == chunk.content and last['block_index'] == end:
                        matched = True
                        break
                    if len(combined) >= len(chunk.content):
                        break
                if matched:
                    break
            if not matched:
                errors.append('section_original_item_boundary_mismatch')
        elif chunk.granularity == 'topic':
            source_lines = [line for _, text in eligible for line in text.splitlines() if line.strip()]
            offset = 0
            for line in chunk.content.splitlines():
                if not line.strip():
                    continue
                while offset < len(source_lines) and source_lines[offset] != line:
                    offset += 1
                if offset == len(source_lines):
                    errors.append('topic_original_line_order_mismatch')
                    break
                offset += 1
        elif chunk.granularity != 'atomic':
            errors.append('unsupported_chunk_granularity')
    source_groups, section_groups = {}, {}
    for row, text in zip(rows, source_contents):
        source_groups.setdefault((row['chapter_code'], row['regulation_type']), []).append(text)
    for chunk in chunks:
        if chunk.granularity == 'section':
            section_groups.setdefault((chunk.chapter_code, chunk.regulation_type), []).append(chunk.content)
    if (set(source_groups) != set(section_groups)
            or any('\n'.join(texts) != '\n'.join(section_groups.get(key, [])) for key, texts in source_groups.items())):
        errors.append('section_source_coverage_or_order_mismatch')
    return {'verified': not errors, 'reason': 'independent_source_chunk_bindings_verified' if not errors else 'source_chunk_contract_failed',
            'chunks': len(chunks), 'atomics': len(atomics), 'error_counts': dict(Counter(errors)),
            'topic_completeness_verified': False, 'semantic_verified': False}

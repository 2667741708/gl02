"""Read-only startup and source-heading metadata probe; never emit book or secrets."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys


def source_heading_signals(text: str) -> dict:
    # Same TOC shape as build_three_rules_hierarchical_kb.TOC_ENTRY. These are
    # diagnostic signals, not an assertion that index scope or answers are valid.
    toc = re.compile(r'^\s*(\d+)[.．、]\s*(.+?)(?:…{2,}|\.{4,})\s*\d+\s*$')
    chapter = re.compile(r'^\s*(\d+)[.．、]\s*(.+)$')
    normalize = lambda value: re.sub(r'[\s.．、:：·]+', '', value).lower()
    entries: dict[str, set[str]] = {}
    for line in text.splitlines():
        match = toc.match(line)
        if match:
            entries.setdefault(match[1], set()).add(normalize(match[2]))
    headings = Counter()
    marked_headings = Counter()
    regulations = Counter()
    role_markers = 0
    for line in text.splitlines():
        if toc.match(line):
            continue
        role_markers += bool(re.search(r'三规[一二]制\s*$', line))
        marked = re.match(r'^\s*(\d+)[.．、]\s*.+三规[一二]制\s*$', line)
        if marked:
            marked_headings[marked[1]] += 1
        for label in ('安全操作规程', '技术操作规程', '设备使用维护规程', '岗位交接班制度', '生产联系确认制'):
            if line.strip() == label:
                regulations[label] += 1
        match = chapter.match(line)
        if match and match[1] in entries:
            actual = normalize(match[2]).replace('三规一制', '').replace('三规二制', '')
            if actual in entries[match[1]]:
                headings[match[1]] += 1
    return {'toc_unique_codes': len(entries),
            'toc_conflicting_codes': sorted(code for code, titles in entries.items() if len(titles) != 1),
            'exact_body_heading_counts': dict(sorted(headings.items(), key=lambda row: int(row[0]))),
            'marked_chapter_heading_counts': dict(sorted(marked_headings.items(), key=lambda row: int(row[0]))),
            'role_marker_lines': role_markers, 'exact_regulation_heading_counts': dict(regulations),
            'scope_confirmed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((args.root / 'tools/service_configs/22012_BFV4PreviewProxy8093.json').read_text(encoding='utf-8-sig'))
    for key, value in (config.get('env') or {}).items():
        if key.startswith(('BF_ASSISTANT_PG', 'GL02_PG', 'PG')):
            os.environ[key] = str(value)
    sys.path.insert(0, str(args.root / '高炉前端数据/智能助手/backend'))
    from qa_readonly_pg import VERSION, readonly_pg_connect

    with readonly_pg_connect() as connection:
        startup = connection.execute(
            "SELECT pg_catalog.current_setting('default_transaction_read_only') AS default_readonly, "
            "pg_catalog.current_setting('transaction_read_only') AS transaction_readonly"
        ).fetchone()
        doc = connection.execute(
            'SELECT full_text, content_hash, source_file FROM rag_document WHERE doc_id=%s',
            ('bf_three_rules_two_systems_20260712',)
        ).fetchone()
        if not doc or not isinstance(doc['full_text'], str) or len(doc['full_text']) > 2000000:
            raise RuntimeError('Authority source missing or outside bounded probe')
        counts = connection.execute(
            'SELECT chunk_type, count(*) AS chunks FROM rag_chunk WHERE doc_id=%s GROUP BY chunk_type ORDER BY chunk_type',
            ('bf_three_rules_two_systems_20260712',)
        ).fetchall()
        signals = source_heading_signals(doc['full_text'])
        source_path = Path(doc['source_file']) if doc.get('source_file') else None
        if source_path is not None and not source_path.is_absolute():
            source_path = args.root / source_path
        source_file_exists = source_path is not None and source_path.is_file()
    print(json.dumps({'schema': 'bf.qa.readonly-startup-source-probe.v1', 'connector_version': VERSION,
                      'startup': dict(startup), 'source_content_hash': doc['content_hash'],
                      'source_text_sha256': hashlib.sha256(doc['full_text'].encode('utf-8')).hexdigest(),
                      'source_canonical_text_sha256': hashlib.sha256(doc['full_text'].replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')).hexdigest(),
                      'source_nonempty_lines': sum(bool(line.strip()) for line in doc['full_text'].splitlines()),
                      'recorded_source_file_exists': source_file_exists,
                      'recorded_source_file_suffix': source_path.suffix.lower() if source_path is not None else None,
                      'chunk_counts': [dict(row) for row in counts], 'heading_signals': signals,
                      'schema_initializers': 0, 'database_writes': 0, 'model_calls': 0, 'question_posts': 0},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

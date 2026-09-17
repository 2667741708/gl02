"""Compare original DOCX extraction with frozen KB authority, without emitting text."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def summarize(chapters: dict, items: list, chunks: list, source_sha256: str, expected_hash: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{64}', expected_hash):
        raise ValueError('Expected authority SHA-256 is required')
    text = '\n'.join(chunk.content for chunk in chunks if chunk.granularity == 'atomic')
    authority_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    groups = Counter((item.chapter_code, item.regulation_type) for item in items)
    return {'schema': 'bf.qa.source-docx-readonly.v1', 'source_docx_sha256': source_sha256,
            'extracted_authority_sha256': authority_hash, 'expected_authority_sha256': expected_hash,
            'authority_bytes_match': authority_hash == expected_hash, 'chapter_count': len(chapters),
            'source_item_count': len(items), 'chunk_counts': dict(Counter(chunk.granularity for chunk in chunks)),
            'source_scope_groups': [{'chapter_code': code, 'regulation_type': regulation, 'source_items': count}
                                    for (code, regulation), count in sorted(groups.items())],
            'scope_validation': 'shared_source_parser_preparation_only', 'semantic_passed': 0,
            'database_writes': 0, 'model_calls': 0, 'question_posts': 0,
            'scope': 'Original DOCX and existing extraction parser; byte match does not validate role assignment or semantics.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docx', type=Path, required=True)
    parser.add_argument('--expected-authority-hash', required=True)
    args = parser.parse_args()
    if not args.docx.is_file() or args.docx.suffix.lower() != '.docx' or args.docx.stat().st_size > 25000000:
        raise ValueError('Original DOCX missing or outside bounded read')
    from docx import Document
    from build_three_rules_hierarchical_kb import parse_source_items, build_chunks
    chapters, items = parse_source_items(Document(args.docx))
    result = summarize(chapters, items, build_chunks(items), hashlib.sha256(args.docx.read_bytes()).hexdigest(), args.expected_authority_hash)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['authority_bytes_match'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

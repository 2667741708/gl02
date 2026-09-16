import hashlib
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '高炉前端数据/智能助手/backend'))
import qa_document_integrity as integrity

def chunk(text, kind='three_rules_atomic'):
    return {'content': text, 'content_hash': hashlib.sha256(text.encode()).hexdigest(),
            'authority_level': 'knowledge_doc', 'chunk_type': kind}

def test_missing_last_part_cannot_pass_using_contiguous_remaining_ids():
    source = '1 工作前\n1.1 确认条件\n1.2 未确认不得操作'
    complete = [chunk(source)]
    assert integrity.inspect(source, complete)['verified']
    result = integrity.inspect(source, [chunk('1 工作前\n1.1 确认条件')])
    assert not result['verified'] and result['missing_source_lines'] == 1
    # Recheck same authority version after deletion: cache must not hide it.
    assert integrity.inspect(source, complete)['verified']

def test_valid_self_hash_is_not_proof_of_authority_membership():
    result = integrity.inspect('1.1 不得操作', [chunk('1.1 允许操作')])
    assert not result['verified'] and result['reason'] == 'atomic_text_outside_authority'

def test_noncontiguous_reviewed_aggregate_is_valid_if_original_lines_and_tail_covered():
    source = '岗位甲\n1.1 原文甲\n岗位乙\n1.2 原文乙'
    rows = [chunk('1.1 原文甲\n1.2 原文乙', 'three_rules_section'), chunk('岗位甲'), chunk('岗位乙')]
    assert integrity.inspect(source, rows)['verified']
    rows[0] = chunk('1.2 原文乙\n1.1 原文甲', 'three_rules_section')
    assert integrity.inspect(source, rows)['reason'] == 'aggregate_text_outside_authority'

def test_version_line_endings_and_whitespace_only_normalization():
    assert integrity.inspect('1.1 不得操作\r\n表 | 数值', [chunk('1.1  不得操作\n表|数值')])['verified']
    assert not integrity.inspect('1.1 不得操作', [chunk('1.1 应当操作')])['verified']

def test_missing_line_cannot_be_assembled_from_separate_chunks():
    assert not integrity.inspect('不得操作', [chunk('不得'), chunk('操作')])['verified']

def test_invalid_hash_authority_and_bounds_are_not_complete():
    row = chunk('原文')
    for field, value in [('content_hash', '0' * 64), ('authority_level', 'report'), ('chunk_type', 'chat')]:
        bad = dict(row, **{field: value})
        assert not integrity.inspect('原文', [bad])['verified']
    assert not integrity.inspect('原文', [])['verified']
    assert not integrity.inspect('', [row])['verified']
    assert not integrity.inspect(' \n\t', [chunk(' \n\t')])['verified']

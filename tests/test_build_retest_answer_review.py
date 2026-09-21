import hashlib
import json
from pathlib import Path

import pytest

from tools.build_retest_answer_review import build_review


def _write_inputs(tmp_path: Path, *, retry: int = 0, answer_sha: str | None = None):
    answer = "完整回答"
    answer_digest = hashlib.sha256(answer.encode("utf-8")).hexdigest()
    result = {
        "rows": [{
            "case_id": "CASE-1", "answer": answer, "result_file_sha256": "a" * 64,
            "request_count": 1, "automatic_retries": retry, "http_status": 200,
            "done": True, "model": "locked:model", "final": {"answer_route": "evidence_without_tools"},
        }]
    }
    manual = {
        "index": 0, "case_id": "CASE-1", "result_sha256": "a" * 64,
        "answer_sha256": answer_sha or answer_digest, "full_answer_read": True,
        "status": "partial", "issue_class": "unit_contract", "reason": "private detail",
    }
    paths = [tmp_path / name for name in ("results.json", "manual.jsonl", "contract.json", "scope.json")]
    paths[0].write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    paths[1].write_text(json.dumps(manual, ensure_ascii=False) + "\n", encoding="utf-8")
    paths[2].write_text("[]", encoding="utf-8")
    paths[3].write_text("[]", encoding="utf-8")
    return paths


def test_sanitized_review_binds_full_answer_without_copying_private_text(tmp_path):
    review = build_review(*_write_inputs(tmp_path))
    assert review["manual_status_counts"] == {"partial": 1}
    assert review["records"][0]["answer_sha256"] == hashlib.sha256("完整回答".encode()).hexdigest()
    serialized = json.dumps(review, ensure_ascii=False)
    assert "完整回答" not in serialized
    assert "private detail" not in serialized
    assert review["review_coverage"]["semantic_pass_must_not_be_inferred_from_transport_or_nonempty_answer"]


def test_rejects_replayed_result(tmp_path):
    with pytest.raises(ValueError, match="replayed or retried"):
        build_review(*_write_inputs(tmp_path, retry=1))


def test_rejects_review_bound_to_different_answer(tmp_path):
    with pytest.raises(ValueError, match="not bound to the full result"):
        build_review(*_write_inputs(tmp_path, answer_sha="b" * 64))


def test_knowledge_scope_alert_is_not_counted_as_semantic_pass(tmp_path):
    paths = _write_inputs(tmp_path)
    paths[1].write_text("", encoding="utf-8")
    answer_sha = hashlib.sha256("完整回答".encode()).hexdigest()
    contract = [{"index": 0, "case_id": "CASE-1", "answer_sha256": answer_sha,
                 "state": "original_coverage_verified_pending_scope_review"}]
    scope = [{"index": 0, "case_id": "CASE-1", "answer_sha256": answer_sha,
              "independent_source_scope_state": "scope_contract_mismatch",
              "scope_reasons": ["answer_body_not_in_original_scope"]}]
    paths[2].write_text(json.dumps(contract), encoding="utf-8")
    paths[3].write_text(json.dumps(scope), encoding="utf-8")
    review = build_review(*paths)
    assert review["knowledge_status_counts"] == {"scope_contract_alert": 1}
    assert review["records"][0]["review_status"] != "passed"


def test_committed_review_contains_only_the_public_per_answer_contract():
    path = Path(__file__).parent / 'qa_regression/retest_answer_review_20260921.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    allowed = {'index', 'case_id', 'result_sha256', 'answer_sha256', 'answer_route',
               'review_basis', 'review_status', 'issue_class', 'reason_codes'}
    assert len(payload['records']) == 822
    assert all(set(record) == allowed for record in payload['records'])
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for private_marker in ('conversation_id', 'question', '"answer"', 'tool_results',
                           'runtime_hashes', '10.30.220.12', 'f:\\'):
        assert private_marker not in serialized

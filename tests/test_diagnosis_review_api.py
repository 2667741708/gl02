from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "高炉前端数据" / "智能助手" / "backend"))
import diagnosis_review as review  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in list(os.environ):
        if name.startswith("BF_DIAG_REVIEW_") or name.startswith("BF_DIAGNOSIS_REVIEW_") or name.startswith("BF_AUTH_SESSION_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BF_AUTH_SESSION_SECRET", "unit-test-session-secret")


def snapshot(number, ts, label, score=80):
    scores = {key: 5 for key in review.DIAGNOSIS_KEYS}
    scores[label] = score
    return {"id": number, "diagnosis_ts": ts, "main_label": label, "main_score": score, "raw_scores": scores}


def test_signed_session_success_tamper_and_expiry():
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    token = review.create_session_token("zhgl", "高组长", now=now, ttl_seconds=60)
    assert review.verify_session_token(token, now=now + timedelta(seconds=30))["sub"] == "zhgl"
    assert review.verify_session_token(token + "x", now=now) is None
    assert review.verify_session_token(token, now=now + timedelta(seconds=60)) is None


def test_role_defaults_to_group_leader(monkeypatch):
    assert review.role_is_allowed("高组长")
    assert not review.role_is_allowed("操作员")
    monkeypatch.setenv("BF_DIAG_REVIEW_ALLOWED_ROLES", "高组长,值班长")
    assert review.role_is_allowed("值班长")


def test_login_account_success_and_failure():
    accounts = {"zhgl": {"password": "local-secret", "role": "高组长"}}
    assert review.authenticate_account(accounts, "zhgl", "local-secret") == {"username": "zhgl", "role": "高组长"}
    assert review.authenticate_account(accounts, "zhgl", "wrong") is None
    assert review.authenticate_account(accounts, "missing", "local-secret") is None


def test_continuous_episode_and_label_or_gap_boundary():
    base = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
    first = review.derive_current_episode([
        snapshot(1, base, "normal"), snapshot(2, base + timedelta(minutes=5), "cold"), snapshot(3, base + timedelta(minutes=14), "cold")
    ])
    assert first["is_abnormal"] and first["episode_start_ts"] == (base + timedelta(minutes=5)).isoformat()
    changed = review.derive_current_episode([
        snapshot(2, base + timedelta(minutes=5), "cold"), snapshot(4, base + timedelta(minutes=7), "hot")
    ])
    assert changed["episode_start_ts"] == (base + timedelta(minutes=7)).isoformat()
    interrupted = review.derive_current_episode([
        snapshot(2, base + timedelta(minutes=5), "cold"), snapshot(5, base + timedelta(minutes=16), "cold")
    ])
    assert interrupted["episode_start_ts"] == (base + timedelta(minutes=16)).isoformat()


def test_context_has_exactly_seven_other_scores_and_formal_labels():
    context = review.build_fixture_context("cold", "case-a")
    assert context["main_display_label"] == "热制度下行"
    assert len(context["candidates"]) == 7
    assert review.display_label("hot") == "热制度上行"
    assert set(review.DIAGNOSIS_KEYS) == {"normal", "lowline", "edge", "center", "channel", "cold", "hot", "column"}


@pytest.mark.parametrize("verdict", ["correct", "uncertain"])
def test_valid_non_correction_verdicts(verdict):
    context = review.build_fixture_context("channel", "valid")
    payload = {"verdict": verdict, "episode_key": context["episode_key"], "snapshot_id": context["snapshot_id"], "idempotency_key": "review-12345678"}
    assert review.validate_review_payload(payload, context)["verdict"] == verdict


def test_incorrect_requires_corrected_main_and_rejects_snapshot_tampering():
    context = review.build_fixture_context("cold", "invalid")
    base = {"verdict": "incorrect", "episode_key": context["episode_key"], "snapshot_id": context["snapshot_id"], "idempotency_key": "review-12345678"}
    with pytest.raises(review.ReviewValidationError, match="实际主炉况"):
        review.validate_review_payload(base, context)
    with pytest.raises(review.ReviewValidationError, match="快照已变化"):
        review.validate_review_payload({**base, "corrected_main_label": "hot", "snapshot_id": "browser-forged"}, context)


def test_review_database_requires_explicit_loopback_configuration(monkeypatch):
    monkeypatch.setenv("BF_DIAG_REVIEW_PGHOST", "10.30.220.12")
    monkeypatch.setenv("BF_DIAG_REVIEW_PGDATABASE", "bf_trend")
    monkeypatch.setenv("BF_DIAG_REVIEW_PGUSER", "writer")
    monkeypatch.setenv("BF_DIAG_REVIEW_PGPASSWORD", "secret")
    with pytest.raises(review.ReviewConfigurationError, match="本机回环"):
        review.load_review_config(require_store=True)
    monkeypatch.setenv("BF_DIAG_REVIEW_PGHOST", "127.0.0.1")
    assert review.load_review_config(require_store=True).pg_port == 18000


def test_review_table_template_formats_without_json_brace_collision():
    ddl = review.REVIEW_TABLE_DDL.format(schema="bf_assistant")
    assert "DEFAULT '{}'::jsonb" in ddl
    assert "diagnosis_manual_score_events" in ddl
    assert "human_match_score SMALLINT" in ddl


def test_manual_score_accepts_score_or_suggestion_and_binds_snapshot():
    context = review.build_fixture_context("normal", "manual-score")
    score_payload = {
        "snapshot_id": context["snapshot_id"],
        "target_label": "edge",
        "human_match_score": "76",
        "idempotency_key": "manual-score-12345678",
    }
    assert review.validate_manual_score_payload(score_payload, context)["human_match_score"] == 76
    suggestion_payload = {
        "snapshot_id": context["snapshot_id"],
        "target_label": "center",
        "suggestion": "建议继续观察中心与边缘气流变化",
        "idempotency_key": "manual-suggest-12345678",
    }
    assert review.validate_manual_score_payload(suggestion_payload, context)["human_match_score"] is None


def test_manual_score_rejects_empty_out_of_range_and_stale_snapshot():
    context = review.build_fixture_context("cold", "manual-invalid")
    base = {
        "snapshot_id": context["snapshot_id"],
        "target_label": "cold",
        "idempotency_key": "manual-score-12345678",
    }
    with pytest.raises(review.ReviewValidationError, match="直接关闭"):
        review.validate_manual_score_payload(base, context)
    with pytest.raises(review.ReviewValidationError, match="0到100"):
        review.validate_manual_score_payload({**base, "human_match_score": 101}, context)
    with pytest.raises(review.ReviewValidationError, match="快照已变化"):
        review.validate_manual_score_payload({**base, "snapshot_id": "stale", "human_match_score": 50}, context)


def test_popup_review_accepts_optional_human_score_and_suggestion():
    context = review.build_fixture_context("channel", "popup-human-input")
    payload = {
        "verdict": "correct",
        "episode_key": context["episode_key"],
        "snapshot_id": context["snapshot_id"],
        "human_match_score": 82,
        "suggestion": "建议十分钟后复查",
        "idempotency_key": "review-human-12345678",
    }
    validated = review.validate_review_payload(payload, context)
    assert validated["human_match_score"] == 82
    assert validated["suggestion"] == "建议十分钟后复查"

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
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


def test_submission_identity_requires_login_by_default():
    config = review.load_review_config()
    assert config.require_login is True
    assert review.submission_identity(None, config) is None


def test_no_login_mode_uses_fixed_server_side_onsite_identity(monkeypatch):
    monkeypatch.setenv("BF_DIAG_REVIEW_REQUIRE_LOGIN", "0")
    monkeypatch.setenv("BF_DIAG_REVIEW_ANONYMOUS_USERNAME", "onsite-8093")
    monkeypatch.setenv("BF_DIAG_REVIEW_ANONYMOUS_ROLE", "现场高炉长")
    config = review.load_review_config()
    identity = review.submission_identity(None, config)
    assert identity == {
        "sub": "onsite-8093",
        "role": "现场高炉长",
        "identity_mode": "onsite_anonymous",
    }


def test_allowed_signed_session_keeps_named_identity_in_no_login_mode(monkeypatch):
    monkeypatch.setenv("BF_DIAG_REVIEW_REQUIRE_LOGIN", "0")
    identity = review.submission_identity({"sub": "zhgl", "role": "高组长"})
    assert identity == {
        "sub": "zhgl",
        "role": "高组长",
        "identity_mode": "signed_session",
    }


def test_password_can_be_resolved_from_named_machine_environment(monkeypatch):
    monkeypatch.setenv("BF_DIAG_REVIEW_PGHOST", "127.0.0.1")
    monkeypatch.setenv("BF_DIAG_REVIEW_PGDATABASE", "bf_trend")
    monkeypatch.setenv("BF_DIAG_REVIEW_PGUSER", "gl02_sync")
    monkeypatch.setenv("GL02_PGPASSWORD", "machine-secret")
    monkeypatch.setenv("BF_DIAG_REVIEW_PGPASSWORD_ENV", "GL02_PGPASSWORD")
    assert review.load_review_config(require_store=True).pg_password == "machine-secret"


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


def test_abc33_b4_is_the_only_hot_display_score_and_legacy_value_is_archived():
    diagnosis_ts = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    context = review.derive_current_episode([snapshot(10, diagnosis_ts, "cold")])
    overlaid = review.apply_abc33_display_score(
        context,
        {
            "evaluation_id": 662,
            "evaluation_ts": diagnosis_ts - timedelta(minutes=5),
            "catalog_version": "abc33-catalog.v3",
            "config_version": "20260810.2",
            "rule": {"rule_id": "B4", "score": 63.5, "score_available": True, "status": "eligible"},
        },
        now=diagnosis_ts,
    )
    assert overlaid["raw_scores"]["hot"] == 5
    assert overlaid["display_scores"]["hot"] == 63.5
    assert next(item for item in overlaid["candidates"] if item["key"] == "hot")["score"] == 63.5
    assert overlaid["score_sources"]["hot"]["rule_id"] == "B4"
    assert overlaid["score_sources"]["hot"]["fallback_used"] is False
    assert overlaid["legacy_score_archive"]["hot"] == {
        "source": "legacy_diagnosis_raw_scores",
        "score": 5.0,
        "archived": True,
        "used_for_display": False,
    }


def test_abc33_score_source_is_json_serializable_for_ai_snapshot_store():
    """The PostgreSQL Jsonb adapter must be able to persist the AI context."""

    diagnosis_ts = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    context = review.derive_current_episode([snapshot(16, diagnosis_ts, "normal")])
    overlaid = review.apply_abc33_display_score(
        context,
        {
            "evaluation_id": 702,
            "evaluation_ts": diagnosis_ts,
            "catalog_version": "abc33-catalog.v3",
            "config_version": "20260810.2",
            "source_snapshot_id": 16,
            "source_snapshot_match": True,
            "rule": {
                "rule_id": "B4",
                "score": 64.5,
                "score_available": True,
                "status": "eligible",
            },
        },
        now=diagnosis_ts,
    )

    overlaid["variable_stats"] = {
        "T_top_A": {
            "sample_ts": diagnosis_ts,
            "baseline_median": Decimal("128.75"),
            "recent_values": (Decimal("127.5"), float("nan")),
        }
    }
    persisted = review.json_safe_value(overlaid)
    encoded = json.dumps(persisted, ensure_ascii=False)

    assert '"evaluation_ts": "2026-08-10T10:00:00+00:00"' in encoded
    assert persisted["variable_stats"]["T_top_A"]["baseline_median"] == 128.75
    assert persisted["variable_stats"]["T_top_A"]["recent_values"] == [127.5, None]


def test_abc33_b4_missing_or_stale_fails_closed_without_legacy_fallback():
    diagnosis_ts = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    context = review.derive_current_episode([snapshot(11, diagnosis_ts, "hot", 88)])
    stale = review.apply_abc33_display_score(
        context,
        {
            "evaluation_id": 600,
            "evaluation_ts": diagnosis_ts - timedelta(minutes=30),
            "rule": {"rule_id": "B4", "score": 72, "score_available": True, "status": "eligible"},
        },
        now=diagnosis_ts,
    )
    assert stale["display_scores"]["hot"] is None
    assert stale["display_main_score"] is None
    assert stale["score_sources"]["hot"]["state"] == "stale"
    assert stale["legacy_score_archive"]["hot"]["score"] == 88.0


def test_abc33_b4_fails_closed_when_both_sources_stopped_updating():
    diagnosis_ts = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    context = review.derive_current_episode([snapshot(12, diagnosis_ts, "hot", 81)])
    overlaid = review.apply_abc33_display_score(
        context,
        {
            "evaluation_id": 601,
            "evaluation_ts": diagnosis_ts,
            "rule": {"rule_id": "B4", "score": 70, "score_available": True, "status": "eligible"},
        },
        now=diagnosis_ts + timedelta(minutes=30),
    )
    assert overlaid["display_scores"]["hot"] is None
    assert overlaid["score_sources"]["hot"]["state"] == "stale"
    assert overlaid["score_sources"]["hot"]["wall_clock_age_minutes"] == 30.0


def test_review_storage_uses_display_score_and_embeds_legacy_archive_evidence():
    diagnosis_ts = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    context = review.derive_current_episode([snapshot(13, diagnosis_ts, "cold")])
    overlaid = review.apply_abc33_display_score(
        context,
        {
            "evaluation_id": 662,
            "evaluation_ts": diagnosis_ts,
            "catalog_version": "abc33-catalog.v3",
            "config_version": "20260810.2",
            "source_snapshot_id": 13,
            "source_snapshot_match": True,
            "rule": {"rule_id": "B4", "score": 66, "score_available": True, "status": "eligible"},
        },
        now=diagnosis_ts,
    )
    stored = review.scores_with_display_archive(overlaid)
    evidence = review.review_evidence_with_score_archive(overlaid)
    assert stored["hot"] == 5.0
    assert stored["_display_contract"]["display_scores"]["hot"] == 66.0
    assert stored["_display_contract"]["score_sources"]["hot"]["rule_id"] == "B4"
    assert evidence[-1]["type"] == "score_source_archive"
    assert evidence[-1]["legacy_score_archive"]["hot"]["score"] == 5.0


def test_public_abc_bundle_and_popup_share_the_same_wall_clock_freshness_gate():
    evaluation_ts = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    bundle = {
        "schema_version": "abc_rule_bundle.v1",
        "rules": [{"rule_id": "B4", "score": 67, "score_available": True, "status": "eligible"}],
        "alerts": [{"rule_id": "B4", "score": 67}],
    }
    stale = review.abc_public_bundle_for_display(
        bundle,
        evaluation_ts,
        now=evaluation_ts + timedelta(minutes=30),
    )
    assert stale["batch_state"] == "stale"
    assert stale["rules"][0]["score"] is None
    assert stale["rules"][0]["source_state"] == "stale_batch"
    assert stale["alerts"] == []


def test_public_abc_bundle_with_missing_timestamp_fails_closed_without_exception():
    bundle = {
        "rules": [
            {"rule_id": "B4", "score": 67, "score_available": True, "status": "eligible"}
        ]
    }
    unavailable = review.abc_public_bundle_for_display(bundle, None)
    assert unavailable["batch_state"] == "stale"
    assert unavailable["evaluation_age_seconds"] is None
    assert unavailable["rules"][0]["score"] is None


@pytest.mark.parametrize(
    ("snapshot_patch", "rule_patch"),
    [
        ({"catalog_version": None}, {}),
        ({"config_version": None}, {}),
        ({}, {"rule_id": "B3"}),
        ({}, {"score": -1}),
        ({}, {"score": 101}),
    ],
)
def test_abc33_b4_invalid_identity_range_or_version_fails_closed(
    snapshot_patch, rule_patch
):
    diagnosis_ts = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    context = review.derive_current_episode([snapshot(14, diagnosis_ts, "hot", 77)])
    abc_snapshot = {
        "evaluation_id": 700,
        "evaluation_ts": diagnosis_ts,
        "catalog_version": "abc33-catalog.v3",
        "config_version": "20260810.2",
        "rule": {
            "rule_id": "B4",
            "score": 0,
            "score_available": True,
            "status": "eligible",
        },
    }
    abc_snapshot.update(snapshot_patch)
    abc_snapshot["rule"].update(rule_patch)
    overlaid = review.apply_abc33_display_score(
        context, abc_snapshot, now=diagnosis_ts
    )
    assert overlaid["display_scores"]["hot"] is None
    assert overlaid["score_sources"]["hot"]["state"] == "invalid"


def test_abc33_b4_zero_is_a_valid_display_score():
    diagnosis_ts = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    context = review.derive_current_episode([snapshot(15, diagnosis_ts, "hot", 77)])
    overlaid = review.apply_abc33_display_score(
        context,
        {
            "evaluation_id": 701,
            "evaluation_ts": diagnosis_ts,
            "catalog_version": "abc33-catalog.v3",
            "config_version": "20260810.2",
            "rule": {
                "rule_id": "B4",
                "score": 0,
                "score_available": True,
                "status": "eligible",
            },
        },
        now=diagnosis_ts,
    )
    assert overlaid["display_scores"]["hot"] == 0.0
    assert overlaid["display_main_score"] == 0.0


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
    assert "identity_mode TEXT NOT NULL" in ddl


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

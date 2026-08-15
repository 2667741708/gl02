from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


SERVICE = Path(__file__).resolve().parents[1] / "自动诊断服务"
sys.path.insert(0, str(SERVICE))

from abc_rule_catalog import RULES
from abc_rule_engine import evaluate, load_config
from abc_rule_explanation import (
    build_assistant_context,
    build_operator_explanation_context,
    canonical_context_hash,
    canonical_json,
    json_safe_value,
)


def _published_bundle(value: float = 0.5):
    features = {term: value for rule in RULES for term in rule.terms}
    features.update({
        "BodyHotConcurrence": value,
        "BodyHotEscalation": value,
        "CoolingConcurrence": value,
        "TopTempRange": value,
        "TopPressRange": value,
        "DrainProxy": value,
    })
    quality = {term: {"available": True} for term in features}
    quality.update({"coverage_ratio": 1.0, "data_age_seconds": 1})
    config = load_config()
    config["release_control"] = {
        "mode": "published",
        "scores_visible": True,
        "alerts_enabled": True,
    }
    return evaluate(features, quality=quality, config=config, timestamp=datetime(2026, 8, 11, tzinfo=timezone.utc))


def test_context_covers_all_33_rules_and_preserves_score_direction():
    bundle = _published_bundle()
    contexts = [build_assistant_context(bundle, rule.rule_id) for rule in RULES]

    assert all(context["schema_version"] == "abc_rule_explanation_context.v1" for context in contexts)
    assert [item["rule"]["rule_id"] for item in contexts] == [rule.rule_id for rule in RULES]
    assert all(item["rule"]["score_direction"]["higher_means"] == "healthier" for item in contexts[:9])
    assert all(item["rule"]["score_direction"]["higher_means"] == "higher_risk" for item in contexts[9:])
    assert all(len(item["calculation"]["terms"]) == len(rule.terms) for item, rule in zip(contexts, RULES))


def test_term_contract_exposes_normalized_weighted_and_ratio_values():
    item = build_operator_explanation_context(_published_bundle()["evaluations"][0])

    assert item["schema_version"] == "abc_rule_explanation_context.v1"
    assert set(item) == {
        "schema_version", "context_id", "context_hash", "furnace_id", "evaluation", "rule",
        "calculation", "process_guidance", "sensor_review", "data_quality", "assistant_policy",
    }
    assert item["rule"]["score"] == pytest.approx(50.0)
    assert item["rule"]["risk_score"] == pytest.approx(50.0)
    assert item["calculation"]["weighted_points_sum"] == pytest.approx(50.0)
    assert sum(term["contribution_ratio"] for term in item["calculation"]["terms"]) == pytest.approx(1.0)
    for term in item["calculation"]["terms"]:
        assert "unit" in term
        assert term["normalized_score_0_100"] == pytest.approx(50.0)
        assert term["weight"] > 0
        assert term["display_name"]
        assert term["semantic"]
        assert term["effective_threshold_description"]


def test_missing_terms_remain_in_contract_with_null_numeric_explanation():
    evaluation = _published_bundle()["evaluations"][0]
    missing_term = RULES[0].terms.keys().__iter__().__next__()
    evaluation["contributions"] = [item for item in evaluation["contributions"] if item["feature_key"] != missing_term]
    evaluation["missing_features"] = [missing_term]
    evaluation["data_complete"] = False

    context = build_operator_explanation_context(evaluation)
    row = next(item for item in context["calculation"]["terms"] if item["term_key"] == missing_term)
    assert row["data_state"] == "missing"
    assert row["normalized_score_0_100"] is None
    assert row["weighted_points"] is None
    assert row["contribution_ratio"] is None
    assert row["missing_reasons"]
    assert missing_term in context["data_quality"]["missing_terms"]


def test_json_normalization_handles_datetime_decimal_and_non_finite_values():
    source = {
        "when": datetime(2026, 8, 11, 12, 34, 56, tzinfo=timezone.utc),
        "decimal": Decimal("12.50"),
        "nan": float("nan"),
        "positive_infinity": float("inf"),
        "negative_infinity": Decimal("-Infinity"),
    }
    safe = json_safe_value(source)

    assert safe == {
        "when": "2026-08-11T12:34:56+00:00",
        "decimal": 12.5,
        "nan": None,
        "positive_infinity": None,
        "negative_infinity": None,
    }
    assert json.loads(canonical_json(source)) == safe


def test_canonical_hash_is_stable_across_mapping_and_set_order():
    left = {"b": {3, 1, 2}, "a": {"y": Decimal("2.0"), "x": float("nan")}}
    right = {"a": {"x": None, "y": 2}, "b": {2, 3, 1}}

    assert canonical_json(left) == canonical_json(right)
    assert canonical_context_hash(left) == canonical_context_hash(right)
    assert canonical_context_hash(left) == canonical_context_hash(left)


def test_hash_field_describes_payload_without_the_hash_field_itself():
    context = build_assistant_context(_published_bundle(), "A1")
    digest = context["context_hash"]
    assert digest == canonical_context_hash(context)

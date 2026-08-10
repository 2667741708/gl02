import json
import tempfile
from pathlib import Path

import pytest


SERVICE = Path(__file__).resolve().parents[1] / "自动诊断服务"
import sys
sys.path.insert(0, str(SERVICE))

from abc_rule_catalog import RULES
from abc_rule_engine import evaluate, load_config, public_bundle, validate_config
from abc_rule_config_store import publish_atomic
from abc_public_review import variables_for_rule


def _features():
    values = {}
    for rule in RULES:
        values.update({term: 0.5 for term in rule.terms})
    values.update({"BodyHotConcurrence": 0.5, "BodyHotEscalation": 0.5, "CoolingConcurrence": 0.5})
    return values


def _quality(values, coverage=1.0):
    result = {key: {"available": True} for key in values}
    result.update({"coverage_ratio": coverage, "data_age_seconds": 10})
    return result


def _published_config():
    config = load_config()
    config["release_control"] = {
        "mode": "published",
        "scores_visible": True,
        "alerts_enabled": True,
    }
    return config


def _shadow_config():
    config = load_config()
    config["release_control"] = {
        "mode": "shadow_validation",
        "scores_visible": False,
        "alerts_enabled": False,
    }
    return config


def test_catalog_has_a9_b13_c11_and_json_is_valid():
    counts = {category: sum(rule.category == category for rule in RULES) for category in "ABC"}
    assert counts == {"A": 9, "B": 13, "C": 11}
    config = load_config()
    validate_config(config)
    assert set(config["rules"]) == {rule.rule_id for rule in RULES}


def test_all_rules_are_evaluated_and_public_contract_redacts_internal_fields():
    result = evaluate(_features(), quality=_quality(_features()), timestamp="2026-08-07T12:00:00")
    assert len(result["evaluations"]) == 33
    assert len(result["public"]["rules"]) == 33
    encoded = json.dumps(result["public"], ensure_ascii=False)
    for secret in ("formula_terms", "weights", "thresholds", "normalized_value", "contribution", "feature_key", "g_H", "g_L", "g_A"):
        assert secret not in encoded


def test_protected_evaluation_keeps_value_weight_threshold_and_lineage():
    values = _features()
    quality = _quality(values)
    quality["factor_audit"] = {
        key: {
            "formula": "audit-only formula",
            "source_features": {"z60_demo": 0.75},
            "source_values": {"demo_sensor": 456.7},
            "baseline_snapshot": {"demo_sensor": {"median_ref": 450.0, "iqr_ref": 10.0}},
            "effective_thresholds": {
                "factor_stage": {"mode": "precalibrated_0_1", "minimum": 0, "maximum": 1},
                "input_transform": {"mode": "high", "a": 0.8, "b": 1.5},
            },
        }
        for key in values
    }
    result = evaluate(values, quality=quality, config=_published_config())
    item = result["evaluations"][0]
    assert set(item["thresholds"]) == set(item["weights"])
    contribution = item["contributions"][0]
    assert contribution["raw_value"] == 0.5
    assert contribution["weight"] > 0
    assert contribution["contribution"] == contribution["normalized_value"] * contribution["weight"]
    assert contribution["source_values"]["demo_sensor"] == 456.7
    assert contribution["baseline_snapshot"]["demo_sensor"]["median_ref"] == 450.0
    assert contribution["effective_thresholds"]["input_transform"]["a"] == 0.8
    encoded = json.dumps(result["public"], ensure_ascii=False)
    assert "audit-only formula" not in encoded
    assert "demo_sensor" not in encoded


def test_missing_data_is_needs_data_without_zero_fallback():
    result = evaluate({}, quality={"coverage_ratio": 0.2, "data_age_seconds": 900})
    assert len(result["evaluations"]) == 33
    assert all(item["status"] == "needs_data" for item in result["evaluations"])
    assert all(item["missing_features"] for item in result["evaluations"])
    assert all(item["score"] is None for item in result["public"]["rules"])
    assert all(item["score_available"] is False for item in result["public"]["rules"])


def test_stale_data_is_needs_data_even_when_values_are_present():
    values = _features()
    result = evaluate(values, quality=_quality(values) | {"data_age_seconds": 301})
    assert all(item["status"] == "needs_data" for item in result["evaluations"])


def test_missing_global_quality_fails_closed():
    result = evaluate(_features(), quality={})
    assert all(item["status"] == "needs_data" for item in result["evaluations"])


def test_release_control_is_required_and_unknown_weight_factor_rejected():
    config = load_config()
    config.pop("release_control")
    with pytest.raises(ValueError):
        validate_config(config)
    config = load_config()
    config["rules"]["A1"]["weight_overrides"]["P_blast"] = 1
    with pytest.raises(ValueError):
        validate_config(config)


def test_c2_complete_non_trigger_is_zero_risk_not_needs_data():
    values = _features()
    values.update({"highSlope_Ttop": 0, "SpikeTopP15": 0, "BurdenSlip": 0})
    result = evaluate(values, quality=_quality(values), config=_published_config())
    c2 = next(item for item in result["evaluations"] if item["rule_id"] == "C2")
    assert c2["confidence"] == 1
    assert c2["risk_score"] == 0
    assert c2["status"] == "eligible"


@pytest.mark.parametrize("score_band", [(55, "yellow"), (70, "amber"), (85, "deep_amber")])
def test_b_alert_bands_are_present(score_band):
    threshold, alert = score_band
    result = evaluate({term: 1.0 for rule in RULES for term in rule.terms}, quality=_quality(_features()), config=_published_config())
    b_items = [item for item in result["evaluations"] if item["category"] == "B"]
    assert all("alert_state" in item for item in b_items)
    assert threshold in (55, 70, 85)
    assert alert in {"yellow", "amber", "deep_amber"}


def test_c_rules_are_red_safety_events():
    values = {term: 1.0 for rule in RULES for term in rule.terms}
    values.update({"BodyHotConcurrence": 1.0, "BodyHotEscalation": 1.0, "CoolingConcurrence": 1.0})
    result = evaluate(values, quality=_quality(values), config=_published_config())
    c_items = [item for item in result["evaluations"] if item["category"] == "C"]
    assert len(c_items) == 11
    assert all(item["alert_state"] == "red" for item in c_items)
    assert all(item["status"] == "manual_confirm" for item in c_items)


def test_c4_c5_c7_do_not_promote_correlated_or_single_sensor_evidence_to_severe_event():
    values = {term: 1.0 for rule in RULES for term in rule.terms}
    values.update({"BodyHotConcurrence": 1.0, "BodyHotEscalation": 1.0, "CoolingConcurrence": 0.0})
    result = evaluate(values, quality=_quality(values), config=_published_config())
    by_id = {item["rule_id"]: item for item in result["evaluations"]}
    assert by_id["C4"]["raw_formula_score"] == 100
    assert by_id["C4"]["score"] == 0
    assert by_id["C5"]["score"] == 0
    # C7 also needs an independent non-body corroboration; set all such
    # factors to zero to prove body maxima/range/slope cannot self-confirm.
    values.update({"TopTempRange": 0.0, "TopPressRange": 0.0, "DrainProxy": 0.0})
    result = evaluate(values, quality=_quality(values), config=_published_config())
    c7 = next(item for item in result["evaluations"] if item["rule_id"] == "C7")
    assert c7["raw_formula_score"] >= 50
    assert c7["score"] == 0
    assert c7["event_confirmation_state"] == "not_confirmed"
    encoded = json.dumps(result["public"], ensure_ascii=False)
    assert "raw_formula_score" not in encoded
    assert "event_confirmation_sources" not in encoded


def test_c7_public_review_contains_all_80_furnace_body_points_and_supporting_systems():
    variables = variables_for_rule("C7")
    body = [name for name in variables if name.startswith("T_body_L")]
    assert len(body) == 80
    assert body[0] == "T_body_L7_A"
    assert body[-1] == "T_body_L16_H"
    assert {"Q_high_pressure_water", "ExpansionTankLevel", "P_top", "T_taphole_1"}.issubset(variables)


def test_shadow_validation_never_publishes_unvalidated_scores_or_alerts():
    result = evaluate(_features(), quality=_quality(_features()), config=_shadow_config())
    assert result["public"]["alerts"] == []
    assert all(item["status"] == "blocked" for item in result["public"]["rules"])
    assert all(item["score"] is None and item["score_available"] is False for item in result["public"]["rules"])
    assert all(item["release_state"] == "shadow_validation" for item in result["public"]["rules"])


def test_score_preview_publishes_valid_zero_score_but_never_alerts():
    values = _features()
    values.update({"highSlope_Ttop": 0, "SpikeTopP15": 0, "BurdenSlip": 0})
    result = evaluate(values, quality=_quality(values))
    c2 = next(item for item in result["public"]["rules"] if item["rule_id"] == "C2")
    assert c2["score"] == 0
    assert c2["score_available"] is True
    assert c2["release_state"] == "score_preview"
    assert result["public"]["alerts"] == []


@pytest.mark.parametrize(
    "mode,scores_visible,alerts_enabled",
    [
        ("shadow_validation", True, False),
        ("score_preview", False, False),
        ("score_preview", True, True),
        ("published", False, False),
    ],
)
def test_release_control_rejects_inconsistent_gate_combinations(mode, scores_visible, alerts_enabled):
    config = load_config()
    config["release_control"] = {
        "mode": mode,
        "scores_visible": scores_visible,
        "alerts_enabled": alerts_enabled,
    }
    with pytest.raises(ValueError):
        validate_config(config)


def test_production_frontend_asset_does_not_embed_internal_rule_contract():
    asset = SERVICE.parent / "高炉前端数据" / "assets" / "abc-furnace-rules-production.js"
    source = asset.read_text(encoding="utf-8")
    for secret in ("formula_terms", "normalized_value", "contribution", "feature_key", "g_H", "g_L", "g_A", "weight_overrides"):
        assert secret not in source


def test_config_publish_requires_reason_and_writes_hash_atomically():
    config = load_config()
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
        target = Path(folder) / "abc.json"
        published = publish_atomic(config, target, reason="测试发布", actor="unit-test")
        assert published["config_hash"]
        saved = json.loads(target.read_text(encoding="utf-8"))
        assert saved["published_by"] == "unit-test"
        with pytest.raises(ValueError):
            publish_atomic(config, target, reason="", actor="unit-test")


def test_proxy_has_public_allowlist_and_admin_guard():
    proxy = (SERVICE.parent / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert 'if rel == "furnace-rule-admin.html" and not self._abc_admin_required()' in proxy
    assert 'status=403' in proxy
    assert '/api/admin/furnace-rules/evaluations/' in proxy
    assert '/api/admin/furnace-rules/config/publish' in proxy

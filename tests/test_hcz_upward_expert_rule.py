from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "炉况规则引擎" / "features" / "hcz_upward_expert_rule.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hcz_upward_expert_rule_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


EVALUATION = datetime(2026, 8, 10, 12, tzinfo=timezone(timedelta(hours=8)))
BASE = {"DP_total": 150.0, "PI": 8.0, "GasUtil": 48.0, "P_blast_cold": 350.0}


def build_records(*, mode: str = "trigger", missing: str | None = None, top_delta: float = 15.5, movement: str = "up"):
    records = []
    start = EVALUATION - timedelta(hours=143)
    for index in range(144):
        hour = start + timedelta(hours=index)
        current = index >= 120
        passing = current
        factor = 1.0
        if mode == "interrupted" and current:
            passing = index % 2 == 0
            factor = 2.0 if passing else 0.0
        direction_factor = -1.0 if movement == "down" else 1.0
        changes = {
            "DP_total": 5.2 * factor,
            "PI": -0.52 * factor,
            "GasUtil": -1.05 * factor,
            "P_blast_cold": 5.2 * factor,
        }
        for name, base_value in BASE.items():
            if name == missing:
                continue
            value = base_value + (changes[name] * direction_factor if current else 0.0)
            records.append({"bucket": hour, "variable_name": name, "value": value, "sample_count": 60})
        top_change = top_delta * factor * direction_factor if current else 0.0
        for sector, offset in zip("ABCD", (-2.0, -0.5, 0.5, 2.0)):
            records.append(
                {
                    "bucket": hour,
                    "variable_name": f"T_top_{sector}",
                    "value": 180.0 + offset + top_change,
                    "sample_count": 60,
                }
            )
        for layer in range(7, 14):
            layer_change = 0.0
            if current and layer in {7, 8, 9}:
                layer_change = (22.0 if layer == 7 else 12.0) * factor * direction_factor
            for sector_index, sector in enumerate("ABCDEFGH"):
                records.append(
                    {
                        "bucket": hour,
                        "variable_name": f"T_body_L{layer}_{sector}",
                        "value": 110.0 + layer + sector_index / 10 + layer_change,
                        "sample_count": 60,
                    }
                )
    return records


def test_rule_triggers_only_for_complete_12_hour_composite_trend() -> None:
    module = load_module()
    result = module.evaluate_hcz_upward_rule(build_records(), evaluation_time=EVALUATION)

    assert result["status"] == "triggered"
    assert result["decision"] == "up"
    assert result["gates"] == {
        "data_sufficient": True,
        "core_all_pass": True,
        "body_layers_pass": True,
        "duration_pass": True,
    }
    assert result["sustained_trend"]["max_consecutive_hours"] == 24
    assert result["body_temperature"]["rising_layers"] == [7, 8, 9]
    assert result["body_temperature"]["strong_rising_layers"] == [7]
    assert result["evidence_strength"] == "strong"
    assert result["safety"]["automatic_control"] == "prohibited"
    assert result["metrics"]["blast_pressure"]["label"] == "冷风风压"
    assert "P_blast_cold" in module.required_variable_names()
    assert "P_blast" not in module.required_variable_names()


def test_24_hour_means_can_pass_but_interrupted_hours_fail_duration_gate() -> None:
    module = load_module()
    result = module.evaluate_hcz_upward_rule(
        build_records(mode="interrupted"),
        evaluation_time=EVALUATION,
    )

    assert result["gates"]["core_all_pass"] is True
    assert result["gates"]["body_layers_pass"] is True
    assert result["sustained_trend"]["max_consecutive_hours"] == 1
    assert result["gates"]["duration_pass"] is False
    assert result["status"] == "not_triggered"
    assert result["decision"] is None


def test_missing_core_data_is_indeterminate_and_never_filled_with_zero() -> None:
    module = load_module()
    result = module.evaluate_hcz_upward_rule(
        build_records(missing="GasUtil"),
        evaluation_time=EVALUATION,
    )

    assert result["status"] == "insufficient_data"
    assert result["triggered"] is False
    assert result["metrics"]["gas_utilisation"]["current_24h_mean"] is None
    assert any("煤气利用率" in reason for reason in result["missing_reasons"])


def test_average_top_temperature_uses_three_or_more_a_to_d_points() -> None:
    module = load_module()
    records = [item for item in build_records() if item["variable_name"] != "T_top_D"]
    result = module.evaluate_hcz_upward_rule(records, evaluation_time=EVALUATION)

    assert result["metrics"]["top_temperature"]["coverage_pass"] is True
    assert result["metrics"]["top_temperature"]["delta"] == 15.5


def test_fixed_config_rejects_control_or_window_relaxation() -> None:
    module = load_module()
    text = module.DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    unsafe = ROOT / ".tmp" / "hcz_upward_rule_unsafe_test.yaml"
    unsafe.parent.mkdir(parents=True, exist_ok=True)
    try:
        unsafe.write_text(text.replace("automatic_control: prohibited", "automatic_control: allowed"), encoding="utf-8")
        try:
            module.load_hcz_upward_rule_config(unsafe)
        except module.HczUpwardRuleConfigurationError as exc:
            assert "safety" in str(exc)
        else:
            raise AssertionError("unsafe control config was accepted")
    finally:
        unsafe.unlink(missing_ok=True)


def test_sensitivity_lowering_top_temperature_changes_upward_event_count() -> None:
    module = load_module()
    records = build_records(top_delta=12.0)
    evaluation_hours = [EVALUATION]

    result = module.evaluate_hcz_rule_sensitivity(
        records,
        evaluation_hours,
        threshold_overrides={"top_temperature_delta_c": 10.0},
    )

    assert result["baseline"]["up"]["episode_count"] == 0
    assert result["scenario"]["up"]["episode_count"] == 1
    assert result["comparison"]["up"]["added_triggered_hour_count"] == 1
    assert result["parameters"]["baseline"]["top_temperature_delta_c"] == 15.0
    assert result["parameters"]["scenario"]["top_temperature_delta_c"] == 10.0
    assert result["production_defaults_changed"] is False


def test_sensitivity_reports_downward_only_as_symmetric_candidate() -> None:
    module = load_module()
    result = module.evaluate_hcz_rule_sensitivity(
        build_records(movement="down"),
        [EVALUATION],
    )

    assert result["baseline"]["up"]["episode_count"] == 0
    assert result["baseline"]["down"]["episode_count"] == 1
    assert result["baseline"]["down"]["definition"] == "symmetric_mirror_candidate"
    assert result["safety"]["downward_definition"] == "symmetric_mirror_candidate_only"


def test_sensitivity_rejects_out_of_range_or_fractional_integer_overrides() -> None:
    module = load_module()
    for overrides in (
        {"top_temperature_delta_c": -1},
        {"required_consecutive_hours": 12.5},
        {"unknown_threshold": 1},
    ):
        try:
            module.evaluate_hcz_rule_sensitivity(build_records(), [EVALUATION], threshold_overrides=overrides)
        except module.HczRuleSensitivityValidationError:
            pass
        else:
            raise AssertionError(f"unsafe sensitivity override was accepted: {overrides}")

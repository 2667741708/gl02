"""Protected calculation lineage for ABC33 factors.

This module is server-side only.  It turns one already-calibrated 0..1 factor
into an auditable snapshot containing its effective transform thresholds,
component values, source sensor values and 30-day baseline references.  The
operator/public serializers must never expose this structure.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


ALIASES = {
    "BlastEnergy": "BlastEnergy",
    "DPlower": "DP_lower",
    "DPupper": "DP_upper",
    "DP_total": "DP_total",
    "Hopper_weight": "Hopper_weight",
    "L": "L",
    "O2rate": "O2_rate",
    "PCI": "PCI_rate",
    "Pblast": "P_blast",
    "Ptop": "P_top",
    "Pcold": "P_blast_cold",
    "PN2": "P_N2",
    "QN2": "Q_N2",
    "QO2": "Q_O2",
    "Qblast": "Q_blast",
    "Tblast": "T_blast",
    "TFT": "TFT",
    "Ttap": "T_taphole_mean",
    "Ttop": "T_top",
}


# Exact component formulas used by abc_feature_builder.py.  Values named here
# are either stored features or physical source variables.  The expressions
# are admin/audit text; calculation remains in controlled Python functions.
COMPOSITES: dict[str, dict[str, Any]] = {
    "TopTempRange": {"formula": "g_H(max(T_top_A..D)-min(T_top_A..D), warn, alarm)", "sources": ["T_top_A", "T_top_B", "T_top_C", "T_top_D"]},
    "TopPressRange": {"formula": "g_H(max(P_top_gas_A..D)-min(P_top_gas_A..D), warn, alarm)", "sources": ["P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D"]},
    "StaticPressRange": {"formula": "max(g_H(layer_range, layer_warn, layer_alarm)) over complete layers", "sources": [f"P_static_{level}_{d}" for level in ("lower", "middle", "upper") for d in "ABCDEF"]},
    "DPHigh": {"formula": "max(g_H(z60_DP_total,.8,1.5),g_H(z60_DP_upper,.8,1.5),g_H(z60_DP_lower,.8,1.5))", "features": ["z60_DP_total", "z60_DP_upper", "z60_DP_lower"], "sources": ["DP_total", "DP_upper", "DP_lower"]},
    "PIBad": {"formula": "max(g_A(z60_PI,.6,1.2),g_H(z15std_PI,.8,1.5))", "features": ["z60_PI", "z15std_PI"], "sources": ["PI"]},
    "GasUtilDev": {"formula": "g_L(z60_GasUtil,-.5,-1.2)", "features": ["z60_GasUtil"], "sources": ["GasUtil"]},
    "AirAcceptBad": {"formula": ".35*g_H(z60_P_blast)+.30*g_L(z60_Q_blast)+.20*DPHigh+.15*g_H(z15std_Q_blast)", "features": ["z60_P_blast", "z60_Q_blast", "DPHigh", "z15std_Q_blast"], "sources": ["P_blast", "Q_blast", "DP_total", "DP_upper", "DP_lower"]},
    "std15_pressure_max": {"formula": "max(g_H(z15std_P_blast),g_H(z15std_DP_total),g_H(z15std_PI))", "features": ["z15std_P_blast", "z15std_DP_total", "z15std_PI"], "sources": ["P_blast", "DP_total", "PI"]},
    "std15_blast_top_max": {"formula": "max(g_H(z15std_P_blast),g_H(z15std_Q_blast),g_H(z15std_P_top))", "features": ["z15std_P_blast", "z15std_Q_blast", "z15std_P_top"], "sources": ["P_blast", "Q_blast", "P_top"]},
    "DPDistributionBad": {"formula": "g_A(z60_DP_upper-z60_DP_lower,.5,1.2)", "features": ["z60_DP_upper", "z60_DP_lower"], "sources": ["DP_upper", "DP_lower"]},
    "SpikeTopP15": {"formula": "g_H((max15(P_top)-min15(P_top))/IQR30(P_top),.8,1.5)", "features": ["z15std_P_top"], "sources": ["P_top"]},
    "LineBias": {"formula": "max(g_H(bias_deviation,warn,alarm),g_H(rate_difference,warn,alarm))", "features": ["LineBiasDeviation", "LineRateDifference"], "sources": ["L_south", "L_north"]},
    "LineLoss": {"formula": "g_H(adverse_line_deviation,.5,1.0)", "features": ["LineSouthEffectiveMax"], "sources": ["L_south"]},
    "LineLossDuration": {"formula": "g_H(trailing_low_line_minutes,duration_warn,duration_alarm)", "sources": ["L_south"]},
    "LineBiasDuration": {"formula": "g_H(trailing_bias_minutes,duration_warn,duration_alarm)", "sources": ["L_south", "L_north"]},
    "BurdenStall": {"formula": ".45*g_L(abs(slope30_L),.10,.03)+.25*g_H(z60_P_blast)+.20*DPHigh+.10*g_L(z60_Q_blast)", "features": ["slope30_L", "z60_P_blast", "DPHigh", "z60_Q_blast"], "sources": ["L", "P_blast", "Q_blast", "DP_total", "DP_upper", "DP_lower"]},
    "BurdenSlip": {"formula": ".40*g_H(LineDropRate_15,drop_warn,drop_alarm)+.25*g_H(z15std_L)+.20*g_H(z15std_P_top)+.15*g_H(z15std_DP_total)", "features": ["z15std_L", "z15std_P_top", "z15std_DP_total"], "sources": ["L", "P_top", "DP_total"]},
    "SlipFreq60": {"formula": "g_H(count60(line_step>=drop_warn),1,4)", "sources": ["L"]},
    "BodyHotRisk": {"formula": "max(g_H(z60_body),g_H(slope30_body)) over required body points", "sources_prefix": "T_body_"},
    "BodyColdRisk": {"formula": "max(g_L(z60_body),g_L(slope30_body)) over required body points", "sources_prefix": "T_body_"},
    "slopeBodyMax": {"formula": "max(g_H(slope30_body,.5,1.2)) over required body points", "sources_prefix": "T_body_"},
    "BodyTempRange": {"formula": "max(g_H(layer_temperature_range,layer_warn,layer_alarm)) over complete body layers", "sources_prefix": "T_body_"},
    "BodyColdDuration": {"formula": "g_H(trailing_body_cold_minutes,duration_warn,duration_alarm)", "sources_prefix": "T_body_"},
    "CoolingRisk": {"formula": "max(g_L(z60_Q_soft_water),g_L(z60_P_soft_water),g_L(z60_Q_high_pressure_water),g_L(z60_P_high_pressure_water),g_L(z60_P_medium_pressure_water),g_A(z60_ExpansionTankLevel))", "features": ["z60_Q_soft_water", "z60_P_soft_water", "z60_Q_high_pressure_water", "z60_P_high_pressure_water", "z60_P_medium_pressure_water", "z60_ExpansionTankLevel"], "sources": ["Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water", "P_medium_pressure_water", "ExpansionTankLevel"]},
    "CoolingFlowLow": {"formula": "max(g_L(z60_Q_soft_water),g_L(z60_Q_high_pressure_water))", "features": ["z60_Q_soft_water", "z60_Q_high_pressure_water"], "sources": ["Q_soft_water", "Q_high_pressure_water"]},
    "HeatProxy": {"formula": "max(g_A(z60_T_taphole_mean,.6,1.2),g_A(slope30_T_taphole_mean,.5,1.2),g_A(slope30_T_top,.5,1.2),g_A(z60_TFT,.6,1.2))", "features": ["z60_T_taphole_mean", "slope30_T_taphole_mean", "slope30_T_top", "z60_TFT"], "sources": ["T_taphole_1", "T_taphole_2", "TFT", "T_top_A", "T_top_B", "T_top_C", "T_top_D"]},
    "DrainProxy": {"formula": ".35*g_L(z60_T_taphole_mean)+.25*g_H(z60_DP_lower)+.20*PIBad+.20*BurdenStall", "features": ["z60_T_taphole_mean", "z60_DP_lower", "PIBad", "BurdenStall"], "sources": ["T_taphole_1", "T_taphole_2", "DP_lower", "PI", "L"]},
    "EconomicIntensityEdge": {"formula": "(.60*largest+.40*second_largest)*(0.30+0.70*operating_limit)", "features": ["EconomicIntensityStrength", "EconomicOperatingLimit"], "sources": ["Q_blast", "O2_rate", "PCI_rate", "DP_total", "PI", "GasUtil", "T_taphole_1", "T_taphole_2"]},
    "high60_heat_input": {"formula": "max(g_H(z60_T_blast),g_H(z60_PCI_rate),g_H(z60_Q_O2),g_H(z60_TFT))", "features": ["z60_T_blast", "z60_PCI_rate", "z60_Q_O2", "z60_TFT"], "sources": ["T_blast", "PCI_rate", "Q_O2", "TFT"]},
    "low60_heat_input": {"formula": "max(g_L(z60_T_blast),g_L(z60_PCI_rate),g_L(z60_Q_O2),g_L(z60_TFT))", "features": ["z60_T_blast", "z60_PCI_rate", "z60_Q_O2", "z60_TFT"], "sources": ["T_blast", "PCI_rate", "Q_O2", "TFT"]},
    "C2CompositeGate": {"formula": "1 if B1/B3 severe gate and highSlope_Ttop=SpikeTopP15=BurdenSlip=1 else 0", "features": ["highSlope_Ttop", "SpikeTopP15", "BurdenSlip"], "sources": ["P_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D", "L", "DP_total"]},
}


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _baseline_snapshot(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, Mapping):
        return None
    keys = ("baseline_day", "window_start", "window_end", "median_ref", "iqr_ref", "p25", "p75", "sample_count", "coverage_ratio", "updated_at")
    result = {key: _json_value(row.get(key)) for key in keys if row.get(key) is not None}
    return result or None


def _primitive(term: str) -> dict[str, Any] | None:
    patterns = (
        ("std15_", "z15std_", "high", .8, 1.5),
        ("abs60_", "z60_", "absolute", .6, 1.2),
        ("high60_", "z60_", "high", .8, 1.5),
        ("low60_", "z60_", "low", -.8, -1.5),
        ("absSlope_", "slope30_", "absolute", .5, 1.2),
        ("highSlope_", "slope30_", "high", .5, 1.2),
        ("lowSlope_", "slope30_", "low", -.5, -1.2),
    )
    for prefix, source_prefix, mode, a, b in patterns:
        if not term.startswith(prefix):
            continue
        suffix = term[len(prefix):]
        severe = suffix.endswith("_severe")
        if severe:
            suffix = suffix[:-7]
            if mode == "low":
                a, b = (-1.2, -2.0)
        if term == "low60_Pcold_severe":
            a, b = (-1.0, -1.8)
        variable = ALIASES.get(suffix, suffix)
        sources = [variable]
        if variable == "T_taphole_mean":
            sources = ["T_taphole_1", "T_taphole_2"]
        elif variable == "T_top":
            sources = ["T_top_A", "T_top_B", "T_top_C", "T_top_D"]
        return {
            "formula": f"g_{mode}({source_prefix}{variable},{a},{b})",
            "features": [f"{source_prefix}{variable}"],
            "sources": sources,
            "baseline_sources": [variable],
            "transform": {"mode": mode, "a": a, "b": b, "input": f"{source_prefix}{variable}"},
        }
    return None


def build_factor_audit(features: Mapping[str, Any], current: Mapping[str, Any], baseline: Mapping[str, Any],
                       thresholds: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Build admin-only lineage for every available factor."""
    cfg = dict(thresholds or {})
    result: dict[str, dict[str, Any]] = {}
    for term, factor_value in features.items():
        spec = dict(COMPOSITES.get(term) or _primitive(term) or {})
        sources = list(spec.get("sources") or [])
        prefix = spec.get("sources_prefix")
        if prefix:
            sources.extend(sorted(key for key in current if re.fullmatch(r"T_body_L(?:[7-9]|1[0-6])_[A-H]", str(key))))
        source_values: dict[str, Any] = {}
        baseline_values: dict[str, Any] = {}
        for name in dict.fromkeys(sources):
            if name in current:
                source_values[name] = _json_value(current.get(name))
        baseline_sources = list(spec.get("baseline_sources") or sources)
        for name in dict.fromkeys(baseline_sources):
            row = _baseline_snapshot(baseline.get(name))
            if row:
                baseline_values[name] = row
        feature_values = {name: _json_value(features.get(name)) for name in spec.get("features", []) if name in features}
        effective: dict[str, Any] = {"factor_stage": {"mode": "precalibrated_0_1", "minimum": 0.0, "maximum": 1.0, "second_threshold_applied": False}}
        if spec.get("transform"):
            effective["input_transform"] = spec["transform"]
        if term == "TopTempRange":
            effective["input_transform"] = {**dict(cfg.get("top_temperature_range") or {}), "mode": "high"}
        elif term == "TopPressRange":
            effective["input_transform"] = {**dict(cfg.get("top_pressure_range") or {}), "mode": "high"}
        elif term == "StaticPressRange":
            effective["input_transform"] = dict(cfg.get("static_pressure_range") or {})
        elif term == "BodyTempRange":
            effective["input_transform"] = dict(cfg.get("body_temperature_range") or {})
        elif term in {"LineBias", "LineLoss", "BurdenSlip", "SlipFreq60"}:
            effective["line"] = dict(cfg.get("line") or {})
        elif term in {"LineLossDuration", "LineBiasDuration", "BodyColdDuration"}:
            effective["duration_minutes"] = dict(cfg.get("duration_minutes") or {})
        result[str(term)] = {
            "factor_value": factor_value,
            "formula": spec.get("formula") or "direct feature value",
            "source_features": feature_values,
            "source_values": source_values,
            "baseline_snapshot": baseline_values,
            "effective_thresholds": effective,
        }
    return result

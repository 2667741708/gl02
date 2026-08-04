"""Expanded process-semantic neuron grouping for the V2 proxy experiment."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


PRIMARY_ABSOLUTE_ERROR_TOLERANCE = 0.05
LEGACY_ABSOLUTE_ERROR_TOLERANCE = 0.10


NEURON_METADATA: dict[str, dict[str, Any]] = {
    "fuel_oxygen_input": {"display_name": "燃料与富氧输入"},
    "blast_tapping_thermal": {"display_name": "鼓风与出铁热状态"},
    "permeability_level": {"display_name": "透气性与压差水平"},
    "permeability_stability": {"display_name": "透气性与压差稳定性"},
    "top_pressure_control": {"display_name": "炉顶压力控制"},
    "gas_utilization": {"display_name": "煤气利用状态"},
    "top_temperature": {"display_name": "炉顶温度状态"},
    "body_layer_temperature": {"display_name": "炉体分层热状态"},
    "body_layer_stability": {"display_name": "炉体分层热稳定性"},
    "body_vertical_profile": {"display_name": "炉体纵向温度梯度"},
    "body_circumference": {"display_name": "炉体圆周均匀性"},
    "body_sector_distribution": {"display_name": "炉体方位煤气流分布"},
    "burden_level": {"display_name": "料线空间状态"},
    "charging_dynamics": {"display_name": "装料与料线动态"},
    "diagnosis_thermal": {"display_name": "热制度诊断"},
    "diagnosis_gas_flow": {"display_name": "煤气流诊断"},
    "diagnosis_normality": {"display_name": "顺行状态诊断"},
    "diagnosis_confidence": {"display_name": "诊断置信度"},
    "data_quality": {"display_name": "输入数据可信度"},
    "previous_si_level": {"display_name": "前序炉Si水平惯性"},
    "previous_si_trend": {"display_name": "前序炉Si变化趋势"},
}


def _assign_group(column: str) -> str | None:
    lower = column.lower()
    if lower.startswith("history__previous_"):
        return "previous_si_trend" if "slope" in lower else "previous_si_level"
    if lower in {
        "diagnosis__coverage_ratio",
        "diagnosis__missing_variable_count",
    }:
        return "data_quality"
    if lower.startswith("diagnosis__"):
        return "diagnosis_confidence"
    if lower in {"score__cold", "score__hot"}:
        return "diagnosis_thermal"
    if lower in {
        "score__center",
        "score__edge",
        "score__channel",
        "score__column",
        "score__lowline",
    }:
        return "diagnosis_gas_flow"
    if lower == "score__normal":
        return "diagnosis_normality"
    if "gasutil" in lower:
        return "gas_utilization"
    if any(token in lower for token in ("pci", "q_o2", "o2_intensity")):
        return "fuel_oxygen_input"
    if any(token in lower for token in ("t_blast", "t_taphole")):
        return "blast_tapping_thermal"
    if "p_top_gas_range" in lower or "high_pressure" in lower:
        return "top_pressure_control"
    pressure_tokens = (
        "dp_lower",
        "dp_total",
        "dp_upper",
        "_pi",
        "p_blast",
        "p_top",
        "q_blast",
    )
    if any(token in lower for token in pressure_tokens):
        return (
            "permeability_stability"
            if "zstd_" in lower
            else "permeability_level"
        )
    if "t_top" in lower:
        return "top_temperature"
    if "t_body_circ_" in lower:
        return "body_circumference"
    if any(
        token in lower
        for token in (
            "sector",
            "hotdev",
            "hotspot",
            "disp",
            "spiketop",
            "coldsectorscore",
        )
    ):
        return "body_sector_distribution"
    if any(
        token in lower
        for token in (
            "t_body_lower",
            "t_body_middle",
            "t_body_upper",
            "g_body_lower_upper",
        )
    ):
        return "body_vertical_profile"
    if any(
        token in lower
        for token in ("t_body_mean_l", "z60_t_body_l", "zstd_t_body_l")
    ):
        return (
            "body_layer_stability"
            if "zstd_" in lower
            else "body_layer_temperature"
        )
    if any(
        token in lower
        for token in (
            "deltal",
            "l_current",
            "l_diff",
            "l_effective",
            "z60_l",
            "zstd_l",
        )
    ):
        return "burden_level"
    if any(
        token in lower
        for token in ("dropbatch", "l_slope", "probe_", "charge_")
    ):
        return "charging_dynamics"
    return None


def expanded_semantic_feature_groups(
    columns: Sequence[str],
) -> dict[str, list[str]]:
    """Split V1 rule features into smaller, auditable process neurons."""

    groups = {name: [] for name in NEURON_METADATA}
    assigned: set[str] = set()
    for column in columns:
        group = _assign_group(column)
        if group is None:
            continue
        if column in assigned:
            raise ValueError(f"feature assigned more than once: {column}")
        groups[group].append(column)
        assigned.add(column)
    return {name: values for name, values in groups.items() if values}


def expanded_neuron_display_name(group_name: str) -> str:
    return str(
        NEURON_METADATA.get(group_name, {}).get("display_name", group_name)
    )

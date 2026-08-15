"""Build the calibrated 60/15/30 minute inputs for the ABC33 rules.

REQ-ABC33-FORMULA-CALIBRATED-REPLAY-20260808.  Missing or low-quality
windows stay missing: this module never substitutes zero for sensor data.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from abc_factor_audit import build_factor_audit

MIN_COVERAGE = .75
TOP_STATE_HOLD_MINUTES = 5
DEFAULT_STATE_HOLD_MINUTES = 5
BODY_STATE_HOLD_MINUTES = 15
BODY_POINT_NAMES = tuple(
    f"T_body_L{level}_{direction}"
    for level in range(7, 17)
    for direction in "ABCDEFGH"
)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _high(x: float | None, a: float, b: float) -> float | None:
    return None if x is None or not b > a else _clip((x - a) / (b - a))


def _low(x: float | None, a: float, b: float) -> float | None:
    return None if x is None or not a > b else _clip((a - x) / (a - b))


def _absolute(x: float | None, a: float, b: float) -> float | None:
    return None if x is None or not b > a else _clip((abs(x) - a) / (b - a))


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _samples(history: Mapping[str, Iterable[Any]] | None, name: str, minutes: int) -> list[tuple[float, float]]:
    if not history or name not in history:
        return []
    raw = list(history[name])
    timestamps = list(history.get("timestamps", []))
    if timestamps:
        if len(timestamps) != len(raw):
            return []
        parsed = [_timestamp(item) for item in timestamps]
        valid_times = [item for item in parsed if item is not None]
        if not valid_times:
            return []
        evaluation_ts = _timestamp(history.get("evaluation_ts"))
        end = evaluation_ts or max(valid_times)
        buckets: dict[int, tuple[datetime, float]] = {}
        for stamp, item in zip(parsed, raw):
            value = _number(item)
            if stamp is None or value is None:
                continue
            age = (end - stamp).total_seconds() / 60
            if 0 <= age < minutes:
                bucket = math.floor(stamp.timestamp() / 60)
                previous = buckets.get(bucket)
                if previous is None or stamp >= previous[0]:
                    buckets[bucket] = (stamp, value)
        return sorted(((stamp-end).total_seconds()/60, value) for stamp, value in buckets.values())
    start = max(0, len(raw) - minutes)
    return [(float(index - len(raw) + 1), value) for index, item in enumerate(raw[start:], start=start)
            if (value := _number(item)) is not None]


def _values(history: Mapping[str, Iterable[Any]] | None, name: str, minutes: int) -> list[float]:
    return [value for _, value in _samples(history, name, minutes)]


def _enough(values: list[float], minutes: int) -> bool:
    return len(values) >= math.ceil(minutes * MIN_COVERAGE)


def _std(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _slope30(samples: list[tuple[float, float]], iqr: float) -> float | None:
    xbar = sum(x for x, _ in samples) / len(samples)
    ybar = sum(y for _, y in samples) / len(samples)
    denominator = sum((x - xbar) ** 2 for x, _ in samples)
    if denominator <= 0:
        return None
    return (sum((x - xbar) * (y - ybar) for x, y in samples) / denominator) * 30 / iqr


def _baseline_row(baseline: Mapping[str, Mapping[str, Any]] | None, name: str) -> tuple[float, float] | None:
    row = (baseline or {}).get(name)
    if not isinstance(row, Mapping):
        return None
    median = _number(row.get("median_ref"))
    iqr = _number(row.get("iqr_ref"))
    coverage = _number(row.get("coverage_ratio"))
    if median is None or iqr is None or iqr <= 0 or coverage is None or coverage < MIN_COVERAGE:
        return None
    return median, iqr


def _put(target: dict[str, float], quality: dict[str, Any], key: str, value: float | None) -> None:
    if value is not None and math.isfinite(value):
        target[key] = float(value)
        quality[key] = {"available": True}


def _bounded_hold_aligned_series(history: dict[str, Any], names: Iterable[str], hold_minutes: int) -> None:
    """Carry a state value only across a short, explicit minute gap.

    This does not invent a trend or fill a long outage.  A value observed at
    10:00 may represent the state at 10:01..10:05 when ``hold_minutes=5``;
    10:06 is missing unless a new observation arrived.
    """
    timestamps = list(history.get("timestamps", []))
    parsed = [_timestamp(item) for item in timestamps]
    if not timestamps or any(item is None for item in parsed):
        return
    for name in names:
        raw = history.get(name)
        if raw is None:
            continue
        values = list(raw)
        if len(values) != len(parsed):
            continue
        held: list[float | None] = []
        last_value: float | None = None
        last_stamp: datetime | None = None
        for stamp, item in zip(parsed, values):
            value = _number(item)
            if value is not None:
                last_value = value
                last_stamp = stamp
                held.append(value)
                continue
            if last_value is not None and last_stamp is not None and 0 <= (stamp-last_stamp).total_seconds() <= hold_minutes*60:
                held.append(last_value)
            else:
                held.append(None)
        history[name] = held


def _factor(features: Mapping[str, float], key: str) -> float | None:
    return _number(features.get(key))


def _max_available(*values: float | None) -> float | None:
    usable = [v for v in values if v is not None]
    return max(usable) if usable else None


def _max_required(*values: float | None) -> float | None:
    return max(values) if values and all(value is not None for value in values) else None


def _weighted(parts: list[tuple[float, float | None]]) -> float | None:
    return sum(w * v for w, v in parts) if all(v is not None for _, v in parts) else None


def standardized_window_features(history: Mapping[str, Iterable[Any]], baseline: Mapping[str, Mapping[str, Any]], name: str) -> dict[str, float]:
    """Reusable implementation of z60_X, z15std_X and slope30_X.

    A feature is omitted unless its own window and 30-day baseline pass the
    75% gate.  This public helper is intentionally independent of any A/B/C
    rule so it can be replayed and tested before rule formulas are enabled.
    """
    ref = _baseline_row(baseline, name)
    if ref is None:
        return {}
    median, iqr = ref
    result: dict[str, float] = {}
    samples60, samples15, samples30 = (_samples(history, name, size) for size in (60, 15, 30))
    v60 = [value for _, value in samples60]
    v15 = [value for _, value in samples15]
    if _enough(v60, 60):
        result[f"z60_{name}"] = (sum(v60) / len(v60) - median) / iqr
    if _enough(v15, 15) and len(v15) > 1:
        result[f"z15std_{name}"] = _std(v15) / (iqr / 1.35)
    if _enough(samples30, 30) and len(samples30) > 1:
        slope = _slope30(samples30, iqr)
        if slope is not None:
            result[f"slope30_{name}"] = slope
    return result


def _trailing_true(values: list[bool]) -> int:
    count = 0
    for value in reversed(values):
        if not value:
            break
        count += 1
    return count


def _trailing_minutes(samples: list[tuple[float, float]], predicate: Any) -> float | None:
    """Duration of the final continuous true run on a minute-bucketed axis."""
    if not samples or samples[-1][0] < -1.5:
        return None
    if not predicate(samples[-1][1]):
        return 0.0
    start = samples[-1][0]
    newer = samples[-1][0]
    for minute, value in reversed(samples[:-1]):
        if newer - minute > 1.5 or not predicate(value):
            break
        start = minute
        newer = minute
    return samples[-1][0] - start + 1.0


def _rolling_max_samples(
    history: Mapping[str, Iterable[Any]],
    name: str,
    *,
    lookback_minutes: float,
    minimum_valid_value: float | None = None,
    limit_minutes: int = 90,
) -> list[tuple[float, float]]:
    """Return trailing-window maxima on the existing minute axis.

    Reciprocating stockline probes report both lifted and lowered positions.
    The lowered reading is represented by the recent non-negative maximum;
    preserving the original minute axis keeps duration checks auditable.
    """
    samples = _samples(history, name, limit_minutes)
    result: list[tuple[float, float]] = []
    for minute, _ in samples:
        candidates = [
            value for sample_minute, value in samples
            if 0 <= minute - sample_minute < lookback_minutes
            and (minimum_valid_value is None or value >= minimum_valid_value)
        ]
        if candidates:
            result.append((minute, max(candidates)))
    return result


def _rolling_min_samples(
    history: Mapping[str, Iterable[Any]],
    name: str,
    *,
    lookback_minutes: float,
    minimum_valid_value: float | None = None,
    limit_minutes: int = 90,
) -> list[tuple[float, float]]:
    samples = _samples(history, name, limit_minutes)
    result: list[tuple[float, float]] = []
    for minute, _ in samples:
        candidates = [
            value for sample_minute, value in samples
            if 0 <= minute - sample_minute < lookback_minutes
            and (minimum_valid_value is None or value >= minimum_valid_value)
        ]
        if candidates:
            result.append((minute, min(candidates)))
    return result


def _current_range(current: Mapping[str, Any], names: tuple[str, ...], field_timestamps: Mapping[str, Any] | None,
                   evaluation_ts: Any, *, maximum_hold_seconds: int = 300,
                   minimum_valid_value: float | None = None) -> float | None:
    values = [_number(current.get(name)) for name in names]
    if not all(value is not None for value in values):
        return None
    if minimum_valid_value is not None and any(value <= minimum_valid_value for value in values):
        return None
    if field_timestamps is not None:
        stamps = [_timestamp(field_timestamps.get(name)) for name in names]
        if not all(stamp is not None for stamp in stamps):
            return None
        end = _timestamp(evaluation_ts) or max(stamps)
        if any(not 0 <= (end-stamp).total_seconds() <= maximum_hold_seconds for stamp in stamps):
            return None
        if (max(stamps)-min(stamps)).total_seconds() > maximum_hold_seconds:
            return None
    return max(values) - min(values)


def build_feature_snapshot(current: Mapping[str, Any], *, baseline: Mapping[str, Mapping[str, Any]] | None = None,
                           history: Mapping[str, Iterable[Any]] | None = None, data_age_seconds: float | None = None,
                           coverage_ratio: float = 1.0, thresholds: Mapping[str, Any] | None = None,
                           current_timestamps: Mapping[str, Any] | None = None) -> tuple[dict[str, float], dict[str, Any]]:
    working_current = dict(current)
    working_history: dict[str, Any] = {}
    for key, value in (history or {}).items():
        working_history[str(key)] = value if key == "evaluation_ts" else list(value)
    working_baseline = {str(k): dict(v) for k, v in (baseline or {}).items() if isinstance(v, Mapping)}
    # New operator/MCP contracts use P_top_A-D. Keep the existing trained
    # feature names during the compatibility window without duplicating data.
    for position in "ABCD":
        canonical = f"P_top_{position}"
        legacy = f"P_top_gas_{position}"
        if canonical in working_current and legacy not in working_current:
            working_current[legacy] = working_current[canonical]
        if canonical in working_history and legacy not in working_history:
            working_history[legacy] = list(working_history[canonical])
        if canonical in working_baseline and legacy not in working_baseline:
            working_baseline[legacy] = dict(working_baseline[canonical])
    hold_cfg = dict((thresholds or {}).get("state_hold_minutes", {}))
    short_hold_minutes = int(hold_cfg.get("default", DEFAULT_STATE_HOLD_MINUTES))
    body_hold_minutes = int(hold_cfg.get("furnace_body", BODY_STATE_HOLD_MINUTES))
    body_sources = [name for name in BODY_POINT_NAMES if name in working_history or name in working_baseline]
    static_pressure_sources = tuple(
        f"P_static_{level}_{direction}"
        for level in ("lower", "middle", "upper")
        for direction in "ABCDEF"
    )
    short_state_sources = (
        "T_top_A", "T_top_B", "T_top_C", "T_top_D",
        "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
        "L", "L_south", "L_north",
        "Q_soft_water", "P_soft_water", "Q_high_pressure_water",
        "P_high_pressure_water", "P_medium_pressure_water", "ExpansionTankLevel",
        *static_pressure_sources,
    )
    _bounded_hold_aligned_series(working_history, short_state_sources, short_hold_minutes)
    _bounded_hold_aligned_series(working_history, body_sources, body_hold_minutes)
    aligned_timestamps = list(working_history.get("timestamps", []))
    held_current_timestamps = dict(current_timestamps or {})
    if aligned_timestamps:
        for name in (*short_state_sources, *body_sources):
            values = working_history.get(name)
            if _number(working_current.get(name)) is None and values and _number(values[-1]) is not None:
                working_current[name] = _number(values[-1])
                held_current_timestamps[name] = aligned_timestamps[-1]
    for derived, sources in {"T_taphole_mean": ("T_taphole_1", "T_taphole_2"), "T_top": ("T_top_A", "T_top_B", "T_top_C", "T_top_D")}.items():
        present = [_number(working_current.get(k)) for k in sources]
        if _number(working_current.get(derived)) is None and all(v is not None for v in present):
            working_current[derived] = sum(present) / len(present)
        series = [working_history.get(k, []) for k in sources]
        if derived not in working_history and series and all(series):
            timestamp_count = len(working_history.get("timestamps", []))
            aligned_size = timestamp_count or len(series[0])
            if aligned_size and all(len(values) == aligned_size for values in series):
                combined = []
                for index in range(aligned_size):
                    row = [_number(values[index]) for values in series]
                    combined.append(sum(row) / len(row) if all(v is not None for v in row) else None)
                working_history[derived] = combined
        # A median/IQR of an arithmetic mean is not the arithmetic mean of the
        # component medians/IQRs.  A derived 30-day baseline must therefore be
        # supplied explicitly by the baseline maintainer.
    features: dict[str, float] = {}
    quality: dict[str, Any] = {"coverage_ratio": coverage_ratio, "data_age_seconds": data_age_seconds}
    for key, value in working_current.items():
        _put(features, quality, str(key), _number(value))
    for factor in (
        "BurdenRateHalfHourDev", "BurdenRateYesterdayDev", "BurdenRate2hDev",
        "BurdenRateHalfHourSlow", "BurdenRateYesterdaySlow", "BurdenRate2hSlow",
        "BurdenRateHalfHourFast", "BurdenRateYesterdayFast", "BurdenRate2hFast",
    ):
        if _number(working_current.get(factor)) is not None:
            quality[factor] = {
                "available": True,
                "required": True,
                "source": "pSpace south/north stockline probe cadence with hopper-weight classification",
            }
        else:
            quality[factor] = {
                "available": False,
                "required": True,
                "source": "pSpace south/north stockline probe cadence with hopper-weight classification",
                "missing_reason": "南北探尺周期、料罐重量分型、历史比较窗口或新鲜度不足",
            }

    if coverage_ratio < MIN_COVERAGE or (data_age_seconds is not None and data_age_seconds > 300):
        quality["window_features_available"] = False
        quality["blocking_reason"] = "coverage_below_75_percent" if coverage_ratio < MIN_COVERAGE else "data_older_than_5_minutes"
        quality["factor_audit"] = build_factor_audit(features, working_current, working_baseline, thresholds)
        return features, quality
    quality["window_features_available"] = True

    names = set(working_baseline) | {str(k) for k in working_history if k not in {"timestamps", "evaluation_ts"}}
    for name in names:
        for key, value in standardized_window_features(working_history, working_baseline, name).items():
            _put(features, quality, key, value)

    # Pointwise-derived signals use their own baseline when supplied.  If a
    # derived baseline is absent they remain unavailable rather than borrowing
    # a physically different sensor's baseline.
    evaluation_ts = working_history.get("evaluation_ts") or current.get("evaluation_ts")
    range_timestamps = held_current_timestamps if held_current_timestamps else None
    top_temp_range = _current_range(working_current, ("T_top_A", "T_top_B", "T_top_C", "T_top_D"),
                                    range_timestamps, evaluation_ts)
    top_press_range = _current_range(working_current, ("P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D"),
                                     range_timestamps, evaluation_ts)
    top_temp_cfg = dict((thresholds or {}).get("top_temperature_range", {}))
    top_press_cfg = dict((thresholds or {}).get("top_pressure_range", {}))
    _put(features, quality, "TopTempRange", _high(top_temp_range,
         _number(top_temp_cfg.get("warn")) or 10, _number(top_temp_cfg.get("alarm")) or 35))
    _put(features, quality, "TopPressRange", _high(top_press_range,
         _number(top_press_cfg.get("warn")) or 8, _number(top_press_cfg.get("alarm")) or 25))
    static_cfg = dict((thresholds or {}).get("static_pressure_range", {}))
    static_warn, static_alarm = _number(static_cfg.get("warn")), _number(static_cfg.get("alarm"))
    static_levels = dict(static_cfg.get("levels") or {})
    static_risks: list[float] = []
    static_missing: list[str] = []
    minimum_static = _number(static_cfg.get("minimum_valid_value"))
    required_static_directions = int(static_cfg.get("required_directions_per_layer", 2))
    for level in ("lower", "middle", "upper"):
        level_cfg = dict(static_levels.get(level) or {})
        warn = _number(level_cfg.get("warn")) if level_cfg else static_warn
        alarm = _number(level_cfg.get("alarm")) if level_cfg else static_alarm
        names_in_level = tuple(
            f"P_static_{level}_{direction}" for direction in "ABCDEF"
            if _number(working_current.get(f"P_static_{level}_{direction}")) is not None
        )
        if len(names_in_level) < required_static_directions:
            static_missing.append(level)
            continue
        spread = _current_range(working_current, names_in_level, range_timestamps, evaluation_ts,
                                minimum_valid_value=minimum_static)
        risk = _high(spread, warn, alarm) if warn is not None and alarm is not None else None
        if risk is None:
            static_missing.append(level)
        else:
            static_risks.append(risk)
    minimum_static_layers = int(static_cfg.get("minimum_complete_layers", 1))
    if len(static_risks) >= minimum_static_layers:
        _put(features, quality, "StaticPressRange", max(static_risks))
        quality["StaticPressRange"]["missing_layers"] = static_missing

    z = lambda n: _factor(features, f"z60_{n}")
    s = lambda n: _factor(features, f"z15std_{n}")
    p = lambda n: _factor(features, f"slope30_{n}")
    high = lambda n, a=.8, b=1.5: _high(z(n), a, b)
    low = lambda n, a=-.8, b=-1.5: _low(z(n), a, b)
    absolute = lambda n, a=.6, b=1.2: _absolute(z(n), a, b)
    std = lambda n, a=.8, b=1.5: _high(s(n), a, b)
    slope_hi = lambda n, a=.5, b=1.2: _high(p(n), a, b)
    slope_lo = lambda n, a=-.5, b=-1.2: _low(p(n), a, b)

    dp_high = _max_required(high("DP_total"), high("DP_upper"), high("DP_lower"))
    pi_bad = _max_required(absolute("PI"), std("PI"))
    _put(features, quality, "DPHigh", dp_high)
    _put(features, quality, "PIBad", pi_bad)
    _put(features, quality, "GasUtilDev", low("GasUtil", -.5, -1.2))
    _put(features, quality, "AirAcceptBad", _weighted([(.35, high("P_blast")), (.30, low("Q_blast")), (.20, dp_high), (.15, std("Q_blast"))]))

    # Pre-normalized primitives used by the exact catalogue.  The rule engine
    # consumes these 0..1 factors directly and never thresholds physical units.
    primitives = {
        "std15_P_top": std("P_top"), "std15_DP_total": std("DP_total"), "std15_Q_blast": std("Q_blast"),
        "std15_P_blast": std("P_blast"), "std15_PI": std("PI"), "std15_L": std("L"),
        "std15_Hopper_weight": std("Hopper_weight"), "std15_Ttap": std("T_taphole_mean"),
        "abs60_Ttap": absolute("T_taphole_mean"), "absSlope_Ttap": _absolute(p("T_taphole_mean"), .5, 1.2), "lowSlope_Ttap": slope_lo("T_taphole_mean"),
        "absSlope_Ttop": _absolute(p("T_top"), .5, 1.2), "highSlope_Ttop": slope_hi("T_top"), "lowSlope_Ttop": slope_lo("T_top"),
        "low60_Ttap": low("T_taphole_mean"), "high60_Ttap": high("T_taphole_mean"),
        "high60_Pblast": high("P_blast"), "low60_Pblast": low("P_blast"), "high60_Qblast": high("Q_blast"),
        "high60_O2rate": high("O2_rate"), "high60_PCI": high("PCI_rate"),
        "low60_Qblast": low("Q_blast"), "low60_Qblast_severe": low("Q_blast", -1.2, -2.0),
        "low60_Pblast_severe": low("P_blast", -1.2, -2.0), "low60_Ptop": low("P_top"),
        "abs60_Ptop": absolute("P_top"), "low60_Pcold_severe": low("P_blast_cold", -1.0, -1.8),
        "low60_QN2": low("Q_N2"), "low60_PN2": low("P_N2"), "high60_DPupper": high("DP_upper"),
        "high60_DPlower": high("DP_lower"), "low60_PI": low("PI"), "high60_PI": high("PI"),
        "abs60_Qblast": absolute("Q_blast"), "abs60_Pblast": absolute("P_blast"),
        "abs60_PCI": absolute("PCI_rate"), "abs60_O2rate": absolute("O2_rate"), "abs60_QO2": absolute("Q_O2"),
        "abs60_Tblast": absolute("T_blast"), "abs60_TFT": absolute("TFT"), "high60_BlastEnergy": high("BlastEnergy"),
        "abs60_BlastEnergy": absolute("BlastEnergy"),
        "low60_heat_input": _max_required(low("T_blast"), low("PCI_rate"), low("Q_O2"), low("TFT")),
        "high60_heat_input": _max_required(high("T_blast"), high("PCI_rate"), high("Q_O2"), high("TFT")),
    }
    for key, value in primitives.items():
        _put(features, quality, key, value)
    _put(features, quality, "std15_pressure_max", _max_required(std("P_blast"), std("DP_total"), std("PI")))
    _put(features, quality, "std15_blast_top_max", _max_required(std("P_blast"), std("Q_blast"), std("P_top")))
    zu, zl = z("DP_upper"), z("DP_lower")
    _put(features, quality, "DPDistributionBad", _absolute(zu - zl, .5, 1.2) if zu is not None and zl is not None else None)
    ptop15 = _values(working_history, "P_top", 15)
    ptop_ref = _baseline_row(working_baseline, "P_top")
    if _enough(ptop15, 15) and ptop_ref:
        _put(features, quality, "SpikeTopP15", _high((max(ptop15) - min(ptop15)) / ptop_ref[1], .8, 1.5))

    line_cfg = dict((thresholds or {}).get("line", {}))
    normal_line = _number(line_cfg.get("normal_level"))
    primary_line = str(line_cfg.get("primary_variable") or "L")
    line_window = float(_number(line_cfg.get("effective_window_minutes")) or 1.0)
    line_minimum = _number(line_cfg.get("minimum_valid_value"))
    if primary_line in {"L_north", "L_south"} and line_window > 1:
        line_samples = _rolling_max_samples(
            working_history,
            primary_line,
            lookback_minutes=line_window,
            minimum_valid_value=line_minimum,
            limit_minutes=90,
        )
        line = line_samples[-1][1] if line_samples else _number(working_current.get(primary_line))
    else:
        line_samples = _samples(working_history, primary_line, 90)
        line = _number(working_current.get(primary_line))
    north_effective = _rolling_max_samples(
        working_history, "L_north", lookback_minutes=line_window,
        minimum_valid_value=line_minimum, limit_minutes=90,
    )
    south_effective = _rolling_max_samples(
        working_history, "L_south", lookback_minutes=line_window,
        minimum_valid_value=line_minimum, limit_minutes=90,
    )
    north_minimum = _rolling_min_samples(
        working_history, "L_north", lookback_minutes=line_window,
        minimum_valid_value=line_minimum, limit_minutes=90,
    )
    south_minimum = _rolling_min_samples(
        working_history, "L_south", lookback_minutes=line_window,
        minimum_valid_value=line_minimum, limit_minutes=90,
    )
    _put(features, quality, "LineNorthEffectiveMax", north_effective[-1][1] if north_effective else None)
    _put(features, quality, "LineNorthEffectiveMin", north_minimum[-1][1] if north_minimum else None)
    _put(features, quality, "LineSouthEffectiveMax", south_effective[-1][1] if south_effective else None)
    _put(features, quality, "LineSouthEffectiveMin", south_minimum[-1][1] if south_minimum else None)
    line_bias_deviation = None
    line_rate_difference = None
    expected_bias = _number(line_cfg.get("south_north_bias_mean"))
    north_by_minute = {round(minute, 6): value for minute, value in north_effective}
    paired_effective = [
        (minute, south_value, north_by_minute[round(minute, 6)])
        for minute, south_value in south_effective if round(minute, 6) in north_by_minute
    ]
    if paired_effective and expected_bias is not None:
        line_bias_deviation = abs((paired_effective[-1][1]-paired_effective[-1][2])-expected_bias)
    elif expected_bias is not None:
        current_south = _number(working_current.get("L_south"))
        current_north = _number(working_current.get("L_north"))
        if current_south is not None and current_north is not None:
            line_bias_deviation = abs((current_south-current_north)-expected_bias)
    if len(paired_effective) > 1:
        south_rate = paired_effective[-1][1]-paired_effective[-2][1]
        north_rate = paired_effective[-1][2]-paired_effective[-2][2]
        line_rate_difference = abs(south_rate-north_rate)
    bias_warn = _number(line_cfg.get("bias_deviation_warn"))
    bias_alarm = _number(line_cfg.get("bias_deviation_alarm"))
    rate_warn = _number(line_cfg.get("rate_difference_warn"))
    rate_alarm = _number(line_cfg.get("rate_difference_alarm"))
    _put(features, quality, "LineBiasDeviation", line_bias_deviation)
    _put(features, quality, "LineRateDifference", line_rate_difference)
    line_direction = str(line_cfg.get("loss_direction", "higher")).lower()
    if line is not None and normal_line is not None and line_direction in {"higher", "lower"}:
        line_deviation = line - normal_line if line_direction == "higher" else normal_line - line
        line_loss = _high(line_deviation, .5, 1.0)
    else:
        line_loss = None
    _put(features, quality, "LineBias", _max_available(
        _high(line_bias_deviation, bias_warn, bias_alarm)
        if bias_warn is not None and bias_alarm is not None else None,
        _high(line_rate_difference, rate_warn, rate_alarm)
        if rate_warn is not None and rate_alarm is not None else None,
    ))
    _put(features, quality, "LineLoss", line_loss)
    duration_cfg = dict((thresholds or {}).get("duration_minutes", {}))
    duration_warn = _number(duration_cfg.get("warn"))
    duration_alarm = _number(duration_cfg.get("alarm"))
    if normal_line is not None and duration_warn is not None and duration_alarm is not None:
        duration = _trailing_minutes(
            line_samples,
            lambda value: (value-normal_line >= .5) if line_direction == "higher" else (normal_line-value >= .5),
        )
        _put(features, quality, "LineLossDuration", _high(duration, duration_warn, duration_alarm))
    if duration_warn is not None and duration_alarm is not None and paired_effective and expected_bias is not None:
        bias_samples = [(minute, abs((south_value-north_value)-expected_bias))
                        for minute, south_value, north_value in paired_effective]
        trigger = bias_warn if bias_warn is not None else .5
        duration = _trailing_minutes(bias_samples, lambda value: value >= trigger)
        _put(features, quality, "LineBiasDuration", _high(duration, duration_warn, duration_alarm))
    burden_stall = _weighted([(.45, _low(abs(p("L")) if p("L") is not None else None, .10, .03)), (.25, high("P_blast")), (.20, dp_high), (.10, low("Q_blast"))])
    _put(features, quality, "BurdenStall", burden_stall)

    drop = _number(current.get("LineDropRate_15"))
    drop_warn = _number(line_cfg.get("drop_warn"))
    drop_alarm = _number(line_cfg.get("drop_alarm"))
    if drop is None:
        recent_line = _values(working_history, "L", 15)
        if len(recent_line) > 1:
            signed_changes = [(right-left) if line_direction == "higher" else (left-right)
                              for left, right in zip(recent_line, recent_line[1:])]
            drop = max(signed_changes)
    burden_slip = _weighted([(.40, _high(drop, drop_warn, drop_alarm) if drop_warn is not None and drop_alarm is not None else None),
                             (.25, std("L")), (.20, std("P_top")), (.15, std("DP_total"))])
    _put(features, quality, "BurdenSlip", burden_slip)
    l60 = _values(working_history, "L", 60)
    if drop_warn is not None and len(l60) > 1:
        slip_count = sum(1 for left, right in zip(l60, l60[1:]) if abs(right - left) >= drop_warn)
        _put(features, quality, "SlipFreq60", _high(slip_count, 1, 4))

    body_names = [k for k in BODY_POINT_NAMES if k in names]
    body_hot = _max_required(*[x for n in body_names for x in (high(n), slope_hi(n))])
    body_cold = _max_required(*[x for n in body_names for x in (low(n), slope_lo(n))])
    _put(features, quality, "BodyHotRisk", body_hot)
    _put(features, quality, "BodyColdRisk", body_cold)
    _put(features, quality, "slopeBodyMax", _max_required(*[slope_hi(n) for n in body_names]))
    # A C-class safety event must not be confirmed by the maximum of one
    # furnace-body point.  Keep the document-level maxima above for formula
    # traceability, and additionally build independent concurrence factors for
    # the operational event gate.  Concurrence requires several physical
    # points; escalation requires the same points to be both high and rising.
    body_point_hot: list[float] = []
    body_point_escalation: list[float] = []
    for name in body_names:
        high_risk = high(name)
        slope_risk = slope_hi(name)
        point_risk = _max_required(high_risk, slope_risk)
        if point_risk is not None:
            body_point_hot.append(float(point_risk))
        if high_risk is not None and slope_risk is not None:
            body_point_escalation.append(min(float(high_risk), float(slope_risk)))
    if len(body_point_hot) >= 3:
        _put(features, quality, "BodyHotConcurrence", sum(sorted(body_point_hot, reverse=True)[:3]) / 3.0)
    if len(body_point_escalation) >= 3:
        _put(features, quality, "BodyHotEscalation", sum(sorted(body_point_escalation, reverse=True)[:3]) / 3.0)
    body_cfg = dict((thresholds or {}).get("body_temperature_range", {}))
    body_warn, body_alarm = _number(body_cfg.get("warn")), _number(body_cfg.get("alarm"))
    body_levels = dict(body_cfg.get("levels") or {})
    required_directions = int(body_cfg.get("required_directions_per_layer", 2))
    body_range_risks: list[float] = []
    body_missing_layers: list[str] = []
    for level in range(7, 17):
        values = [_number(working_current.get(f"T_body_L{level}_{direction}")) for direction in "ABCDEFGH"]
        values = [value for value in values if value is not None]
        level_cfg = dict(body_levels.get(f"L{level}") or {})
        warn = _number(level_cfg.get("warn")) if level_cfg else body_warn
        alarm = _number(level_cfg.get("alarm")) if level_cfg else body_alarm
        if len(values) < required_directions or warn is None or alarm is None:
            body_missing_layers.append(f"L{level}")
            continue
        risk = _high(max(values)-min(values), warn, alarm)
        if risk is not None:
            body_range_risks.append(risk)
    minimum_body_layers = int(body_cfg.get("minimum_complete_layers", 1))
    if len(body_range_risks) >= minimum_body_layers:
        _put(features, quality, "BodyTempRange", max(body_range_risks))
        quality["BodyTempRange"]["missing_layers"] = body_missing_layers
    body_duration = _number(working_current.get("BodyColdDurationMinutes"))
    if body_duration is None and aligned_timestamps and body_names:
        body_cold_samples: list[tuple[float, float]] = []
        end_ts = _timestamp(working_history.get("evaluation_ts")) or _timestamp(aligned_timestamps[-1])
        if end_ts is not None:
            for index, raw_ts in enumerate(aligned_timestamps):
                sample_ts = _timestamp(raw_ts)
                if sample_ts is None:
                    continue
                risks: list[float] = []
                for name in body_names:
                    values = working_history.get(name, [])
                    if index >= len(values):
                        continue
                    value = _number(values[index])
                    baseline_row = _baseline_row(working_baseline, name)
                    if value is None or baseline_row is None:
                        continue
                    median, iqr = baseline_row
                    risk = _low((value-median)/iqr, -.8, -1.5)
                    if risk is not None:
                        risks.append(risk)
                if risks:
                    body_cold_samples.append(((sample_ts-end_ts).total_seconds()/60.0, max(risks)))
        body_duration = _trailing_minutes(body_cold_samples, lambda value: value > 0)
    if body_duration is not None and duration_warn is not None and duration_alarm is not None:
        _put(features, quality, "BodyColdDuration", _high(body_duration, duration_warn, duration_alarm))

    cooling_low = [low(n) for n in ("Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water", "P_medium_pressure_water")]
    cooling_inputs = (*cooling_low, absolute("ExpansionTankLevel"))
    cooling = _max_required(*cooling_inputs)
    _put(features, quality, "CoolingRisk", cooling)
    # The second-largest independent cooling indication is zero when only one
    # sensor deviates.  This prevents one sparse/noisy point from declaring the
    # whole cooling system overloaded while preserving CoolingRisk for A/B
    # maintenance diagnostics.
    if cooling is not None:
        _put(features, quality, "CoolingConcurrence", sorted((float(value) for value in cooling_inputs if value is not None), reverse=True)[1])
    _put(features, quality, "CoolingFlowLow", _max_required(low("Q_soft_water"), low("Q_high_pressure_water")))

    heat_proxy = _max_required(absolute("T_taphole_mean"), _absolute(p("T_taphole_mean"), .5, 1.2),
                                _absolute(p("T_top"), .5, 1.2), absolute("TFT"))
    _put(features, quality, "HeatProxy", heat_proxy)
    drain = _weighted([(.35, low("T_taphole_mean")), (.25, high("DP_lower")), (.20, pi_bad), (.20, burden_stall)])
    _put(features, quality, "DrainProxy", drain)
    # A9 is a safe economic-intensification boundary, not a penalty for a
    # single high operating rate.  Q_blast/O2_rate/PCI_rate are standardized
    # rates.  PCI_rate is the measured t/h rate (mass requires integration);
    # PCI_set is deliberately excluded because it is an operator target.
    intensity_parts = [high("Q_blast"), high("O2_rate"), high("PCI_rate")]
    if all(value is not None for value in intensity_parts):
        ranked = sorted((float(value) for value in intensity_parts), reverse=True)
        strength = .60 * ranked[0] + .40 * ranked[1]
        operating_limit = _max_required(dp_high, pi_bad, low("GasUtil"), drain, cooling, low("T_taphole_mean"))
        edge = strength * (.30 + .70 * operating_limit) if operating_limit is not None else None
        _put(features, quality, "EconomicIntensityStrength", strength)
        _put(features, quality, "EconomicOperatingLimit", operating_limit)
        _put(features, quality, "EconomicIntensityEdge", edge)
    quality["factor_audit"] = build_factor_audit(features, working_current, working_baseline, thresholds)
    return features, quality

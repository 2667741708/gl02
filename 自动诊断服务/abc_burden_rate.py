"""Realtime burden cadence reconstructed from the south/north stockline probes.

One completed probe excursion (working descent followed by a return to the
lifted zero position) is one small charge.  Synchronous south/north returns are
merged into one event.  Two small charges form one complete large batch.

Requirement: REQ-ABC33-PSPACE-PROBE-BURDEN-RATE-20260811.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping


DATASET_KEY = "bf_sensor.one_minute_values:L_south,L_north,Hopper_weight"
PROBE_NAMES = ("L_south", "L_north")
WEIGHT_NAME = "Hopper_weight"
NORMAL_DELTA_LARGE_PER_HOUR = 0.25
HARD_DELTA_LARGE_PER_HOUR = 0.5
TWO_HOUR_EXCESS_LARGE_PER_HOUR = 1.0
TWO_HOUR_WARN_LARGE_PER_HOUR = 0.5
MAX_SOURCE_AGE_MINUTES = 5.0
MIN_WINDOW_COVERAGE = 0.75
LIFTED_MAX_VALUE = 0.0
WORKING_MIN_VALUE = 0.30
MINIMUM_EXCURSION_DEPTH = 0.50
MERGE_TOLERANCE_MINUTES = 2.0
DEFAULT_ORE_WEIGHT_THRESHOLD = 20.0
WEIGHT_LOOKBACK_MINUTES = 2.0


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _clip(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _high(value: float | None, warn: float, alarm: float) -> float | None:
    if value is None or alarm <= warn:
        return None
    return _clip((value - warn) / (alarm - warn))


def _probe_events(
    samples: list[tuple[datetime, float]], *, lifted_max: float, working_min: float,
    minimum_depth: float,
) -> list[datetime]:
    """Return completed descent/lift timestamps for one probe."""
    events: list[datetime] = []
    active = False
    deepest: float | None = None
    for stamp, value in sorted(samples):
        if value >= working_min:
            active = True
            deepest = value if deepest is None else max(deepest, value)
        elif value <= lifted_max and active:
            if deepest is not None and deepest >= minimum_depth:
                events.append(stamp)
            active = False
            deepest = None
    return events


def _merge_probe_events(events: list[tuple[datetime, str]], tolerance_minutes: float) -> list[dict[str, Any]]:
    """Merge synchronous returns so two probes never double-count a charge."""
    clusters: list[list[tuple[datetime, str]]] = []
    tolerance = timedelta(minutes=tolerance_minutes)
    for event in sorted(events):
        if (
            not clusters
            or event[0] - clusters[-1][0][0] > tolerance
            or event[1] in {probe for _, probe in clusters[-1]}
        ):
            clusters.append([event])
        else:
            clusters[-1].append(event)
    return [
        {
            "event_ts": max(stamp for stamp, _ in cluster),
            "probes": sorted({probe for _, probe in cluster}),
        }
        for cluster in clusters
    ]


def _classify_charge_events(
    events: list[dict[str, Any]], weight_samples: list[tuple[datetime, float]],
    *, fallback_threshold: float, lookback_minutes: float,
) -> tuple[list[dict[str, Any]], float, str]:
    """Classify heavy vessel loads as ore and light loads as coke."""
    weighted: list[tuple[dict[str, Any], float]] = []
    lookback = timedelta(minutes=lookback_minutes)
    for event in events:
        stamp = event["event_ts"]
        candidates = [value for sample_ts, value in weight_samples if stamp-lookback <= sample_ts <= stamp]
        if candidates:
            weighted.append((event, max(candidates)))
    ordered = sorted({weight for _, weight in weighted})
    threshold = fallback_threshold
    threshold_source = "preset_fallback"
    if len(ordered) >= 4:
        gaps = [(right-left, left, right) for left, right in zip(ordered, ordered[1:])]
        gap, low, high = max(gaps)
        if gap >= 5.0:
            threshold = (low+high)/2.0
            threshold_source = "rolling_event_weight_bimodal_gap"
    result: list[dict[str, Any]] = []
    weights_by_stamp = {item["event_ts"]: weight for item, weight in weighted}
    for event in events:
        enriched = dict(event)
        weight = weights_by_stamp.get(event["event_ts"])
        enriched["hopper_weight_t"] = weight
        enriched["charge_type"] = None if weight is None else ("矿批" if weight >= threshold else "焦批")
        result.append(enriched)
    return result, threshold, threshold_source


def _coverage(sample_minutes: set[datetime], start: datetime, end: datetime) -> float:
    expected = max(1, int(math.ceil((end - start).total_seconds() / 60.0)))
    observed = sum(1 for stamp in sample_minutes if start < stamp <= end)
    return min(1.0, observed / expected)


def _count_rate(events: list[dict[str, Any]], start: datetime, end: datetime) -> tuple[float | None, int]:
    """Return cadence from small-batch intervals ending in the window."""
    stamps = sorted(item["event_ts"] for item in events)
    intervals = [
        (current-previous).total_seconds()/60.0
        for previous, current in zip(stamps, stamps[1:])
        if start < current <= end and 0 < (current-previous).total_seconds()/60.0 <= 12.0
    ]
    if not intervals:
        return None, 0
    return 60.0/(sum(intervals)/len(intervals)), len(intervals)


def calculate_burden_rate_snapshot(
    rows: Iterable[Mapping[str, Any]], evaluation_ts: datetime,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate small/large batch rates from pSpace-mirrored probe samples."""
    evaluation_ts = evaluation_ts.replace(tzinfo=None)
    policy = dict(policy or {})
    normal_delta = _number(policy.get("normal_delta_large_per_hour")) or NORMAL_DELTA_LARGE_PER_HOUR
    hard_delta = _number(policy.get("hard_delta_large_per_hour")) or HARD_DELTA_LARGE_PER_HOUR
    two_hour_warn = _number(policy.get("two_hour_warn_excess_large_per_hour")) or TWO_HOUR_WARN_LARGE_PER_HOUR
    two_hour_alarm = _number(policy.get("two_hour_full_risk_excess_large_per_hour")) or TWO_HOUR_EXCESS_LARGE_PER_HOUR
    maximum_age = _number(policy.get("maximum_source_age_minutes")) or MAX_SOURCE_AGE_MINUTES
    minimum_coverage = _number(policy.get("minimum_window_coverage_ratio")) or MIN_WINDOW_COVERAGE
    lifted_max = _number(policy.get("probe_lifted_max_value"))
    lifted_max = LIFTED_MAX_VALUE if lifted_max is None else lifted_max
    working_min = _number(policy.get("probe_working_min_value")) or WORKING_MIN_VALUE
    minimum_depth = _number(policy.get("probe_minimum_excursion_depth")) or MINIMUM_EXCURSION_DEPTH
    merge_tolerance = _number(policy.get("probe_merge_tolerance_minutes")) or MERGE_TOLERANCE_MINUTES
    ore_weight_threshold = _number(policy.get("ore_weight_threshold_t")) or DEFAULT_ORE_WEIGHT_THRESHOLD
    weight_lookback = _number(policy.get("hopper_weight_lookback_minutes")) or WEIGHT_LOOKBACK_MINUTES
    if hard_delta <= normal_delta or two_hour_alarm <= two_hour_warn or maximum_age <= 0:
        raise ValueError("invalid burden-rate threshold ordering")

    per_probe: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    weight_samples: list[tuple[datetime, float]] = []
    all_minutes: set[datetime] = set()
    latest_sample: datetime | None = None
    for row in rows:
        name = str(row.get("variable_name") or "")
        stamp = _timestamp(row.get("ts") or row.get("event_ts"))
        value = _number(row.get("value"))
        if name not in (*PROBE_NAMES, WEIGHT_NAME) or stamp is None or value is None or stamp > evaluation_ts:
            continue
        if name == WEIGHT_NAME:
            weight_samples.append((stamp, value))
            continue
        per_probe[name].append((stamp, value))
        all_minutes.add(stamp.replace(second=0, microsecond=0))
        latest_sample = stamp if latest_sample is None else max(latest_sample, stamp)

    raw_events = [
        (stamp, name)
        for name, samples in per_probe.items()
        for stamp in _probe_events(samples, lifted_max=lifted_max, working_min=working_min, minimum_depth=minimum_depth)
    ]
    events = _merge_probe_events(raw_events, merge_tolerance)
    events, effective_weight_threshold, weight_threshold_source = _classify_charge_events(
        events, weight_samples, fallback_threshold=ore_weight_threshold, lookback_minutes=weight_lookback,
    )
    yesterday_start = datetime.combine(evaluation_ts.date() - timedelta(days=1), datetime.min.time())
    windows = {
        "previous_30": (evaluation_ts - timedelta(minutes=60), evaluation_ts - timedelta(minutes=30)),
        "current_30": (evaluation_ts - timedelta(minutes=30), evaluation_ts),
        "rolling_2h": (evaluation_ts - timedelta(hours=2), evaluation_ts),
        "rolling_24h": (evaluation_ts - timedelta(hours=24), evaluation_ts),
        "yesterday": (yesterday_start, yesterday_start + timedelta(days=1)),
    }
    values: dict[str, float] = {}
    counts: dict[str, int] = {}
    coverages: dict[str, float] = {}
    for label, (start, end) in windows.items():
        small_rate, count = _count_rate(events, start, end)
        window_events = [item for item in events if start < item["event_ts"] <= end]
        classified = [item for item in window_events if item.get("charge_type")]
        ore_count = sum(item.get("charge_type") == "矿批" for item in classified)
        coke_count = sum(item.get("charge_type") == "焦批" for item in classified)
        coverage = _coverage(all_minutes, start, end)
        counts[f"{label}_small_events"] = count
        counts[f"{label}_ore_events"] = ore_count
        counts[f"{label}_coke_events"] = coke_count
        coverages[label] = coverage
        # Hopper weight classifies ore/coke, but total probe cadence remains
        # valid without that optional classification evidence.
        if coverage >= minimum_coverage and small_rate is not None:
            values[f"BurdenRate_{label}_small_per_hour"] = small_rate
            values[f"BurdenRate_{label}_large_per_hour"] = small_rate / 2.0

    source_age_seconds = (evaluation_ts - latest_sample).total_seconds() if latest_sample else None
    fresh = source_age_seconds is not None and 0 <= source_age_seconds <= maximum_age * 60
    previous_rate = values.get("BurdenRate_previous_30_large_per_hour")
    current_rate = values.get("BurdenRate_current_30_large_per_hour")
    yesterday_rate = values.get("BurdenRate_yesterday_large_per_hour")
    rolling_24h = values.get("BurdenRate_rolling_24h_large_per_hour")
    rolling_2h = values.get("BurdenRate_rolling_2h_large_per_hour")
    delta = current_rate - previous_rate if current_rate is not None and previous_rate is not None else None
    if delta is not None:
        values["BurdenRate_delta_large_per_hour"] = delta
    if current_rate is not None and yesterday_rate is not None:
        values["BurdenRate_current_vs_yesterday_large_per_hour"] = current_rate - yesterday_rate
    if current_rate is not None and rolling_24h is not None:
        values["BurdenRate_current_vs_24h_large_per_hour"] = current_rate - rolling_24h
    if rolling_2h is not None and rolling_24h is not None:
        values["BurdenRate_2h_vs_24h_large_per_hour"] = rolling_2h - rolling_24h
    if source_age_seconds is not None:
        values["BurdenRate_source_age_seconds"] = source_age_seconds

    if fresh and delta is not None:
        values["BurdenRateHalfHourDev"] = _high(abs(delta), normal_delta, hard_delta) or 0.0
        values["BurdenRateHalfHourSlow"] = _high(-delta, normal_delta, hard_delta) or 0.0
        values["BurdenRateHalfHourFast"] = _high(delta, normal_delta, hard_delta) or 0.0
    if fresh and current_rate is not None and yesterday_rate is not None:
        yesterday_delta = current_rate-yesterday_rate
        values["BurdenRateYesterdayDev"] = _high(abs(yesterday_delta), two_hour_warn, two_hour_alarm) or 0.0
        values["BurdenRateYesterdaySlow"] = _high(-yesterday_delta, two_hour_warn, two_hour_alarm) or 0.0
        values["BurdenRateYesterdayFast"] = _high(yesterday_delta, two_hour_warn, two_hour_alarm) or 0.0
    if fresh and rolling_2h is not None and yesterday_rate is not None:
        sustained_delta = rolling_2h-yesterday_rate
        values["BurdenRate2hDev"] = _high(abs(sustained_delta), two_hour_warn, two_hour_alarm) or 0.0
        values["BurdenRate2hSlow"] = _high(-sustained_delta, two_hour_warn, two_hour_alarm) or 0.0
        values["BurdenRate2hFast"] = _high(sustained_delta, two_hour_warn, two_hour_alarm) or 0.0

    return {
        "schema_version": "abc_burden_rate.v2.pspace_probe",
        "evaluation_ts": evaluation_ts,
        "source_dataset": DATASET_KEY,
        "source_semantics": "south_north_probe_descent_then_lift_equals_one_small_batch",
        "latest_event_ts": events[-1]["event_ts"] if events else None,
        "latest_source_update": latest_sample,
        "source_age_seconds": source_age_seconds,
        "fresh": fresh,
        "values": values,
        "interval_counts": counts,
        "coverage_by_window": coverages,
        "detected_events": events,
        "availability": {
            factor: fresh and factor in values
            for factor in (
                "BurdenRateHalfHourDev", "BurdenRateYesterdayDev", "BurdenRate2hDev",
                "BurdenRateHalfHourSlow", "BurdenRateYesterdaySlow", "BurdenRate2hSlow",
                "BurdenRateHalfHourFast", "BurdenRateYesterdayFast", "BurdenRate2hFast",
            )
        },
        "policy_version": {
            "normal_delta_large_per_hour": normal_delta, "hard_delta_large_per_hour": hard_delta,
            "two_hour_warn_excess_large_per_hour": two_hour_warn,
            "two_hour_full_risk_excess_large_per_hour": two_hour_alarm,
            "maximum_source_age_minutes": maximum_age, "minimum_window_coverage_ratio": minimum_coverage,
            "probe_lifted_max_value": lifted_max, "probe_working_min_value": working_min,
            "probe_minimum_excursion_depth": minimum_depth, "probe_merge_tolerance_minutes": merge_tolerance,
            "ore_weight_threshold_t": effective_weight_threshold,
            "ore_weight_threshold_source": weight_threshold_source,
            "hopper_weight_lookback_minutes": weight_lookback,
        },
    }


def fetch_burden_rate_snapshot(conn: Any, evaluation_ts: datetime, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Read the pSpace mirror and calculate A2/B4/B5 probe cadence."""
    evaluation_ts = evaluation_ts.replace(tzinfo=None)
    yesterday_start = datetime.combine(evaluation_ts.date() - timedelta(days=1), datetime.min.time())
    start = min(evaluation_ts - timedelta(hours=25), yesterday_start)
    rows = conn.execute(
        """
        SELECT r.variable_name,v.ts,avg(v.value)::double precision AS value
        FROM bf_sensor.one_minute_values v
        JOIN bf_sensor.sensor_registry r ON r.tag_long_name=v.tag_long_name
        WHERE r.variable_name=ANY(%s) AND v.ts>=%s AND v.ts<=%s
        GROUP BY r.variable_name,v.ts ORDER BY v.ts,r.variable_name
        """,
        ([*PROBE_NAMES, WEIGHT_NAME], start, evaluation_ts),
    ).fetchall()
    normalized = [dict(row) if isinstance(row, Mapping) else {"variable_name": row[0], "ts": row[1], "value": row[2]} for row in rows]
    return calculate_burden_rate_snapshot(normalized, evaluation_ts, policy)


def burden_rate_quality(snapshot: Mapping[str, Any], factor: str) -> dict[str, Any]:
    available = bool((snapshot.get("availability") or {}).get(factor))
    return {
        "available": available, "required": True, "source": DATASET_KEY,
        "source_age_seconds": _number(snapshot.get("source_age_seconds")),
        "missing_reason": None if available else "南北探尺实时覆盖率、前后30分钟、昨日24小时平均或连续2小时比较窗口不足",
    }

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from store import DiagnosisStore


DESCRIPTION = "Maintain daily 30-day historical baselines in PostgreSQL for later diagnosis queries."
EPILOG = """
Examples:
  python 自动诊断服务/baseline_maintainer.py --build-day 2026-05-10 --write
  python 自动诊断服务/baseline_maintainer.py --build-day 2026-05-10 --derived-only --write
  python 自动诊断服务/baseline_maintainer.py --build-day 2026-05-10 --cooling-only --write
  python 自动诊断服务/baseline_maintainer.py --backfill-days 30 --end-day 2026-05-10 --dry-run
  python 自动诊断服务/baseline_maintainer.py --query --day 2026-05-10 --variable PI
"""


DERIVED_BASELINE_COMPONENTS: dict[str, tuple[str, ...]] = {
    "T_taphole_mean": ("T_taphole_1", "T_taphole_2"),
    "T_top": ("T_top_A", "T_top_B", "T_top_C", "T_top_D"),
}

HOURLY_DAILY_BASELINE_VARIABLES = {"ExpansionTankLevel"}

# Baselines describe the process state over time.  Most pSpace points are
# minute-like but can miss a few consecutive buckets; a bounded hold preserves
# the last observed state without bridging long outages.  Furnace-body points
# are change-triggered and need a longer, still auditable hold.  Expansion tank
# level has its own hourly->daily policy and is never filled here.
DEFAULT_BASELINE_HOLD_MINUTES = 5
BODY_TEMPERATURE_HOLD_MINUTES = 15
NO_HOLD_BASELINE_VARIABLES = {"ExpansionTankLevel", "T_taphole_1", "T_taphole_2", "T_taphole_mean"}

COOLING_BASELINE_VARIABLES: tuple[str, ...] = (
    "Q_soft_water",
    "P_soft_water",
    "Q_high_pressure_water",
    "P_high_pressure_water",
    "P_medium_pressure_water",
    "ExpansionTankLevel",
)

FOREMAN_BASELINE_VARIABLES: tuple[str, ...] = (
    "BlastEnergy",
    "BlastSpeedStd",
    "BlastSpeedActual",
    "Q_N2",
    "P_N2",
    "P_O2_valve_in",
    "P_O2_valve_out",
    "Hopper_weight",
    "CO_top",
    "CO2_top",
    "H2_top",
    "PCI_previous_hour",
)


def parse_day(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(value.replace("T", " ")).date()


def baseline_window(day: date, baseline_days: int) -> tuple[datetime, datetime]:
    end = datetime.combine(day, datetime.min.time())
    start = end - timedelta(days=baseline_days)
    return start, end - timedelta(minutes=1)


def add_strict_derived_series(frame: pd.DataFrame) -> pd.DataFrame:
    """Build auditable derived series only from fully aligned minute samples.

    A row contributes to a derived mean only when every required component is
    finite in that same row/minute.  Existing physical/authoritative derived
    columns are retained; only absent columns are synthesized.
    """
    result = frame.copy()
    for variable_name, components in DERIVED_BASELINE_COMPONENTS.items():
        if variable_name in result.columns:
            continue
        if not all(component in result.columns for component in components):
            continue
        numeric = result.loc[:, list(components)].apply(pd.to_numeric, errors="coerce")
        if variable_name == "T_top":
            numeric = numeric.ffill(limit=DEFAULT_BASELINE_HOLD_MINUTES)
        complete = numeric.notna().all(axis=1)
        result[variable_name] = numeric.mean(axis=1).where(complete)
    return result


def baseline_hold_minutes(variable_name: str) -> int:
    if variable_name in NO_HOLD_BASELINE_VARIABLES:
        return 0
    if variable_name.startswith("T_body_"):
        return BODY_TEMPERATURE_HOLD_MINUTES
    return DEFAULT_BASELINE_HOLD_MINUTES


def baseline_series(frame: pd.DataFrame, variable_name: str) -> tuple[pd.Series, dict[str, Any]]:
    numeric = pd.to_numeric(frame[variable_name], errors="coerce")
    raw_count = int(numeric.notna().sum())
    if variable_name not in HOURLY_DAILY_BASELINE_VARIABLES:
        hold_minutes = baseline_hold_minutes(variable_name)
        effective = numeric.ffill(limit=hold_minutes) if hold_minutes else numeric
        return effective.dropna(), {
            "type": "bounded_state_series" if hold_minutes else "local_pg",
            "table": "bf_sensor.one_minute_values",
            "raw_sample_count": raw_count,
            "hold_method": "forward_fill_observed_state" if hold_minutes else "none",
            "maximum_hold_minutes": hold_minutes,
        }
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    valid = pd.DataFrame({"timestamp": timestamps, "value": numeric}).dropna()
    if valid.empty:
        return pd.Series(dtype="float64"), {
            "type": "hourly_then_daily_mean", "table": "bf_sensor.one_minute_values",
            "hourly_samples": 0, "daily_samples": 0,
        }
    hourly = valid.set_index("timestamp")["value"].resample("1h").mean().dropna()
    daily = hourly.resample("1D").mean().dropna()
    return daily, {
        "type": "hourly_then_daily_mean",
        "table": "bf_sensor.one_minute_values",
        "minute_to_hour": "arithmetic_mean_of_observed_minutes",
        "hour_to_day": "arithmetic_mean_of_available_hours",
        "baseline_statistics": "percentiles_of_daily_means",
        "hourly_samples": int(len(hourly)),
        "daily_samples": int(len(daily)),
    }


def build_day(
    day: date,
    baseline_days: int = 30,
    config_path: str | Path | None = None,
    write: bool = False,
    derived_only: bool = False,
    cooling_only: bool = False,
    foreman_only: bool = False,
) -> dict[str, Any]:
    exclusive = sum([derived_only, cooling_only, foreman_only])
    if exclusive > 1:
        raise ValueError("derived_only, cooling_only and foreman_only are mutually exclusive")
    store = DiagnosisStore(config_path)
    start, end = baseline_window(day, baseline_days)
    source_frame = (
        store.fetch_wide_frame(start, end, variables=list(COOLING_BASELINE_VARIABLES))
        if cooling_only
        else store.fetch_wide_frame(start, end, variables=list(FOREMAN_BASELINE_VARIABLES))
        if foreman_only
        else store.fetch_wide_frame(start, end)
    )
    target_vars = (
        DERIVED_BASELINE_COMPONENTS if derived_only
        else COOLING_BASELINE_VARIABLES if cooling_only
        else FOREMAN_BASELINE_VARIABLES if foreman_only
        else None
    )
    frame = add_strict_derived_series(source_frame)
    expected_minutes = int((end - start).total_seconds() // 60) + 1
    rows: list[dict[str, Any]] = []
    if not frame.empty:
        for col in frame.columns:
            if col == "timestamp":
                continue
            if target_vars and col not in target_vars:
                continue
            series, source = baseline_series(frame, col)
            if len(series) < 10:
                continue
            expected_samples = baseline_days if col in HOURLY_DAILY_BASELINE_VARIABLES else expected_minutes
            if expected_samples and col not in HOURLY_DAILY_BASELINE_VARIABLES:
                source["raw_coverage_ratio"] = round(float(source.get("raw_sample_count", len(series))) / expected_samples, 6)
                source["effective_coverage_ratio"] = round(float(len(series)) / expected_samples, 6)
            q1 = float(series.quantile(0.25))
            q3 = float(series.quantile(0.75))
            rows.append(
                {
                    "baseline_window_start": start,
                    "baseline_window_end": end,
                    "baseline_days": baseline_days,
                    "variable_name": col,
                    "median_ref": round(float(series.median()), 6),
                    "iqr_ref": round(q3 - q1, 6),
                    "p10": round(float(series.quantile(0.10)), 6),
                    "p25": round(q1, 6),
                    "p50": round(float(series.quantile(0.50)), 6),
                    "p75": round(q3, 6),
                    "p90": round(float(series.quantile(0.90)), 6),
                    "sample_count": int(len(series)),
                    "expected_minutes": expected_samples,
                    "coverage_ratio": round(float(len(series) / expected_samples), 6) if expected_samples else 0,
                    "source": (
                        {
                            **source,
                            "type": "derived_aligned_minute_mean",
                            "table": "bf_sensor.one_minute_values",
                            "components": list(DERIVED_BASELINE_COMPONENTS[col]),
                            "alignment": (
                                "bounded_5m_component_hold_all_components_required"
                                if col == "T_top"
                                else "same_minute_all_components_required"
                            ),
                        }
                        if col in DERIVED_BASELINE_COMPONENTS
                        else source
                    ),
                }
            )
    written = 0
    if write:
        store.ensure_schema()
        written = store.upsert_daily_baselines(day, rows)
    return {
        "ok": True,
        "baseline_day": day.isoformat(),
        "baseline_window_start": start,
        "baseline_window_end": end,
        "baseline_days": baseline_days,
        "variables": len(rows),
        "written": written,
        "rows": rows,
    }


def backfill(
    end_day: date,
    days: int,
    baseline_days: int,
    config_path: str | Path | None,
    write: bool,
    derived_only: bool = False,
    cooling_only: bool = False,
    foreman_only: bool = False,
) -> list[dict[str, Any]]:
    outputs = []
    first = end_day - timedelta(days=max(days - 1, 0))
    cursor = first
    while cursor <= end_day:
        outputs.append(
            build_day(
                cursor,
                baseline_days=baseline_days,
                config_path=config_path,
                write=write,
                derived_only=derived_only,
                cooling_only=cooling_only,
                foreman_only=foreman_only,
            )
        )
        cursor += timedelta(days=1)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build-day", default="", help="Build and optionally write one day's 30-day baseline.")
    parser.add_argument("--backfill-days", type=int, default=0, help="Build baselines for N days ending at --end-day.")
    parser.add_argument("--end-day", default="", help="Backfill end day, for example 2026-05-10.")
    parser.add_argument("--query", action="store_true", help="Query persisted baseline rows.")
    parser.add_argument("--day", default="", help="Baseline day to query.")
    parser.add_argument("--variable", default="", help="Optional variable name to query.")
    parser.add_argument("--baseline-days", type=int, default=30, help="Lookback days used to build baselines.")
    parser.add_argument("--config", default="", help="Optional config.yaml path.")
    parser.add_argument("--write", action="store_true", help="Write baseline records to PostgreSQL.")
    parser.add_argument("--dry-run", action="store_true", help="Calculate/report without writing.")
    parser.add_argument(
        "--derived-only",
        action="store_true",
        help="Calculate/write only strict aligned derived baselines (T_taphole_mean and T_top).",
    )
    parser.add_argument(
        "--cooling-only",
        action="store_true",
        help="Calculate/write only the six independent physical baselines required by CoolingRisk.",
    )
    parser.add_argument(
        "--foreman-only",
        action="store_true",
        help="Calculate/write only the twelve foreman extra baselines (BlastEnergy, N2, etc.).",
    )
    args = parser.parse_args()
    if sum([args.derived_only, args.cooling_only, args.foreman_only]) > 1:
        parser.error("--derived-only, --cooling-only and --foreman-only are mutually exclusive")
    config_path = args.config or None
    store = DiagnosisStore(config_path)
    if args.query:
        if not args.day:
            raise SystemExit("--query requires --day")
        rows = store.query_daily_baselines(args.day, variable=args.variable, baseline_days=args.baseline_days)
        print(json.dumps({"ok": True, "count": len(rows), "rows": rows}, ensure_ascii=False, default=str, indent=2))
        return 0
    if args.backfill_days:
        end_day = parse_day(args.end_day) if args.end_day else datetime.now().date()
        rows = backfill(
            end_day,
            args.backfill_days,
            args.baseline_days,
            config_path,
            write=args.write and not args.dry_run,
            derived_only=args.derived_only,
            cooling_only=args.cooling_only,
            foreman_only=args.foreman_only,
        )
        print(json.dumps({"ok": True, "count": len(rows), "days": rows}, ensure_ascii=False, default=str, indent=2))
        return 0
    day = parse_day(args.build_day) if args.build_day else datetime.now().date()
    result = build_day(
        day,
        baseline_days=args.baseline_days,
        config_path=config_path,
        write=args.write and not args.dry_run,
        derived_only=args.derived_only,
        cooling_only=args.cooling_only,
        foreman_only=args.foreman_only,
    )
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

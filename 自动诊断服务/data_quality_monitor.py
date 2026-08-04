from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from service_config import load_config
from store import DiagnosisStore


class DataQualityMonitor:
    def __init__(self, config_path: str | Path | None = None):
        self.config = load_config(config_path) if config_path else load_config()
        self.store = DiagnosisStore(config_path)
        self.diag_cfg = self.config["diagnosis"]

    @property
    def required_variables(self) -> list[str]:
        return [
            "P_blast",
            "P_top",
            "DP_total",
            "PI",
            "T_top_A",
            "T_top_B",
            "T_top_C",
            "T_top_D",
            "L",
            "GasUtil",
        ]

    def check_window(self, minutes: int, window_kind: str, write: bool = False) -> dict:
        end = datetime.now().replace(second=0, microsecond=0)
        start = end - timedelta(minutes=minutes)
        df = self.store.fetch_wide_frame(start, end, variables=self.required_variables)
        coverage = self.store.data_coverage(df, start, end, self.required_variables)
        zero_audit = self.store.zero_audit_summary(start, end, self.required_variables)
        latest_ts = self.store.latest_data_ts()
        lag = int((end - latest_ts).total_seconds()) if latest_ts else None
        missing = [name for name, ratio in coverage.get("variable_coverage", {}).items() if ratio <= 0]
        warn_lag = int(self.diag_cfg.get("max_source_lag_minutes_warn", 10)) * 60
        ok_lag = int(self.diag_cfg.get("max_source_lag_minutes_ok", 5)) * 60
        if lag is None or lag > warn_lag or coverage["coverage_ratio"] < 0.5:
            status = "error"
        elif lag > ok_lag or coverage["coverage_ratio"] < 0.9:
            status = "warn"
        else:
            status = "ok"
        payload = {
            "window_start": start,
            "window_end": end,
            "window_kind": window_kind,
            "latest_data_ts": latest_ts,
            "source_lag_seconds": lag,
            "expected_minutes": coverage["expected_minutes"],
            "observed_minutes": coverage["observed_minutes"],
            "coverage_ratio": coverage["coverage_ratio"],
            "missing_variables": missing,
            "stale_variables": [],
            "status": status,
            "details": {**coverage, "zero_value_audit": zero_audit},
        }
        if write:
            self.store.ensure_schema()
            self.store.insert_quality_status(payload)
        return payload

    def check_all(self, write: bool = False) -> list[dict]:
        return [
            self.check_window(60, "recent_60min", write=write),
            self.check_window(24 * 60, "recent_24h", write=write),
            self.check_window(int(self.diag_cfg["baseline_days"]) * 24 * 60, "baseline_window", write=write),
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check V3 local database data quality.")
    parser.add_argument("--config", default="")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    monitor = DataQualityMonitor(args.config or None)
    print(json.dumps(monitor.check_all(write=args.write), ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

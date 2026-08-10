"""Run V19 mean-Si predictions at 5-minute cutoffs and append a local ledger.

This script deliberately treats ``predict_next_heat_si_v19.py`` as the atomic
predictor.  It can be used in two modes:

* one-shot/live: run once at the current or supplied cutoff;
* backfill: replay a range of cutoffs every N minutes for one heat.

It writes only local JSONL/CSV artifacts by default; it does not write 220.12
business data or change production model settings.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ATOMIC = ROOT / "tools" / "predict_next_heat_si_v19.py"
DEFAULT_OUT = ROOT / "PT" / "预测铁水Si含量" / "reports" / "live_predictions"


def parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.now().replace(second=0, microsecond=0)
    return datetime.fromisoformat(value.replace("T", " "))


def iter_cutoffs(args: argparse.Namespace) -> list[datetime]:
    if args.start_ts and args.end_ts:
        start = parse_ts(args.start_ts)
        end = parse_ts(args.end_ts)
        step = timedelta(minutes=max(1, int(args.step_minutes)))
        values: list[datetime] = []
        current = start
        while current <= end:
            values.append(current)
            current += step
        return values
    return [parse_ts(args.cutoff_ts)]


def extract_json(stdout: str) -> dict[str, Any]:
    start = stdout.find("{")
    if start < 0:
        raise RuntimeError("atomic predictor produced no JSON object")
    decoder = json.JSONDecoder()
    index = start
    last: dict[str, Any] | None = None
    while index < len(stdout):
        marker = stdout.find("{", index)
        if marker < 0:
            break
        try:
            obj, end = decoder.raw_decode(stdout[marker:])
        except json.JSONDecodeError:
            index = marker + 1
            continue
        if isinstance(obj, dict):
            last = obj
        index = marker + end
    if last is None:
        raise RuntimeError("atomic predictor JSON parse failed")
    return last


def compact_record(result: dict[str, Any]) -> dict[str, Any]:
    prediction = result.get("prediction") or {}
    interval = result.get("prediction_interval") or {}
    audit = result.get("audit") or {}
    history = (audit.get("history") or [{}])[0]
    pci = (audit.get("pci") or [{}])[0]
    official_pci = (audit.get("pci_official") or [{}])[0]
    return {
        "target_meltno": result.get("target_meltno"),
        "prediction_cutoff_ts": result.get("prediction_cutoff_ts"),
        "prediction_si": prediction.get("prediction"),
        "p10": interval.get("p10"),
        "p50": interval.get("p50"),
        "p90": interval.get("p90"),
        "actual_si_mean": result.get("actual_si_mean"),
        "absolute_error": result.get("absolute_error"),
        "signed_error": result.get("signed_error"),
        "history_lag_1": history.get("history_mean__Si_lag_1"),
        "history_lag_2": history.get("history_mean__Si_lag_2"),
        "history_lag_3": history.get("history_mean__Si_lag_3"),
        "history_lag_4": history.get("history_mean__Si_lag_4"),
        "history_lag_5": history.get("history_mean__Si_lag_5"),
        "history_available_heat_count": history.get("history_mean__available_heat_count"),
        "pci_current_hour_total": pci.get("pci_context__current_hour_total"),
        "pci_current_hour_coverage_minutes": pci.get("pci_context__current_hour_coverage_minutes"),
        "pci_previous_hour_total": pci.get("pci_context__previous_hour_total"),
        "pci_official_current_hour": official_pci.get("pci_current_hour"),
        "pci_official_previous_hour": official_pci.get("pci_previous_hour"),
        "pci_official_current_hour_source": official_pci.get("pci_current_hour_source"),
        "pci_official_previous_hour_source": official_pci.get("pci_previous_hour_source"),
        "windows_minutes": ",".join(str(item) for item in (audit.get("windows_minutes") or [])),
        "target_source_status": result.get("target_source_status"),
        "target_open_ts_effective": result.get("target_open_ts_effective"),
        "output_path": result.get("output_path"),
    }


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def rewrite_csv(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    fieldnames = list(records[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def run_atomic(args: argparse.Namespace, cutoff: datetime) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ATOMIC),
        "--target-meltno",
        args.target_meltno,
        "--cutoff-ts",
        cutoff.strftime("%Y-%m-%d %H:%M:%S"),
        "--output-dir",
        str(args.atomic_output_dir),
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.history_limit:
        command.extend(["--history-limit", str(args.history_limit)])
    if args.windows_minutes:
        command.extend(["--windows-minutes", args.windows_minutes])
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return extract_json(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one heat V19 Si prediction every 5 minutes or replay a cutoff range."
    )
    parser.add_argument("--target-meltno", required=True)
    parser.add_argument("--cutoff-ts")
    parser.add_argument("--start-ts")
    parser.add_argument("--end-ts")
    parser.add_argument("--step-minutes", type=int, default=5)
    parser.add_argument("--history-limit", type=int, default=40)
    parser.add_argument("--windows-minutes", default="30,60,120,240,360,480")
    parser.add_argument("--model")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--atomic-output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.atomic_output_dir.mkdir(parents=True, exist_ok=True)
    safe = args.target_meltno.replace("/", "_").replace("\\", "_")
    ledger_jsonl = args.output_dir / f"{safe}_v19_live_ledger.jsonl"
    ledger_csv = args.output_dir / f"{safe}_v19_live_ledger.csv"
    records: list[dict[str, Any]] = []
    for cutoff in iter_cutoffs(args):
        result = run_atomic(args, cutoff)
        record = compact_record(result)
        append_jsonl(ledger_jsonl, record)
        records.append(record)
        print(json.dumps(record, ensure_ascii=False, default=str), flush=True)
    rewrite_csv(ledger_csv, records)
    print(json.dumps({
        "ok": True,
        "target_meltno": args.target_meltno,
        "points": len(records),
        "ledger_jsonl": str(ledger_jsonl),
        "ledger_csv": str(ledger_csv),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

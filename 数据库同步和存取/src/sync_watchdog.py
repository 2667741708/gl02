from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pg_store import connect


ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT_DIR.parent
LOG_DIR = ROOT_DIR / "logs"
LOCK_PATH = LOG_DIR / "sync_watchdog.lock"
STATE_PATH = LOG_DIR / "sync_watchdog_state.json"
REALTIME_RUNNER = ROOT_DIR / "run_realtime_sync_pg_bg.ps1"
HIDDEN_LAUNCHER = PROJECT_ROOT / "tools" / "run_hidden_ps1.vbs"
SYNC_SCRIPT = ROOT_DIR / "src" / "sync_from_243_pg.py"
PWSH_EXE = Path(r"C:\Program Files\PowerShell\7\pwsh.exe")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watchdog for GL02 PostgreSQL sync from pSpace 243.")
    parser.add_argument("--config", default=str(ROOT_DIR / "config" / "sync_config.json"))
    parser.add_argument("--stale-minutes", type=float, default=12)
    parser.add_argument("--recent-hours", type=float, default=12)
    parser.add_argument("--history-days", type=float, default=90)
    parser.add_argument("--history-bucket-minutes", type=int, default=60)
    parser.add_argument("--history-backfill-enabled", action="store_true", help="Also backfill old 90-day hourly empty buckets. Disabled by default to protect realtime sync.")
    parser.add_argument("--min-gap-minutes", type=int, default=5)
    parser.add_argument("--backfill-max-ranges", type=int, default=4)
    parser.add_argument("--backfill-max-hours", type=float, default=6)
    parser.add_argument("--backfill-chunk-hours", type=float, default=0.2)
    parser.add_argument("--backfill-timeout-seconds", type=int, default=900)
    parser.add_argument("--batch-size", type=int, default=115)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--lock-stale-minutes", type=float, default=30)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def now_minute() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def text_time(value: datetime) -> str:
    return value.replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def run_powershell(script: str, timeout: int = 60) -> str:
    if not PWSH_EXE.is_file():
        raise RuntimeError(f"PowerShell 7 is unavailable: {PWSH_EXE}")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(
        [str(PWSH_EXE), "-WindowStyle", "Hidden", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        creationflags=creationflags,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())
    return completed.stdout.strip()


def load_json_from_powershell(script: str) -> Any:
    text = run_powershell(script)
    if not text:
        return []
    data = json.loads(text)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return [data]


def realtime_processes() -> list[dict[str, Any]]:
    script = r"""
$selfPid = $PID
$p = Get-CimInstance Win32_Process |
  Where-Object {
    $_.ProcessId -ne $selfPid -and $_.CommandLine -and (
      ($_.Name -match '^(powershell|pwsh)\.exe$' -and $_.CommandLine -match '-File\s+.*run_realtime_sync_pg_bg\.ps1') -or
      ($_.Name -match '^python' -and $_.CommandLine -match 'sync_from_243_pg.py' -and $_.CommandLine -match '--continuous')
    )
  } |
  Select-Object ProcessId,CreationDate,CommandLine
$p | ConvertTo-Json -Depth 4
"""
    try:
        return load_json_from_powershell(script)
    except Exception as exc:  # noqa: BLE001
        return [{"error": str(exc)}]


def stop_realtime_processes() -> list[str]:
    script = r"""
$stopped = @()
$selfPid = $PID
Get-CimInstance Win32_Process |
  Where-Object {
    $_.ProcessId -ne $selfPid -and $_.CommandLine -and (
      ($_.Name -match '^python' -and $_.CommandLine -match 'sync_from_243_pg.py' -and $_.CommandLine -match '--continuous') -or
      ($_.Name -match '^(powershell|pwsh)\.exe$' -and $_.CommandLine -match '-File\s+.*run_realtime_sync_pg_bg\.ps1')
    )
  } |
  ForEach-Object {
    $stopped += ("pid=" + $_.ProcessId + " " + $_.CommandLine)
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
$stopped | ConvertTo-Json -Depth 3
"""
    try:
        data = json.loads(run_powershell(script) or "[]")
        if isinstance(data, list):
            return [str(item) for item in data]
        if data:
            return [str(data)]
    except Exception as exc:  # noqa: BLE001
        return [f"stop_error={exc}"]
    return []


def start_realtime_runner() -> str:
    if HIDDEN_LAUNCHER.exists():
        script = rf"""
Start-Process -FilePath 'wscript.exe' `
  -ArgumentList @('//B','//Nologo','{HIDDEN_LAUNCHER}','{REALTIME_RUNNER}') `
  -WindowStyle Hidden
'started'
"""
        return run_powershell(script)
    script = rf"""
Start-Process -FilePath '{PWSH_EXE}' `
  -ArgumentList @('-WindowStyle','Hidden','-NoLogo','-NoProfile','-NonInteractive','-File','{REALTIME_RUNNER}') `
  -WindowStyle Hidden
'started'
"""
    return run_powershell(script)


def latest_meta(conn) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT count(*) AS rows,
               count(distinct tag_long_name) AS tags,
               min(ts) AS min_ts,
               max(ts) AS max_ts
          FROM bf_sensor.one_minute_values
        """
    ).fetchone()
    latest = row["max_ts"] if row else None
    current = now_minute()
    lag_minutes = None
    if latest is not None:
        lag_minutes = max(0.0, (current - latest.replace(second=0, microsecond=0)).total_seconds() / 60.0)
    return {
        "rows": int(row["rows"] or 0) if row else 0,
        "tags": int(row["tags"] or 0) if row else 0,
        "min_ts": text_time(row["min_ts"]) if row and row["min_ts"] else None,
        "max_ts": text_time(latest) if latest else None,
        "lag_minutes": round(lag_minutes, 3) if lag_minutes is not None else None,
        "checked_at": text_time(current),
    }


def merge_gap_minutes(minutes: list[datetime], min_gap_minutes: int) -> list[tuple[datetime, datetime]]:
    if not minutes:
        return []
    minutes = sorted(value.replace(second=0, microsecond=0) for value in minutes)
    ranges: list[tuple[datetime, datetime]] = []
    start = minutes[0]
    previous = minutes[0]
    for value in minutes[1:]:
        if value <= previous + timedelta(minutes=1):
            previous = value
            continue
        if (previous - start).total_seconds() / 60 + 1 >= min_gap_minutes:
            ranges.append((start, previous + timedelta(minutes=1)))
        start = previous = value
    if (previous - start).total_seconds() / 60 + 1 >= min_gap_minutes:
        ranges.append((start, previous + timedelta(minutes=1)))
    return ranges


def find_recent_empty_minute_gaps(conn, hours: float, min_gap_minutes: int) -> list[tuple[datetime, datetime]]:
    rows = conn.execute(
        """
        WITH bounds AS (
          SELECT max(ts) AS max_ts FROM bf_sensor.one_minute_values
        ),
        minutes AS (
          SELECT generate_series(
            date_trunc('minute', (SELECT max_ts FROM bounds) - (%s || ' hours')::interval),
            date_trunc('minute', (SELECT max_ts FROM bounds)),
            interval '1 minute'
          ) AS minute_ts
        ),
        agg AS (
          SELECT date_trunc('minute', ts) AS minute_ts, count(*) AS row_count
            FROM bf_sensor.one_minute_values
           WHERE ts >= (SELECT max_ts - (%s || ' hours')::interval FROM bounds)
           GROUP BY 1
        )
        SELECT m.minute_ts
          FROM minutes m
          LEFT JOIN agg a USING(minute_ts)
         WHERE coalesce(a.row_count, 0) = 0
         ORDER BY m.minute_ts
        """,
        (hours, hours),
    ).fetchall()
    return merge_gap_minutes([row["minute_ts"] for row in rows], min_gap_minutes)


def find_history_empty_bucket_gaps(
    conn,
    days: float,
    bucket_minutes: int,
    min_gap_minutes: int,
) -> list[tuple[datetime, datetime]]:
    # Aggregate the table once, then compare to generated buckets. Avoid joining
    # every bucket against the full value table; that becomes very slow on 90d.
    rows = conn.execute(
        """
        WITH bounds AS (
          SELECT max(ts) AS max_ts FROM bf_sensor.one_minute_values
        ),
        buckets AS (
          SELECT generate_series(
            date_bin((%s || ' minutes')::interval, (SELECT max_ts FROM bounds) - (%s || ' days')::interval, timestamp '2000-01-01'),
            date_bin((%s || ' minutes')::interval, (SELECT max_ts FROM bounds), timestamp '2000-01-01'),
            (%s || ' minutes')::interval
          ) AS bucket_ts
        ),
        agg AS (
          SELECT date_bin((%s || ' minutes')::interval, ts, timestamp '2000-01-01') AS bucket_ts,
                 count(*) AS row_count
            FROM bf_sensor.one_minute_values
           WHERE ts >= (SELECT max_ts - (%s || ' days')::interval FROM bounds)
           GROUP BY 1
        )
        SELECT bucket_ts
          FROM buckets
          LEFT JOIN agg USING(bucket_ts)
         WHERE coalesce(row_count, 0) = 0
         ORDER BY bucket_ts
        """,
        (bucket_minutes, days, bucket_minutes, bucket_minutes, bucket_minutes, days),
    ).fetchall()
    ranges = [(row["bucket_ts"], row["bucket_ts"] + timedelta(minutes=bucket_minutes)) for row in rows]
    merged: list[tuple[datetime, datetime]] = []
    for start, end in ranges:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return [item for item in merged if (item[1] - item[0]).total_seconds() / 60 >= min_gap_minutes]


def clamp_and_dedupe_ranges(
    ranges: list[tuple[datetime, datetime]],
    max_ranges: int,
    max_hours: float,
) -> list[tuple[datetime, datetime]]:
    if not ranges:
        return []
    padded = []
    ceiling = now_minute() - timedelta(minutes=1)
    for start, end in ranges:
        start = (start - timedelta(minutes=1)).replace(second=0, microsecond=0)
        end = min((end + timedelta(minutes=1)).replace(second=0, microsecond=0), ceiling)
        if start < end:
            padded.append((start, end))
    padded.sort(key=lambda item: item[1], reverse=True)
    selected: list[tuple[datetime, datetime]] = []
    used_hours = 0.0
    for start, end in padded:
        hours = (end - start).total_seconds() / 3600
        if hours <= 0:
            continue
        if selected and any(not (end <= a or start >= b) for a, b in selected):
            continue
        if len(selected) >= max_ranges:
            break
        remaining = max_hours - used_hours
        if remaining <= 0:
            break
        if hours > remaining:
            start = end - timedelta(hours=remaining)
            hours = remaining
        selected.append((start, end))
        used_hours += hours
    return sorted(selected)


def run_backfill(start: datetime, end: datetime, args: argparse.Namespace) -> dict[str, Any]:
    recent_cutoff = now_minute() - timedelta(hours=max(1.0, args.recent_hours + 1))
    source_mode = "raw" if end >= recent_cutoff else "processed"
    cmd = [
        sys.executable,
        str(SYNC_SCRIPT),
        "--config",
        args.config,
        "--start-time",
        text_time(start),
        "--end-time",
        text_time(end),
        "--chunk-hours",
        str(args.backfill_chunk_hours),
        "--batch-size",
        str(args.batch_size),
        "--max-workers",
        str(args.max_workers),
        "--retries",
        "3",
        "--retry-sleep",
        "8",
        "--source-mode",
        source_mode,
        "--skip-schema",
    ]
    if args.dry_run:
        return {"range": [text_time(start), text_time(end)], "dry_run": True, "cmd": cmd}
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.backfill_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "range": [text_time(start), text_time(end)],
            "returncode": 124,
            "timeout_seconds": args.backfill_timeout_seconds,
            "stdout_tail": (exc.stdout or "")[-4000:],
            "stderr_tail": (exc.stderr or "")[-4000:],
        }
    return {
        "range": [text_time(start), text_time(end)],
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


@contextmanager
def single_instance(lock_stale_minutes: float):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    current = time.time()
    if LOCK_PATH.exists():
        age_minutes = (current - LOCK_PATH.stat().st_mtime) / 60.0
        if age_minutes > lock_stale_minutes:
            try:
                LOCK_PATH.unlink()
            except OSError:
                pass
        else:
            raise RuntimeError(f"watchdog lock is active: {LOCK_PATH} age={age_minutes:.1f}min")
    fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, f"pid={os.getpid()} started={datetime.now().isoformat()}".encode("utf-8"))
        yield
    finally:
        os.close(fd)
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass


def main() -> int:
    args = parse_args()
    report: dict[str, Any] = {
        "checked_at": text_time(now_minute()),
        "actions": [],
        "errors": [],
    }
    try:
        with single_instance(args.lock_stale_minutes):
            conn = connect(args.config)
            meta = latest_meta(conn)
            report["database"] = meta
            processes = realtime_processes()
            report["realtime_processes"] = processes
            process_running = any("ProcessId" in proc for proc in processes)
            stale = meta.get("lag_minutes") is None or float(meta["lag_minutes"]) >= args.stale_minutes

            if stale or not process_running:
                report["actions"].append({"restart_realtime": {"stale": stale, "process_running": process_running}})
                if not args.dry_run:
                    report["actions"].append({"stopped": stop_realtime_processes()})
                    report["actions"].append({"started": start_realtime_runner()})

            recent_gaps = find_recent_empty_minute_gaps(conn, args.recent_hours, args.min_gap_minutes)
            history_gaps = (
                find_history_empty_bucket_gaps(
                    conn,
                    args.history_days,
                    args.history_bucket_minutes,
                    max(args.min_gap_minutes, args.history_bucket_minutes),
                )
                if args.history_backfill_enabled
                else []
            )
            report["history_backfill_enabled"] = bool(args.history_backfill_enabled)
            report["recent_empty_gaps"] = [[text_time(a), text_time(b)] for a, b in recent_gaps[:20]]
            report["history_empty_gaps"] = [[text_time(a), text_time(b)] for a, b in history_gaps[:20]]

            backfill_candidates = []
            if stale and meta.get("max_ts"):
                latest = datetime.strptime(str(meta["max_ts"]), "%Y-%m-%d %H:%M:%S")
                backfill_candidates.append((latest - timedelta(minutes=2), now_minute() - timedelta(minutes=1)))
            backfill_candidates.extend(recent_gaps)
            backfill_candidates.extend(history_gaps)
            selected = clamp_and_dedupe_ranges(backfill_candidates, args.backfill_max_ranges, args.backfill_max_hours)
            report["selected_backfills"] = [[text_time(a), text_time(b)] for a, b in selected]
            report["backfill_results"] = [run_backfill(start, end, args) for start, end in selected]
            report["database_after"] = latest_meta(conn)
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(str(exc))

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"sync_watchdog_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")
    STATE_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str), flush=True)
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

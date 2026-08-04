from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_DIR = ROOT / "自动诊断服务"
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

from local_pg_ws_bridge import (  # noqa: E402
    CHRONOS_TARGET_IDS,
    DISPLAY_NAMES,
    build_chronos_job,
    chronos_context_minutes_for_target,
    fetch_chronos_feature_frame,
)


DB_PROFILES: dict[str, dict[str, str]] = {
    "local": {
        "host": "127.0.0.1",
        "port": "15432",
        "dbname": "bf_trend",
        "user": "gl02_sync",
        "password": "gl02_local_sync",
    },
    "22012": {
        "host": "10.30.220.12",
        "port": "5432",
        "dbname": "bf_trend",
        "user": "gl02_reader",
        "password": os.getenv("GL02_PGPASSWORD", ""),
    },
}


def parse_ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value).tz_localize(None)


def finite_array(values: list[object]) -> np.ndarray:
    out: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = math.nan
        if not math.isfinite(number):
            number = math.nan
        out.append(number)
    return np.asarray(out, dtype=float)


def metrics(truth: np.ndarray, pred: np.ndarray) -> dict[str, float | int | None]:
    mask = np.isfinite(truth) & np.isfinite(pred)
    if not mask.any():
        return {
            "n": 0,
            "mae": None,
            "rmse": None,
            "mape_percent": None,
            "bias": None,
            "error_std": None,
            "direction_accuracy": None,
            "corr": None,
            "pred_step_std": None,
            "truth_step_std": None,
        }
    t = truth[mask]
    p = pred[mask]
    err = p - t
    nonzero = np.abs(t) > 1e-9
    if nonzero.any():
        mape = float(np.mean(np.abs(err[nonzero] / t[nonzero])) * 100.0)
    else:
        mape = None
    truth_step = np.diff(t)
    pred_step = np.diff(p)
    step_mask = np.isfinite(truth_step) & np.isfinite(pred_step)
    direction = None
    corr = None
    if step_mask.any():
        direction = float(np.mean(np.sign(truth_step[step_mask]) == np.sign(pred_step[step_mask])))
        if len(truth_step[step_mask]) >= 2 and np.std(truth_step[step_mask]) > 1e-12 and np.std(pred_step[step_mask]) > 1e-12:
            corr = float(np.corrcoef(truth_step[step_mask], pred_step[step_mask])[0, 1])
    return {
        "n": int(mask.sum()),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mape_percent": mape,
        "bias": float(np.mean(err)),
        "error_std": float(np.std(err)),
        "direction_accuracy": direction,
        "corr": corr,
        "pred_step_std": float(np.std(pred_step)) if len(pred_step) else None,
        "truth_step_std": float(np.std(truth_step)) if len(truth_step) else None,
    }


def post_json(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url.rstrip("/") + "/api/chronos/predict", data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def db_params(args: argparse.Namespace) -> dict[str, object]:
    params = dict(DB_PROFILES[args.db_profile]) if args.db_profile in DB_PROFILES else {}
    if args.db_host:
        params["host"] = args.db_host
    if args.db_port:
        params["port"] = str(args.db_port)
    if args.db_name:
        params["dbname"] = args.db_name
    if args.db_user:
        params["user"] = args.db_user
    if args.db_password:
        params["password"] = args.db_password
    elif args.db_password_env:
        env_password = os.getenv(args.db_password_env, "")
        if env_password and args.db_profile != "local":
            params["password"] = env_password
    return {
        "host": params.get("host", "127.0.0.1"),
        "port": int(params.get("port", "5432")),
        "dbname": params.get("dbname", "bf_trend"),
        "user": params.get("user", ""),
        "password": params.get("password", ""),
        "connect_timeout": 12,
    }


def choose_cutoffs(
    frame: pd.DataFrame,
    targets: list[str],
    context_minutes: int,
    horizon_minutes: int,
    count: int,
    stride_minutes: int,
    explicit: str,
    context_policy: str,
) -> list[pd.Timestamp]:
    if explicit:
        return [parse_ts(item.strip()) for item in explicit.split(",") if item.strip()]
    if frame.empty:
        return []
    latest = frame.index.max()
    earliest = frame.index.min()
    cutoffs: list[pd.Timestamp] = []
    candidate = latest - pd.Timedelta(minutes=horizon_minutes)
    while candidate - pd.Timedelta(minutes=context_minutes) >= earliest and len(cutoffs) < count:
        ok = True
        for target in targets:
            target_context_minutes = (
                chronos_context_minutes_for_target(target, context_minutes)
                if context_policy == "target"
                else context_minutes
            )
            context = frame.loc[
                (frame.index > candidate - pd.Timedelta(minutes=target_context_minutes)) & (frame.index <= candidate),
                target,
            ]
            truth = frame.loc[(frame.index > candidate) & (frame.index <= candidate + pd.Timedelta(minutes=horizon_minutes)), target]
            if len(context.dropna()) < min(30, target_context_minutes) or len(truth.dropna()) < max(5, int(horizon_minutes * 0.5)):
                ok = False
                break
        if ok:
            cutoffs.append(candidate.floor("min"))
        candidate -= pd.Timedelta(minutes=stride_minutes)
    return sorted(dict.fromkeys(cutoffs))


def build_payload_for_cutoff(
    frame: pd.DataFrame,
    targets: list[str],
    cutoff: pd.Timestamp,
    context_minutes: int,
    horizon_minutes: int,
    context_policy: str,
) -> tuple[dict, list[dict]]:
    history = frame.loc[frame.index <= cutoff]
    jobs: list[dict] = []
    skipped: list[dict] = []
    for target in targets:
        try:
            target_context_minutes = (
                chronos_context_minutes_for_target(target, context_minutes)
                if context_policy == "target"
                else context_minutes
            )
            job = build_chronos_job(history, target, horizon_minutes, target_context_minutes)
            job["cutoff_time"] = cutoff.isoformat(sep=" ")
            job["future_timestamps"] = [
                (cutoff + pd.Timedelta(minutes=idx)).isoformat(sep=" ")
                for idx in range(1, horizon_minutes + 1)
            ]
            jobs.append(job)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"target_id": target, "reason": str(exc)})
    return {
        "jobs": jobs,
        "skipped": skipped,
        "source": {"type": "postgresql_backtest"},
        "feature_source": {
            "type": "postgresql_115_points_with_prediction_feature_frame",
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "time_start": frame.index.min().isoformat(sep=" ") if len(frame.index) else None,
            "time_end": frame.index.max().isoformat(sep=" ") if len(frame.index) else None,
        },
        "request": {
            "context_minutes": context_minutes,
            "context_policy": context_policy,
            "prediction_minutes": horizon_minutes,
            "target_ids": targets,
            "cutoff_time": cutoff.isoformat(sep=" "),
            "data_source": "postgresql_history_backtest",
        },
    }, skipped


def summarize(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    df = pd.DataFrame(rows)
    out: list[dict] = []
    for target, group in df.groupby("target_id", sort=False):
        item = {
            "target_id": target,
            "target_name": group["target_name"].iloc[0],
            "windows": int(len(group)),
            "covariate_count_mean": float(group["covariate_count"].mean()),
        }
        for col in ["mae", "rmse", "mape_percent", "bias", "direction_accuracy", "corr", "pred_step_std", "truth_step_std"]:
            numeric = pd.to_numeric(group[col], errors="coerce")
            item[col + "_mean"] = None if numeric.dropna().empty else float(numeric.mean())
        out.append(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest Chronos2 predictions from PostgreSQL historical sensor data.")
    parser.add_argument("--db-profile", choices=["local", "22012", "custom"], default="local")
    parser.add_argument("--db-host", default="")
    parser.add_argument("--db-port", default="")
    parser.add_argument("--db-name", default="")
    parser.add_argument("--db-user", default="")
    parser.add_argument("--db-password", default="")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument("--chronos-url", default="http://127.0.0.1:8777")
    parser.add_argument("--targets", default=",".join(CHRONOS_TARGET_IDS), help="Comma separated target ids, or 'all'.")
    parser.add_argument("--context-minutes", type=int, default=480)
    parser.add_argument("--context-policy", choices=["target", "fixed"], default="target")
    parser.add_argument("--prediction-minutes", type=int, default=120)
    parser.add_argument("--lookback-days", type=float, default=3.0)
    parser.add_argument("--cutoffs", default="")
    parser.add_argument("--cutoff-count", type=int, default=3)
    parser.add_argument("--cutoff-stride-minutes", type=int, default=360)
    parser.add_argument("--timeout-seconds", type=float, default=1200)
    parser.add_argument("--output-dir", default=str(ROOT / "chronos外推预测" / "results" / "pg_backtest"))
    args = parser.parse_args()

    targets = list(CHRONOS_TARGET_IDS) if args.targets.strip().lower() == "all" else [
        item.strip() for item in args.targets.split(",") if item.strip()
    ]
    unknown = [item for item in targets if item not in CHRONOS_TARGET_IDS]
    if unknown:
        raise SystemExit(f"unsupported targets: {unknown}; valid={list(CHRONOS_TARGET_IDS)}")

    params = db_params(args)
    safe_params = {k: ("***" if k == "password" and v else v) for k, v in params.items()}
    print("DB", safe_params, flush=True)
    since = datetime.now() - timedelta(days=args.lookback_days)
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        frame = fetch_chronos_feature_frame(conn, since)
    if frame.empty:
        raise SystemExit("no feature data loaded from PostgreSQL")
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    print(
        f"FEATURE_FRAME rows={len(frame)} columns={len(frame.columns)} "
        f"start={frame.index.min()} end={frame.index.max()}",
        flush=True,
    )

    cutoffs = choose_cutoffs(
        frame,
        targets,
        args.context_minutes,
        args.prediction_minutes,
        args.cutoff_count,
        args.cutoff_stride_minutes,
        args.cutoffs,
        args.context_policy,
    )
    if not cutoffs:
        raise SystemExit("no valid cutoffs found for requested targets/context/horizon")
    print("CUTOFFS", [x.isoformat(sep=" ") for x in cutoffs], flush=True)

    detail_rows: list[dict] = []
    raw_results: list[dict] = []
    for cutoff in cutoffs:
        payload, skipped = build_payload_for_cutoff(
            frame,
            targets,
            cutoff,
            args.context_minutes,
            args.prediction_minutes,
            args.context_policy,
        )
        print(
            f"REQUEST cutoff={cutoff} jobs={len(payload['jobs'])} skipped={len(skipped)} "
            f"chronos={args.chronos_url}",
            flush=True,
        )
        result = post_json(args.chronos_url, payload, args.timeout_seconds)
        raw_results.append({"cutoff": cutoff.isoformat(sep=" "), "payload_meta": payload["feature_source"], "result": result})
        for prediction in result.get("predictions") or []:
            target = prediction.get("target_id")
            if target not in frame.columns:
                continue
            truth_series = frame.loc[
                (frame.index > cutoff) & (frame.index <= cutoff + pd.Timedelta(minutes=args.prediction_minutes)),
                target,
            ].head(args.prediction_minutes)
            pred = finite_array(prediction.get("p50") or [])
            truth = truth_series.to_numpy(dtype=float)
            n = min(len(pred), len(truth))
            row_metrics = metrics(truth[:n], pred[:n])
            row = {
                "cutoff": cutoff.isoformat(sep=" "),
                "target_id": target,
                "target_name": prediction.get("target_name") or DISPLAY_NAMES.get(target, target),
                "context_minutes": prediction.get("context_minutes"),
                "prediction_minutes": prediction.get("prediction_minutes"),
                "covariate_count": prediction.get("covariate_count"),
                "feature_type": prediction.get("feature_type"),
                "feature_engine": prediction.get("feature_engine"),
                "truth_points": int(len(truth)),
                "pred_points": int(len(pred)),
                "first_truth": None if not len(truth) or not math.isfinite(float(truth[0])) else float(truth[0]),
                "first_p50": None if not len(pred) or not math.isfinite(float(pred[0])) else float(pred[0]),
                "last_truth": None if not len(truth) or not math.isfinite(float(truth[-1])) else float(truth[-1]),
                "last_p50": None if not len(pred) or not math.isfinite(float(pred[-1])) else float(pred[-1]),
            }
            row.update(row_metrics)
            detail_rows.append(row)
            print(
                "RESULT",
                target,
                "cov",
                row["covariate_count"],
                "mae",
                row["mae"],
                "rmse",
                row["rmse"],
                "dir",
                row["direction_accuracy"],
                flush=True,
            )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail_path = output_dir / f"pg_chronos2_backtest_detail_{stamp}.csv"
    summary_path = output_dir / f"pg_chronos2_backtest_summary_{stamp}.json"
    raw_path = output_dir / f"pg_chronos2_backtest_raw_{stamp}.json"
    pd.DataFrame(detail_rows).to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary = {
        "created_at": datetime.now().isoformat(sep=" "),
        "chronos_url": args.chronos_url,
        "db": {k: ("***" if k == "password" and v else v) for k, v in params.items()},
        "feature_frame": {
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "time_start": frame.index.min().isoformat(sep=" "),
            "time_end": frame.index.max().isoformat(sep=" "),
        },
        "targets": targets,
        "cutoffs": [x.isoformat(sep=" ") for x in cutoffs],
        "context_minutes": args.context_minutes,
        "context_policy": args.context_policy,
        "prediction_minutes": args.prediction_minutes,
        "summary_by_target": summarize(detail_rows),
        "detail_csv": str(detail_path),
        "raw_json": str(raw_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_path.write_text(json.dumps(raw_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DETAIL_CSV", detail_path, flush=True)
    print("SUMMARY_JSON", summary_path, flush=True)
    print("RAW_JSON", raw_path, flush=True)
    print(json.dumps(summary["summary_by_target"], ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""V19 extractor with explicit NULL casts for optional PCI point tags."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "PT" / "预测铁水Si含量" / "src"))

import build_hot_metal_si_dataset as legacy_reader  # noqa: E402
import extract_v19_context as impl  # noqa: E402


def fetch_pci(connection: psycopg.Connection[Any], targets: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    registry = {
        str(row["variable_name"]): str(row["tag_long_name"])
        for row in connection.execute(
            """
            SELECT variable_name, tag_long_name FROM bf_sensor.sensor_registry
            WHERE is_enabled AND variable_name IN ('PCI_rate','PCI_current_hour','PCI_previous_hour')
            """
        ).fetchall()
    }
    rate_tag = registry.get("PCI_rate")
    if not rate_tag:
        raise RuntimeError("220.12 sensor_registry缺少PCI_rate")
    records = targets[["official_meltno", "prediction_cutoff_ts"]].to_dict("records")
    minutes: list[dict[str, Any]] = []
    official: dict[str, dict[str, Any]] = {}
    for chunk in impl._chunks(records, 50):
        values_sql = ",".join(["(%s::text,%s::timestamp)"] * len(chunk))
        target_params: list[Any] = []
        for item in chunk:
            target_params.extend([str(item["official_meltno"]), item["prediction_cutoff_ts"]])
        current_tag = registry.get("PCI_current_hour")
        previous_tag = registry.get("PCI_previous_hour")
        params = [*target_params, rate_tag, current_tag, current_tag, previous_tag, previous_tag]
        rows = connection.execute(
            f"""
            WITH targets(official_meltno,target_ts) AS (VALUES {values_sql})
            SELECT t.official_meltno, rate.ts, rate.value,
                   current_hour.value AS pci_current_hour,
                   previous_hour.value AS pci_previous_hour
            FROM targets t
            LEFT JOIN LATERAL (
                SELECT v.ts,v.value FROM bf_sensor.one_minute_values v
                WHERE v.tag_long_name=%s
                  AND v.ts >= date_trunc('hour',t.target_ts)-interval '1 hour'
                  AND v.ts < t.target_ts ORDER BY v.ts
            ) rate ON TRUE
            LEFT JOIN LATERAL (
                SELECT v.value FROM bf_sensor.one_minute_values v
                WHERE %s::text IS NOT NULL AND v.tag_long_name=%s
                  AND v.ts < t.target_ts AND v.ts >= t.target_ts-interval '120 minutes'
                ORDER BY v.ts DESC LIMIT 1
            ) current_hour ON TRUE
            LEFT JOIN LATERAL (
                SELECT v.value FROM bf_sensor.one_minute_values v
                WHERE %s::text IS NOT NULL AND v.tag_long_name=%s
                  AND v.ts < t.target_ts AND v.ts >= t.target_ts-interval '120 minutes'
                ORDER BY v.ts DESC LIMIT 1
            ) previous_hour ON TRUE
            ORDER BY t.official_meltno,rate.ts
            """,
            params,
        ).fetchall()
        for raw in rows:
            item = dict(raw)
            meltno = str(item["official_meltno"])
            if item.get("ts") is not None and item.get("value") is not None:
                minutes.append({"official_meltno": meltno, "ts": item["ts"], "value": item["value"]})
            if item.get("pci_current_hour") is not None or item.get("pci_previous_hour") is not None:
                official.setdefault(meltno, {"official_meltno": meltno, "pci_current_hour": item.get("pci_current_hour"), "pci_previous_hour": item.get("pci_previous_hour")})
    minute_frame = pd.DataFrame(minutes, columns=["official_meltno","ts","value"])
    official_frame = pd.DataFrame(list(official.values()), columns=["official_meltno","pci_current_hour","pci_previous_hour"])
    context = impl.build_pci_context_features(targets, minute_frame, official_frame)
    return context, {"registry_variables": sorted(registry), "minute_rows": len(minute_frame), "official_rows": len(official_frame), "official_source_coverage": float(context["pci_context__source_official"].mean()) if len(context) else 0.0}


def main() -> int:
    cli = impl.parser()
    args = cli.parse_args()
    args.connect_timeout = 20
    targets = pd.read_csv(args.heat_targets.resolve(), low_memory=False, encoding="utf-8-sig")
    targets["official_meltno"] = targets["official_meltno"].astype(str)
    targets["prediction_cutoff_ts"] = pd.to_datetime(targets["prediction_cutoff_ts"], errors="raise")
    history = impl.build_mean_si_history_context(targets)
    with legacy_reader.sensor_ssh_tunnel(args) as (port, ssh_client):
        params = legacy_reader.remote_sensor_params(args, port, ssh_client)
        params["options"] = "-c default_transaction_read_only=on -c statement_timeout=120000"
        with psycopg.connect(**params, row_factory=dict_row) as connection:
            pci, pci_audit = fetch_pci(connection, targets)
    chemistry, chemistry_audit = impl.fetch_chemistry(targets, args.imes_env_file)
    context = impl.merge_v19_context_features(targets[["official_meltno"]], history, pci, chemistry)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    context.to_csv(output, index=False, encoding="utf-8-sig")
    audit = {"requirement_id":"REQ-SI-V19-CONTEXT-ABLATION-20260806","generated_at":datetime.now().isoformat(timespec="seconds"),"read_policy":"readonly","rows":len(context),"history_columns":len(history.columns)-1,"pci":pci_audit,"chemistry":chemistry_audit,"chemistry_lineage_status":"batch_to_heat_unverified_time_background_only"}
    audit_path = output.with_suffix(".audit.json")
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=impl._json_default), encoding="utf-8")
    print(json.dumps({"ok":True,"output":str(output),"audit":str(audit_path),"rows":len(context)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

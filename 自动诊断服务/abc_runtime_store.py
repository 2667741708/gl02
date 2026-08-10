"""Idempotent ABC33 persistence for the 8768 bridge connection."""
from __future__ import annotations

import json
from typing import Any, Mapping

from abc_rule_engine import public_rule


def persist_bundle(conn: Any, bundle: Mapping[str, Any], *, source_snapshot_id: int | None = None, furnace_id: str = "GL02") -> int | None:
    timestamp = bundle.get("evaluation_ts")
    if not timestamp:
        return None
    row = conn.execute(
        """
        INSERT INTO bf_sensor.abc_rule_evaluation_batches
            (furnace_id,evaluation_ts,catalog_version,config_version,config_hash,source_snapshot_id,coverage_ratio,data_age_seconds,public_bundle)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (furnace_id,evaluation_ts,config_hash) DO UPDATE SET public_bundle=excluded.public_bundle
        RETURNING id
        """,
        (furnace_id, timestamp, bundle.get("catalog_version"), bundle.get("config_version"), bundle.get("config_hash"), source_snapshot_id,
         (bundle.get("quality") or {}).get("coverage_ratio"), (bundle.get("quality") or {}).get("data_age_seconds"), json.dumps(bundle.get("public", {}), ensure_ascii=False, default=str)),
    ).fetchone()
    batch_id = row["id"] if isinstance(row, Mapping) else row[0]
    for item in bundle.get("evaluations", []):
        conn.execute(
            """
            INSERT INTO bf_sensor.abc_rule_evaluation_items
                (batch_id,rule_id,category,display_name,score,confidence,status,formula_terms,weights,thresholds,normalized_values,contributions,missing_features,public_detail)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb)
            ON CONFLICT (batch_id,rule_id) DO UPDATE SET score=excluded.score,confidence=excluded.confidence,status=excluded.status,
                formula_terms=excluded.formula_terms,weights=excluded.weights,thresholds=excluded.thresholds,
                normalized_values=excluded.normalized_values,contributions=excluded.contributions,missing_features=excluded.missing_features,
                public_detail=excluded.public_detail
            """,
            (batch_id,item["rule_id"],item["category"],item["display_name"],item["score"],item["confidence"],item["status"],
             json.dumps(item.get("formula_terms", []), ensure_ascii=False),json.dumps(item.get("weights", {}), ensure_ascii=False),json.dumps(item.get("thresholds", {}), ensure_ascii=False),
             json.dumps({x["feature_key"]:x["normalized_value"] for x in item.get("contributions", [])}, ensure_ascii=False),json.dumps(item.get("contributions", []), ensure_ascii=False),
             json.dumps(item.get("missing_features", []), ensure_ascii=False),json.dumps(public_rule(item), ensure_ascii=False, default=str)),
        )
    conn.commit()
    return int(batch_id)

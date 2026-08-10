#!/usr/bin/env python3
"""Verify WebSocket-to-PostgreSQL full recommendation audit persistence."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

import psycopg
import websockets
from psycopg.rows import dict_row


LABELS = {"normal", "lowline", "edge", "center", "channel", "cold", "hot", "column"}
FULL_ACTION_FIELDS = {
    "source_refs",
    "trigger_evidence",
    "preconditions",
    "blocking_reasons",
    "delta",
    "sequence",
    "missing_inputs",
    "observation_window",
    "approval",
}


def environment_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    if os.name != "nt":
        return default
    try:
        import winreg

        path = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value or default)
    except OSError:
        return default


async def read_init(uri: str, timeout_seconds: float) -> dict[str, Any]:
    async with websockets.connect(uri, open_timeout=timeout_seconds, max_size=24 * 1024 * 1024) as socket:
        raw = await asyncio.wait_for(socket.recv(), timeout=timeout_seconds)
    payload = json.loads(raw)
    if payload.get("type") != "init":
        raise RuntimeError(f"first WebSocket frame is {payload.get('type')!r}, expected 'init'")
    return payload


def verify_payload(payload: dict[str, Any]) -> dict[str, Any]:
    diagnosis = payload.get("diagnosis") or {}
    status = diagnosis.get("recommendation_status") or {}
    audit = diagnosis.get("recommendation_audit") or {}
    bundle = diagnosis.get("recommendation_bundle") or {}
    conditions = bundle.get("conditions") or []
    if status.get("state") != "ready" or status.get("audit_state") != "persisted":
        raise RuntimeError(f"recommendation is not audit-persisted: {status}")
    if not audit.get("immutable") or audit.get("read_only") is not True:
        raise RuntimeError(f"audit metadata is not immutable/read-only: {audit}")
    if not audit.get("batch_id"):
        raise RuntimeError("audit batch_id is missing")
    if bundle.get("schema_version") != "multi_condition_recommendation.v1":
        raise RuntimeError("multi-condition bundle schema is missing")
    labels = {item.get("label") for item in conditions if isinstance(item, dict)}
    if len(conditions) != 8 or labels != LABELS:
        raise RuntimeError(f"expected all eight conditions, got: {sorted(labels)}")
    actions = [
        action
        for condition in conditions
        for action in ((condition.get("recommendation") or {}).get("actions") or [])
    ]
    for action in actions:
        missing = FULL_ACTION_FIELDS.difference(action)
        if missing:
            raise RuntimeError(f"action {action.get('id')} is missing full fields: {sorted(missing)}")
        if action.get("read_only") is not True:
            raise RuntimeError(f"action {action.get('id')} is not read-only")
    if len(actions) != int(audit.get("action_count") or 0):
        raise RuntimeError("WebSocket bundle action count differs from audit metadata")
    return {
        "batch_id": int(audit["batch_id"]),
        "idempotency_key": str(audit.get("idempotency_key") or ""),
        "condition_count": len(conditions),
        "action_count": len(actions),
        "created": bool(audit.get("created")),
        "engine_version": (bundle.get("engine_meta") or {}).get("version"),
        "policy_sha256": (bundle.get("engine_meta") or {}).get("policy_sha256"),
    }


def verify_database(args: argparse.Namespace, expected: dict[str, Any]) -> dict[str, Any]:
    password = environment_value(args.password_env)
    if not password:
        raise RuntimeError(f"database password environment variable is missing: {args.password_env}")
    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=args.database,
        user=args.user,
        password=password,
        connect_timeout=15,
        row_factory=dict_row,
    ) as conn:
        batch = conn.execute(
            """
            SELECT id, idempotency_key, condition_count, action_count, status_counts,
                   recommendation_bundle, read_only, engine_version, policy_sha256
            FROM bf_assistant.recommendation_audit_batches
            WHERE id = %s
            """,
            (expected["batch_id"],),
        ).fetchone()
        if not batch:
            raise RuntimeError(f"audit batch {expected['batch_id']} does not exist")
        summary = conn.execute(
            """
            SELECT count(*) AS action_count,
                   count(DISTINCT condition_label) AS condition_count,
                   bool_and(read_only) AS all_read_only,
                   bool_and(jsonb_typeof(trigger_evidence) = 'array') AS evidence_complete,
                   bool_and(jsonb_typeof(sequence_plan) = 'object') AS sequence_complete,
                   bool_and(jsonb_typeof(approval) = 'object') AS approval_complete,
                   bool_and(action_payload ?& ARRAY[
                       'source_refs','trigger_evidence','preconditions','blocking_reasons',
                       'delta','sequence','missing_inputs','observation_window','approval'
                   ]) AS payload_complete
            FROM bf_assistant.recommendation_audit_actions
            WHERE batch_id = %s
            """,
            (expected["batch_id"],),
        ).fetchone()
        duplicate_count = conn.execute(
            """
            SELECT count(*) AS count
            FROM bf_assistant.recommendation_audit_batches
            WHERE idempotency_key = %s
            """,
            (batch["idempotency_key"],),
        ).fetchone()["count"]
        privileges = conn.execute(
            """
            SELECT
                has_table_privilege('gl02_sync', 'bf_assistant.recommendation_audit_batches', 'SELECT,INSERT') AS writer_batch_append,
                has_table_privilege('gl02_sync', 'bf_assistant.recommendation_audit_actions', 'SELECT,INSERT') AS writer_action_append,
                has_table_privilege('gl02_sync', 'bf_assistant.recommendation_audit_batches', 'UPDATE') AS writer_batch_update,
                has_table_privilege('gl02_sync', 'bf_assistant.recommendation_audit_actions', 'DELETE') AS writer_action_delete,
                has_table_privilege('gl02_reader', 'bf_assistant.recommendation_audit_batches', 'SELECT') AS reader_batch_select,
                has_table_privilege('gl02_reader', 'bf_assistant.recommendation_audit_actions', 'SELECT') AS reader_action_select
            """
        ).fetchone()
        immutable_trigger_count = conn.execute(
            """
            SELECT count(*) AS count
            FROM pg_trigger
            WHERE tgname IN (
                'trg_recommendation_audit_batches_immutable',
                'trg_recommendation_audit_actions_immutable'
            ) AND NOT tgisinternal
            """
        ).fetchone()["count"]

    if int(batch["condition_count"]) != 8 or int(summary["condition_count"]) != 8:
        raise RuntimeError("database batch does not contain all eight conditions")
    if int(batch["action_count"]) != expected["action_count"] or int(summary["action_count"]) != expected["action_count"]:
        raise RuntimeError("database action count differs from WebSocket bundle")
    if not all(summary[key] for key in ("all_read_only", "evidence_complete", "sequence_complete", "approval_complete", "payload_complete")):
        raise RuntimeError(f"database full-field contract failed: {summary}")
    if int(duplicate_count) != 1:
        raise RuntimeError(f"idempotency key has {duplicate_count} batch rows")
    if not privileges["writer_batch_append"] or not privileges["writer_action_append"]:
        raise RuntimeError("runtime writer lacks append privileges")
    if privileges["writer_batch_update"] or privileges["writer_action_delete"]:
        raise RuntimeError("runtime writer has forbidden mutation privileges")
    if not privileges["reader_batch_select"] or not privileges["reader_action_select"]:
        raise RuntimeError("read-only role lacks audit SELECT privileges")
    if int(immutable_trigger_count) != 2:
        raise RuntimeError(f"immutable audit trigger count is {immutable_trigger_count}, expected 2")
    return {
        "batch": {
            "id": batch["id"],
            "condition_count": batch["condition_count"],
            "action_count": batch["action_count"],
            "status_counts": batch["status_counts"],
            "read_only": batch["read_only"],
            "engine_version": batch["engine_version"],
            "policy_sha256": batch["policy_sha256"],
        },
        "actions": dict(summary),
        "idempotency_rows": int(duplicate_count),
        "privileges": dict(privileges),
        "immutable_trigger_count": int(immutable_trigger_count),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    first = verify_payload(await read_init(args.uri, args.timeout))
    second = verify_payload(await read_init(args.uri, args.timeout))
    if first["batch_id"] != second["batch_id"]:
        raise RuntimeError(f"repeated init created different audit batches: {first['batch_id']} != {second['batch_id']}")
    database = verify_database(args, second)
    return {
        "ok": True,
        "schema_version": "recommendation_audit.runtime_acceptance.v1",
        "uri": args.uri,
        "first": first,
        "second": second,
        "database": database,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default="ws://127.0.0.1:8768")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="bf_trend")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password-env", default="GL02_PGADMIN_PASSWORD")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import re
import select
import socket
import socketserver
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import paramiko
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
DB_SRC_CANDIDATES = [
    ROOT / "db_sync_storage" / "src",
    ROOT / "数据库同步和存取" / "src",
]
for DB_SRC in DB_SRC_CANDIDATES:
    if (DB_SRC / "pg_store.py").exists() and str(DB_SRC) not in sys.path:
        sys.path.insert(0, str(DB_SRC))
        break

from pg_store import ensure_partitions  # noqa: E402


def read_agents_value(pattern: str) -> str | None:
    if not AGENTS.exists():
        return None
    text = AGENTS.read_text(encoding="utf-8", errors="ignore")
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


class ForwardServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(socketserver.BaseRequestHandler):
    ssh_transport: paramiko.Transport
    remote_host: str
    remote_port: int

    def handle(self) -> None:
        try:
            chan = self.ssh_transport.open_channel(
                "direct-tcpip",
                (self.remote_host, self.remote_port),
                self.request.getpeername(),
            )
        except Exception:
            return
        if chan is None:
            return
        try:
            while True:
                r, _, _ = select.select([self.request, chan], [], [], 1.0)
                if self.request in r:
                    data = self.request.recv(16384)
                    if not data:
                        break
                    chan.send(data)
                if chan in r:
                    data = chan.recv(16384)
                    if not data:
                        break
                    self.request.send(data)
        finally:
            chan.close()
            self.request.close()


@contextmanager
def ssh_tunnel(args: argparse.Namespace):
    password = os.getenv("BF_22012_SSH_PASSWORD") or read_agents_value(r"SSH 密码：([^\r\n]+)")
    if not password:
        password = getpass.getpass(f"SSH password for {args.ssh_user}@{args.ssh_host}: ")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=args.ssh_host,
        username=args.ssh_user,
        password=password,
        timeout=30,
        banner_timeout=60,
        auth_timeout=30,
        look_for_keys=False,
        allow_agent=False,
    )
    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport was not opened")
    handler = type(
        "PostgresForwardHandler",
        (Handler,),
        {"ssh_transport": transport, "remote_host": args.remote_pg_host, "remote_port": args.remote_pg_port},
    )
    server = ForwardServer(("127.0.0.1", args.local_tunnel_port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield args.local_tunnel_port, client
    finally:
        server.shutdown()
        server.server_close()
        client.close()


def pg_params(host: str, port: int, user: str, password: str, dbname: str, timeout: int = 10) -> dict[str, Any]:
    return {
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": user,
        "password": password,
        "connect_timeout": timeout,
    }


def local_params(args: argparse.Namespace) -> dict[str, Any]:
    return pg_params(
        os.getenv("GL02_LOCAL_PGHOST", args.local_pg_host),
        int(os.getenv("GL02_LOCAL_PGPORT", str(args.local_pg_port))),
        os.getenv("GL02_LOCAL_PGUSER", args.local_pg_user),
        os.getenv("GL02_LOCAL_PGPASSWORD", args.local_pg_password),
        os.getenv("GL02_LOCAL_PGDATABASE", args.local_pg_db),
    )


def fetch_remote_machine_env(client: paramiko.SSHClient, names: list[str]) -> dict[str, str]:
    ps_names = "@(" + ",".join("'" + name.replace("'", "''") + "'" for name in names) + ")"
    script = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        + f"$names={ps_names}; "
        + "$o=@{}; foreach($n in $names){ $o[$n]=[Environment]::GetEnvironmentVariable($n,'Machine') }; "
        + "$o | ConvertTo-Json -Compress"
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    command = f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}"
    _, stdout, stderr = client.exec_command(command, timeout=30)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    status = stdout.channel.recv_exit_status()
    if status != 0:
        raise RuntimeError(f"Failed to read remote machine environment: {err or out}")
    return {key: str(value or "") for key, value in json.loads(out or "{}").items()}


def remote_params(args: argparse.Namespace, tunnel_port: int, client: paramiko.SSHClient) -> dict[str, Any]:
    env = fetch_remote_machine_env(client, ["GL02_PGUSER", "GL02_PGPASSWORD", "GL02_READER_PASSWORD"])
    user = os.getenv("GL02_REMOTE_PGUSER") or env.get("GL02_PGUSER") or args.remote_pg_user
    password = os.getenv("GL02_REMOTE_PGPASSWORD") or env.get("GL02_PGPASSWORD") or env.get("GL02_READER_PASSWORD") or ""
    return pg_params("127.0.0.1", tunnel_port, user, password or "", args.remote_pg_db)


def table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def latest_ts(conn, table: str, column: str) -> datetime | None:
    row = conn.execute(f"SELECT max({column}) AS ts FROM {table}").fetchone()
    return row["ts"] if row and row["ts"] else None


def sync_sensor(remote, local, since: datetime | None, batch_size: int) -> int:
    remote_max = latest_ts(remote, "bf_sensor.one_minute_values", "ts")
    if remote_max:
        ensure_partitions(local, since or (remote_max - timedelta(days=1)), remote_max)
    where = ""
    params: list[Any] = []
    if since:
        where = "WHERE ts > %s"
        params.append(since)
    cur = remote.cursor()
    cur.execute(
        f"""
        SELECT tag_long_name, ts, value, quality, value_type, aggregate, interval_seconds, source_server, collected_at
        FROM bf_sensor.one_minute_values
        {where}
        ORDER BY ts ASC
        """,
        params,
    )
    written = 0
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        with local.cursor() as out:
            out.executemany(
                """
                INSERT INTO bf_sensor.one_minute_values (
                    tag_long_name, ts, value, quality, value_type,
                    aggregate, interval_seconds, source_server, collected_at
                )
                VALUES (%(tag_long_name)s, %(ts)s, %(value)s, %(quality)s, %(value_type)s,
                        %(aggregate)s, %(interval_seconds)s, %(source_server)s, %(collected_at)s)
                ON CONFLICT(tag_long_name, ts) DO UPDATE SET
                    value=excluded.value,
                    quality=excluded.quality,
                    value_type=excluded.value_type,
                    aggregate=excluded.aggregate,
                    interval_seconds=excluded.interval_seconds,
                    source_server=excluded.source_server,
                    collected_at=excluded.collected_at
                """,
                rows,
            )
        local.commit()
        written += len(rows)
        print(json.dumps({"section": "sensor", "written": written, "last_ts": str(rows[-1]["ts"])}, ensure_ascii=False), flush=True)
    cur.close()
    return written


def sync_dynamic(
    remote,
    local,
    table: str,
    key_columns: list[str],
    since_column: str | None,
    since: datetime | None,
    batch_size: int,
) -> int:
    if not table_exists(remote, table) or not table_exists(local, table):
        return 0
    column_meta = remote.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
        """,
        tuple(table.split(".")),
    ).fetchall()
    columns = [row["column_name"] for row in column_meta]
    json_columns = {row["column_name"] for row in column_meta if row["data_type"] in {"json", "jsonb"}}
    if "id" in columns and "id" not in key_columns:
        columns = [c for c in columns if c != "id"]
    update_columns = [c for c in columns if c not in key_columns]
    where = ""
    params: list[Any] = []
    if since_column and since:
        where = f"WHERE {since_column} > %s"
        params.append(since)
    col_sql = ", ".join(columns)
    order_col = since_column or key_columns[0]
    cur = remote.cursor()
    cur.execute(f"SELECT {col_sql} FROM {table} {where} ORDER BY {order_col} ASC", params)
    placeholders = ", ".join(f"%({c})s" for c in columns)
    conflict = ", ".join(key_columns)
    update_sql = ", ".join(f"{c}=excluded.{c}" for c in update_columns)
    if update_sql:
        sql = f"""
            INSERT INTO {table} ({col_sql})
            VALUES ({placeholders})
            ON CONFLICT({conflict}) DO UPDATE SET {update_sql}
        """
    else:
        sql = f"""
            INSERT INTO {table} ({col_sql})
            VALUES ({placeholders})
            ON CONFLICT({conflict}) DO NOTHING
        """
    written = 0
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        adapted_rows = []
        for row in rows:
            item = dict(row)
            for column in json_columns:
                if column in item and isinstance(item[column], (dict, list)):
                    item[column] = Jsonb(item[column])
            adapted_rows.append(item)
        with local.cursor() as out:
            out.executemany(sql, adapted_rows)
        local.commit()
        written += len(rows)
        print(json.dumps({"section": table, "written": written}, ensure_ascii=False), flush=True)
    cur.close()
    return written


def ensure_local_aux_schema(conn) -> None:
    conn.execute(
        """
        CREATE SCHEMA IF NOT EXISTS bf_sensor;

        CREATE TABLE IF NOT EXISTS bf_sensor.zero_value_audits (
            id bigserial PRIMARY KEY,
            tag_long_name text NOT NULL,
            variable_name text NOT NULL DEFAULT '',
            ts timestamp without time zone NOT NULL,
            db_value double precision,
            pspace_value double precision,
            pspace_quality text NOT NULL DEFAULT '',
            pspace_aggregate text NOT NULL DEFAULT 'PS_HIS_AVERAGE',
            source_server text NOT NULL DEFAULT '',
            verification_status text NOT NULL,
            error text NOT NULL DEFAULT '',
            details jsonb NOT NULL DEFAULT '{}'::jsonb,
            verified_at timestamp without time zone NOT NULL DEFAULT now(),
            UNIQUE (tag_long_name, ts, pspace_aggregate)
        );

        CREATE INDEX IF NOT EXISTS idx_zero_value_audits_status
            ON bf_sensor.zero_value_audits (verification_status, verified_at DESC);

        CREATE INDEX IF NOT EXISTS idx_zero_value_audits_ts
            ON bf_sensor.zero_value_audits (ts DESC, tag_long_name);
        """
    )
    conn.commit()


def safe_sync(name: str, fn, *, required: bool = True) -> dict[str, Any]:
    try:
        return {"ok": True, "written": fn()}
    except Exception as exc:  # noqa: BLE001
        if required:
            raise
        return {"ok": False, "written": 0, "error": f"{type(exc).__name__}: {exc}"}


def reset_local_sequences(conn) -> dict[str, int]:
    tables = [
        "bf_sensor.diagnosis_snapshots",
        "bf_sensor.data_quality_status",
        "bf_sensor.backfill_tasks",
        "bf_sensor.automation_runs",
        "bf_sensor.daily_baselines",
        "bf_sensor.zero_value_audits",
        "bf_sensor.conversation_delta_contexts",
    ]
    result: dict[str, int] = {}
    for table in tables:
        if not table_exists(conn, table):
            continue
        row = conn.execute("SELECT pg_get_serial_sequence(%s, 'id') AS seq", (table,)).fetchone()
        seq = row["seq"] if row else None
        if not seq:
            continue
        max_row = conn.execute(f"SELECT coalesce(max(id), 0) AS max_id FROM {table}").fetchone()
        max_id = int(max_row["max_id"] or 0)
        conn.execute("SELECT setval(%s, %s, %s)", (seq, max(max_id, 1), max_id > 0))
        result[table] = max_id
    conn.commit()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync read-only PostgreSQL data from 220.12 to local Docker PostgreSQL through SSH tunnel.")
    parser.add_argument("--ssh-host", default="10.30.220.12")
    parser.add_argument("--ssh-user", default="administrator")
    parser.add_argument("--remote-pg-host", default="127.0.0.1")
    parser.add_argument("--remote-pg-port", type=int, default=5432)
    parser.add_argument("--remote-pg-user", default="gl02_sync")
    parser.add_argument("--remote-pg-db", default="bf_trend")
    parser.add_argument("--local-tunnel-port", type=int, default=56432)
    parser.add_argument("--local-pg-host", default="127.0.0.1")
    parser.add_argument("--local-pg-port", type=int, default=15432)
    parser.add_argument("--local-pg-user", default="gl02_sync")
    parser.add_argument("--local-pg-password", default="gl02_local_sync")
    parser.add_argument("--local-pg-db", default="bf_trend")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--sensor-since", default="local-max", help="'local-max', ISO datetime, or empty for all.")
    parser.add_argument("--diagnosis-since", default="local-max", help="'local-max', ISO datetime, or empty for all.")
    args = parser.parse_args()

    with ssh_tunnel(args) as (port, ssh_client):
        with psycopg.connect(**remote_params(args, port, ssh_client), row_factory=dict_row) as remote, psycopg.connect(
            **local_params(args), row_factory=dict_row
        ) as local:
            ensure_local_aux_schema(local)
            sensor_since = None
            if args.sensor_since == "local-max":
                sensor_since = latest_ts(local, "bf_sensor.one_minute_values", "ts")
            elif args.sensor_since:
                sensor_since = datetime.fromisoformat(args.sensor_since.replace("T", " "))

            diag_since = None
            if args.diagnosis_since == "local-max":
                diag_since = latest_ts(local, "bf_sensor.diagnosis_snapshots", "diagnosis_ts")
            elif args.diagnosis_since:
                diag_since = datetime.fromisoformat(args.diagnosis_since.replace("T", " "))

            quality_since = latest_ts(local, "bf_sensor.data_quality_status", "checked_at")
            zero_audit_since = latest_ts(local, "bf_sensor.zero_value_audits", "verified_at")
            result = {
                "registry": safe_sync(
                    "sensor_registry",
                    lambda: sync_dynamic(remote, local, "bf_sensor.sensor_registry", ["variable_name"], None, None, args.batch_size),
                ),
                "sensor": safe_sync("sensor", lambda: sync_sensor(remote, local, sensor_since, args.batch_size)),
                "baseline": safe_sync(
                    "daily_baselines",
                    lambda: sync_dynamic(
                        remote,
                        local,
                        "bf_sensor.daily_baselines",
                        ["baseline_day", "baseline_days", "variable_name"],
                        None,
                        None,
                        args.batch_size,
                    ),
                ),
                "diagnosis": safe_sync(
                    "diagnosis_snapshots",
                    lambda: sync_dynamic(
                        remote,
                        local,
                        "bf_sensor.diagnosis_snapshots",
                        ["diagnosis_ts", "baseline_days", "window_minutes", "source"],
                        "diagnosis_ts",
                        diag_since,
                        args.batch_size,
                    ),
                ),
                "quality": safe_sync(
                    "data_quality_status",
                    lambda: sync_dynamic(remote, local, "bf_sensor.data_quality_status", ["id"], "checked_at", quality_since, args.batch_size),
                    required=False,
                ),
                "zero_audits": safe_sync(
                    "zero_value_audits",
                    lambda: sync_dynamic(
                        remote,
                        local,
                        "bf_sensor.zero_value_audits",
                        ["tag_long_name", "ts", "pspace_aggregate"],
                        "verified_at",
                        zero_audit_since,
                        args.batch_size,
                    ),
                    required=False,
                ),
                "queues": safe_sync(
                    "diagnosis_queues",
                    lambda: sync_dynamic(remote, local, "bf_sensor.diagnosis_queues", ["queue_id"], None, None, args.batch_size),
                    required=False,
                ),
                "summaries": safe_sync(
                    "short_window_summaries",
                    lambda: sync_dynamic(
                        remote,
                        local,
                        "bf_sensor.short_window_summaries",
                        ["queue_id", "model_name"],
                        None,
                        None,
                        args.batch_size,
                    ),
                    required=False,
                ),
            }
            result["sequences"] = {"ok": True, "values": reset_local_sequences(local)}
            print(json.dumps({"ok": True, **result}, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

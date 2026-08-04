from __future__ import annotations

import argparse
import importlib.util
import io
import json
import logging
import os
import re
import sys
import textwrap
import time
from pathlib import Path

import paramiko


logging.getLogger("paramiko").setLevel(logging.WARNING)


ROOT = Path(__file__).resolve().parents[3]
MCP_SERVER = Path(__file__).resolve().parent / "bf_data_mcp_server.py"
AGENTS = ROOT / "AGENTS.md"


def load_mcp_module():
    spec = importlib.util.spec_from_file_location("bf_data_mcp_server_local", MCP_SERVER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load MCP module: {MCP_SERVER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ssh_password(allow_agents_password: bool) -> str:
    value = os.getenv("BF_22012_SSH_PASSWORD")
    if value:
        return value
    if allow_agents_password:
        text = AGENTS.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"SSH 密码：([^\r\n]+)", text)
        if match:
            return match.group(1).strip()
    raise SystemExit("缺少 220.12 SSH 密码。请设置 BF_22012_SSH_PASSWORD，或显式传 --allow-agents-password。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query GL02 pSpace data via 10.30.220.12 jump host.")
    parser.add_argument("action", choices=("latest", "history", "stats", "info", "search"))
    parser.add_argument("--variable", default="")
    parser.add_argument("--keyword", default="")
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--agg", choices=("avg", "min", "max", "count", "first", "last", "all"), default="avg")
    parser.add_argument("--jump-host", default=os.getenv("BF_22012_HOST", "10.30.220.12"))
    parser.add_argument("--jump-user", default=os.getenv("BF_22012_USER", "administrator"))
    parser.add_argument("--remote-root", default=os.getenv("BF_22012_PROJECT_ROOT", r"F:\高炉炼铁项目-real-sensor-v2_V3"))
    parser.add_argument("--pspace-server", default=os.getenv("PSPACE_SERVER", "10.22.181.243"))
    parser.add_argument("--pspace-port", default=os.getenv("PSPACE_PORT", "8889"))
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("BF_MCP_PSPACE_INTERVAL_SECONDS", "60")))
    parser.add_argument("--aggregate", default=os.getenv("BF_MCP_PSPACE_AGGREGATE", "PS_HIS_AVERAGE"))
    parser.add_argument("--allow-agents-password", action="store_true")
    return parser.parse_args()


def remote_python(params: dict) -> str:
    return r'''
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

P = json.loads(r"""__PARAMS__""")
ROOT = Path(P["remote_root"])
SDK_ROOT = ROOT / "pythonSDK(1)"
CFG = ROOT / "ghsc" / "src" / "main" / "resources" / "application-prod.yml"

def clean(raw):
    value = raw.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] in "'\"" and value[-1] == value[0]:
        return value[1:-1]
    return value

def read_config(path):
    values = {}
    in_pspace = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if re.match(r"^pspace\s*:\s*$", line):
            in_pspace = True
            continue
        if in_pspace and line.strip() and not line[:1].isspace():
            break
        if not in_pspace or ":" not in line:
            continue
        key, raw = line.strip().split(":", 1)
        if key.strip() in {"ip", "port", "username", "password"}:
            values[key.strip()] = clean(raw)
    return values

def parse_dt(value):
    value = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo:
        dt = dt.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
    return dt

def ps_time(dt):
    return dt.strftime("%Y/%m/%d %H:%M:%S.000")

def numeric_items(mapping):
    def key(item):
        try:
            return int(item[0])
        except Exception:
            return 10**12
    for k, v in sorted(mapping.items(), key=key):
        try:
            int(k)
        except Exception:
            continue
        yield k, v

sys.path.insert(0, str(SDK_ROOT))
from PythonAPI.PsServer import PsObject
from PythonAPI import Type as T

cfg = read_config(CFG)
conn = {
    T.ServerDict: P["pspace_server"] or cfg.get("ip") or "10.22.181.243",
    T.ServerPortDict: str(P["pspace_port"] or cfg.get("port") or "8889"),
    T.UserDict: os.getenv("PSPACE_USER") or cfg.get("username") or "",
    T.PassDict: os.getenv("PSPACE_PASSWORD") or cfg.get("password") or "",
}
pspace = PsObject()
try:
    result = pspace.Connect(conn)
    if result.get(T.Return) != 0:
        raise RuntimeError(f"Connect failed: return={result.get(T.Return)} error={result.get(T.Error)}")
    tag = P["tag"]
    action = P["action"]
    if action == "latest":
        raw = pspace.RealReadList({T.RealReadListTagNameBuffer: [tag]})
        latest = None
        for _, item in numeric_items(raw):
            if not isinstance(item, dict):
                continue
            latest = {
                "ts": item.get(T.PsRealReadListTimeStamp, ""),
                "value": item.get(T.PsRealReadListValueDict, None),
                "quality": item.get(T.PsRealReadListListQualityDict, ""),
                "aggregate": "REALTIME",
                "interval_seconds": 0,
            }
            break
        print(json.dumps({"ok": True, "latest": latest}, ensure_ascii=False, default=str))
    else:
        start = parse_dt(P["start"])
        end = parse_dt(P["end"])
        raw = pspace.HisReadProcessed({
            T.HisReadProcessedTagNameBuffer: [tag],
            T.HisReadProcessedstartTime: ps_time(start),
            T.HisReadProcessedendTime: ps_time(end),
            T.HisReadProcessedInterval: int(P["interval_seconds"]),
            T.HisReadProcessedStatistics: [P["aggregate"]],
        })
        records = raw.get(tag, {})
        rows = []
        if isinstance(records, dict):
            for _, rec in numeric_items(records):
                if not isinstance(rec, dict):
                    continue
                rows.append({
                    "ts": rec.get(T.TimeStamp, ""),
                    "value": rec.get(T.ValueDict, None),
                    "quality": rec.get(T.QualityDict, ""),
                    "value_type": rec.get(T.ReadTypeDict, ""),
                    "aggregate": P["aggregate"],
                    "interval_seconds": int(P["interval_seconds"]),
                })
                if len(rows) >= int(P["limit"]):
                    break
        values = []
        for row in rows:
            try:
                if row.get("value") is not None:
                    values.append(float(row["value"]))
            except Exception:
                pass
        stats = {
            "count": len(values),
            "avg": sum(values) / len(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "first": rows[0] if rows else None,
            "last": rows[-1] if rows else None,
        }
        if action == "stats":
            agg = P["agg"]
            out_stats = stats if agg == "all" else {agg: stats.get(agg), "count": stats.get("count")}
            print(json.dumps({"ok": True, "statistics": out_stats, "sample_count": len(rows)}, ensure_ascii=False, default=str))
        else:
            print(json.dumps({"ok": True, "count": len(rows), "data": rows}, ensure_ascii=False, default=str))
finally:
    try:
        pspace.CloseConnect()
    except Exception:
        pass
'''.replace("__PARAMS__", json.dumps(params, ensure_ascii=False))


def run_remote(args: argparse.Namespace, meta: dict) -> dict:
    params = {
        "action": args.action,
        "tag": meta["tag_long_name"],
        "start": args.start,
        "end": args.end,
        "limit": args.limit,
        "agg": args.agg,
        "remote_root": args.remote_root,
        "pspace_server": args.pspace_server,
        "pspace_port": args.pspace_port,
        "interval_seconds": args.interval_seconds,
        "aggregate": args.aggregate,
    }
    code = remote_python(params)
    remote_script = f"C:/Users/Administrator/AppData/Local/Temp/gl02_jump_query_{int(time.time() * 1000)}.py"
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        args.jump_host,
        username=args.jump_user,
        password=ssh_password(args.allow_agents_password),
        timeout=10,
        auth_timeout=10,
        banner_timeout=10,
        look_for_keys=False,
        allow_agent=False,
    )
    try:
        sftp = ssh.open_sftp()
        with sftp.file(remote_script, "w") as handle:
            handle.write(code)
        sftp.close()
        command = (
            "powershell -NoProfile -ExecutionPolicy Bypass -Command "
            f"\"`$env:PYTHONIOENCODING='utf-8'; `$env:PYTHONUTF8='1'; "
            f"python '{remote_script}'; "
            f"Remove-Item -LiteralPath '{remote_script}' -Force -ErrorAction SilentlyContinue\""
        )
        _, stdout, stderr = ssh.exec_command(command, timeout=180)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
    finally:
        ssh.close()
    if exit_code != 0:
        return {"ok": False, "error": "REMOTE_COMMAND_FAILED", "exit_code": exit_code, "stderr": err, "stdout": out}
    json_line = next((line for line in reversed(out.splitlines()) if line.strip().startswith("{")), "")
    if not json_line:
        return {"ok": False, "error": "REMOTE_JSON_NOT_FOUND", "stdout": out, "stderr": err}
    result = json.loads(json_line)
    result["stderr_note"] = "pSpace SDK may write diagnostic logs to stderr; credentials are not printed." if err else ""
    return result


def main() -> None:
    args = parse_args()
    mcp = load_mcp_module()
    if args.action == "search":
        print(json.dumps(mcp.find_gl02_variables(args.keyword or args.variable, args.limit), ensure_ascii=False, indent=2, default=str))
        return
    try:
        variable = mcp.resolve_variable(args.variable)
        meta = mcp.public_variable(variable)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "VARIABLE_NOT_AVAILABLE", "message": str(exc)}, ensure_ascii=False, indent=2))
        return
    if args.action == "info":
        print(json.dumps({"ok": True, "variable": meta}, ensure_ascii=False, indent=2, default=str))
        return
    if not meta.get("tag_long_name"):
        print(json.dumps({"ok": False, "error": "NO_PHYSICAL_TAG", "variable": meta}, ensure_ascii=False, indent=2, default=str))
        return
    if args.action in {"history", "stats"} and (not args.start or not args.end):
        raise SystemExit("history/stats 必须传 --start 和 --end。")
    result = run_remote(args, meta)
    result["variable"] = meta
    result["source"] = {
        "profile": "pspace_243_via_22012",
        "jump_host": args.jump_host,
        "pspace_server": args.pspace_server,
        "pspace_port": args.pspace_port,
        "read_policy": "readonly",
        "remote_root": args.remote_root,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

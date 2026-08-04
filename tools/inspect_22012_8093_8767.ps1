$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 > $null

function Section($name) {
    Write-Host ""
    Write-Host "===== $name ====="
}

Section "LISTEN_PORTS"
Get-NetTCPConnection -LocalPort 8093,8767 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess |
    Format-Table -AutoSize

Section "PROCESS_COMMANDS"
$ports = Get-NetTCPConnection -LocalPort 8093,8767 -State Listen -ErrorAction SilentlyContinue
$pids = @($ports | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique)
foreach ($procId in $pids) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    if ($proc) {
        [pscustomobject]@{
            ProcessId = $proc.ProcessId
            Name = $proc.Name
            CommandLine = $proc.CommandLine
            WorkingDirectory = $proc.ExecutablePath
        } | Format-List
    }
}

Section "CANDIDATE_FILES"
$roots = @(
    "F:\高炉炼铁项目-real-sensor-v2_V3",
    "F:\高炉炼铁项目-real-sensor-v2_V3_AUTO_PREVIEW"
)
foreach ($root in $roots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    $files = @(
        "$root\自动诊断服务\local_pg_ws_bridge.py",
        "$root\auto_diagnosis_service\local_pg_ws_bridge.py",
        "$root\高炉前端数据\frontend_dashboard_v3.server.html",
        "$root\blast_furnace_frontend\frontend_dashboard_v3.server.html"
    )
    foreach ($file in $files) {
        if (Test-Path -LiteralPath $file) {
            $content = Get-Content -LiteralPath $file -Raw -Encoding UTF8
            [pscustomobject]@{
                Path = $file
                Length = $content.Length
                HasDiagnosisHistory = $content.Contains("diagnosis_history")
                HasForemanCoreIds = $content.Contains("FOREMAN_CORE_IDS")
                HasO2Rate = $content.Contains("O2_rate")
                HasStatic20m35 = $content.Contains("P_static_20m35")
                HasTFT = $content.Contains("TFT")
                LastWriteTime = (Get-Item -LiteralPath $file).LastWriteTime
            } | Format-List
        }
    }
}

Section "DB_HISTORY_AND_VARIABLES"
$env:PYTHONIOENCODING = "utf-8"
$py = @'
import json, os, sys
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception as exc:
    print(json.dumps({"ok": False, "stage": "import_psycopg", "error": repr(exc)}, ensure_ascii=False, indent=2))
    raise SystemExit(0)

params = {
    "host": os.environ.get("GL02_PGHOST", "127.0.0.1"),
    "port": int(os.environ.get("GL02_PGPORT", "5432")),
    "dbname": os.environ.get("GL02_PGDATABASE", "bf_trend"),
    "user": os.environ.get("GL02_PGUSER", "gl02_sync"),
    "password": os.environ.get("GL02_PGPASSWORD", ""),
    "connect_timeout": 10,
}
out = {"ok": True, "params": {k: ("<set>" if k == "password" and v else v) for k, v in params.items()}}
try:
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        out["latest_diagnosis"] = conn.execute(
            """
            SELECT count(*) AS cnt, max(diagnosis_ts) AS max_ts,
                   min(diagnosis_ts) FILTER (WHERE diagnosis_ts >= (SELECT max(diagnosis_ts) - interval '2 hours' FROM bf_sensor.diagnosis_snapshots)) AS first_2h
            FROM bf_sensor.diagnosis_snapshots
            """
        ).fetchone()
        out["latest_rows"] = conn.execute(
            """
            SELECT diagnosis_ts, main_label, main_score, raw_scores
            FROM bf_sensor.diagnosis_snapshots
            ORDER BY diagnosis_ts DESC, updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
            LIMIT 3
            """
        ).fetchall()
        names = ["O2_rate","Q_O2","P_static_20m35","P_static_23m49","P_static_28m98","TFT"]
        out["registry"] = conn.execute(
            """
            SELECT variable_name, tag_long_name, is_enabled, is_derived
            FROM bf_sensor.sensor_registry
            WHERE variable_name = ANY(%s)
            ORDER BY variable_name
            """,
            (names,),
        ).fetchall()
        out["values"] = conn.execute(
            """
            WITH reg AS (
                SELECT variable_name, tag_long_name
                FROM bf_sensor.sensor_registry
                WHERE variable_name = ANY(%s)
            )
            SELECT r.variable_name, count(v.value) AS cnt, max(v.ts) AS max_ts,
                   (array_agg(v.value ORDER BY v.ts DESC))[1] AS latest_value
            FROM reg r
            LEFT JOIN bf_sensor.one_minute_values v ON v.tag_long_name = r.tag_long_name
            GROUP BY r.variable_name
            ORDER BY r.variable_name
            """,
            (names,),
        ).fetchall()
except Exception as exc:
    out = {"ok": False, "stage": "query", "error": repr(exc), "params": out.get("params")}
print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
'@

$pythonCandidates = @(
    "C:\Program Files\Python311\python.exe",
    "python"
)
$tmpPy = Join-Path $env:TEMP "inspect_22012_8093_8767_db.py"
Set-Content -LiteralPath $tmpPy -Value $py -Encoding UTF8
foreach ($candidate in $pythonCandidates) {
    try {
        & $candidate $tmpPy
        break
    } catch {
        Write-Host "python candidate failed: $candidate :: $($_.Exception.Message)"
    }
}
Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue

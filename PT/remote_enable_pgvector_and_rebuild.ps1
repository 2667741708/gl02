$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$python = "C:\Program Files\Python311\python.exe"
$code = @"
import os, json, subprocess, sys
try:
    import psycopg
except Exception as e:
    print(json.dumps({"ok": False, "stage": "import", "error": str(e)}, ensure_ascii=False))
    raise SystemExit(0)

params = {
    "host": os.environ.get("GL02_PGHOST") or "127.0.0.1",
    "port": int(os.environ.get("GL02_PGPORT") or 5432),
    "dbname": os.environ.get("GL02_PGDATABASE") or "bf_trend",
    "user": os.environ.get("GL02_PGUSER"),
    "password": os.environ.get("GL02_PGPASSWORD"),
}
out = {"params": {k:v for k,v in params.items() if k != "password"}}
try:
    conn = psycopg.connect(**params)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("select name, default_version, installed_version from pg_available_extensions where name='vector'")
        out["available_before"] = cur.fetchall()
        try:
            cur.execute("create extension if not exists vector")
            out["create_extension"] = "ok"
        except Exception as e:
            out["create_extension_error"] = str(e)
        cur.execute("select name, default_version, installed_version from pg_available_extensions where name='vector'")
        out["available_after"] = cur.fetchall()
        cur.execute("select extname, extversion from pg_extension where extname='vector'")
        out["installed"] = cur.fetchall()
        try:
            cur.execute("select '[1,2,3]'::vector <=> '[1,2,4]'::vector")
            out["distance_test"] = cur.fetchone()[0]
        except Exception as e:
            out["distance_test_error"] = str(e)
    conn.close()
except Exception as e:
    out["connect_error"] = str(e)
print(json.dumps(out, ensure_ascii=False, default=str))
"@
$tmp = Join-Path $env:TEMP ("enable_pgvector_" + [guid]::NewGuid().ToString("N") + ".py")
[System.IO.File]::WriteAllText($tmp, $code, [System.Text.Encoding]::UTF8)
try { & $python $tmp } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }

Write-Host "=== 8093 pgvector status after extension ==="
try {
    (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/knowledge/pgvector/status" -TimeoutSec 30).Content
} catch {
    "status_error=" + $_.Exception.Message
}

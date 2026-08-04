$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== PostgreSQL services ==="
Get-CimInstance Win32_Service | Where-Object { $_.Name -match "postgres|pgsql|PostgreSQL" -or $_.DisplayName -match "postgres|pgsql|PostgreSQL" } |
  Select-Object Name,DisplayName,State,StartMode,PathName | ConvertTo-Json -Depth 4

Write-Host "=== Listening 5432 ==="
Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" -ErrorAction SilentlyContinue
    [pscustomobject]@{ pid=$_.OwningProcess; local=$_.LocalAddress; port=$_.LocalPort; command=$p.CommandLine }
} | ConvertTo-Json -Depth 4

Write-Host "=== Extension files ==="
$roots = @("F:\PostgreSQL\16", "C:\Program Files\PostgreSQL\16", "C:\Program Files\PostgreSQL\15", "C:\Program Files\PostgreSQL\14")
foreach ($root in $roots) {
    $control = Join-Path $root "share\extension\vector.control"
    [pscustomobject]@{ root=$root; vector_control_exists=(Test-Path -LiteralPath $control); vector_control=$control } | ConvertTo-Json -Depth 3
}

Write-Host "=== Env GL02 PG ==="
foreach ($name in @("GL02_PGHOST","GL02_PGPORT","GL02_PGDATABASE","GL02_PGUSER","PGHOST","PGPORT","PGDATABASE","PGUSER")) {
    [pscustomobject]@{ name=$name; machine=[Environment]::GetEnvironmentVariable($name, "Machine"); process=[Environment]::GetEnvironmentVariable($name, "Process") } | ConvertTo-Json -Depth 3
}

Write-Host "=== Query current DB if env available ==="
$python = "C:\Program Files\Python311\python.exe"
$code = @"
import os, json
try:
    import psycopg
except Exception as e:
    print(json.dumps({"ok": False, "stage": "import_psycopg", "error": str(e)}, ensure_ascii=False))
    raise SystemExit(0)

params = {
    "host": os.environ.get("GL02_PGHOST") or os.environ.get("PGHOST") or "127.0.0.1",
    "port": int(os.environ.get("GL02_PGPORT") or os.environ.get("PGPORT") or 5432),
    "dbname": os.environ.get("GL02_PGDATABASE") or os.environ.get("PGDATABASE") or "bf_trend",
    "user": os.environ.get("GL02_PGUSER") or os.environ.get("PGUSER"),
    "password": os.environ.get("GL02_PGPASSWORD") or os.environ.get("PGPASSWORD"),
}
try:
    conn = psycopg.connect(**params)
    with conn.cursor() as cur:
        out = {"ok": True, "params": {k:v for k,v in params.items() if k != "password"}}
        cur.execute("select current_database(), current_user, inet_server_addr()::text, inet_server_port(), version()")
        out["server"] = cur.fetchone()
        cur.execute("select name, default_version, installed_version from pg_available_extensions where name='vector'")
        out["available_vector"] = cur.fetchall()
        cur.execute("select extname, extversion from pg_extension where extname='vector'")
        out["installed_vector"] = cur.fetchall()
        cur.execute("select count(*) from information_schema.tables where table_schema='bf_assistant' and table_name in ('rag_document','rag_chunk','rag_chunk_embedding','rag_query_log')")
        out["rag_table_count"] = cur.fetchone()[0]
        for table in ["rag_document","rag_chunk","rag_chunk_embedding"]:
            try:
                cur.execute(f"select count(*) from bf_assistant.{table}")
                out[table + "_rows"] = cur.fetchone()[0]
            except Exception as e:
                out[table + "_error"] = str(e)
                conn.rollback()
        print(json.dumps(out, ensure_ascii=False, default=str))
except Exception as e:
    print(json.dumps({"ok": False, "stage": "connect_or_query", "params": {k:v for k,v in params.items() if k != "password"}, "error": str(e)}, ensure_ascii=False))
"@
$tmp = Join-Path $env:TEMP ("check_pgvector_" + [guid]::NewGuid().ToString("N") + ".py")
[System.IO.File]::WriteAllText($tmp, $code, [System.Text.Encoding]::UTF8)
try {
    & $python $tmp
} finally {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}

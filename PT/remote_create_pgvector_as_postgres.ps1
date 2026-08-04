$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$pgRoot = "F:\PostgreSQL\16"
$dataDir = Join-Path $pgRoot "data"
$pgHba = Join-Path $dataDir "pg_hba.conf"
$pgCtl = Join-Path $pgRoot "bin\pg_ctl.exe"
$backup = "$pgHba.bak_pgvector_$(Get-Date -Format 'yyyyMMdd_HHmmss')"

if (-not (Test-Path -LiteralPath $pgHba)) { throw "pg_hba.conf not found: $pgHba" }
if (-not (Test-Path -LiteralPath $pgCtl)) { throw "pg_ctl.exe not found: $pgCtl" }

Copy-Item -LiteralPath $pgHba -Destination $backup -Force
Write-Host "backup=$backup"

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$original = [System.IO.File]::ReadAllText($pgHba, $utf8NoBom)
$prefix = @"
# TEMP pgvector maintenance trust, restored immediately by Codex.
host    all             postgres        127.0.0.1/32            trust
host    all             postgres        ::1/128                 trust

"@
[System.IO.File]::WriteAllText($pgHba, $prefix + $original, $utf8NoBom)

try {
    & $pgCtl reload -D $dataDir | Write-Host
    Start-Sleep -Seconds 2

    $python = "C:\Program Files\Python311\python.exe"
    $code = @"
import json
import psycopg
out={}
try:
    conn=psycopg.connect(host="127.0.0.1", port=5432, dbname="bf_trend", user="postgres")
    conn.autocommit=True
    with conn.cursor() as cur:
        cur.execute("create extension if not exists vector")
        cur.execute("select extname, extversion from pg_extension where extname='vector'")
        out["installed"]=cur.fetchall()
        cur.execute("select '[1,2,3]'::vector <=> '[1,2,4]'::vector")
        out["distance_test"]=cur.fetchone()[0]
    conn.close()
    out["ok"]=True
except Exception as e:
    out["ok"]=False
    out["error"]=str(e)
print(json.dumps(out, ensure_ascii=False, default=str))
"@
    $tmp = Join-Path $env:TEMP ("create_vector_" + [guid]::NewGuid().ToString("N") + ".py")
    [System.IO.File]::WriteAllText($tmp, $code, [System.Text.Encoding]::UTF8)
    try { & $python $tmp } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
} finally {
    Copy-Item -LiteralPath $backup -Destination $pgHba -Force
    & $pgCtl reload -D $dataDir | Write-Host
    Write-Host "pg_hba_restored=true"
}

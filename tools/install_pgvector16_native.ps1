#requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$pgRoot = 'C:\Program Files\PostgreSQL\16'
$staged = Join-Path $env:TEMP 'pgvector16'
$dump = Join-Path $PSScriptRoot '..\logs\rag_8093_knowledge.dump'
if (-not (Test-Path -LiteralPath (Join-Path $staged 'lib\vector.dll'))) {
    throw "Missing staged pgvector files at $staged"
}
Copy-Item -LiteralPath (Join-Path $staged 'lib\vector.dll') -Destination (Join-Path $pgRoot 'lib\vector.dll') -Force
Get-ChildItem -LiteralPath (Join-Path $staged 'share\extension') -Filter 'vector*' | Copy-Item -Destination (Join-Path $pgRoot 'share\extension') -Force
Restart-Service -Name 'postgresql-x64-16' -Force
Start-Sleep -Seconds 3
$env:PGPASSWORD = 'postgres'
$psql = Join-Path $pgRoot 'bin\psql.exe'
$restore = Join-Path $pgRoot 'bin\pg_restore.exe'
& $psql -w -h 127.0.0.1 -p 5443 -U postgres -d bf_trend -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'
& $restore -w -h 127.0.0.1 -p 5443 -U postgres -d bf_trend --no-owner --no-privileges --exit-on-error -t 'rag_chunk_embedding' $dump
$verifySql = @'
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
SELECT count(*) AS embedding_count FROM bf_assistant.rag_chunk_embedding;
'@
& $psql -w -h 127.0.0.1 -p 5443 -U postgres -d bf_trend -tA -c $verifySql
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

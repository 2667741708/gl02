$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$pgRoot = 'F:\PostgreSQL\16\bin'
$psql = Join-Path $pgRoot 'psql.exe'
$pgDump = Join-Path $pgRoot 'pg_dump.exe'
$sql = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\import_three_rules_rag.sql'
$backup = 'C:\Windows\Temp\rag_before_three_rules_20260713.dump'

if (-not (Test-Path -LiteralPath $psql)) { throw "psql not found: $psql" }
if (-not (Test-Path -LiteralPath $pgDump)) { throw "pg_dump not found: $pgDump" }
if (-not (Test-Path -LiteralPath $sql)) { throw "SQL not found: $sql" }
if ([string]::IsNullOrWhiteSpace($env:GL02_PGPASSWORD)) { throw 'GL02_PGPASSWORD is not set on the server.' }

$env:PGPASSWORD = $env:GL02_PGPASSWORD
& $pgDump -w -h 127.0.0.1 -p 5432 -U gl02_sync -d bf_trend -Fc -f $backup -t bf_assistant.rag_document -t bf_assistant.rag_chunk -t bf_assistant.rag_chunk_embedding
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed: $LASTEXITCODE" }

& $psql -q -w -h 127.0.0.1 -p 5432 -U gl02_sync -d bf_trend -v ON_ERROR_STOP=1 -f $sql
if ($LASTEXITCODE -ne 0) { throw "psql import failed: $LASTEXITCODE" }

& $psql -w -h 127.0.0.1 -p 5432 -U gl02_sync -d bf_trend -tA -v ON_ERROR_STOP=1 -c "SELECT 'backup=' || '$backup'; SELECT 'doc=' || count(*) FROM bf_assistant.rag_document WHERE doc_id='bf_three_rules_two_systems_20260712'; SELECT 'chunks=' || count(*) FROM bf_assistant.rag_chunk WHERE doc_id='bf_three_rules_two_systems_20260712'; SELECT 'embeddings=' || count(*) FROM bf_assistant.rag_chunk_embedding e JOIN bf_assistant.rag_chunk c USING(chunk_id) WHERE c.doc_id='bf_three_rules_two_systems_20260712'; SELECT 'all_chunks=' || count(*) FROM bf_assistant.rag_chunk; SELECT 'all_embeddings=' || count(*) FROM bf_assistant.rag_chunk_embedding;"
if ($LASTEXITCODE -ne 0) { throw "verification failed: $LASTEXITCODE" }


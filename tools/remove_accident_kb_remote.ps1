$ErrorActionPreference = 'Stop'
$env:PGPASSWORD = [Environment]::GetEnvironmentVariable('GL02_PGPASSWORD','Machine')
if (-not $env:PGPASSWORD) { $env:PGPASSWORD = [Environment]::GetEnvironmentVariable('GL02_PGPASSWORD','User') }
$psql = 'F:\PostgreSQL\16\bin\psql.exe'
$dump = 'C:\Windows\Temp\rag_before_remove_accident_20260712_4chunks.dump'
& 'F:\PostgreSQL\16\bin\pg_dump.exe' -Fc -h 127.0.0.1 -p 5432 -U gl02_sync -d bf_trend --no-owner --no-privileges --table=bf_assistant.rag_document --table=bf_assistant.rag_chunk --table=bf_assistant.rag_chunk_embedding -f $dump
$sql = @'
BEGIN;
DELETE FROM bf_assistant.rag_chunk_embedding WHERE chunk_id IN (SELECT chunk_id FROM bf_assistant.rag_chunk WHERE doc_id='bf_accident_20260711');
DELETE FROM bf_assistant.rag_chunk WHERE doc_id='bf_accident_20260711';
DELETE FROM bf_assistant.rag_document WHERE doc_id='bf_accident_20260711';
COMMIT;
'@
& $psql -w -h 127.0.0.1 -p 5432 -U gl02_sync -d bf_trend -v ON_ERROR_STOP=1 -c $sql
Write-Output "backup=$dump"
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

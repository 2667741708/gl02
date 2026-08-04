$ErrorActionPreference = 'Stop'
$pw = [Environment]::GetEnvironmentVariable('GL02_PGPASSWORD','Machine')
if (-not $pw) { $pw = [Environment]::GetEnvironmentVariable('GL02_PGPASSWORD','User') }
$env:PGPASSWORD = $pw
$psql = 'F:\PostgreSQL\16\bin\psql.exe'
$sql = @'
SELECT table_name FROM information_schema.tables WHERE table_schema='bf_assistant' AND table_name LIKE 'rag_%' ORDER BY table_name;
SELECT 'document_count='||count(*) FROM bf_assistant.rag_document;
SELECT 'chunk_count='||count(*) FROM bf_assistant.rag_chunk;
SELECT 'embedding_count='||count(*) FROM bf_assistant.rag_chunk_embedding;
SELECT 'embedding_models='||coalesce(string_agg(embedding_model||':'||n::text,','),'') FROM (SELECT embedding_model,count(*) AS n FROM bf_assistant.rag_chunk_embedding GROUP BY embedding_model) s;
'@
& $psql -w -h 127.0.0.1 -p 5432 -U gl02_sync -d bf_trend -tA -c $sql

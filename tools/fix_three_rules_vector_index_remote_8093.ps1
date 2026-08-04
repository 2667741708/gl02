$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$psql = 'F:\PostgreSQL\16\bin\psql.exe'
if ([string]::IsNullOrWhiteSpace($env:GL02_PGPASSWORD)) { throw 'GL02_PGPASSWORD is not set on the server.' }
$env:PGPASSWORD = $env:GL02_PGPASSWORD

$sql = @'
BEGIN;
ALTER TABLE bf_assistant.rag_chunk_embedding
  ALTER COLUMN embedding TYPE vector(768)
  USING embedding::vector(768);
COMMIT;
CREATE INDEX IF NOT EXISTS idx_rag_chunk_embedding_hnsw_cosine
  ON bf_assistant.rag_chunk_embedding
  USING hnsw (embedding vector_cosine_ops);
ANALYZE bf_assistant.rag_chunk_embedding;
SELECT format_type(a.atttypid,a.atttypmod) AS embedding_type
FROM pg_attribute a
WHERE a.attrelid='bf_assistant.rag_chunk_embedding'::regclass
  AND a.attname='embedding';
SELECT indexname FROM pg_indexes
WHERE schemaname='bf_assistant' AND tablename='rag_chunk_embedding'
ORDER BY indexname;
'@

& $psql -w -h 127.0.0.1 -p 5432 -U gl02_sync -d bf_trend -v ON_ERROR_STOP=1 -c $sql
if ($LASTEXITCODE -ne 0) { throw "vector index migration failed: $LASTEXITCODE" }


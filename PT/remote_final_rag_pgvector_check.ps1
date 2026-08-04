$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$python = "C:\Program Files\Python311\python.exe"
$code = @"
import os, json
import psycopg
params={
 "host": os.environ.get("GL02_PGHOST") or "127.0.0.1",
 "port": int(os.environ.get("GL02_PGPORT") or 5432),
 "dbname": os.environ.get("GL02_PGDATABASE") or "bf_trend",
 "user": os.environ.get("GL02_PGUSER"),
 "password": os.environ.get("GL02_PGPASSWORD"),
}
out={}
conn=psycopg.connect(**params)
with conn.cursor() as cur:
    cur.execute("select rolname, rolsuper, rolcanlogin from pg_roles order by rolname")
    out["roles"]=cur.fetchall()
    cur.execute("select extname, extversion from pg_extension where extname='vector'")
    out["vector_extension"]=cur.fetchall()
    cur.execute("select count(*) from bf_assistant.rag_document")
    out["rag_document"]=cur.fetchone()[0]
    cur.execute("select count(*) from bf_assistant.rag_chunk")
    out["rag_chunk"]=cur.fetchone()[0]
    cur.execute("select embedding_model, count(*), min(embedding_dimension), max(embedding_dimension) from bf_assistant.rag_chunk_embedding group by embedding_model")
    out["embeddings"]=cur.fetchall()
print(json.dumps(out, ensure_ascii=False, default=str))
"@
$tmp = Join-Path $env:TEMP ("final_rag_check_" + [guid]::NewGuid().ToString("N") + ".py")
[System.IO.File]::WriteAllText($tmp, $code, [System.Text.Encoding]::UTF8)
try { & $python $tmp } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }

Write-Host "=== 8093 pgvector status ==="
(Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/knowledge/pgvector/status" -TimeoutSec 30).Content
Write-Host "=== ollama ps ==="
& "F:\Ollama\ollama.exe" ps

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
conn=psycopg.connect(**params)
with conn.cursor() as cur:
    cur.execute("""
        select
          c.*, d.title, d.source_file, d.knowledge_category as doc_knowledge_category,
          d.task_scope_json as doc_task_scope_json, d.authority_level, d.version,
          e.embedding_model, e.embedding_dimension
        from bf_assistant.rag_chunk c
        join bf_assistant.rag_document d on d.doc_id=c.doc_id
        left join bf_assistant.rag_chunk_embedding e on e.chunk_id=c.chunk_id
        where c.chunk_id='bf_doc_14_chunk_001'
    """)
    cols=[d[0] for d in cur.description]
    row=cur.fetchone()
    print(json.dumps(dict(zip(cols,row)), ensure_ascii=False, default=str, indent=2))
"@
$tmp = Join-Path $env:TEMP ("show_chunk_" + [guid]::NewGuid().ToString("N") + ".py")
[System.IO.File]::WriteAllText($tmp, $code, [System.Text.Encoding]::UTF8)
try { & $python $tmp } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }

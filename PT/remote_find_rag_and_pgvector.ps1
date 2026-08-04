$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== DB env names present (masked) ==="
foreach ($scope in @("Machine","User","Process")) {
    foreach ($name in @("GL02_PGHOST","GL02_PGPORT","GL02_PGDATABASE","GL02_PGUSER","GL02_PGPASSWORD","PGHOST","PGPORT","PGDATABASE","PGUSER","PGPASSWORD","BF_QA_KNOWLEDGE_DB","BF_QA_EMBEDDING_MODEL","BF_QA_EMBEDDING_BASE_URL")) {
        $v = [Environment]::GetEnvironmentVariable($name, $scope)
        if ($null -ne $v -and $v -ne "") {
            $shown = if ($name -match "PASSWORD|PASS|TOKEN|SECRET") { "<set:length=$($v.Length)>" } else { $v }
            [pscustomobject]@{ scope=$scope; name=$name; value=$shown } | ConvertTo-Json -Depth 3
        }
    }
}

Write-Host "=== Search likely RAG files ==="
$roots = @(
    "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW",
    "F:\高炉炼铁项目-real-sensor-v2_V3",
    "F:\炽穹·高炉炼铁大模型V3",
    "F:\Ollama",
    "D:\文件"
)
foreach ($root in $roots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Name -match "rag|vector|知识库|bf_unified|qa|assistant" -and
        $_.Extension -match "\.sqlite3|\.db|\.zip|\.docx|\.sql|\.json|\.md"
      } |
      Select-Object FullName,Length,LastWriteTime |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 80 |
      ConvertTo-Json -Depth 4
}

Write-Host "=== Check DBs for bf_assistant rag counts ==="
$python = "C:\Program Files\Python311\python.exe"
$code = @"
import os, json
try:
    import psycopg
except Exception as e:
    print(json.dumps({"ok": False, "error": "psycopg import failed: " + str(e)}, ensure_ascii=False))
    raise SystemExit(0)

host=os.environ.get("GL02_PGHOST") or "127.0.0.1"
port=int(os.environ.get("GL02_PGPORT") or 5432)
user=os.environ.get("GL02_PGUSER")
password=os.environ.get("GL02_PGPASSWORD")
out=[]
try:
    admin=psycopg.connect(host=host, port=port, dbname="postgres", user=user, password=password)
    with admin.cursor() as cur:
        cur.execute("select datname from pg_database where datallowconn and not datistemplate order by datname")
        dbs=[r[0] for r in cur.fetchall()]
except Exception as e:
    dbs=[os.environ.get("GL02_PGDATABASE") or "bf_trend"]
    out.append({"stage":"list_dbs_failed","error":str(e)})
for db in dbs:
    item={"db":db}
    try:
        conn=psycopg.connect(host=host, port=port, dbname=db, user=user, password=password)
        with conn.cursor() as cur:
            cur.execute("select extname, extversion from pg_extension order by extname")
            item["extensions"]=cur.fetchall()
            cur.execute("select table_name from information_schema.tables where table_schema='bf_assistant' order by table_name")
            item["assistant_tables"]=[r[0] for r in cur.fetchall()]
            for t in ["rag_document","rag_chunk","rag_chunk_embedding","qa_conversation","qa_message"]:
                try:
                    cur.execute(f"select count(*) from bf_assistant.{t}")
                    item[t]=cur.fetchone()[0]
                except Exception as e:
                    item[t+"_error"]=str(e).split("\\n")[0]
                    conn.rollback()
        conn.close()
    except Exception as e:
        item["connect_error"]=str(e)
    out.append(item)
print(json.dumps(out, ensure_ascii=False, default=str))
"@
$tmp = Join-Path $env:TEMP ("find_rag_db_" + [guid]::NewGuid().ToString("N") + ".py")
[System.IO.File]::WriteAllText($tmp, $code, [System.Text.Encoding]::UTF8)
try { & $python $tmp } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }

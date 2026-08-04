from __future__ import annotations
import hashlib, json, os, re, subprocess, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path

DOCX = Path(r"D:\文件\冀南钢铁运行中第二版本\docs\高炉事故处理.docx")
PSQL = Path(r"C:\Program Files\PostgreSQL\16\bin\psql.exe")
DB = os.environ.get("BF_PG_DB", "bf_trend")
HOST = os.environ.get("BF_PG_HOST", "127.0.0.1")
PORT = os.environ.get("BF_PG_PORT", "5443")
USER = os.environ.get("BF_PG_USER", "postgres")
PASSWORD = os.environ.get("BF_PG_PASSWORD", "postgres")
EMBED_BASE = os.environ.get("BF_QA_EMBEDDING_BASE_URL", "http://10.30.220.12:11434").rstrip("/")
MODEL = "nomic-embed-text"
DOC_ID = "bf_accident_20260711"

def sqlq(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"

def extract() -> str:
    with zipfile.ZipFile(DOCX) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    return re.sub(r"\n{2,}", "\n", text).strip()

def chunks(text: str) -> list[str]:
    """Return one exact question+answer pair per retrieval chunk.

    The source document is formatted as alternating question and answer
    paragraphs.  Chunking by character count caused a question to land in
    one chunk and its answer in the next, so retrieval could only provide a
    heading without the corresponding procedure.  Keep each pair together
    and fail fast if the source layout changes unexpectedly.
    """
    paragraphs = [x.strip() for x in re.split(r"\n+", text) if x.strip()]
    if len(paragraphs) % 2:
        raise ValueError(f"事故文档应按题目/答案成对，段落数为奇数：{len(paragraphs)}")
    pairs: list[str] = []
    for index in range(0, len(paragraphs), 2):
        question, answer = paragraphs[index : index + 2]
        if not answer.startswith(("答：", "答:")):
            raise ValueError(f"事故文档第 {index // 2 + 1} 条缺少答复段落：{answer[:80]}")
        pairs.append(f"{question}\n{answer}")
    if len(pairs) != 15:
        raise ValueError(f"事故文档应解析为 15 条问答，实际得到 {len(pairs)} 条")
    return pairs

def embed(text: str) -> list[float]:
    for path, payload in (("/api/embed", {"model": MODEL, "input": text[:3000]}), ("/api/embeddings", {"model": MODEL, "prompt": text[:3000]})):
        req=urllib.request.Request(EMBED_BASE+path, data=json.dumps(payload,ensure_ascii=False).encode(), headers={"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r: data=json.loads(r.read().decode())
            vals=data.get("embedding") or ((data.get("embeddings") or [None])[0])
            if vals: return [float(x) for x in vals]
        except Exception: pass
    raise RuntimeError("embedding service unavailable")

def main():
    text=extract(); cs=chunks(text); now=datetime.now(timezone.utc).isoformat(); full_hash=hashlib.sha256(text.encode()).hexdigest()
    lines=["BEGIN;", "CREATE SCHEMA IF NOT EXISTS bf_assistant;", f"DELETE FROM bf_assistant.rag_chunk_embedding WHERE chunk_id IN (SELECT chunk_id FROM bf_assistant.rag_chunk WHERE doc_id={sqlq(DOC_ID)});", f"DELETE FROM bf_assistant.rag_chunk WHERE doc_id={sqlq(DOC_ID)};", f"DELETE FROM bf_assistant.rag_document WHERE doc_id={sqlq(DOC_ID)};"]
    lines.append(f"INSERT INTO bf_assistant.rag_document(doc_id,title,source_file,knowledge_category,task_scope_json,version,authority_level,full_text,content_hash,created_at,updated_at) VALUES({sqlq(DOC_ID)},{sqlq('高炉事故处理')},{sqlq(str(DOCX))},{sqlq('高炉事故处理')},{sqlq(json.dumps(['process_qa','case_analysis'],ensure_ascii=False))},'v1.0','knowledge_doc',{sqlq(text)},{sqlq(full_hash)},{sqlq(now)},{sqlq(now)});")
    for i,c in enumerate(cs,1):
        cid=f"{DOC_ID}_chunk_{i:03d}"; h=hashlib.sha256(c.encode()).hexdigest(); enriched=f"【文档标题】高炉事故处理\n【知识类别】高炉事故处理\n【适用任务】工艺问答、事故处置、案例分析\n【正文片段】\n{c}"
        lines.append(f"INSERT INTO bf_assistant.rag_chunk(chunk_id,doc_id,parent_chunk_id,title,content,enriched_content,summary,keywords_json,entities_json,phenomenon_json,parameter_names_json,chunk_type,token_count,source_file,knowledge_category,task_scope_json,authority_level,source_priority,content_hash,created_at) VALUES({sqlq(cid)},{sqlq(DOC_ID)},{sqlq(DOC_ID+'_parent')},{sqlq('高炉事故处理')},{sqlq(c)},{sqlq(enriched)},{sqlq(c[:120])},{sqlq('[]')},{sqlq('[]')},{sqlq('[]')},{sqlq('[]')},{sqlq('事故处置')},{len(c)},{sqlq(str(DOCX))},{sqlq('高炉事故处理')},{sqlq('["process_qa","case_analysis"]')},'knowledge_doc',100,{sqlq(h)},{sqlq(now)});")
        v=embed(enriched); lit="["+",".join(format(x,'.9g') for x in v)+"]"; lines.append(f"INSERT INTO bf_assistant.rag_chunk_embedding(chunk_id,embedding_model,embedding,embedding_dimension,embedding_text_hash,updated_at) VALUES({sqlq(cid)},{sqlq(MODEL)},{sqlq(lit)}::{ 'vector' },{len(v)},{sqlq(h)},{sqlq(now)});")
    lines += ["COMMIT;", f"SELECT 'documents='||count(*) FROM bf_assistant.rag_document WHERE doc_id={sqlq(DOC_ID)};", f"SELECT 'chunks='||count(*) FROM bf_assistant.rag_chunk WHERE doc_id={sqlq(DOC_ID)};", f"SELECT 'embeddings='||count(*) FROM bf_assistant.rag_chunk_embedding WHERE chunk_id LIKE {sqlq(DOC_ID+'%')};"]
    sql=Path('logs')/'import_accident_docx.sql'; sql.write_text("\n".join(lines),encoding='utf-8')
    env=os.environ.copy(); env['PGPASSWORD']=PASSWORD
    subprocess.run([str(PSQL),'-w','-h',HOST,'-p',PORT,'-U',USER,'-d',DB,'-v','ON_ERROR_STOP=1','-f',str(sql)],env=env,check=True)
    print(f"imported_doc={DOC_ID} chunks={len(cs)} questions_per_chunk=1")

if __name__=='__main__': main()

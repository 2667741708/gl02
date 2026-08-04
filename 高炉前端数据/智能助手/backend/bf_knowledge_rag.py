from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from assistant_pg import ensure_rag_schema, raw_pg_connect, schema_name


DEFAULT_SOURCE_DIR = Path(r"D:\文件\服务器实际运行版\高炉四智能体配置以及知识库")
DEFAULT_DB_PATH = Path("__postgresql_bf_assistant_rag__")
DEFAULT_SEARCH_MODE = os.environ.get("BF_QA_KNOWLEDGE_SEARCH_MODE", "hybrid").strip().lower()
DEFAULT_EMBEDDING_MODEL = os.environ.get("BF_QA_EMBEDDING_MODEL", "nomic-embed-text").strip()
DEFAULT_EMBEDDING_BASE_URL = os.environ.get(
    "BF_QA_EMBEDDING_BASE_URL",
    os.environ.get("OLLAMA_BASE_URL", "http://10.30.220.12:11434"),
).rstrip("/")
EMBEDDING_TIMEOUT_SECONDS = float(os.environ.get("BF_QA_EMBEDDING_TIMEOUT_SECONDS", "30"))
EMBEDDING_MAX_CHARS = int(os.environ.get("BF_QA_EMBEDDING_MAX_CHARS", "3000"))

_RAG_SCHEMA_LOCK = threading.Lock()
_RAG_SCHEMA_READY = False
_PGVECTOR_SCHEMA_LOCK = threading.Lock()
_PGVECTOR_SCHEMA_STATE: dict[str, Any] | None = None

TASK_PROCESS_QA = "process_qa"
TASK_DIAGNOSIS = "condition_diagnosis"
TASK_OPTIMIZATION = "parameter_optimization"
TASK_REPORT = "operation_report"
TASK_CASE = "case_analysis"
TASK_MIXED = "mixed"

DOC_CATEGORY_RULES = [
    (range(1, 9), "基础机理类", [TASK_PROCESS_QA, TASK_DIAGNOSIS, TASK_OPTIMIZATION]),
    (range(9, 18), "工况诊断类", [TASK_DIAGNOSIS, TASK_REPORT, TASK_OPTIMIZATION]),
    (range(18, 23), "参数协同类", [TASK_OPTIMIZATION, TASK_DIAGNOSIS]),
    (range(23, 27), "汇报表达类", [TASK_REPORT]),
]

TERM_EXPANSIONS = {
    "炉子不顺": ["顺行变差", "透气性下降", "压差升高", "煤气流异常"],
    "不顺": ["顺行变差", "透气性下降", "压差升高", "煤气流异常"],
    "炉凉": ["热制度不足", "炉缸热量不足", "铁水硅下降", "铁水温度偏低"],
    "压差上来": ["压差升高", "透气性变差", "料柱阻力增加"],
    "多喷煤": ["提高喷煤量", "喷煤量", "风温", "富氧", "透气性", "热制度"],
    "煤比": ["喷煤量", "燃料比", "焦比", "置换比"],
    "顶温": ["炉顶温度", "煤气流分布", "中心气流", "边缘气流"],
}

PARAMETER_TERMS = [
    "压差",
    "风量",
    "风温",
    "富氧",
    "喷煤",
    "煤比",
    "焦比",
    "透气性",
    "料速",
    "炉顶温度",
    "顶温",
    "铁水硅",
    "铁水温度",
    "煤气利用率",
    "中心气流",
    "边缘气流",
]

PHENOMENON_TERMS = [
    "压差升高",
    "风量下降",
    "透气性变差",
    "炉凉",
    "炉热",
    "悬料",
    "崩料",
    "管道",
    "偏行",
    "煤气流异常",
    "炉顶温度分布不均",
    "铁水硅波动",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def ensure_schema(conn: Any) -> None:
    global _RAG_SCHEMA_READY
    if _RAG_SCHEMA_READY:
        return
    with _RAG_SCHEMA_LOCK:
        if _RAG_SCHEMA_READY:
            return
        ensure_rag_schema(conn)
        conn.commit()
        _RAG_SCHEMA_READY = True


def parse_docx_bytes(data: bytes) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    out: list[str] = []
    with zipfile.ZipFile(PathLikeBytes(data)) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    for node in root.iter():
        if node.tag.endswith("}p"):
            text = "".join(t.text or "" for t in node.findall(".//w:t", ns)).strip()
            if text:
                out.append(text)
        elif node.tag.endswith("}tr"):
            cells = []
            for cell in node.findall(".//w:tc", ns):
                txt = "".join(t.text or "" for t in cell.findall(".//w:t", ns)).strip()
                if txt:
                    cells.append(txt)
            if cells:
                out.append(" | ".join(cells))
    return "\n".join(dedupe_adjacent(out))


class PathLikeBytes:
    def __init__(self, data: bytes):
        self.data = data

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        import io

        if not hasattr(self, "_bio"):
            self._bio = io.BytesIO(self.data)
        return self._bio.seek(offset, whence)

    def tell(self) -> int:
        import io

        if not hasattr(self, "_bio"):
            self._bio = io.BytesIO(self.data)
        return self._bio.tell()

    def read(self, size: int = -1) -> bytes:
        import io

        if not hasattr(self, "_bio"):
            self._bio = io.BytesIO(self.data)
        return self._bio.read(size)


def dedupe_adjacent(lines: list[str]) -> list[str]:
    out: list[str] = []
    prev = ""
    for line in lines:
        clean = normalize_text(line)
        if clean and clean != prev:
            out.append(clean)
            prev = clean
    return out


def normalize_text(text: str) -> str:
    text = re.sub(r"[\u00a0\t\r]+", " ", str(text or ""))
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


def doc_meta_from_name(name: str) -> dict[str, Any] | None:
    base = Path(name).name
    match = re.match(r"^(\d{1,2})[-_－—](.+?)\.docx$", base, re.I)
    if not match:
        return None
    doc_num = int(match.group(1))
    title = match.group(2).strip()
    category = "企业知识"
    task_scope = [TASK_PROCESS_QA]
    for nums, candidate_category, candidate_scope in DOC_CATEGORY_RULES:
        if doc_num in nums:
            category = candidate_category
            task_scope = candidate_scope
            break
    return {
        "doc_id": f"{doc_num:02d}",
        "title": title,
        "source_file": base,
        "knowledge_category": category,
        "task_scope": task_scope,
    }


def iter_knowledge_docx(source_dir: Path) -> list[dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    zip_path = source_dir / "知识库.zip"
    if zip_path.exists():
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".docx"):
                    continue
                meta = doc_meta_from_name(info.filename)
                if not meta:
                    continue
                docs[meta["doc_id"]] = {**meta, "data": zf.read(info.filename)}
    for path in source_dir.glob("*.docx"):
        meta = doc_meta_from_name(path.name)
        if meta and meta["doc_id"] not in docs:
            docs[meta["doc_id"]] = {**meta, "data": path.read_bytes()}
    return [docs[key] for key in sorted(docs.keys())]


def split_semantic_chunks(text: str, max_chars: int = 700, overlap: int = 100) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(para) > max_chars * 1.4:
            if buf:
                chunks.append(buf.strip())
                buf = ""
            for piece in sliding_pieces(para, max_chars, overlap):
                chunks.append(piece)
            continue
        if not buf:
            buf = para
        elif len(buf) + len(para) + 1 <= max_chars:
            buf = f"{buf}\n{para}"
        else:
            chunks.append(buf.strip())
            tail = buf[-overlap:] if overlap and len(buf) > overlap else ""
            buf = f"{tail}\n{para}".strip() if tail else para
    if buf:
        chunks.append(buf.strip())
    return [c for c in chunks if len(c) >= 20]


def sliding_pieces(text: str, max_chars: int, overlap: int) -> list[str]:
    pieces = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return pieces


def extract_terms(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term in text]


def infer_chunk_type(content: str, title: str) -> str:
    text = title + "\n" + content
    if any(word in text for word in ["是什么", "定义", "概念", "区别"]):
        return "定义"
    if any(word in text for word in ["信号", "表现", "判断", "判读", "原因"]):
        return "信号"
    if any(word in text for word in ["建议", "优化", "调整", "关注"]):
        return "建议"
    if any(word in text for word in ["日报", "班报", "汇报", "模板", "写法"]):
        return "模板"
    return "机理"


def keywords_for_doc(title: str, content: str) -> list[str]:
    candidates = extract_terms(title + "\n" + content, PARAMETER_TERMS + PHENOMENON_TERMS)
    for key, values in TERM_EXPANSIONS.items():
        if key in title or key in content:
            candidates.extend(values)
    return sorted(set(candidates))[:16]


def build_enriched_content(meta: dict[str, Any], chunk: str, keywords: list[str]) -> str:
    task_names = "、".join(meta["task_scope"])
    return (
        f"【文档标题】{meta['title']}\n"
        f"【知识类别】{meta['knowledge_category']}\n"
        f"【适用任务】{task_names}\n"
        f"【关键词】{'、'.join(keywords)}\n"
        f"【正文片段】\n{chunk}"
    )


def rebuild_index(source_dir: Path = DEFAULT_SOURCE_DIR, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    docs = iter_knowledge_docx(source_dir)
    with raw_pg_connect() as conn:
        ensure_schema(conn)
        conn.execute("DELETE FROM rag_chunk")
        conn.execute("DELETE FROM rag_document")
        chunk_total = 0
        ts = utc_now()
        for doc in docs:
            full_text = parse_docx_bytes(doc["data"])
            if not full_text.strip():
                continue
            conn.execute(
                """
                INSERT INTO rag_document(
                    doc_id, title, source_file, knowledge_category, task_scope_json,
                    version, authority_level, full_text, content_hash, created_at, updated_at
                ) VALUES(%s, %s, %s, %s, %s, 'v1.0', 'knowledge_doc', %s, %s, %s, %s)
                """,
                (
                    doc["doc_id"],
                    doc["title"],
                    doc["source_file"],
                    doc["knowledge_category"],
                    json.dumps(doc["task_scope"], ensure_ascii=False),
                    full_text,
                    content_hash(full_text),
                    ts,
                    ts,
                ),
            )
            chunks = split_semantic_chunks(full_text)
            for idx, chunk in enumerate(chunks, start=1):
                keywords = keywords_for_doc(doc["title"], chunk)
                entities = extract_terms(chunk, PARAMETER_TERMS)
                phenomenon = extract_terms(chunk, PHENOMENON_TERMS)
                chunk_type = infer_chunk_type(chunk, doc["title"])
                enriched = build_enriched_content(doc, chunk, keywords)
                chunk_id = f"bf_doc_{doc['doc_id']}_chunk_{idx:03d}"
                conn.execute(
                    """
                    INSERT INTO rag_chunk(
                        chunk_id, doc_id, parent_chunk_id, title, content, enriched_content,
                        summary, keywords_json, entities_json, phenomenon_json, parameter_names_json,
                        chunk_type, token_count, source_file, knowledge_category, task_scope_json,
                        authority_level, source_priority, content_hash, created_at
                    ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chunk_id,
                        doc["doc_id"],
                        f"bf_doc_{doc['doc_id']}_parent",
                        doc["title"],
                        chunk,
                        enriched,
                        chunk[:120],
                        json.dumps(keywords, ensure_ascii=False),
                        json.dumps(entities, ensure_ascii=False),
                        json.dumps(phenomenon, ensure_ascii=False),
                        json.dumps(entities, ensure_ascii=False),
                        chunk_type,
                        len(chunk),
                        doc["source_file"],
                        doc["knowledge_category"],
                        json.dumps(doc["task_scope"], ensure_ascii=False),
                        "knowledge_doc",
                        source_priority(doc["knowledge_category"]),
                        content_hash(chunk),
                        ts,
                    ),
                )
                chunk_total += 1
        conn.commit()
    return {"documents": len(docs), "chunks": chunk_total, "storage": "postgresql", "schema": schema_name()}


def normalize_search_mode(mode: str | None) -> str:
    value = (mode or DEFAULT_SEARCH_MODE or "hybrid").strip().lower()
    aliases = {
        "pgvector": "vector",
        "embedding": "vector",
        "embeddings": "vector",
        "semantic": "vector",
        "tfidf": "keyword",
        "lexical": "keyword",
        "postgresql": "keyword",
        "postgres": "keyword",
        "auto": "hybrid",
        "mixed": "hybrid",
    }
    value = aliases.get(value, value)
    return value if value in {"keyword", "vector", "hybrid"} else "hybrid"


def vector_literal(values: list[float]) -> str:
    if not values:
        raise RuntimeError("embedding 向量为空。")
    return "[" + ",".join(f"{float(item):.8g}" for item in values) + "]"


def text_hash_for_embedding(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def call_embedding_model(text: str) -> list[float]:
    prompt = text[:EMBEDDING_MAX_CHARS]
    errors: list[str] = []
    endpoints = [
        ("/api/embed", {"model": DEFAULT_EMBEDDING_MODEL, "input": prompt}),
        ("/api/embeddings", {"model": DEFAULT_EMBEDDING_MODEL, "prompt": prompt}),
    ]
    for path, payload in endpoints:
        req = Request(
            f"{DEFAULT_EMBEDDING_BASE_URL}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=EMBEDDING_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        if isinstance(data.get("embedding"), list):
            return [float(item) for item in data["embedding"]]
        embeddings = data.get("embeddings")
        if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
            return [float(item) for item in embeddings[0]]
        errors.append(f"{path}: 响应中没有 embedding/embeddings 字段")
    raise RuntimeError("embedding 服务不可用：" + "；".join(errors))


def ensure_pgvector_schema(conn: Any) -> dict[str, Any]:
    global _PGVECTOR_SCHEMA_STATE
    if _PGVECTOR_SCHEMA_STATE is not None:
        return dict(_PGVECTOR_SCHEMA_STATE)
    with _PGVECTOR_SCHEMA_LOCK:
        if _PGVECTOR_SCHEMA_STATE is not None:
            return dict(_PGVECTOR_SCHEMA_STATE)
        state = _ensure_pgvector_schema_uncached(conn)
        if state.get("ok"):
            _PGVECTOR_SCHEMA_STATE = dict(state)
        return state


def _ensure_pgvector_schema_uncached(conn: Any) -> dict[str, Any]:
    schema = schema_name()
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.rag_chunk_embedding (
                chunk_id text PRIMARY KEY REFERENCES {schema}.rag_chunk(chunk_id) ON DELETE CASCADE,
                embedding_model text NOT NULL,
                embedding vector NOT NULL,
                embedding_dimension integer NOT NULL,
                embedding_text_hash text NOT NULL,
                updated_at text NOT NULL
            )
            """
        )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_rag_chunk_embedding_model
                ON {schema}.rag_chunk_embedding(embedding_model)
            """
        )
        conn.commit()
        try:
            conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_rag_chunk_embedding_hnsw
                    ON {schema}.rag_chunk_embedding
                    USING hnsw (embedding vector_cosine_ops)
                """
            )
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            conn.execute(f"SET search_path TO {schema}, bf_sensor, public")
            return {"ok": True, "index": "none", "message": f"HNSW 索引未创建：{exc}"}
        return {"ok": True, "index": "hnsw", "message": ""}
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        return {"ok": False, "index": "none", "message": f"pgvector 不可用：{exc}"}


def initialize_knowledge_runtime() -> dict[str, Any]:
    """Run schema and pgvector checks once during service startup."""
    try:
        with raw_pg_connect() as conn:
            ensure_schema(conn)
            vector = ensure_pgvector_schema(conn)
        return {"ok": bool(vector.get("ok")), "vector": vector}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "vector": {"ok": False, "message": str(exc)}}


def pgvector_status() -> dict[str, Any]:
    try:
        with raw_pg_connect() as conn:
            ensure_schema(conn)
            vector = ensure_pgvector_schema(conn)
            if not vector.get("ok"):
                return {"ok": True, "enabled": False, **vector}
            row = conn.execute(
                """
                SELECT count(*) AS embedding_count
                FROM rag_chunk_embedding
                WHERE embedding_model = %s
                """,
                (DEFAULT_EMBEDDING_MODEL,),
            ).fetchone()
            chunk_row = conn.execute("SELECT count(*) AS chunk_count FROM rag_chunk").fetchone()
            return {
                "ok": True,
                "enabled": True,
                "embedding_model": DEFAULT_EMBEDDING_MODEL,
                "embedding_base_url": DEFAULT_EMBEDDING_BASE_URL,
                "embedding_count": int((row or {}).get("embedding_count") or 0),
                "chunk_count": int((chunk_row or {}).get("chunk_count") or 0),
                "index": vector.get("index"),
                "message": vector.get("message") or "",
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "enabled": False, "message": str(exc)}


def rebuild_pgvector_embeddings(limit: int | None = None, force: bool = False) -> dict[str, Any]:
    with raw_pg_connect() as conn:
        ensure_schema(conn)
        vector = ensure_pgvector_schema(conn)
        if not vector.get("ok"):
            return {"ok": False, "updated": 0, "message": vector.get("message")}
        params: list[Any] = [DEFAULT_EMBEDDING_MODEL]
        where = """
            WHERE e.chunk_id IS NULL
               OR e.embedding_model <> %s
               OR e.embedding_text_hash <> c.content_hash
        """
        if force:
            where = "WHERE TRUE AND %s = %s"
            params = [DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_MODEL]
        sql = f"""
            SELECT c.chunk_id, c.enriched_content, c.content_hash
            FROM rag_chunk c
            LEFT JOIN rag_chunk_embedding e ON e.chunk_id = c.chunk_id
            {where}
            ORDER BY c.source_priority DESC, c.created_at DESC
        """
        if limit and limit > 0:
            sql += " LIMIT %s"
            params.append(int(limit))
        rows = conn.execute(sql, params).fetchall()
        updated = 0
        dimensions: set[int] = set()
        for row in rows:
            text = str(row["enriched_content"])
            embedding = call_embedding_model(text)
            dimensions.add(len(embedding))
            conn.execute(
                """
                INSERT INTO rag_chunk_embedding(
                    chunk_id, embedding_model, embedding, embedding_dimension,
                    embedding_text_hash, updated_at
                ) VALUES(%s, %s, %s::vector, %s, %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    embedding_model = EXCLUDED.embedding_model,
                    embedding = EXCLUDED.embedding,
                    embedding_dimension = EXCLUDED.embedding_dimension,
                    embedding_text_hash = EXCLUDED.embedding_text_hash,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    row["chunk_id"],
                    DEFAULT_EMBEDDING_MODEL,
                    vector_literal(embedding),
                    len(embedding),
                    row["content_hash"],
                    utc_now(),
                ),
            )
            updated += 1
        conn.commit()
        return {
            "ok": True,
            "updated": updated,
            "candidate_chunks": len(rows),
            "embedding_model": DEFAULT_EMBEDDING_MODEL,
            "dimensions": sorted(dimensions),
            "index": vector.get("index"),
            "message": vector.get("message") or "",
        }


def source_priority(category: str) -> int:
    return {
        "工况诊断类": 95,
        "参数协同类": 90,
        "基础机理类": 80,
        "汇报表达类": 75,
        "案例类": 85,
    }.get(category, 50)


def classify_intent(question: str) -> dict[str, Any]:
    q = normalize_text(question)
    has_report = any(x in q for x in ["日报", "班报", "汇报", "运行分析", "整理成", "总结今天"])
    has_case = any(x in q for x in ["案例", "事故", "故障", "复盘", "类似"])
    has_opt = any(x in q for x in ["优化", "调整", "提高", "降低", "多喷", "降燃料比", "怎么调", "建议"])
    has_diag = any(x in q for x in ["原因", "怎么判断", "可能", "不顺", "压差", "风量下降", "异常", "炉凉", "波动"])
    has_qa = any(x in q for x in ["什么是", "是什么意思", "为什么是", "作用", "区别", "解释"])
    if has_case:
        intent = TASK_CASE
    elif has_report:
        intent = TASK_REPORT
    elif has_diag and has_opt:
        intent = TASK_MIXED
    elif has_opt:
        intent = TASK_OPTIMIZATION
    elif has_diag:
        intent = TASK_DIAGNOSIS
    elif has_qa:
        intent = TASK_PROCESS_QA
    else:
        intent = TASK_PROCESS_QA
    return {
        "intent_type": intent,
        "confidence": 0.78 if intent != TASK_PROCESS_QA else 0.66,
        "need_retrieval": True,
        "need_structured_data": intent in {TASK_DIAGNOSIS, TASK_MIXED},
        "need_case_search": intent == TASK_CASE,
        "output_style": {
            TASK_PROCESS_QA: "technical_explanation",
            TASK_DIAGNOSIS: "diagnosis",
            TASK_OPTIMIZATION: "optimization",
            TASK_REPORT: "operation_report",
            TASK_CASE: "case_review",
            TASK_MIXED: "diagnosis_then_optimization",
        }[intent],
    }


def expand_query(question: str) -> str:
    terms = [question]
    for key, values in TERM_EXPANSIONS.items():
        if key in question:
            terms.extend(values)
    terms.extend(extract_terms(question, PARAMETER_TERMS + PHENOMENON_TERMS))
    return " ".join(dict.fromkeys(terms))


def scopes_for_intent(intent_type: str) -> list[str]:
    if intent_type == TASK_MIXED:
        return [TASK_DIAGNOSIS, TASK_OPTIMIZATION]
    return {
        TASK_PROCESS_QA: [TASK_PROCESS_QA],
        TASK_DIAGNOSIS: [TASK_DIAGNOSIS],
        TASK_OPTIMIZATION: [TASK_OPTIMIZATION],
        TASK_REPORT: [TASK_REPORT],
        TASK_CASE: [TASK_CASE],
    }.get(intent_type, [TASK_PROCESS_QA])


def search_knowledge(
    question: str,
    db_path: Path = DEFAULT_DB_PATH,
    top_k: int = 6,
    mode: str | None = None,
) -> dict[str, Any]:
    del db_path  # 兼容旧参数；当前运行期固定使用 PostgreSQL bf_assistant.rag_* 表。
    search_mode = normalize_search_mode(mode)
    intent = classify_intent(question)
    expanded = expand_query(question)
    vector_message = ""
    vector_enabled = False
    lexical_rows: list[dict[str, Any]] = []
    vector_rows: list[dict[str, Any]] = []
    try:
        with raw_pg_connect() as conn:
            ensure_schema(conn)
            if search_mode in {"keyword", "hybrid"}:
                lexical_rows = query_keyword_candidates(conn, expanded)
                if not lexical_rows:
                    lexical_rows = query_fallback_candidates(conn)
            if search_mode in {"vector", "hybrid"}:
                vector_pack = query_pgvector_candidates(conn, expanded, max(60, top_k * 12))
                vector_enabled = bool(vector_pack.get("enabled"))
                vector_message = str(vector_pack.get("message") or "")
                vector_rows = list(vector_pack.get("rows") or [])
    except Exception as exc:
        return {
            "enabled": False,
            "intent": intent,
            "evidence": [],
            "message": f"PostgreSQL 知识索引不可用：{exc}",
            "retrieval_mode": search_mode,
        }
    if search_mode == "vector":
        rows = vector_rows
    elif search_mode == "keyword":
        rows = lexical_rows
    else:
        rows = merge_candidate_rows(lexical_rows, vector_rows)
        if not rows and vector_message:
            rows = lexical_rows
    scored = rank_rows(question, expanded, rows, scopes_for_intent(intent["intent_type"]))
    evidence = [row_to_evidence(item) for item in scored[:top_k]]
    return {
        "enabled": True,
        "intent": intent,
        "expanded_query": expanded,
        "evidence": evidence,
        "answer_constraints": constraints_for_intent(intent["intent_type"]),
        "retrieval_mode": search_mode,
        "vector_enabled": vector_enabled,
        "vector_message": vector_message,
        "candidate_counts": {
            "keyword": len(lexical_rows),
            "vector": len(vector_rows),
            "merged": len(rows),
        },
    }


def query_keyword_candidates(conn: Any, expanded: str) -> list[dict[str, Any]]:
    tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]{2,}", expanded)
    where = ""
    params: list[Any] = []
    if tokens:
        where = "WHERE " + " OR ".join("search_text ILIKE %s" for _ in tokens[:16])
        params.extend(f"%{token}%" for token in tokens[:16])
    return conn.execute(
        f"""
        SELECT *
        FROM rag_chunk
        {where}
        ORDER BY source_priority DESC, created_at DESC
        LIMIT 300
        """,
        params,
    ).fetchall()


def query_fallback_candidates(conn: Any) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT *
        FROM rag_chunk
        ORDER BY source_priority DESC, created_at DESC
        LIMIT 300
        """
    ).fetchall()


def query_pgvector_candidates(conn: Any, expanded: str, limit: int) -> dict[str, Any]:
    vector = ensure_pgvector_schema(conn)
    if not vector.get("ok"):
        return {"enabled": False, "rows": [], "message": vector.get("message") or "pgvector 不可用"}
    row = conn.execute(
        """
        SELECT count(*) AS embedding_count
        FROM rag_chunk_embedding
        WHERE embedding_model = %s
        """,
        (DEFAULT_EMBEDDING_MODEL,),
    ).fetchone()
    if int((row or {}).get("embedding_count") or 0) <= 0:
        return {"enabled": False, "rows": [], "message": "pgvector 表可用，但当前 embedding_model 尚无索引数据。"}
    try:
        query_embedding = call_embedding_model(expanded)
    except Exception as exc:  # noqa: BLE001
        return {"enabled": False, "rows": [], "message": str(exc)}
    rows = conn.execute(
        """
        SELECT c.*, (1 - (e.embedding <=> %s::vector)) AS vector_score
        FROM rag_chunk_embedding e
        JOIN rag_chunk c ON c.chunk_id = e.chunk_id
        WHERE e.embedding_model = %s
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
        """,
        (vector_literal(query_embedding), DEFAULT_EMBEDDING_MODEL, vector_literal(query_embedding), int(limit)),
    ).fetchall()
    return {"enabled": True, "rows": rows, "message": vector.get("message") or ""}


def merge_candidate_rows(lexical_rows: list[dict[str, Any]], vector_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in lexical_rows:
        merged[str(row["chunk_id"])] = dict(row)
    for row in vector_rows:
        chunk_id = str(row["chunk_id"])
        existing = merged.get(chunk_id)
        if existing is None:
            merged[chunk_id] = dict(row)
            continue
        if row.get("vector_score") is not None:
            existing["vector_score"] = max(float(existing.get("vector_score") or 0), float(row["vector_score"]))
    return list(merged.values())


def fts_query(text: str) -> str:
    tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]{2,}", text)
    return " OR ".join(tokens[:24]) or "\"高炉\""


def rank_rows(question: str, expanded: str, rows: list[dict[str, Any]], scopes: list[str]) -> list[dict[str, Any]]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        corpus = [expanded] + [str(row["enriched_content"]) for row in rows]
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), max_features=8000)
        mat = vec.fit_transform(corpus)
        sims = cosine_similarity(mat[0:1], mat[1:]).flatten()
    except Exception:
        sims = [simple_overlap(expanded, str(row["enriched_content"])) for row in rows]
    ranked: list[dict[str, Any]] = []
    for row, sim in zip(rows, sims):
        task_scope = load_json(row["task_scope_json"], [])
        scope_bonus = 0.18 if any(scope in task_scope for scope in scopes) else 0.0
        priority_bonus = min(float(row["source_priority"] or 50) / 1000.0, 0.1)
        vector_bonus = max(float(row.get("vector_score") or 0.0), 0.0) * 0.35
        score = float(sim) + vector_bonus + scope_bonus + priority_bonus
        ranked.append({"row": row, "score": score})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    deduped: list[dict[str, Any]] = []
    seen_docs: dict[str, int] = {}
    for item in ranked:
        doc_id = item["row"]["doc_id"]
        if seen_docs.get(doc_id, 0) >= 2:
            continue
        seen_docs[doc_id] = seen_docs.get(doc_id, 0) + 1
        deduped.append(item)
    return deduped


def simple_overlap(query: str, text: str) -> float:
    q = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]{2,}", query))
    t = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]{2,}", text))
    if not q or not t:
        return 0.0
    return len(q & t) / math.sqrt(len(q) * len(t))


def row_to_evidence(item: dict[str, Any]) -> dict[str, Any]:
    row = item["row"]
    return {
        "chunk_id": row["chunk_id"],
        "doc_id": row["doc_id"],
        "title": row["title"],
        "source_file": row["source_file"],
        "knowledge_category": row["knowledge_category"],
        "task_scope": load_json(row["task_scope_json"], []),
        "chunk_type": row["chunk_type"],
        "content": row["content"],
        "score": round(float(item["score"]), 4),
    }


def constraints_for_intent(intent_type: str) -> list[str]:
    common = ["不得编造用户未提供的数值、时间、设备状态或检测结果", "结论必须说明适用边界"]
    if intent_type == TASK_DIAGNOSIS:
        return common + ["不得认定唯一主因", "需要提示补充关键趋势和相关参数"]
    if intent_type == TASK_OPTIMIZATION:
        return common + ["不得直接下操作指令", "建议必须体现变量耦合、边界条件和顺行约束"]
    if intent_type == TASK_REPORT:
        return common + ["报告类输出不得补充未提供的变化幅度", "语言应接近日报、班报或汇报文本"]
    if intent_type == TASK_CASE:
        return common + ["案例只能类比，不能直接等同当前工况"]
    if intent_type == TASK_MIXED:
        return common + ["先诊断再建议", "不得把异常工况简化成单参数调整"]
    return common


def load_json(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default


def evidence_pack_text(pack: dict[str, Any]) -> str:
    if not pack.get("enabled"):
        return f"【知识库状态】{pack.get('message') or '未启用'}"
    lines = [
        "【知识检索意图】",
        json.dumps(pack.get("intent") or {}, ensure_ascii=False),
        "【回答约束】",
    ]
    lines.extend(f"- {item}" for item in pack.get("answer_constraints") or [])
    lines.append("【检索证据】")
    for idx, item in enumerate(pack.get("evidence") or [], start=1):
        lines.append(
            f"{idx}. 来源：{item['source_file']}；类别：{item['knowledge_category']}；"
            f"片段类型：{item['chunk_type']}；相关度：{item['score']}\n{item['content']}"
        )
    return "\n".join(lines)

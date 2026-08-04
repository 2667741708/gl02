from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DOC_ID = "bf_three_rules_two_systems_20260712"
MODEL = "nomic-embed-text"
PSQL = Path(r"C:\Program Files\PostgreSQL\16\bin\psql.exe")
EMBEDDING_TEXT_MAX_CHARS = 1800


def sql_quote(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(format(float(value), ".9g") for value in values) + "]"


def load_cache(path: Path) -> dict[str, list[float]]:
    cache: dict[str, list[float]] = {}
    if not path.exists():
        return cache
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cache[str(row["chunk_id"])] = [float(value) for value in row["embedding"]]
    return cache


def request_embeddings(base_url: str, model: str, texts: list[str], timeout: int) -> list[list[float]]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/embed",
        data=json.dumps({"model": model, "input": texts}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    embeddings = payload.get("embeddings") or []
    if len(embeddings) != len(texts):
        raise RuntimeError(f"embedding batch count mismatch: expected={len(texts)} actual={len(embeddings)}")
    return [[float(value) for value in row] for row in embeddings]


def embed_missing(
    chunks: list[dict],
    cache_path: Path,
    base_url: str,
    model: str,
    batch_size: int,
    timeout: int,
) -> dict[str, list[float]]:
    cache = load_cache(cache_path)
    missing = [chunk for chunk in chunks if chunk["chunk_id"] not in cache]
    print(f"embedding_cache={len(cache)} missing={len(missing)} total={len(chunks)}")
    if not missing:
        return cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with cache_path.open("a", encoding="utf-8", newline="\n") as handle:
        for offset in range(0, len(missing), batch_size):
            batch = missing[offset : offset + batch_size]
            # nomic-embed-text on the 220.12 Ollama runtime has a finite token
            # context.  Keep the stored chunk/content intact and only cap the
            # retrieval representation used to calculate its vector.
            texts = [str(chunk["enriched_content"])[:EMBEDDING_TEXT_MAX_CHARS] for chunk in batch]
            try:
                vectors = request_embeddings(base_url, model, texts, timeout)
            except Exception as batch_error:
                print(f"batch_fallback offset={offset} error={batch_error}")
                vectors = []
                for text in texts:
                    vectors.extend(request_embeddings(base_url, model, [text], timeout))
            for chunk, vector in zip(batch, vectors):
                if not vector:
                    raise RuntimeError(f"empty embedding: {chunk['chunk_id']}")
                cache[chunk["chunk_id"]] = vector
                handle.write(json.dumps({"chunk_id": chunk["chunk_id"], "embedding": vector}, ensure_ascii=False) + "\n")
            handle.flush()
            done = min(offset + len(batch), len(missing))
            if done == len(missing) or done % max(batch_size * 10, 1) == 0:
                elapsed = max(time.monotonic() - started, 0.001)
                print(f"embedded={done}/{len(missing)} rate={done / elapsed:.1f}_chunks_per_sec")
    return cache


def build_sql(payload: dict, embeddings: dict[str, list[float]], output: Path, model: str) -> None:
    document = payload["document"]
    chunks = payload["chunks"]
    atomic_text = "\n".join(chunk["content"] for chunk in chunks if chunk["granularity"] == "atomic")
    now = datetime.now(timezone.utc).isoformat()
    full_hash = hashlib.sha256(atomic_text.encode("utf-8")).hexdigest()
    lines = [
        "BEGIN;",
        f"DELETE FROM bf_assistant.rag_chunk_embedding WHERE chunk_id IN (SELECT chunk_id FROM bf_assistant.rag_chunk WHERE doc_id={sql_quote(DOC_ID)});",
        f"DELETE FROM bf_assistant.rag_chunk WHERE doc_id={sql_quote(DOC_ID)};",
        f"DELETE FROM bf_assistant.rag_document WHERE doc_id={sql_quote(DOC_ID)};",
        "INSERT INTO bf_assistant.rag_document(doc_id,title,source_file,knowledge_category,task_scope_json,version,authority_level,full_text,content_hash,created_at,updated_at) VALUES("
        + ",".join(
            [
                sql_quote(DOC_ID),
                sql_quote(document["title"]),
                sql_quote(document["source_file"]),
                sql_quote("三规二制"),
                sql_quote(json.dumps(["process_qa", "case_analysis", "condition_diagnosis"], ensure_ascii=False)),
                sql_quote("v1.0-hierarchical"),
                sql_quote("knowledge_doc"),
                sql_quote(atomic_text),
                sql_quote(full_hash),
                sql_quote(now),
                sql_quote(now),
            ]
        )
        + ");",
    ]
    for chunk in chunks:
        vector = embeddings.get(chunk["chunk_id"])
        if vector is None:
            raise RuntimeError(f"missing embedding for {chunk['chunk_id']}")
        keywords = list(
            dict.fromkeys(
                [
                    chunk["chapter_title"],
                    chunk["regulation_type"],
                    chunk["section_code"],
                    chunk["granularity"],
                    *chunk["hierarchy_path"],
                ]
            )
        )
        source_priority = {"atomic": 110, "topic": 105, "section": 95}[chunk["granularity"]]
        chunk_values = [
            chunk["chunk_id"],
            DOC_ID,
            chunk.get("parent_chunk_id"),
            chunk["title"],
            chunk["content"],
            chunk["enriched_content"],
            chunk["title"][:300],
            json.dumps(keywords, ensure_ascii=False),
            json.dumps([chunk["chapter_title"], chunk["regulation_type"]], ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            f"three_rules_{chunk['granularity']}",
            len(chunk["content"]),
            document["source_file"],
            "三规二制",
            json.dumps(["process_qa", "case_analysis", "condition_diagnosis"], ensure_ascii=False),
            "knowledge_doc",
            source_priority,
            chunk["content_hash"],
            now,
        ]
        lines.append(
            "INSERT INTO bf_assistant.rag_chunk(chunk_id,doc_id,parent_chunk_id,title,content,enriched_content,summary,keywords_json,entities_json,phenomenon_json,parameter_names_json,chunk_type,token_count,source_file,knowledge_category,task_scope_json,authority_level,source_priority,content_hash,created_at) VALUES("
            + ",".join(sql_quote(value) for value in chunk_values)
            + ");"
        )
        embedding_hash = hashlib.sha256(str(chunk["enriched_content"])[:3000].encode("utf-8")).hexdigest()
        lines.append(
            "INSERT INTO bf_assistant.rag_chunk_embedding(chunk_id,embedding_model,embedding,embedding_dimension,embedding_text_hash,updated_at) VALUES("
            + ",".join(
                [
                    sql_quote(chunk["chunk_id"]),
                    sql_quote(model),
                    sql_quote(vector_literal(vector)) + "::vector",
                    str(len(vector)),
                    sql_quote(embedding_hash),
                    sql_quote(now),
                ]
            )
            + ");"
        )
    lines.extend(
        [
            "COMMIT;",
            f"SELECT 'documents='||count(*) FROM bf_assistant.rag_document WHERE doc_id={sql_quote(DOC_ID)};",
            f"SELECT 'chunks='||count(*) FROM bf_assistant.rag_chunk WHERE doc_id={sql_quote(DOC_ID)};",
            f"SELECT 'embeddings='||count(*) FROM bf_assistant.rag_chunk_embedding WHERE chunk_id IN (SELECT chunk_id FROM bf_assistant.rag_chunk WHERE doc_id={sql_quote(DOC_ID)});",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Vectorize hierarchical 三规二制 chunks and import them into the active RAG tables.")
    parser.add_argument("--input", type=Path, default=Path("logs/three_rules_hierarchical_chunks.json"))
    parser.add_argument("--cache", type=Path, default=Path("logs/three_rules_embeddings.jsonl"))
    parser.add_argument("--sql-output", type=Path, default=Path("logs/import_three_rules_rag.sql"))
    parser.add_argument("--embedding-base-url", default=os.getenv("BF_QA_EMBEDDING_BASE_URL", "http://10.30.220.12:11434"))
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--host", default=os.getenv("BF_PG_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=os.getenv("BF_PG_PORT", "5443"))
    parser.add_argument("--database", default=os.getenv("BF_PG_DB", "bf_trend"))
    parser.add_argument("--user", default=os.getenv("BF_PG_USER", "postgres"))
    parser.add_argument("--password-env", default="BF_PG_PASSWORD")
    parser.add_argument("--no-import", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    chunks = list(payload["chunks"])
    embeddings = embed_missing(
        chunks,
        args.cache,
        args.embedding_base_url,
        args.model,
        max(1, args.batch_size),
        args.timeout,
    )
    dimensions = sorted({len(embeddings[chunk["chunk_id"]]) for chunk in chunks})
    if dimensions != [768]:
        raise RuntimeError(f"expected 768-dimensional embeddings, got {dimensions}")
    build_sql(payload, embeddings, args.sql_output, args.model)
    print(f"sql={args.sql_output.resolve()} size={args.sql_output.stat().st_size}")
    if args.no_import:
        return 0
    env = os.environ.copy()
    env["PGPASSWORD"] = os.getenv(args.password_env, "postgres")
    subprocess.run(
        [
            str(PSQL), "-q", "-w", "-h", args.host, "-p", str(args.port), "-U", args.user,
            "-d", args.database, "-v", "ON_ERROR_STOP=1", "-f", str(args.sql_output),
        ],
        env=env,
        check=True,
    )
    print(f"imported_doc={DOC_ID} chunks={len(chunks)} embeddings={len(chunks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

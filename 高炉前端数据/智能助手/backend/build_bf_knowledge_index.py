from __future__ import annotations

import argparse
from pathlib import Path

from bf_knowledge_rag import DEFAULT_DB_PATH, DEFAULT_SOURCE_DIR, rebuild_index, rebuild_pgvector_embeddings


def main() -> None:
    parser = argparse.ArgumentParser(description="Build blast furnace unified knowledge RAG index.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR), help="Directory containing 知识库.zip.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="兼容旧参数；当前写入 PostgreSQL bf_assistant.rag_* 表。")
    parser.add_argument("--with-pgvector", action="store_true", help="同步重建 pgvector embedding 索引。")
    parser.add_argument("--embedding-limit", type=int, default=None, help="限制本次生成 embedding 的 chunk 数。")
    parser.add_argument("--force-embeddings", action="store_true", help="强制重建已存在的 embedding。")
    args = parser.parse_args()

    result = rebuild_index(Path(args.source_dir), Path(args.db_path))
    print(f"documents={result['documents']}")
    print(f"chunks={result['chunks']}")
    print(f"storage={result['storage']}")
    print(f"schema={result['schema']}")
    if args.with_pgvector:
        vector_result = rebuild_pgvector_embeddings(limit=args.embedding_limit, force=args.force_embeddings)
        print(f"pgvector_ok={vector_result.get('ok')}")
        print(f"pgvector_updated={vector_result.get('updated')}")
        print(f"pgvector_message={vector_result.get('message') or ''}")


if __name__ == "__main__":
    main()

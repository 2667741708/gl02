from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


PSQL = Path(r"C:\Program Files\PostgreSQL\16\bin\psql.exe")
DEFAULT_JSON = Path("logs/three_rules_hierarchical_chunks.json")


def sql_quote(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def build_sql(payload: dict, output: Path) -> None:
    document = payload["document"]
    chunks = payload["chunks"]
    lines = [
        "BEGIN;",
        "CREATE SCHEMA IF NOT EXISTS bf_assistant;",
        """
CREATE TABLE IF NOT EXISTS bf_assistant.rag_hierarchical_chunk (
    chunk_id text PRIMARY KEY,
    doc_id text NOT NULL,
    parent_chunk_id text,
    title text NOT NULL,
    content text NOT NULL,
    enriched_content text NOT NULL,
    granularity text NOT NULL CHECK (granularity IN ('atomic','topic','section')),
    chapter_code text NOT NULL,
    chapter_title text NOT NULL,
    regulation_type text NOT NULL,
    section_code text NOT NULL DEFAULT '',
    hierarchy_path_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_block_start integer NOT NULL,
    source_block_end integer NOT NULL,
    content_hash text NOT NULL,
    source_file text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);""".strip(),
        "CREATE INDEX IF NOT EXISTS idx_rag_hierarchical_doc ON bf_assistant.rag_hierarchical_chunk(doc_id, granularity, chapter_code);",
        "CREATE INDEX IF NOT EXISTS idx_rag_hierarchical_section ON bf_assistant.rag_hierarchical_chunk(doc_id, chapter_code, regulation_type, section_code);",
        f"DELETE FROM bf_assistant.rag_hierarchical_chunk WHERE doc_id={sql_quote(document['doc_id'])};",
    ]
    source_file = document["source_file"]
    for chunk in chunks:
        values = (
            chunk["chunk_id"],
            document["doc_id"],
            chunk.get("parent_chunk_id"),
            chunk["title"],
            chunk["content"],
            chunk["enriched_content"],
            chunk["granularity"],
            chunk["chapter_code"],
            chunk["chapter_title"],
            chunk["regulation_type"],
            chunk["section_code"],
            json.dumps(chunk["hierarchy_path"], ensure_ascii=False),
            chunk["source_block_start"],
            chunk["source_block_end"],
            chunk["content_hash"],
            source_file,
        )
        lines.append(
            "INSERT INTO bf_assistant.rag_hierarchical_chunk("
            "chunk_id,doc_id,parent_chunk_id,title,content,enriched_content,granularity,"
            "chapter_code,chapter_title,regulation_type,section_code,hierarchy_path_json,"
            "source_block_start,source_block_end,content_hash,source_file) VALUES("
            + ",".join(sql_quote(value) for value in values[:11])
            + ","
            + sql_quote(values[11])
            + "::jsonb,"
            + ",".join(sql_quote(value) for value in values[12:])
            + ");"
        )
    lines.extend(
        [
            "COMMIT;",
            f"SELECT granularity, count(*) FROM bf_assistant.rag_hierarchical_chunk WHERE doc_id={sql_quote(document['doc_id'])} GROUP BY granularity ORDER BY granularity;",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import hierarchical 三规二制 chunks into native PostgreSQL 16.")
    parser.add_argument("--input", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--sql-output", type=Path, default=Path("logs/import_three_rules_hierarchical.sql"))
    parser.add_argument("--host", default=os.getenv("BF_PG_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=os.getenv("BF_PG_PORT", "5443"))
    parser.add_argument("--database", default=os.getenv("BF_PG_DB", "bf_trend"))
    parser.add_argument("--user", default=os.getenv("BF_PG_USER", "postgres"))
    parser.add_argument("--password-env", default="BF_PG_PASSWORD")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    build_sql(payload, args.sql_output)
    env = os.environ.copy()
    env["PGPASSWORD"] = os.getenv(args.password_env, "postgres")
    subprocess.run(
        [
            str(PSQL),
            "-w",
            "-h",
            args.host,
            "-p",
            str(args.port),
            "-U",
            args.user,
            "-d",
            args.database,
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(args.sql_output),
        ],
        env=env,
        check=True,
    )
    print(f"imported_doc={payload['document']['doc_id']} chunks={payload['counts']['chunks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Probe source-table FK/trigger/vector metadata from startup-readonly connections."""
import argparse
import json
import os
from pathlib import Path
import sys

TABLES = ['rag_document', 'rag_chunk', 'rag_chunk_embedding',
          'qa_knowledge_source_releases', 'qa_knowledge_source_bindings']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((args.root / 'tools/service_configs/22012_BFV4PreviewProxy8093.json').read_text(encoding='utf-8-sig'))
    for key, value in (config.get('env') or {}).items():
        if key.startswith(('BF_ASSISTANT_PG', 'GL02_PG', 'PG')):
            os.environ[key] = str(value)
    sys.path.insert(0, str(args.root / '高炉前端数据/智能助手/backend'))
    from qa_readonly_pg import readonly_pg_connect
    with readonly_pg_connect() as connection:
        foreign = connection.execute(
            "SELECT s.nspname AS source_schema,c.relname AS source_table,ts.nspname AS target_schema,"
            "t.relname AS target_table,k.confdeltype AS delete_action FROM pg_catalog.pg_constraint k "
            "JOIN pg_catalog.pg_class c ON c.oid=k.conrelid JOIN pg_catalog.pg_namespace s ON s.oid=c.relnamespace "
            "JOIN pg_catalog.pg_class t ON t.oid=k.confrelid JOIN pg_catalog.pg_namespace ts ON ts.oid=t.relnamespace "
            "WHERE k.contype='f' AND ((s.nspname='bf_assistant' AND c.relname=ANY(%s)) "
            "OR (ts.nspname='bf_assistant' AND t.relname=ANY(%s))) ORDER BY source_schema,source_table,target_table",
            (TABLES, TABLES)
        ).fetchall()
        triggers = connection.execute(
            "SELECT c.relname AS table_name,t.tgname AS trigger_name,t.tgenabled AS enabled "
            "FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='bf_assistant' "
            "AND c.relname=ANY(%s) AND NOT t.tgisinternal AND t.tgenabled<>'D' ORDER BY table_name,trigger_name",
            (TABLES,)
        ).fetchall()
        vector = connection.execute(
            "SELECT udt_name,udt_schema FROM information_schema.columns WHERE table_schema='bf_assistant' "
            "AND table_name='rag_chunk_embedding' AND column_name='embedding'"
        ).fetchone()
    print(json.dumps({'schema': 'bf.qa.keyword-source-dependencies-readonly.v1',
                      'foreign_keys': [dict(row) for row in foreign],
                      'active_user_triggers': [dict(row) for row in triggers],
                      'vector_type': dict(vector) if vector else None,
                      'database_writes': 0, 'model_calls': 0, 'question_posts': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()

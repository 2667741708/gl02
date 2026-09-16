"""Verify known once-only test turns in PostgreSQL; emit no IDs or raw content."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    ids = {case['case_id']: case['user_message_id'] for case in cases}
    if len(ids) != len(cases) or len(set(ids.values())) != len(cases):
        raise ValueError('duplicate provenance fixture')
    config = json.loads((args.root / 'tools/service_configs/22012_BFV4PreviewProxy8093.json').read_text(encoding='utf-8-sig'))
    for key, value in (config.get('env') or {}).items():
        if key.startswith(('BF_ASSISTANT_PG', 'GL02_PG', 'PG')):
            os.environ[key] = str(value)
    sys.path.insert(0, str(args.root / '高炉前端数据/智能助手/backend'))
    from assistant_pg import raw_pg_connect, PgCompatConnection
    import mcp_conversation_context as context
    results = []
    with raw_pg_connect() as raw:
        raw.execute('SET TRANSACTION READ ONLY')
        conn = PgCompatConnection(raw)
        for case in cases:
            row = conn.execute('''SELECT m.content, m.hidden_context_json, c.owner_subject
                FROM qa_messages m JOIN qa_conversations c ON c.id=m.conversation_id
                WHERE m.id=? AND m.conversation_id=? AND m.role='user' ''',
                (case['user_message_id'], case['conversation_id'])).fetchone()
            if not row:
                results.append({'case_id': case['case_id'], 'state': 'failed', 'reason': 'known_turn_missing'})
                continue
            hidden = json.loads(row['hidden_context_json'])
            state = hidden.get('mcp_conversation_context') or {}
            provenance = state.get('inheritance_provenance') or {}
            expected_objects = {name: ids[source_case] for name, source_case in case['objects'].items()}
            window = case.get('window')
            expected_window = {'mode':'relative','minutes':window['minutes']} if window else None
            checks = {
                'question_hash': hashlib.sha256(row['content'].encode('utf-8')).hexdigest() == case['question_sha256'],
                'server_turn_binding': state.get('source_message_id') == case['user_message_id'],
                'objects': state.get('selected_objects') == list(case['objects']),
                'object_sources': (provenance.get('objects') or {}).get('sources') == expected_objects,
                'window': state.get('time_range') == expected_window,
                'window_source': (provenance.get('time_range') or {}).get('source_message_id') == (ids[window['source_case']] if window else None),
                'no_evidence_reuse': state.get('evidence_reuse') is False and state.get('last_evidence') == [],
                'all_sources_owned_user_turns': context._owned_ancestry(conn, case['conversation_id'], row['owner_subject'], state),
            }
            results.append({'case_id':case['case_id'], 'state':'passed' if all(checks.values()) else 'failed', 'checks':checks})
    print(json.dumps({'schema':'bf.qa.context-provenance-readonly.v1', 'total':len(results),
        'passed':sum(row['state']=='passed' for row in results), 'results':results,
        'database_writes':0, 'question_posts':0, 'model_calls':0,
        'scope':'Known guest test turns only; operator/admin concurrency is not inferred.'}, ensure_ascii=False))
    return 0 if all(row['state']=='passed' for row in results) else 1


if __name__ == '__main__': raise SystemExit(main())

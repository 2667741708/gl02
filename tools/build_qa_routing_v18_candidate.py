"""Bind actual accepted V16 proxy to owner-scoped routing provenance (QAOPT-R10)."""
import argparse
import ast
import hashlib
from pathlib import Path
import shutil
from build_qa_routing_v16_candidate import replace_one

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = '3e535565e7579b4f33a29faf5938092d4b2b84708fa3dd410ff4ba8d4c6d50b6'


def build(text):
    text = replace_one(text, 'from mcp_conversation_context import (',
                       'import mcp_conversation_context as qa_context_state\nfrom mcp_conversation_context import (')
    start = text.index('def last_qa_tool_context(')
    end = text.index('\ndef qa_snapshots_for_turn(', start)
    text = text[:start] + '''def last_qa_tool_context(conn: Any, conversation_id: str, owner: str) -> dict[str, Any] | None:
    """Load routing state from owner-restricted persisted user turns."""
    return qa_context_state.load_owned_tool_context(conn, conversation_id, owner)

''' + text[end:]
    text = replace_one(text, 'previous_tool_context = last_qa_tool_context(conn, conversation_id)',
                       'previous_tool_context = last_qa_tool_context(conn, conversation_id, owner_subject)')
    text = replace_one(text, '''                hidden_context=hidden_context,
            )
            if context_refs:
                insert_context_refs(conn, conversation_id, user_message_id, project_id_int, context_refs)''',
                       '''                hidden_context=hidden_context,
            )
            hidden_context = qa_context_state.persist_owned_context_binding(
                conn, conversation_id, owner_subject, user_message_id, hidden_context)
            if context_refs:
                insert_context_refs(conn, conversation_id, user_message_id, project_id_int, context_refs)''')
    ast.parse(text)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = ROOT / '.codex_runtime/qa-routing-v16/candidate/ollama_proxy_server.py'
    if hashlib.sha256(source.read_bytes()).hexdigest() != BASE_SHA:
        raise ValueError('Accepted production proxy changed')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'ollama_proxy_server.py').write_text(build(source.read_text(encoding='utf-8')), encoding='utf-8', newline='\n')
    shutil.copyfile(ROOT / '高炉前端数据/智能助手/backend/mcp_conversation_context.py', args.output / 'mcp_conversation_context.py')
    print('V18 exact proxy and context candidate prepared')


if __name__ == '__main__': main()

"""Owner-checked current-turn response projection for controlled clients.

REQ-QA-FULL-ISSUE-INVENTORY-20260916; QAOPT-O04/O05.
Legacy UI receives the existing complete conversation unless it opts in.
"""
from typing import Any

VERSION = "qa-response-projection-v1"
PUBLIC_FIELDS = ("id", "conversation_id", "role", "content", "created_at", "snapshot_id")

def load_turn_messages(conn: Any, prepared: dict, assistant_message_id: int) -> list[dict]:
    owner = prepared.get("owner_subject")
    conversation = prepared.get("conversation_id")
    user_id = prepared.get("user_message_id")
    if not owner or not conversation or not isinstance(user_id, int) or not isinstance(assistant_message_id, int):
        raise PermissionError("turn identity incomplete")
    rows = conn.execute(
        "SELECT m.id, m.conversation_id, m.role, m.content, m.created_at, m.snapshot_id "
        "FROM qa_messages m JOIN qa_conversations c ON c.id = m.conversation_id "
        "WHERE c.id = ? AND c.owner_subject = ? AND m.id IN (?, ?) ORDER BY m.id",
        (conversation, owner, user_id, assistant_message_id),
    ).fetchall()
    if len(rows) != 2 or rows[0]["id"] != user_id or rows[0]["role"] != "user" or rows[1]["id"] != assistant_message_id or rows[1]["role"] != "assistant":
        raise PermissionError("turn messages do not match owner and role")
    return [{key: row[key] for key in PUBLIC_FIELDS} for row in rows]

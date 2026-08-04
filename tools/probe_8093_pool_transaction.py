from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
sys.path.insert(0, str(BACKEND))

from assistant_pg import db_connect  # noqa: E402


conversation_id = f"pool_probe_{int(time.time())}_{uuid.uuid4().hex[:8]}"
result: dict[str, object] = {"conversation_id": conversation_id}

try:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO qa_conversations(id, title, created_at, updated_at, last_user_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (conversation_id, "pool probe", "2026-07-14T00:00:00+00:00", "2026-07-14T00:00:00+00:00", None),
        )
        same = conn.execute("SELECT id FROM qa_conversations WHERE id = ?", (conversation_id,)).fetchone()
        result["same_connection_visible"] = bool(same)

    with db_connect() as conn:
        committed = conn.execute("SELECT id FROM qa_conversations WHERE id = ?", (conversation_id,)).fetchone()
        result["committed_visible"] = bool(committed)
        conn.execute(
            """
            INSERT INTO qa_messages(conversation_id, role, content, created_at)
            VALUES(?, 'user', 'pool probe', ?)
            """,
            (conversation_id, "2026-07-14T00:00:00+00:00"),
        )
        result["message_inserted"] = True
        conn.execute("DELETE FROM qa_conversations WHERE id = ?", (conversation_id,))
    result["ok"] = True
except Exception as exc:  # noqa: BLE001
    result["ok"] = False
    result["error"] = f"{type(exc).__name__}: {exc}"
    try:
        with db_connect() as conn:
            conn.execute("DELETE FROM qa_conversations WHERE id = ?", (conversation_id,))
    except Exception as cleanup_exc:  # noqa: BLE001
        result["cleanup_error"] = f"{type(cleanup_exc).__name__}: {cleanup_exc}"

print(json.dumps(result, ensure_ascii=False, default=str))

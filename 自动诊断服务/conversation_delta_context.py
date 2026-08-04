from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

from store import DiagnosisStore


DESCRIPTION = "Build incremental diagnosis context for a selected short-window conversation."
EPILOG = """
Examples:
  python 自动诊断服务/conversation_delta_context.py --conversation-id swc_001 --message-time "2026-05-10 19:03:00"
  python 自动诊断服务/conversation_delta_context.py --queue-id dq_20260510_185000 --message-time "2026-05-10 19:03:00" --user-text "现在炉况怎么看？"
"""


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("T", " ")).replace(second=0, microsecond=0)


def build_delta_context(
    config_path: str | None,
    conversation_id: str,
    queue_id: str,
    message_time: datetime,
    user_text: str = "",
    write: bool = False,
) -> dict:
    store = DiagnosisStore(config_path)
    store.ensure_schema()
    conv = store.get_short_window_conversation(conversation_id) if conversation_id else None
    queue = None
    if conv:
        queue = store.get_diagnosis_queue(conv["queue_id"])
    if queue is None and queue_id:
        queue = store.get_diagnosis_queue(queue_id)
    if queue is None:
        queue = store.latest_diagnosis_queue()
    if queue is None:
        raise RuntimeError("No diagnosis queue is available.")
    if not conversation_id:
        conversation_id = "swc_" + str(queue["queue_id"])
    conv = store.ensure_short_window_conversation(conversation_id, queue)
    previous_end = conv["last_queue_diagnosis_ts"]
    delta_start = previous_end + timedelta(minutes=1)
    diagnoses = store.list_diagnoses(previous_end + timedelta(seconds=1), message_time, limit=500)
    diagnoses = list(reversed(diagnoses))
    hidden_context = {
        "conversation_id": conversation_id,
        "queue_id": queue["queue_id"],
        "queue_hash": queue["queue_hash"],
        "operator_message_ts": message_time,
        "operator_message": user_text,
        "delta_diagnoses": [
            {
                "id": item["id"],
                "diagnosis_ts": item["diagnosis_ts"],
                "main_label": item["main_label"],
                "main_score": item["main_score"],
                "main_confidence": item["main_confidence"],
                "secondary_label": item["secondary_label"],
                "evidence": item["evidence"],
            }
            for item in diagnoses
        ],
    }
    payload = {
        "conversation_id": conversation_id,
        "queue_id": queue["queue_id"],
        "message_ts": message_time,
        "previous_queue_end_ts": previous_end,
        "delta_start_ts": delta_start if diagnoses else None,
        "delta_end_ts": diagnoses[-1]["diagnosis_ts"] if diagnoses else None,
        "delta_diagnosis_ids": [item["id"] for item in diagnoses],
        "operator_message": user_text,
        "hidden_context_json": hidden_context,
    }
    saved = store.insert_conversation_delta_context(payload) if write else payload
    return {"ok": True, "has_delta": bool(diagnoses), "context": saved, "hidden_context": hidden_context}


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--conversation-id", default="", help="Short-window conversation id.")
    parser.add_argument("--queue-id", default="", help="Known diagnosis queue id/hash.")
    parser.add_argument("--message-time", required=True, help="Operator message timestamp.")
    parser.add_argument("--user-text", default="", help="Operator message text.")
    parser.add_argument("--write-context", action="store_true", help="Persist generated hidden context references.")
    parser.add_argument("--config", default="", help="Optional config.yaml path.")
    args = parser.parse_args()
    result = build_delta_context(args.config or None, args.conversation_id, args.queue_id, parse_time(args.message_time), args.user_text, args.write_context)
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

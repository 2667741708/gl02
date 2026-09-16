"""Owner-bound history evidence and plain-text rendering (QAOPT-R02/E01/O05).

Only the server's authenticated owner and current persisted message ID can
bind a query. History excerpts are historical statements, never current facts.
"""
from __future__ import annotations

import json
import re
from typing import Any

VERSION = "qa-history-projection-v1"


def history_keyword(question: str) -> str:
    text = re.sub(r"^(?:请)?(?:检索|查询|查找)?(?:最近有没有关于|之前有没有问过|以前有没有问过|历史问答里关于|历史问答中关于)", "", question.strip())
    text = re.sub(r"(?:的历史问答|的历史回答|的回答|历史问答|历史会话|聊天记录|对话记录)[？?。\s]*$", "", text)
    return text.strip("？?。 ，,")[:120]


def fetch_owned_history(conn: Any, *, owner: str, before_message_id: int, question: str) -> dict[str, Any]:
    if not isinstance(owner, str) or not owner.strip() or isinstance(before_message_id, bool) or not isinstance(before_message_id, int) or before_message_id <= 0:
        return {"ok": False, "error": "history_scope_required"}
    keyword = history_keyword(question)
    if not keyword:
        return {"ok": False, "error": "history_keyword_required"}
    pattern = "%" + keyword.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
    rows = conn.execute("""
        SELECT m.role, m.content, m.created_at
        FROM qa_messages m JOIN qa_conversations c ON c.id = m.conversation_id
        WHERE c.owner_subject = ? AND m.id < ?
          AND m.role IN ('user', 'assistant')
          AND lower(m.content) LIKE lower(?) ESCAPE '!'
        ORDER BY m.created_at DESC, m.id DESC LIMIT 10
    """, (owner, before_message_id, pattern)).fetchall()
    messages = []
    for row in rows:
        row = dict(row)
        text = str(row.get("content") or "")
        messages.append({"role": row.get("role"), "created_at": str(row.get("created_at") or "时间未登记"), "excerpt": text[:600], "truncated": len(text) > 600})
    return {"ok": True, "keyword": keyword, "count": len(messages), "messages": messages,
            "source": {"type": "owner_scoped_qa_history", "read_policy": "readonly"}}


def history_outcome(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("ok") is not True or payload.get("source", {}).get("type") != "owner_scoped_qa_history":
        return {"ok": True, "answer": "历史问答未完成受限范围检索，本次无法确认；没有查询其他用户的会话。", "answer_route": "history_scope_failed_closed", "model_request_count": 0, "grounding_status": "no_verified_history"}
    rows = payload.get("messages")
    if not isinstance(rows, list):
        return history_outcome({})
    lines = [f"在当前会话身份可访问的历史中找到 {len(rows)} 条匹配消息：" if rows else "在当前会话身份可访问的历史中未找到匹配消息；这不证明其他范围不存在记录。"]
    for item in rows[:10]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        excerpt = str(item.get("excerpt") or "")
        try:
            structured = isinstance(json.loads(excerpt), (dict, list))
        except (ValueError, TypeError):
            structured = '{"' in excerpt or '[{"' in excerpt
        if structured:
            excerpt = "[历史消息含结构化结果，未在摘要中展开原始字段]"
        excerpt = re.sub(r"```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)", "[代码示例已省略]", excerpt)
        lines.append(f"- {item.get('created_at') or '时间未登记'}；{'历史提问' if item['role'] == 'user' else '历史回答摘录'}：{excerpt}{'（摘录截断）' if item.get('truncated') else ''}")
    lines.append("以上是历史记录摘录，未重新核实当时的回答，不代表当前实时数据、正式制度或新的分析结论。")
    return {"ok": True, "answer": "\n".join(lines), "answer_route": "owner_scoped_history", "model_request_count": 0,
            "tool_used": True, "grounding_status": "verified_history_excerpt", "tool_trace": [], "history_status": "found" if rows else "no_match"}

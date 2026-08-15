from __future__ import annotations

import importlib
import sys
from contextlib import nullcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend"
DASHBOARD = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _module():
    return importlib.import_module("ollama_proxy_server")


def test_guest_identity_is_stable_per_service_address() -> None:
    module = _module()
    first = module.shared_guest_identity("10.30.220.12:8093")
    second = module.shared_guest_identity("10.30.220.12:8093")
    preview = module.shared_guest_identity("10.30.220.12:8094")
    assert first == second
    assert first["access_mode"] == "guest_shared"
    assert first["role"] == "anonymous_guest"
    assert first["sub"].startswith("guest:")
    assert first["sub"] != preview["sub"]


def test_guest_room_is_single_durable_conversation_contract() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert 'conversation_id = f"qa_guest_{room_id}"' in source
    assert 'title="局域网共享访客会话"' in source
    assert 'owner_role="anonymous_guest"' in source
    assert '"access_mode": "guest_shared"' in source
    assert '"shared_guest": guest_mode' in source


def test_guest_chat_rebinds_stale_conversation_id(monkeypatch) -> None:
    module = _module()
    session = module.shared_guest_identity("10.30.220.12:8093")
    shared_id = "qa_guest_expected"
    monkeypatch.setattr(
        module,
        "ensure_shared_guest_conversation",
        lambda conn, identity: {"id": shared_id},
    )

    class Probe:
        def qa_conversation_owned(self, conn, conversation_id, identity):
            raise AssertionError("guest requests must not use private owner validation")

    resolved = module.Handler.qa_chat_conversation_id(
        Probe(), object(), "stale-private-conversation", session
    )
    assert resolved == shared_id


def test_guest_chat_overwrites_stale_id_before_preparation(monkeypatch) -> None:
    module = _module()
    session = module.shared_guest_identity("10.30.220.12:8093")
    shared_id = "qa_guest_expected"
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "db_connect", lambda: nullcontext(object()))
    monkeypatch.setattr(
        module,
        "ensure_shared_guest_conversation",
        lambda conn, identity: {"id": shared_id},
    )

    class Probe:
        headers = {"Accept": "application/json"}
        qa_chat_conversation_id = module.Handler.qa_chat_conversation_id

        def qa_session_required(self):
            return session

        def read_json_body(self):
            return {"conversation_id": "stale-private-conversation", "message": "当前炉况如何？"}

        def qa_conversation_owned(self, conn, conversation_id, identity):
            raise AssertionError("guest requests must not use private owner validation")

        def handle_qa_chat_json(self, payload, question):
            captured["payload"] = payload
            captured["question"] = question

    module.Handler.handle_qa_chat(Probe())
    assert captured["question"] == "当前炉况如何？"
    assert captured["payload"]["conversation_id"] == shared_id


def test_authenticated_chat_keeps_private_owner_validation() -> None:
    module = _module()
    calls: list[tuple[str, str]] = []

    class Probe:
        def qa_conversation_owned(self, conn, conversation_id, session):
            calls.append((conversation_id, str(session["sub"])))
            return False

    session = {"sub": "operator:1", "role": "operator", "access_mode": "authenticated"}
    resolved = module.Handler.qa_chat_conversation_id(
        Probe(), object(), "another-owner-conversation", session
    )
    assert resolved is None
    assert calls == [("another-owner-conversation", "operator:1")]


def test_guest_cannot_attach_private_context_or_mutate_projects() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert '"guest_context_not_allowed"' in source
    assert '"project_id", "context_assets", "attachments"' in source
    assert "def qa_operator_session_required" in source
    assert "def handle_qa_projects_get" in source
    assert "if self.qa_operator_session_required() is None:" in source


def test_messages_keep_database_timestamps() -> None:
    source = (BACKEND / "ollama_proxy_server.py").read_text(encoding="utf-8")
    assert "INSERT INTO qa_messages(" in source
    assert "conversation_id, role, content, created_at, snapshot_id" in source
    assert '"created_at": row["created_at"]' in source


def test_dashboard_defaults_to_shared_guest_and_keeps_private_login() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "function QaGuestNav" in source
    assert "所有通过当前服务地址访问的人共享这一个会话窗口" in source
    assert "问答内容与时间戳保存到本地 PostgreSQL" in source
    assert "loginOpen" in source
    assert "登录私有模式（可选）" in source
    assert "普通智能问答可以匿名使用" in source
    assert "继续匿名使用" in source
    assert "else window.location.reload()" in source
    assert "guestMode ? { conversation_id: activeId, message: text, current_snapshot: currentSnapshot }" in source
    assert "访客问答包含页面当前炉况与时间戳" in source
    assert "setInterval(refreshGuest, 5000)" in source


def test_schema_limits_one_guest_conversation_per_room_owner() -> None:
    schema = (BACKEND / "schema" / "postgresql_assistant.sql").read_text(encoding="utf-8")
    migration = (BACKEND / "schema" / "20260811_abc_contextual_assistant.sql").read_text(encoding="utf-8")
    for source in (schema, migration):
        assert "uq_qa_shared_guest_room" in source
        assert "WHERE owner_role = 'anonymous_guest'" in source

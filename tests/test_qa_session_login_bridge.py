from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


def source() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def test_qa_transport_preserves_session_error_code_for_json_and_sse():
    text = source()

    assert "function qaApiError(data, status" in text
    assert "error.code = String(data?.error || '')" in text
    assert "error.status = Number(status || 0)" in text
    assert "function qaIsSessionRequired(error)" in text
    assert text.count("credentials: 'same-origin'") >= 2
    assert "throw qaApiError(data, res.status)" in text
    assert "throw qaApiError(errorData, errorData.status || 0" in text


def test_qa_tab_has_explicit_login_bridge_without_persisting_password():
    text = source()

    assert "REQ-QA-SESSION-LOGIN-BRIDGE-20260812" in text
    assert "function QaSessionLogin({ onAuthenticated, onContinueGuest })" in text
    assert "qaServerJson('/api/auth/login'" in text
    assert "登录私有会话（可选）" in text
    assert "继续匿名使用" in text
    assert "登录凭据只提交到当前 8093 服务，不写入页面存储" in text
    assert "localStorage.setItem('qa" not in text
    assert "sessionStorage.setItem('qa" not in text


def test_bootstrap_distinguishes_auth_from_connectivity_and_reloads_after_login():
    text = source()
    qa_tab = text[text.index("function QaTab({ buf, diagnosis })"):text.index("function reportEnsureStyle()")]

    assert "if (qaIsSessionRequired(e))" in qa_tab
    assert "setAuthRequired(true)" in qa_tab
    assert "智能助手需要登录后使用" in qa_tab
    assert "else setErr(`代理不可达或问答服务未启动" in qa_tab
    assert "const ok = await loadBootstrap(false)" in qa_tab
    assert "if (!ok) throw new Error('当前账号没有智能助手操作权限。')" in qa_tab
    assert "await reloadProjects(); await loadShortConversations()" in qa_tab


def test_expired_session_restores_question_and_never_replays_chat_post():
    text = source()
    qa_tab = text[text.index("function QaTab({ buf, diagnosis })"):text.index("function reportEnsureStyle()")]

    assert "setInput(text)" in qa_tab
    assert "m.id !== pendingId && m.id !== userLocalId" in qa_tab
    assert "登录状态已过期，本次提问未发送；登录后请手动再次发送。" in qa_tab
    assert "await qaServerChatStream" in qa_tab
    assert qa_tab.count("await qaServerChatStream") == 1
    assert "onAuthenticated={async () =>" in qa_tab
    assert "qaServerChatStream" not in qa_tab.split("onAuthenticated={async () =>", 1)[1].split("/>}", 1)[0]

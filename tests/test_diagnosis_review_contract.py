from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"
SCRIPT = ROOT / "高炉前端数据" / "assets" / "bf-diagnosis-review-local.js"
CSS = ROOT / "高炉前端数据" / "assets" / "bf-diagnosis-review-local.css"


def test_proxy_exposes_review_routes_and_conditional_injection():
    text = PROXY.read_text(encoding="utf-8")
    for route in ("/api/auth/logout", "/api/diagnosis-review-context", "/api/diagnosis-reviews"):
        assert route in text
    assert "/api/diagnosis-manual-scores" in text
    assert "diagnosis_review.review_enabled()" in text
    assert "bf-diagnosis-review-local.js" in text
    assert "BF_SKIP_ASSISTANT_STARTUP" in text
    assert "store = self.review_store()" in text
    assert "diagnosis_review.submission_identity(session, config)" in text
    assert '"login_required": config.require_login' in text
    assert "ON CONFLICT (idempotency_key) DO NOTHING" in (ROOT / "高炉前端数据" / "智能助手" / "backend" / "diagnosis_review.py").read_text(encoding="utf-8")


def test_frontend_contract_has_three_states_and_seven_score_source():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "诊断正确" in text and "诊断不正确" in text and "暂无法判断" in text
    assert "规则符合度，不是统计概率" in text
    assert 'cold:"热制度下行"' in text and 'hot:"热制度上行"' in text
    assert "ctx.candidates" in text
    assert "bfdr-human-score" in text and "bfdr-suggestion" in text
    assert 'form.classList.toggle("bfdr-hidden",!canSubmit||reviewed)' in text
    assert '!auth.authenticated||!auth.can_submit||reviewed' not in text


def test_modal_is_scrollable_and_uses_required_chinese_font():
    text = CSS.read_text(encoding="utf-8")
    assert 'SimSun,"宋体",serif' in text
    assert ".bfdr-scroll" in text and "overflow:auto" in text
    assert "text-overflow:ellipsis" not in text


def test_main_html_is_not_hardwired_to_local_review_asset():
    html = (ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html").read_text(encoding="utf-8")
    assert "bf-diagnosis-review-local.js" not in html


def test_manual_diagnosis_scoring_contract_and_dashboard_projection():
    manual = (ROOT / "高炉前端数据" / "assets" / "bf-diagnosis-manual-score-local.js").read_text(encoding="utf-8")
    dashboard_server = (ROOT / "db_dashboard" / "server.py").read_text(encoding="utf-8")
    dashboard_html = (ROOT / "db_dashboard" / "index.html").read_text(encoding="utf-8")
    assert ".diag-rank-card" in manual
    assert "data-bfdms-label" in manual
    assert "if(name.textContent!==LABELS[key])" in manual
    assert "/api/diagnosis-manual-scores" in manual
    assert "关闭且不保存" in manual
    assert 'form.classList.toggle("bfdms-hidden",!canSubmit)' in manual
    assert '!auth.authenticated||!auth.can_submit' not in manual
    assert "system_score" in dashboard_server and "foreman_score_status" in dashboard_server
    assert "/api/diagnosis-foreman-scores" in dashboard_server
    assert 'source_mode not in {"live_readonly", "local_fixture"}' in dashboard_server
    assert "elif isinstance(value, (datetime, date))" in dashboard_server
    assert 'data-tab="foreman-score"' in dashboard_html
    assert '<option value="local_fixture">本机测试记录</option>' in dashboard_html
    assert "未打分" in dashboard_html

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "高炉前端数据" / "assets"
DASHBOARD = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


def test_each_rendered_abc33_card_has_one_ids_only_assistant_entry():
    """REQ-ABC33-CONTEXTUAL-ASSISTANT-20260811 card/event contract."""
    source = (ASSETS / "abc-furnace-rules-production.js").read_text(encoding="utf-8")
    card_template = source[source.index("function ruleCard"):source.index("function renderState")]

    assert card_template.count('class="abc33-assistant-open"') == 1
    assert "abc33-card-head" in card_template
    assert "智能助手解释" in card_template
    event_payload = card_template.split("new CustomEvent", 1)[1].split("))", 1)[0]
    assert "rule_id:String(x.rule_id||'')" in event_payload
    assert "evaluation_id:String(x.evaluation_id||data&&data.evaluation_id||'')" in event_payload
    assert "source_page:'optimization'" in event_payload
    assert "trigger: event.currentTarget" in event_payload
    for forbidden in ("score", "weights", "context", "prompt"):
        assert forbidden not in event_payload


def test_contextual_dialog_uses_contract_and_never_replays_sse_post():
    """The initial explanation and every follow-up use one explicit SSE POST."""
    source = (ASSETS / "bf-abc33-assistant-dialog.js").read_text(encoding="utf-8")

    assert "'/api/furnace-rules/'" in source
    assert "'/explanation-context?evaluation_id='" in source
    assert "'/api/qa/contextual-conversations'" in source
    assert "source_type:'abc_rule'" in source
    assert "source_page:'optimization'" in source
    assert "reuse_policy:'same_rule_active'" in source
    assert "analysis_mode:initial?'initial_context_explanation':undefined" in source
    assert source.count("fetch('/api/qa/chat'") == 1
    assert source.count("streamQuestion('请解释当前炉况规则的判断依据、形成过程与处置顺序。',{initial:true})") == 1
    assert "payload.error||payload.error_code||payload.message" in source
    assert "本次提问未自动重发" in source
    assert "attempts" not in source


def test_contextual_dialog_has_full_state_accessibility_and_degraded_contract():
    source = (ASSETS / "bf-abc33-assistant-dialog.js").read_text(encoding="utf-8")
    css = (ASSETS / "bf-abc33-assistant-dialog.css").read_text(encoding="utf-8")

    for state in (
        "closed", "opening", "context_ready", "analysis_preparing",
        "analysis_streaming", "streaming", "ready", "minimized",
        "failed", "stopped",
    ):
        assert f"'{state}'" in source
    for field in (
        "operator_explanation", "calculation.terms", "display_name",
        "raw_value", "unit", "normalized_score_0_100", "weight",
        "weighted_points", "semantic", "process_guidance",
        "intervention_order",
    ):
        assert field in source
    assert 'role="dialog"' in source
    assert 'aria-modal="true"' in source
    assert "event.key==='Escape'" in source
    assert "event.key==='Tab'" in source
    assert "规则分析接口暂不可用" in source
    assert "规则解释已就绪；登录操作或管理账号后可继续对话" in source
    assert "payload.message||payload.error||payload.error_code" in source
    assert "failed to fetch" in source.lower()
    assert "min(82vh,720px)" in css
    close_body = source[source.index("function close()"):source.index("function minimize()")]
    assert ".abort()" not in close_body


def test_dialog_phase_and_visible_state_are_independent_during_streaming():
    source = (ASSETS / "bf-abc33-assistant-dialog.js").read_text(encoding="utf-8")

    assert "state='closed',viewState='closed'" in source
    assert "viewState==='minimized'?'minimized':next" in source
    assert "fullButton.disabled=busy" in source
    assert "['analysis_preparing','analysis_streaming','streaming'].includes(state)" in source
    assert "viewState='minimized';setState(state)" in source
    assert "viewState='open';setState(state)" in source
    assert "setState('minimized')" not in source
    assert "if(dismissed||viewState==='closed')return" in source
    assert "function finishStream()" in source


def test_full_assistant_handoff_uses_storage_and_same_page_event():
    dialog = (ASSETS / "bf-abc33-assistant-dialog.js").read_text(encoding="utf-8")
    dashboard = DASHBOARD.read_text(encoding="utf-8")

    assert "bf_qa_contextual_conversation_id" in dialog
    assert "new CustomEvent('bf:qa-open-conversation'" in dialog
    assert "document.addEventListener('bf:qa-open-conversation'" in dashboard
    assert "document.removeEventListener('bf:qa-open-conversation'" in dashboard
    assert "event?.detail?.conversation_id" in dashboard
    assert "[booting, loading]" in dashboard


def test_real_explanation_response_shape_keeps_deterministic_and_ai_content_distinct():
    """The GET contract puts deterministic material under operator_explanation."""
    source = (ASSETS / "bf-abc33-assistant-dialog.js").read_text(encoding="utf-8")
    response_shape = {
        "ok": True,
        "operator_explanation": {
            "calculation": {
                "terms": [{
                    "display_name": "综合压差",
                    "raw_value": 142.2,
                    "unit": "kPa",
                    "normalized_score_0_100": 68.0,
                    "weight": 0.35,
                    "weighted_points": 23.8,
                    "semantic": "压差偏高",
                }]
            },
            "process_guidance": {"intervention_order": ["第一步", "第二步"]},
        },
    }

    assert response_shape["operator_explanation"]["calculation"]["terms"][0]["normalized_score_0_100"] == 68.0
    assert "payload&&payload.operator_explanation||payload&&payload.context||payload" in source
    assert "payload.ai_analysis||payload.analysis||payload.analysis_text" in source
    assert "payload.operator_explanation||payload.analysis" not in source


def test_dashboard_loads_cache_busted_assets_and_filters_contextual_conversations():
    source = DASHBOARD.read_text(encoding="utf-8")

    assert "bf-abc33-assistant-dialog.css?v=abc33-context-assistant-20260812-r2" in source
    assert "bf-abc33-assistant-dialog.js?v=abc33-initial-question-20260814-r1" in source
    assert "abc-furnace-rules-production.js?v=abc33-20260813-a-score-deduction-r2" in source
    for value, label in (
        ("all", "全部"),
        ("direct_qa", "直接问答"),
        ("abc_rule", "参数优化炉框"),
        ("diagnosis", "炉况诊断"),
        ("short_window", "短时值守"),
        ("period_report", "报表分析"),
    ):
        assert f"['{value}','{label}']" in source
    assert "sourceFilter === 'all' ? projectVisibleConversations" in source
    assert "(c.source_type || 'direct_qa') === sourceFilter" in source
    assert "bf_qa_contextual_conversation_id" in source

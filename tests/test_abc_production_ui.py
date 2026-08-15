from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "高炉前端数据" / "assets" / "abc-furnace-rules-production.js"


def test_abc_workbench_is_mounted_prominently_in_decision_page_and_has_real_detail_dialog():
    source = ASSET.read_text(encoding="utf-8")
    assert "AI决策中心 · 33项炉况研判" in source
    assert "document.querySelector('.bf-recommendation-summary-v2')" in source
    assert "anchor.insertAdjacentElement('afterend',root)" in source
    assert "[['ALL','全部33项'],['A','A类9项'],['B','B类13项'],['C','C类11项'],['FOREMAN','工长偏好']]" in source
    assert "abc33-category-column category-" in source
    assert "abc-furnace-rule-detail" in source
    assert "renderDetail(payload.detail" in source
    assert "alert(JSON.stringify" not in source


def test_needs_data_score_is_never_rendered_as_100():
    source = ASSET.read_text(encoding="utf-8")
    assert "x.status!=='needs_data'" in source
    assert "'不可计算'" in source
    assert "score_available!==false" in source


def test_operator_bundle_does_not_embed_formula_implementation():
    source = ASSET.read_text(encoding="utf-8")
    for internal_name in ("formula_terms", "normalized_value", "g_H", "g_L", "g_A"):
        assert internal_name not in source


def test_b_and_c_score_contributions_and_foreman_settings_are_available() -> None:
    source = ASSET.read_text(encoding="utf-8")
    assert "REQ-8093-BC-SCORE-CONTRIBUTION-20260814" in source
    assert "当前贡献" in source
    assert "category==='B'?'风险':'危险'" in source
    assert "<h3>主要'+noun+'贡献</h3>" in source
    assert "['settings','权重设置']" in source
    assert "/furnace-rule-admin.html?view=foreman" in source


def test_rule_detail_prominently_renders_formation_principle_and_five_step_flow():
    source = ASSET.read_text(encoding="utf-8")
    assert "处置顺序" in source
    assert "guidanceHtml(d)" in source
    assert "d.principle" in source
    assert "d.intervention_order" in source
    assert "abc33-guidance-panel intervention" in source


def test_action_order_is_first_and_basis_is_button_revealed_without_handbook_indexes():
    source = ASSET.read_text(encoding="utf-8")
    guidance_start = source.index("function guidanceHtml")
    guidance_end = source.index("function renderDetail", guidance_start)
    guidance = source[guidance_start:guidance_end]
    operator_guidance = guidance[guidance.index("}return'<div") :]
    assert "window.location.port!=='8093'" in guidance
    assert operator_guidance.index("处置顺序") < operator_guidance.index("查看工艺依据与操作原理")
    assert "aria-expanded=\"false\"" in operator_guidance
    assert "abc33-basis-content" in operator_guidance
    assert "工艺依据" in operator_guidance
    assert "操作原理" in operator_guidance
    assert "source_refs" not in operator_guidance
    assert "对应手册章节" not in operator_guidance


def test_delayed_host_mount_cannot_leave_the_workbench_body_blank():
    source = ASSET.read_text(encoding="utf-8")
    assert "BUG-8093-ABC33-OVERVIEW-ENTRY-20260811" in source
    assert "data=d;render()" in source
    assert "data?render():renderState" in source
    assert "abc33-state-message" in source


def test_overview_entry_is_embedded_and_overlay_remains_open_after_mount_observer_runs():
    source = ASSET.read_text(encoding="utf-8")
    assert "document.querySelector('.overview-furnace-panel-v12 > .panel-head')" in source
    assert "overviewHead.appendChild(entry)" in source
    assert "abc33-entry-overview" in source
    assert "root.style.display=panelOpen?'block':'none'" in source
    assert "panelOpen=true" in source
    assert "abc33-entry-fallback" not in source


def test_severe_event_cross_confirmation_banner_is_not_rendered_on_8093():
    source = ASSET.read_text(encoding="utf-8")
    assert "window.location.port!=='8093'&&d.event_confirmation_summary" in source


def test_operator_metric_table_shows_chinese_labels_without_internal_keys():
    source = ASSET.read_text(encoding="utf-8")
    assert "function metricLabel(m)" in source
    assert "TFT:'理论燃烧温度'" in source
    assert "T_blast:'热风温度'" in source
    assert "Hopper_weight:'料罐重量'" in source
    assert "Hopper_weight_set:'料罐重量设定'" in source
    assert "P_N2:'氮气压力'" in source
    assert "Q_N2:'氮气流量'" in source
    assert "<b>'+escapeHtml(metricLabel(m))+'</b></td>" in source
    assert "<small>'+escapeHtml(m.variable_name||'')+'</small>" not in source


def test_review_groups_are_deduplicated_in_priority_order_before_rendering():
    source = ASSET.read_text(encoding="utf-8")
    assert "function disjointReviewGroups(review)" in source
    assert "seen.has(key)" in source
    assert "main:take(review.main_metrics)" in source
    assert "body:take(review.body_metrics)" in source
    assert "cooling:take(review.cooling_metrics)" in source
    assert "other:take(review.other_metrics)" in source
    assert "metricBlock('最重要复核点',groups.main" in source
    assert "metricBlock('其余炉壳温度点位',groups.body" in source
    assert "metricBlock('其余冷却系统点位',groups.cooling" in source


def test_metric_semantics_use_full_width_vertical_rows_without_horizontal_scroll():
    source = ASSET.read_text(encoding="utf-8")
    assert ".abc33-detail-body{max-height:calc(100vh - 105px);padding:16px;overflow-y:auto;overflow-x:hidden" in source
    assert ".abc33-metric-scroll{overflow:visible;max-height:none;width:100%}" in source
    assert ".abc33-metric-table{width:100%;min-width:0;table-layout:fixed" in source
    assert "min-width:1120px" not in source
    assert "abc33-metric-semantic-row" in source
    assert "colspan=\"6\"" in source
    assert "<b class=\"abc33-semantic-label\">实际变化语义</b>" in source
    assert "data-label=\"15 / 30 / 60分钟变化\"" in source
    assert ".abc33-semantic{min-width:0;max-width:100%" in source

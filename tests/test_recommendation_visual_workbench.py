from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
PATCHER = ROOT / "tools" / "patch_8094_multi_condition_review.py"


def _html() -> str:
    return HTML.read_text(encoding="utf-8")


def _visual_block() -> str:
    source = _html()
    start = source.index("/* REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806")
    end = source.index("OptimizationTab = OptimizationVisualWorkbenchLayout;", start)
    return source[start:end]


def test_visual_workbench_is_the_active_optimization_page() -> None:
    source = _html()
    assert 'data-requirement="REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806"' in source
    assert "OptimizationTab = OptimizationVisualWorkbenchLayout;" in source
    assert "bf-visual-recommendation-page" in source
    assert "overflow-y:auto!important" in source
    assert "grid-template-rows:auto auto!important" in source


def test_core_evidence_center_contains_exactly_the_requested_19_variables() -> None:
    block = _visual_block()
    groups = re.search(
        r"const BF_CORE_EVIDENCE_GROUPS_V2 = \[(.*?)\n    \];",
        block,
        re.DOTALL,
    )
    assert groups is not None
    arrays = re.findall(r"ids: \[([^\]]+)\]", groups.group(1))
    ids = [value for array in arrays for value in re.findall(r"'([^']+)'", array)]
    expected = {
        "P_top_gas_A",
        "P_top_gas_B",
        "P_top_gas_C",
        "P_top_gas_D",
        "P_top",
        "T_top_A",
        "T_top_B",
        "T_top_C",
        "T_top_D",
        "T_top",
        "Q_blast",
        "P_blast_cold",
        "P_blast",
        "T_blast",
        "PI",
        "DP_total",
        "DP_upper",
        "DP_lower",
        "GasUtil",
    }
    assert len(ids) == 19
    assert len(set(ids)) == 19
    assert set(ids) == expected


def test_primary_evidence_keeps_rule_specific_four_and_restores_sparklines() -> None:
    source = _html()
    block = _visual_block()
    for label in ("normal", "lowline", "edge", "center", "channel", "cold", "hot", "column"):
        assert re.search(rf"{label}: \[[^\]]+(?:,[^\]]+){{3}}\]", block)
    assert 'data-primary-evidence-id={m.id}' in source
    assert 'className="cockpit-spark bf-primary-evidence-spark"' in source
    assert "option={sparkOption(buf, m.id)}" in source


def test_action_drawer_preserves_all_audit_fields_and_statuses() -> None:
    source = _html()
    for status in ("eligible", "blocked", "needs_data", "manual_confirm"):
        assert status in source
    for label in (
        "原文章节",
        "触发证据",
        "前置条件",
        "阻断原因",
        "调剂幅度",
        "当前值与目标值",
        "限值快照",
        "生效时刻",
        "执行顺序",
        "缺失数据",
        "观察窗口",
        "审批要求",
    ):
        assert label in source
    block = _visual_block()
    assert "BFWorkbenchDrawerV2" in block
    assert "BFActionAuditDetails" in block
    assert "只读，不执行生产写入" in block


def test_main_operation_area_only_opens_pressure_and_pci_setpoint() -> None:
    block = _visual_block()
    controls = re.search(r"const BF_FOREMAN_CONTROLS_V2 = \[(.*?)\];", block)
    assert controls is not None
    ids = re.findall(r"id: '([^']+)'", controls.group(1))
    assert ids == ["P_blast_cold", "PCI_set"]
    assert 'data-control-variable={control.id}' in block
    assert "冷风压力与喷煤设定建议" in block
    assert "30天Q3或400 kPa硬下限限幅" in block
    assert "下个整点生效" in block


def test_missing_8768_bundle_never_reuses_legacy_frontend_advice() -> None:
    source = _html()
    bundle_start = source.index("function bfRecommendationBundleView")
    bundle_end = source.index("function bfConditionDiagnosis", bundle_start)
    bundle_function = source[bundle_start:bundle_end]
    assert "activeRecommendation" not in bundle_function
    assert "legacy-summary" not in bundle_function
    assert "foreman-dual-control-unavailable" in bundle_function
    assert "已禁用旧前端启发式回退" in source


def test_19_variable_charts_are_lazy_and_support_detail_and_group_comparison() -> None:
    block = _visual_block()
    assert "useState(false)" in block
    assert "{expanded && <div className=\"bf-core-evidence-content-v2\"" in block
    assert "CoreMetricDetailModalV1" in block
    assert "BFCoreEvidenceCompareModalV2" in block
    assert "30分钟" in block
    assert "2小时" in block
    assert "8小时" in block


def test_8094_visual_block_does_not_require_the_8093_only_realtime_hook() -> None:
    block = _visual_block()
    center = block[block.index("function BFCoreEvidenceCenterV2Base"):]
    assert "useCoreMetricRealtime8093()" not in center
    assert "coreMetricCurrent8093(" not in block
    assert "bfCoreEvidenceCurrentV2" in block
    assert "BF_HAS_INTEGRATED_PRIMARY_CHARTS_V2" in block
    assert "BFPrimaryEvidenceStripV2" in block
    assert "window.CoreMetricDetailModalV1" in block


def test_model_review_auto_runs_only_for_current_active_condition() -> None:
    block = _visual_block()
    assert "condition.label === d.label && condition.scope === 'active'" in block
    assert "if (autoReview) request(false)" in block
    assert "立即复核" in block
    assert "不改写规则和安全门禁" in _html()


def test_8094_patcher_targets_the_new_visual_workbench_assignment() -> None:
    patcher = PATCHER.read_text(encoding="utf-8")
    assert 'VISUAL_REQ_MARKER = "REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806"' in patcher
    assert 'FEATURE_END = "    OptimizationTab = OptimizationVisualWorkbenchLayout;"' in patcher
    assert "PREVIOUS_FEATURE_END" in patcher

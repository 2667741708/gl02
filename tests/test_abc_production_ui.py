from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "高炉前端数据" / "assets" / "abc-furnace-rules-production.js"


def test_abc_workbench_is_mounted_prominently_in_decision_page_and_has_real_detail_dialog():
    source = ASSET.read_text(encoding="utf-8")
    assert "AI决策中心 · 33项炉况研判" in source
    assert "document.querySelector('.bf-recommendation-summary-v2')" in source
    assert "anchor.insertAdjacentElement('afterend',root)" in source
    assert "[['ALL','全部33项'],['A','A类9项'],['B','B类13项'],['C','C类11项']]" in source
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
    for internal_name in ("formula_terms", "normalized_value", "contribution", "g_H", "g_L", "g_A"):
        assert internal_name not in source


def test_delayed_host_mount_cannot_leave_the_workbench_body_blank():
    source = ASSET.read_text(encoding="utf-8")
    assert "BUG-ABC33-INLINE-RENDER-RACE-20260808-R4" in source
    assert "data=d;render()" in source
    assert "data?render():renderState" in source
    assert "abc33-state-message" in source

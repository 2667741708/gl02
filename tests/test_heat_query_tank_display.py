from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_8093_heat_query_displays_assigned_tank_list_without_forced_segment_join() -> None:
    asset = (ROOT / "高炉前端数据" / "assets" / "bf-heat-performance-quality-8093-query-v2.js").read_text(encoding="utf-8")
    assert "const tankList = item =>" in asset
    assert "tank_no" in asset
    assert "\\u5DF2\\u6D3E\\u7F50\\u53F7" in asset
    assert "出铁段/罐次明细" in asset
    assert "不会把样本强行一一绑定到某个罐" in asset

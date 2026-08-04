from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"
ASSET = ROOT / "高炉前端数据" / "assets" / "bf-heat-dashboard-link.js"
HEAT_PAGE = ROOT / "db_dashboard" / "heat.html"


def test_8094_source_keeps_heat_dashboard_link_disabled_by_default() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert 'src="assets/bf-heat-dashboard-link.js?v=20260726-r1"' not in source
    assert 'data-url="http://127.0.0.1:8890/heat"' not in source


def test_link_asset_has_safe_external_navigation_and_mobile_layout() -> None:
    asset = ASSET.read_text(encoding="utf-8")
    assert "REQ-8094-HEAT-DASHBOARD-LINK-20260726" in asset
    assert "window.__BF_HEAT_DASHBOARD_URL__" in asset
    assert 'link.target = "_blank"' in asset
    assert 'link.rel = "noopener noreferrer"' in asset
    assert 'dataset.testid = "heat-dashboard-link"' in asset
    assert "grid-template-columns:repeat(6" in asset
    assert "@media(max-width:600px)" in asset


def test_heat_dashboard_does_not_expose_8094_jump_by_default() -> None:
    page = HEAT_PAGE.read_text(encoding="utf-8")
    assert "返回高炉工作台" not in page
    assert "http://10.30.220.12:8094/?ws_port=8768#overview" not in page

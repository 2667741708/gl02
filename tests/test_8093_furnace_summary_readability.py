from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOYER = ROOT / "tools" / "remote_deploy_8093_furnace_summary_readability.py"
CSS = ROOT / "高炉前端数据" / "assets" / "bf3d-furnace-summary-readability-8093.css"
PAGE = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


def load_deployer():
    spec = importlib.util.spec_from_file_location("summary_readability_deployer", DEPLOYER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_css_is_scoped_to_seven_follow_model_cards_only() -> None:
    text = CSS.read_text(encoding="utf-8")
    assert "REQ-BF3D-8093-FURNACE-SUMMARY-READABILITY-20260802" in text
    assert ".layered-cad-stage .furnace-layer-callouts.follow-model .furnace-layer-card" in text
    assert ".furnace-billboard" not in text
    assert ".core-group-row" not in text


def test_css_enlarges_cards_and_never_hides_units() -> None:
    text = CSS.read_text(encoding="utf-8")
    for marker in (
        "width: clamp(208px, 23%, 228px) !important",
        "width: 198px !important",
        "width: 190px !important",
        "grid-template-columns: minmax(78px, 1fr) max-content max-content !important",
        "overflow: visible !important",
        "text-overflow: clip !important",
        "display: inline !important",
    ):
        assert marker in text


def test_local_page_links_cache_busted_asset_once() -> None:
    text = PAGE.read_text(encoding="utf-8")
    assert text.count("REQ-BF3D-8093-FURNACE-SUMMARY-READABILITY-20260802") == 1
    assert text.count("bf3d-furnace-summary-readability-8093.css") == 1
    assert "bf3d-furnace-summary-readability-8093.css?v=20260802-expanded7-r2" in text


def test_patcher_is_idempotent() -> None:
    module = load_deployer()
    original = "<html><head><title>x</title></head><body></body></html>"
    once = module.patch_page(original)
    twice = module.patch_page(once)
    assert once == twice
    assert once.count(module.REQ_ID) == 1
    assert once.count(module.CSS_ASSET) == 1


def test_css_validator_rejects_billboard_scope() -> None:
    module = load_deployer()
    valid = CSS.read_text(encoding="utf-8")
    module.validate_css(valid)
    try:
        module.validate_css(valid + "\n.furnace-billboard{font-size:20px}\n")
    except RuntimeError as error:
        assert "must not target" in str(error)
    else:
        raise AssertionError("Billboard selector must be rejected")

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "高炉前端数据" / "frontend_dashboard_v3.server.html"


def test_blocked_and_needs_data_null_targets_are_not_rendered_as_zero():
    text = HTML.read_text(encoding="utf-8")
    assert "REQ-FOREMAN-DUAL-CONTROL-ZERO-GUARD-20260807" in text
    assert "bfFiniteControlNumberV3(action?.recommended_target)" in text
    assert "bfFiniteControlNumberV3(action?.recommended_change)" in text
    assert "const current = Number(action?.current_value), target = Number(action?.recommended_target)" not in text


def test_zero_is_still_a_valid_explicit_manual_stop_target():
    text = HTML.read_text(encoding="utf-8")
    assert "if (value === null || value === undefined || value === '') return null" in text

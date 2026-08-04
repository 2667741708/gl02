from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEAT_HTML = ROOT / "db_dashboard" / "heat.html"


def test_si_distribution_frontend_contract() -> None:
    text = HEAT_HTML.read_text(encoding="utf-8")
    for token in (
        "REQ-HEAT-SI-DISTRIBUTION-20260726",
        "全部Si样本",
        "Si中位数",
        "Si最小—最大",
        "hot_metal_si_summary",
        "siSummaryPanel",
    ):
        assert token in text
    assert "latest_hot_metal||{}).Si" not in text


def test_detail_request_race_is_guarded() -> None:
    text = HEAT_HTML.read_text(encoding="utf-8")
    assert "detailRequestId: 0" in text
    assert "const requestId = ++state.detailRequestId" in text
    assert "requestId !== state.detailRequestId || state.selected !== meltno" in text

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "db_dashboard" / "heat_data_explorer.js").read_text(
    encoding="utf-8"
)
HTML = (ROOT / "db_dashboard" / "heat.html").read_text(encoding="utf-8")


def test_explorer_has_real_query_and_state_controls() -> None:
    for token in (
        "多源数据查询工作台",
        'type="datetime-local"',
        "查询数据",
        "正在执行只读查询",
        "该数据集在当前条件下没有记录",
        "数据查询失败",
        "重试",
        "导出当前页CSV",
        "导出当前页XLSX",
        "上一页",
        "下一页",
        "刷新数据源状态",
    ):
        assert token in SCRIPT


def test_explorer_exposes_source_boundaries_without_credentials() -> None:
    for token in ("pSpace", "IMES Web", "Vastbase", "PostgreSQL GL02"):
        assert token in SCRIPT
    lowered = SCRIPT.lower()
    assert "imes_web_password" not in lowered
    assert "pspace_password" not in lowered
    assert "gl02_pgpassword" not in lowered
    assert "/api/data-source-health" in SCRIPT
    assert "/api/data-query" in SCRIPT
    assert "/api/imes-web/login" in SCRIPT


def test_heat_page_loads_explorer() -> None:
    assert '<script src="/heat-data-explorer.js"></script>' in HTML


def test_mobile_query_grid_cannot_expand_the_page_width() -> None:
    assert ".data-query-form>*{min-width:0}" in SCRIPT
    assert "grid-template-columns:minmax(0,1fr)" in SCRIPT
    assert ".data-query-form input,.data-query-form select" in SCRIPT
    assert "max-width:100%;min-width:0" in SCRIPT

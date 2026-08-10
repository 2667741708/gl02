from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_heat_quality_query_contract_covers_heat_tank_and_sample_filters() -> None:
    store = (ROOT / "高炉前端数据" / "智能助手" / "backend" / "heat_performance_quality.py").read_text(encoding="utf-8")
    proxy = (ROOT / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py").read_text(encoding="utf-8")
    asset = (ROOT / "高炉前端数据" / "assets" / "bf-heat-performance-quality-8093-query-v2.js").read_text(encoding="utf-8")

    assert "query: str | None = None" in store
    assert "sample_details::text ILIKE" in store
    assert "output_details::text ILIKE" in store
    assert '"filters"' in store
    assert 'params.get("q")' in proxy
    assert 'date_from' in proxy
    assert 'has_samples' in proxy
    assert 'include_future' in proxy
    assert 'data-filter="q"' in asset
    assert 'data-filter="hasSamples"' in asset
    assert "output_details" in asset
    assert "原始试样" in asset
    assert "罐号未提供" in asset
    assert "REFRESH_MS = 5000" in asset

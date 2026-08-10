from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_heat_sync_uses_exact_batch_to_thankno_mapping() -> None:
    source = (ROOT / "db_dashboard" / "heat_service.py").read_text(encoding="utf-8")
    assert "public.v_qpes_mat_final" in source
    assert "DISTINCT ON (batchno)" in source
    assert "CAST(thankno AS text) AS tank_no" in source
    assert 'row["tank_no"] = tank_numbers.get' in source
    assert "sample_no" in source

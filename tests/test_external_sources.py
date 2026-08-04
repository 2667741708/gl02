from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "db_dashboard"))

import external_sources  # noqa: E402


def test_catalog_contains_every_confirmed_read_only_source() -> None:
    catalog = external_sources.full_catalog()
    assert catalog["ok"] is True
    assert catalog["policy"] == "read_only_allowlist"
    assert catalog["dataset_count"] == 31
    assert len(catalog["sources"]["vastbase_operations"]) == 6
    assert len(catalog["sources"]["vastbase_laboratory"]) == 5
    assert len(catalog["sources"]["imes_web"]) == 12
    assert len(catalog["sources"]["postgres_gl02"]) == 6
    assert len(catalog["sources"]["pspace"]) == 2
    rendered = repr(catalog).lower()
    assert "password" not in rendered


def test_unknown_dataset_is_rejected_before_any_connection() -> None:
    with pytest.raises(KeyError):
        external_sources.query_dataset(
            "raw.sql",
            pg_connect=lambda: None,
        )


def test_invalid_time_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="start must be earlier than end"):
        external_sources.query_dataset(
            "vastbase.heat_master",
            pg_connect=lambda: None,
            start="2026-07-27T10:00",
            end="2026-07-27T09:00",
        )


def test_pspace_aggregate_is_an_allowlist() -> None:
    assert "PS_HIS_AVERAGE" in external_sources.PSPACE_HISTORY_AGGREGATES
    assert "PS_HIS_MAXIMUM" in external_sources.PSPACE_HISTORY_AGGREGATES
    assert "PS_HIS_DROP_TABLE" not in external_sources.PSPACE_HISTORY_AGGREGATES


def test_formal_hot_metal_contract_uses_exact_keys() -> None:
    spec = external_sources.DATASETS["vastbase.formal_hot_metal"]
    assert spec.lineage == "exact_heatno_batchno"
    assert spec.meltno_field == "official_meltno"
    assert "t_qpes_inner_batch" in spec.relation
    assert "inner_batch_insp_bb" in spec.relation

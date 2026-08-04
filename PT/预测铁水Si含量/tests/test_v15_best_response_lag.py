from __future__ import annotations

import numpy as np
import pandas as pd

from si_semantic_engine.train_v15 import (
    response_lag_descriptor,
    select_best_response_lags,
)


def test_response_lag_descriptor_preserves_variable_and_band() -> None:
    parsed = response_lag_descriptor(
        "lagmoment__P_top_gas_A__m30_60__std"
    )
    assert parsed is not None
    assert parsed["variable"] == "P_top_gas_A"
    assert parsed["family"] == "band_volatility"
    assert parsed["response_center_minutes"] == 45.0


def test_selector_uses_one_best_lag_per_variable_family() -> None:
    residual = pd.Series(np.arange(20, dtype=float))
    train = pd.DataFrame(
        {
            "lagband__TFT__m0_30__mean": np.sin(residual),
            "lagband__TFT__m30_60__mean": residual,
            "lagmoment__TFT__m0_30__std": residual[::-1].to_numpy(),
            "lagmoment__TFT__m30_60__std": np.ones(20),
        }
    )
    selected, audit = select_best_response_lags(
        train, residual, list(train.columns)
    )
    assert "lagband__TFT__m30_60__mean" in selected
    assert "lagmoment__TFT__m0_30__std" in selected
    assert len(audit) == 2
    assert len({(item["variable"], item["family"]) for item in audit}) == 2


def test_selector_rejects_non_lag_and_low_coverage_features() -> None:
    residual = pd.Series(np.arange(10, dtype=float))
    train = pd.DataFrame(
        {
            "Si_representative": residual,
            "lagband__PI__m0_30__coverage_ratio": 1.0,
            "lagband__PI__m0_30__mean": [
                1.0,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
            ],
        }
    )
    selected, audit = select_best_response_lags(
        train, residual, list(train.columns)
    )
    assert selected == []
    assert audit == []

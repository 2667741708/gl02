from __future__ import annotations

import numpy as np
import pandas as pd

from si_semantic_engine.train_v16 import select_importance_for_target


def test_importance_selector_uses_explicit_residual_target() -> None:
    rng = np.random.default_rng(20260727)
    rows = 240
    baseline_signal = rng.normal(size=rows)
    residual_signal = rng.normal(size=rows)
    frame = pd.DataFrame(
        {
            "baseline_feature": baseline_signal,
            "residual_feature": residual_signal,
            "noise_feature": rng.normal(size=rows),
        }
    )
    selected, audit = select_importance_for_target(
        frame,
        pd.Series(residual_signal),
        list(frame.columns),
        top_k=1,
        n_estimators=80,
    )
    assert selected == ["residual_feature"]
    assert audit[0]["importance"] > 0.5


def test_importance_selector_rejects_constant_and_sparse() -> None:
    frame = pd.DataFrame(
        {
            "usable": np.arange(20, dtype=float),
            "constant": 1.0,
            "sparse": [1.0, 2.0] + [np.nan] * 18,
        }
    )
    selected, _ = select_importance_for_target(
        frame,
        pd.Series(np.arange(20, dtype=float)),
        list(frame.columns),
        top_k=10,
        n_estimators=40,
    )
    assert selected == ["usable"]

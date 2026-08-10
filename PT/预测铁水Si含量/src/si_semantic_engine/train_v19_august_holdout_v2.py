"""Compatibility wrapper fixing pandas Series period conversion."""
from __future__ import annotations

import pandas as pd

from . import train_v19_august_holdout as impl


def _rolling_folds(frame: pd.DataFrame, july_end: pd.Timestamp):
    cutoff = pd.to_datetime(frame["prediction_cutoff_ts"])
    months = cutoff.dt.to_period("M").astype(str)
    july_eval = (cutoff >= pd.Timestamp("2026-07-01")) & (cutoff <= july_end)
    return {
        "2026-04": (cutoff < pd.Timestamp("2026-04-01"), months == "2026-04"),
        "2026-05": (cutoff < pd.Timestamp("2026-05-01"), months == "2026-05"),
        "2026-06": (cutoff < pd.Timestamp("2026-06-01"), months == "2026-06"),
        "2026-07_validation": (cutoff < pd.Timestamp("2026-07-01"), july_eval),
    }


impl._rolling_folds = _rolling_folds


if __name__ == "__main__":
    raise SystemExit(impl.main())

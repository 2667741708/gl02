# -*- coding: utf-8 -*-
"""基于现场实际字段的派生特征计算工具。"""

from __future__ import annotations

from typing import Iterable, List, Optional

import numpy as np
import pandas as pd

from features.rolling_stats import linear_slope


def _available_series(series_list: Iterable[Optional[pd.Series]]) -> List[pd.Series]:
    available: List[pd.Series] = []
    for series in series_list:
        if isinstance(series, pd.Series) and not series.dropna().empty:
            available.append(series)
    return available


def calculate_mean_available(series_list: Iterable[Optional[pd.Series]]) -> float:
    available = _available_series(series_list)
    if not available:
        return 0.0
    values = [float(series.dropna().iloc[-1]) for series in available if not series.dropna().empty]
    if not values:
        return 0.0
    return float(np.mean(values))


def calculate_mean_series(series_list: Iterable[Optional[pd.Series]]) -> Optional[pd.Series]:
    available = _available_series(series_list)
    if not available:
        return None
    return pd.concat(available, axis=1).mean(axis=1)


def calculate_max_available(series_list: Iterable[Optional[pd.Series]]) -> float:
    available = _available_series(series_list)
    if not available:
        return 0.0
    values = [float(series.dropna().iloc[-1]) for series in available if not series.dropna().empty]
    if not values:
        return 0.0
    return float(np.max(values))


def calculate_current_range(series_list: Iterable[Optional[pd.Series]]) -> float:
    available = _available_series(series_list)
    values = [float(series.dropna().iloc[-1]) for series in available if not series.dropna().empty]
    if len(values) < 2:
        return 0.0
    return float(np.max(values) - np.min(values))


def calculate_current_std(series_list: Iterable[Optional[pd.Series]]) -> float:
    available = _available_series(series_list)
    values = [float(series.dropna().iloc[-1]) for series in available if not series.dropna().empty]
    if len(values) < 2:
        return 0.0
    return float(np.std(values, ddof=1))


def calculate_hot_deviation(series_list: Iterable[Optional[pd.Series]], eps: float = 1e-6) -> float:
    available = _available_series(series_list)
    values = np.array([float(series.dropna().iloc[-1]) for series in available if not series.dropna().empty])
    if len(values) < 4:
        return 0.0
    q75, q25 = np.percentile(values, [75, 25])
    iqr = q75 - q25
    return float((np.max(values) - np.median(values)) / (iqr + eps))


def calculate_rolling_cv(series_list: Iterable[Optional[pd.Series]], window: int = 15) -> float:
    available = _available_series(series_list)
    if len(available) < 2:
        return 0.0
    frame = pd.concat([series.tail(window).reset_index(drop=True) for series in available], axis=1)
    if frame.empty:
        return 0.0
    row_means = frame.mean(axis=1)
    row_stds = frame.std(axis=1, ddof=1)
    cv = (row_stds / row_means.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).dropna()
    if cv.empty:
        return 0.0
    return float(cv.mean())


def calculate_rolling_range(series_list: Iterable[Optional[pd.Series]], window: int = 15) -> float:
    available = _available_series(series_list)
    if len(available) < 2:
        return 0.0
    frame = pd.concat([series.tail(window).reset_index(drop=True) for series in available], axis=1)
    if frame.empty:
        return 0.0
    row_ranges = frame.max(axis=1) - frame.min(axis=1)
    row_ranges = row_ranges.dropna()
    if row_ranges.empty:
        return 0.0
    return float(row_ranges.max())


def calculate_abs_diff_latest(left: Optional[pd.Series], right: Optional[pd.Series]) -> float:
    if left is None or right is None:
        return 0.0
    left_valid = left.dropna()
    right_valid = right.dropna()
    if left_valid.empty or right_valid.empty:
        return 0.0
    return float(abs(left_valid.iloc[-1] - right_valid.iloc[-1]))


def calculate_priority_or_mean(
    primary: Optional[pd.Series],
    secondary_a: Optional[pd.Series],
    secondary_b: Optional[pd.Series],
) -> Optional[pd.Series]:
    if primary is None and secondary_a is None and secondary_b is None:
        return None

    index = None
    for series in (primary, secondary_a, secondary_b):
        if isinstance(series, pd.Series):
            index = series.index
            break
    if index is None:
        return None

    fallback = None
    if isinstance(secondary_a, pd.Series) and isinstance(secondary_b, pd.Series):
        fallback = pd.concat([secondary_a, secondary_b], axis=1).mean(axis=1)
    elif isinstance(secondary_a, pd.Series):
        fallback = secondary_a.copy()
    elif isinstance(secondary_b, pd.Series):
        fallback = secondary_b.copy()

    if isinstance(primary, pd.Series):
        effective = primary.copy()
        if fallback is not None:
            effective = effective.combine_first(fallback)
        return effective
    return fallback


def calculate_l_slope(series: Optional[pd.Series], window: int = 20) -> float:
    if series is None:
        return 0.0
    valid = series.dropna()
    if len(valid) < 2:
        return 0.0
    return float(linear_slope(valid, window))


def calculate_stall_flag(
    series: Optional[pd.Series],
    window: int = 20,
    max_abs_slope_m_per_min: float = 0.01,
) -> bool:
    if series is None:
        return False
    valid = series.dropna()
    if len(valid) < 5:
        return False
    slope = calculate_l_slope(valid, window=window)
    return bool(abs(slope) <= max_abs_slope_m_per_min)


def calculate_deltal(l_current: Optional[float], l_target: float = 1.5) -> float:
    if l_current is None:
        return 0.0
    return max(0.0, float(l_current) - float(l_target))


def calculate_drop_batch(l_series: Optional[pd.Series], window: int = 10) -> float:
    if l_series is None or len(l_series) < 2:
        return 0.0
    diffs = l_series.tail(window).diff().dropna()
    drops = diffs[diffs > 0]
    if drops.empty:
        return 0.0
    return float(drops.max())

# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import pandas as pd
import yaml

from features.baseline import z_level, z_trend, z_vol
from features.derived import (
    calculate_abs_diff_latest,
    calculate_current_range,
    calculate_current_std,
    calculate_deltal,
    calculate_drop_batch,
    calculate_hot_deviation,
    calculate_l_slope,
    calculate_max_available,
    calculate_mean_available,
    calculate_mean_series,
    calculate_priority_or_mean,
    calculate_rolling_cv,
    calculate_rolling_range,
    calculate_stall_flag,
)
from features.event_features import extract_event_flags
from features.rolling_stats import count_spikes, linear_slope, rolling_mean, rolling_std


class FeatureAggregator:
    def __init__(self, baseline_config_path):
        if not os.path.exists(baseline_config_path):
            raise Exception("Baseline config not found at {}".format(baseline_config_path))
        with open(baseline_config_path, "r", encoding="utf-8") as f:
            self.baseline_meta = yaml.safe_load(f) or {}

    def _first_baseline(self, *names):
        for name in names:
            meta = self.baseline_meta.get(name, {})
            median_ref = meta.get("median_ref")
            iqr_ref = meta.get("iqr_ref")
            if median_ref is not None and iqr_ref not in (None, 0):
                return median_ref, iqr_ref
        return None, None

    def _mean_baseline(self, names):
        medians = []
        iqrs = []
        for name in names:
            meta = self.baseline_meta.get(name, {})
            median_ref = meta.get("median_ref")
            iqr_ref = meta.get("iqr_ref")
            if median_ref is None or iqr_ref in (None, 0):
                continue
            medians.append(float(median_ref))
            iqrs.append(float(iqr_ref))
        if not medians or not iqrs:
            return None, None
        return sum(medians) / len(medians), sum(iqrs) / len(iqrs)

    def _add_level_and_vol(self, features, df, column, feature_name=None, baseline_names=None):
        if column not in df.columns:
            return
        series = df[column]
        self._add_series_level_and_vol(
            features,
            series,
            feature_name or column,
            baseline_names or [feature_name or column],
        )

    def _add_series_level_and_vol(self, features, series, feature_name, baseline_names):
        if series is None or len(series.dropna()) == 0:
            return
        median_ref, iqr_ref = self._first_baseline(*baseline_names)
        if median_ref is None or iqr_ref in (None, 0):
            return
        features["z60_" + feature_name] = z_level(rolling_mean(series, 60), median_ref, iqr_ref)
        features["zstd_" + feature_name] = z_vol(rolling_std(series, 15), iqr_ref)

    def _resolved_top_temperature(self, df):
        top_multi = [df[c] for c in ["T_top_A", "T_top_B", "T_top_C", "T_top_D"] if c in df.columns]
        top_mean_4pt = None
        if top_multi:
            top_mean_4pt = pd.concat(top_multi, axis=1).mean(axis=1)
        if "T_top" in df.columns and top_mean_4pt is not None:
            return df["T_top"].combine_first(top_mean_4pt)
        if "T_top" in df.columns:
            return df["T_top"]
        return top_mean_4pt

    def _add_body_temperature_features(self, features, df):
        layers = range(7, 17)
        sectors = "ABCDEFGH"
        layer_series = {}
        layer_columns = {}
        all_columns = []

        for layer in layers:
            columns = [f"T_body_L{layer}_{sector}" for sector in sectors if f"T_body_L{layer}_{sector}" in df.columns]
            if not columns:
                continue
            series_list = [df[column] for column in columns]
            layer_columns[layer] = columns
            all_columns.extend(columns)
            features[f"T_body_mean_L{layer}"] = calculate_mean_available(series_list)
            features[f"T_body_circ_std_L{layer}"] = calculate_current_std(series_list)
            mean_val = features[f"T_body_mean_L{layer}"]
            features[f"T_body_circ_cv_L{layer}"] = (
                features[f"T_body_circ_std_L{layer}"] / mean_val if mean_val else 0.0
            )
            features[f"HotDev_L{layer}"] = calculate_hot_deviation(series_list)
            layer_mean_series = calculate_mean_series(series_list)
            if layer_mean_series is not None:
                layer_series[layer] = layer_mean_series
                self._add_series_level_and_vol(features, layer_mean_series, f"T_body_L{layer}", columns)

        sections = {
            "lower": [7, 8, 9],
            "middle": [10, 11, 12, 13],
            "upper": [14, 15, 16],
        }
        section_series = {}
        for section, section_layers in sections.items():
            series_list = [layer_series[layer] for layer in section_layers if layer in layer_series]
            baseline_names = [
                column
                for layer in section_layers
                for column in layer_columns.get(layer, [])
            ]
            section_mean = calculate_mean_series(series_list)
            if section_mean is None:
                continue
            section_series[section] = section_mean
            latest = section_mean.dropna()
            if not latest.empty:
                features[f"T_body_{section}"] = float(latest.iloc[-1])
            self._add_series_level_and_vol(features, section_mean, f"T_body_{section}", baseline_names)

        if "lower" in section_series and "upper" in section_series:
            lower = section_series["lower"].dropna()
            upper = section_series["upper"].dropna()
            if not lower.empty and not upper.empty:
                features["G_body_lower_upper"] = float(lower.iloc[-1] - upper.iloc[-1])

        sector_bias = {}
        for sector in sectors:
            deviations = []
            for layer, mean_series in layer_series.items():
                column = f"T_body_L{layer}_{sector}"
                if column not in df.columns:
                    continue
                latest_col = df[column].dropna()
                latest_mean = mean_series.dropna()
                if latest_col.empty or latest_mean.empty:
                    continue
                deviations.append(float(latest_col.iloc[-1] - latest_mean.iloc[-1]))
            if deviations:
                sector_bias[sector] = float(sum(deviations) / len(deviations))
                features[f"SectorBias_{sector}"] = sector_bias[sector]
        if sector_bias:
            hot_sector, hot_score = max(sector_bias.items(), key=lambda item: item[1])
            cold_sector, cold_score = min(sector_bias.items(), key=lambda item: item[1])
            features["HotSector"] = hot_sector
            features["ColdSector"] = cold_sector
            features["HotSectorScore"] = float(hot_score)
            features["ColdSectorScore"] = float(cold_score)

        hot_spot_level = 0.0
        hot_spot_jump = 0.0
        hot_spot_name = None
        for column in all_columns:
            series = df[column]
            median_ref, iqr_ref = self._first_baseline(column)
            if median_ref is None or iqr_ref in (None, 0) or series.dropna().empty:
                continue
            level = z_level(rolling_mean(series, 60), median_ref, iqr_ref)
            jump = z_trend(linear_slope(series, 15), 15, iqr_ref)
            if level > hot_spot_level:
                hot_spot_level = float(level)
                hot_spot_name = column
            if jump > hot_spot_jump:
                hot_spot_jump = float(jump)
        if all_columns:
            features["HotSpotLevel"] = hot_spot_level
            features["HotSpotJump"] = hot_spot_jump
            if hot_spot_name:
                features["HotSpotName"] = hot_spot_name

    def aggregate(self, df):
        features = {}
        if df is None or len(df) == 0:
            return features

        self._add_level_and_vol(features, df, "P_blast", baseline_names=["P_hot_blast", "P_blast"])
        self._add_level_and_vol(features, df, "P_blast_cold", baseline_names=["P_blast"])
        self._add_level_and_vol(features, df, "Q_blast")
        self._add_level_and_vol(features, df, "P_top")
        self._add_level_and_vol(features, df, "DP_upper")
        self._add_level_and_vol(features, df, "DP_lower")
        self._add_level_and_vol(features, df, "DP_total")
        self._add_level_and_vol(features, df, "T_blast")
        self._add_level_and_vol(features, df, "PCI_rate")
        self._add_level_and_vol(features, df, "Q_O2")
        self._add_level_and_vol(features, df, "PI")
        self._add_level_and_vol(features, df, "GasUtil")
        self._add_body_temperature_features(features, df)

        top_temp_series = self._resolved_top_temperature(df)
        if top_temp_series is not None:
            median_ref, iqr_ref = self._first_baseline("T_top")
            if median_ref is not None and iqr_ref not in (None, 0):
                features["z30_T_top_slope"] = z_trend(linear_slope(top_temp_series, 30), 30, iqr_ref)
            features["T_top_effective"] = float(top_temp_series.dropna().iloc[-1]) if not top_temp_series.dropna().empty else 0.0

        top_temp_multi = [df[c] for c in ["T_top_A", "T_top_B", "T_top_C", "T_top_D"] if c in df.columns]
        if top_temp_multi:
            features["T_top_mean_4pt"] = calculate_mean_available(top_temp_multi)
            features["T_top_range_4pt"] = calculate_current_range(top_temp_multi)
            features["DispTop_15"] = calculate_rolling_cv(top_temp_multi, window=15)

        top_gas_multi = [df[c] for c in ["P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D"] if c in df.columns]
        if top_gas_multi:
            features["P_top_gas_range_15"] = calculate_rolling_range(top_gas_multi, window=15)

        l_effective_series = calculate_priority_or_mean(
            df["L"] if "L" in df.columns else None,
            df["L_south"] if "L_south" in df.columns else None,
            df["L_north"] if "L_north" in df.columns else None,
        )
        if l_effective_series is not None and not l_effective_series.dropna().empty:
            features["L_effective_series"] = l_effective_series
            features["L_series"] = l_effective_series
            l_current = float(l_effective_series.dropna().iloc[-1])
            features["L_effective"] = l_current
            features["L_current"] = l_current
            features["L_slope_20"] = calculate_l_slope(l_effective_series, window=20)
            l_normal, _ = self._first_baseline("L")
            features["DeltaL"] = calculate_deltal(l_current, l_target=l_normal or 1.5)
            features["DropBatch"] = calculate_drop_batch(l_effective_series, window=10)
            features["probe_stall_flag"] = calculate_stall_flag(l_effective_series, window=20, max_abs_slope_m_per_min=0.01)
            self._add_series_level_and_vol(features, l_effective_series, "L", ["L"])

        if "L_south" in df.columns and "L_north" in df.columns:
            features["L_diff_NS"] = calculate_abs_diff_latest(df["L_south"], df["L_north"])
        if "L" in df.columns and "L_south" in df.columns and "L_north" in df.columns:
            mechanical_mean = pd.concat([df["L_south"], df["L_north"]], axis=1).mean(axis=1)
            features["L_diff_radar_mech"] = calculate_abs_diff_latest(df["L"], mechanical_mean)

        if "P_top" in df.columns:
            features["SpikeTopP_15"] = count_spikes(df["P_top"], 15)

        taphole_series = []
        for column in ["T_taphole_1", "T_taphole_2", "T_taphole_3"]:
            if column in df.columns:
                cleaned = df[column].where(df[column] > 0)
                taphole_series.append(cleaned)
        if taphole_series:
            features["T_taphole_mean"] = calculate_mean_available(taphole_series)
            features["T_taphole_max"] = calculate_max_available(taphole_series)
            median_ref, iqr_ref = self._mean_baseline(["T_taphole_1", "T_taphole_2", "T_taphole_3"])
            if median_ref is not None and iqr_ref not in (None, 0):
                features["z_T_taphole_mean"] = z_level(features["T_taphole_mean"], median_ref, iqr_ref)
                features["z_T_taphole_max"] = z_level(features["T_taphole_max"], median_ref, iqr_ref)

        if "PCI_rate" in df.columns and not df["PCI_rate"].dropna().empty:
            features["PCI_intensity"] = float(df["PCI_rate"].dropna().iloc[-1])
        if "Q_O2" in df.columns and not df["Q_O2"].dropna().empty:
            features["O2_intensity"] = float(df["Q_O2"].dropna().iloc[-1])

        features.update(extract_event_flags(df, features=features))
        return features

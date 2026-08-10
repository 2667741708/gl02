"""Validate a blast-furnace TFT empirical formula against aligned PG minute data.

Formula under test (all values use the units documented by the formula):
    TFT = 1570 + 0.808*T_blast - 5.85*H - 2.50*W_coal + 4.37*W_o2
    W_coal = PCI_rate[t/h] * 1_000_000 / (60 * Q_blast[m3/min])
    W_o2 = Q_O2[m3/h] * 1_000 / (60 * Q_blast[m3/min])
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np


VARIABLES = ("TFT", "T_blast", "Q_blast", "Q_O2", "O2_rate", "PCI_rate")


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    errors = [p - a for a, p in zip(actual, predicted)]
    mean_actual = statistics.fmean(actual)
    sse = sum(error * error for error in errors)
    sst = sum((value - mean_actual) ** 2 for value in actual)
    return {
        "bias_c": statistics.fmean(errors),
        "mae_c": statistics.fmean(abs(error) for error in errors),
        "rmse_c": math.sqrt(sse / len(errors)),
        "r2": 1.0 - sse / sst if sst > 0 else math.nan,
    }


def describe(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "p10": percentile(values, 0.10),
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "p90": percentile(values, 0.90),
        "max": max(values),
    }


def fit_linear_model(
    observations: list[dict[str, float | str]],
    feature_names: tuple[str, ...],
) -> dict[str, object]:
    split = max(len(feature_names) + 2, int(len(observations) * 0.70))
    split = min(split, len(observations) - 1)
    train = observations[:split]
    test = observations[split:]

    def matrix(rows: list[dict[str, float | str]]) -> np.ndarray:
        return np.asarray(
            [[1.0, *(float(row[name]) for name in feature_names)] for row in rows],
            dtype=float,
        )

    x_train = matrix(train)
    y_train = np.asarray([float(row["actual_tft"]) for row in train], dtype=float)
    coefficients, _, _, _ = np.linalg.lstsq(x_train, y_train, rcond=None)
    x_test = matrix(test)
    y_test = [float(row["actual_tft"]) for row in test]
    predicted_test = (x_test @ coefficients).tolist()
    return {
        "formula": " + ".join(
            [f"{coefficients[0]:.9g}"]
            + [f"({coefficient:.9g})*{name}" for name, coefficient in zip(feature_names, coefficients[1:])]
        ),
        "coefficients": {
            "intercept": float(coefficients[0]),
            **{name: float(value) for name, value in zip(feature_names, coefficients[1:])},
        },
        "train_rows": len(train),
        "test_rows": len(test),
        "test_metrics": metrics(y_test, predicted_test),
        "matrix_condition_number": float(np.linalg.cond(x_train)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--sample-limit", type=int, default=12)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))
    from pg_store import connect

    conn = connect(root / "config" / "sync_config.json")
    registry_rows = conn.execute(
        """
        SELECT variable_name, tag_long_name, description
        FROM bf_sensor.sensor_registry
        WHERE variable_name = ANY(%s)
        ORDER BY variable_name
        """,
        (list(VARIABLES),),
    ).fetchall()
    registry = {row["variable_name"]: dict(row) for row in registry_rows}
    missing = sorted(set(VARIABLES) - registry.keys())
    if missing:
        raise SystemExit(f"Missing registry variables: {missing}")

    rows = conn.execute(
        """
        WITH latest AS (
            SELECT max(v.ts) AS latest_ts
            FROM bf_sensor.one_minute_values v
            WHERE v.tag_long_name = %s
        )
        SELECT v.ts,
               max(v.value) FILTER (WHERE r.variable_name = 'TFT') AS tft,
               max(v.value) FILTER (WHERE r.variable_name = 'T_blast') AS t_blast,
               max(v.value) FILTER (WHERE r.variable_name = 'Q_blast') AS q_blast,
               max(v.value) FILTER (WHERE r.variable_name = 'Q_O2') AS q_o2,
               max(v.value) FILTER (WHERE r.variable_name = 'O2_rate') AS o2_rate,
               max(v.value) FILTER (WHERE r.variable_name = 'PCI_rate') AS pci_rate
        FROM bf_sensor.one_minute_values v
        JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
        CROSS JOIN latest
        WHERE r.variable_name = ANY(%s)
          AND v.ts >= latest.latest_ts - (%s * interval '1 hour')
          AND v.ts <= latest.latest_ts
        GROUP BY v.ts
        HAVING count(DISTINCT r.variable_name) = %s
        ORDER BY v.ts
        """,
        (registry["TFT"]["tag_long_name"], list(VARIABLES), args.hours, len(VARIABLES)),
    ).fetchall()

    observations: list[dict[str, float | str]] = []
    for row in rows:
        tft = float(row["tft"])
        t_blast = float(row["t_blast"])
        q_blast = float(row["q_blast"])
        q_o2 = float(row["q_o2"])
        o2_rate = float(row["o2_rate"])
        pci_rate = float(row["pci_rate"])
        if not (1000 <= tft <= 3500 and 500 <= t_blast <= 1600 and 100 <= q_blast <= 10000):
            continue
        if not (0 <= q_o2 <= 100000 and 0 <= o2_rate <= 30 and 0 <= pci_rate <= 200):
            continue
        w_coal = pci_rate * 1_000_000.0 / (60.0 * q_blast)
        w_o2 = q_o2 * 1_000.0 / (60.0 * q_blast)
        dry_tft = 1570.0 + 0.808 * t_blast - 2.50 * w_coal + 4.37 * w_o2
        inferred_humidity = (dry_tft - tft) / 5.85
        observations.append(
            {
                "ts": str(row["ts"]),
                "actual_tft": tft,
                "t_blast": t_blast,
                "q_blast": q_blast,
                "q_o2": q_o2,
                "o2_rate": o2_rate,
                "pci_rate": pci_rate,
                "w_coal": w_coal,
                "w_o2": w_o2,
                "dry_tft": dry_tft,
                "inferred_humidity": inferred_humidity,
            }
        )

    if not observations:
        raise SystemExit("No complete aligned observations found")

    actual = [float(item["actual_tft"]) for item in observations]
    inferred = [float(item["inferred_humidity"]) for item in observations]
    fitted_humidity = statistics.fmean(inferred)
    fixed_humidities = (0.0, 10.0, 20.0, 30.0, fitted_humidity)
    comparisons = {}
    for humidity in fixed_humidities:
        predicted = [float(item["dry_tft"]) - 5.85 * humidity for item in observations]
        key = "fitted_mean" if humidity == fitted_humidity else f"fixed_{humidity:g}"
        comparisons[key] = {"humidity_g_m3": humidity, **metrics(actual, predicted)}

    output = {
        "formula": "1570 + 0.808*T_blast - 5.85*H - 2.50*W_coal + 4.37*W_o2",
        "conversion": {
            "W_coal": "PCI_rate[t/h]*1_000_000/(60*Q_blast[m3/min])",
            "W_o2": "Q_O2[m3/h]*1_000/(60*Q_blast[m3/min])",
        },
        "window_hours": args.hours,
        "row_count": len(observations),
        "first_ts": observations[0]["ts"],
        "last_ts": observations[-1]["ts"],
        "registry": registry,
        "ranges": {
            key: describe([float(item[key]) for item in observations])
            for key in ("actual_tft", "t_blast", "q_blast", "q_o2", "o2_rate", "pci_rate", "w_coal", "w_o2")
        },
        "inferred_humidity_g_m3": describe(inferred),
        "comparisons": comparisons,
        "exploratory_regressions": {
            "physical_terms": fit_linear_model(observations, ("t_blast", "w_coal", "w_o2")),
            "direct_points": fit_linear_model(
                observations,
                ("t_blast", "q_blast", "q_o2", "o2_rate", "pci_rate"),
            ),
        },
        "samples": observations[-max(1, args.sample_limit) :],
    }
    print(json.dumps(output, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

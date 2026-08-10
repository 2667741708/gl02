"""Compare two V19 per-heat prediction CSVs deterministically."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    args = parser.parse_args()
    a = pd.read_csv(args.first, low_memory=False, encoding="utf-8-sig")
    b = pd.read_csv(args.second, low_memory=False, encoding="utf-8-sig")
    key = "official_meltno"
    a = a.sort_values(key).reset_index(drop=True)
    b = b.sort_values(key).reset_index(drop=True)
    cols = ["prediction__fixed", "prediction__selected", "actual__Si_mean"]
    equal_keys = a[key].astype(str).tolist() == b[key].astype(str).tolist()
    max_delta = max(float(np.nanmax(np.abs(a[c].to_numpy() - b[c].to_numpy()))) for c in cols)
    print({"rows_first": len(a), "rows_second": len(b), "keys_equal": equal_keys, "max_numeric_delta": max_delta, "identical": bool(equal_keys and max_delta == 0.0)})
    return 0 if equal_keys and max_delta == 0.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

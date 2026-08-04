from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the robust normal-score aggregation rule.")
    parser.add_argument("--rule-engine-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.rule_engine_dir.resolve()
    sys.path.insert(0, str(root))

    from engine.resolver import Resolver
    from rules.normal import _percentile, score_normal

    if not math.isclose(_percentile([0.2, 0.4, 2.0], 0.75), 1.2, abs_tol=1e-9):
        raise AssertionError("body-temperature P75 interpolation is incorrect")
    if not math.isclose(_percentile([0.1] * 9 + [1.0], 0.80), 0.1, abs_tol=1e-9):
        raise AssertionError("body-circumference P80 interpolation is incorrect")

    features = {
        "zstd_P_top": 0.0,
        "zstd_DP_total": 0.0,
        "zstd_PI": 0.0,
        "zstd_P_blast": 0.0,
        "DispTop_15": 0.0,
        "zstd_T_body_lower": 0.2,
        "zstd_T_body_middle": 0.4,
        "zstd_T_body_upper": 2.0,
        "L_diff_NS": 0.0,
    }
    features.update({f"T_body_circ_cv_L{layer}": 0.1 for layer in range(7, 16)})
    features["T_body_circ_cv_L16"] = 1.0

    normal = score_normal(features)
    if not math.isclose(normal["score"], 85.38947368421053, abs_tol=1e-9):
        raise AssertionError(f"unexpected normal score: {normal['score']}")

    resolver = Resolver()
    score_template = {"confidence": 1.0, "evidence": []}
    case_44 = {
        "normal": {**score_template, "score": normal["score"]},
        "cold": {**score_template, "score": 44.0},
    }
    case_45 = {
        "normal": {**score_template, "score": normal["score"]},
        "cold": {**score_template, "score": 45.0},
    }
    main_44, secondary_44 = resolver.resolve(case_44)
    main_45, secondary_45 = resolver.resolve(case_45)
    if (
        main_44[0] != "normal"
        or secondary_44 is not None
        or main_45[0] != "normal"
        or secondary_45 is None
        or secondary_45[0] != "cold"
    ):
        raise AssertionError("main-condition threshold changed unexpectedly")

    print(
        json.dumps(
            {
                "ok": True,
                "rule_engine_dir": str(root),
                "normal_score": round(normal["score"], 6),
                "body_p75": 1.2,
                "circumference_p80": 0.1,
                "case_44": main_44[0],
                "case_45": main_45[0],
                "case_45_secondary": secondary_45[0],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

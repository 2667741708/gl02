from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify normal/abnormal conflict resolution boundaries."
    )
    parser.add_argument("--rule-engine-dir", type=Path, required=True)
    return parser.parse_args()


def result(score: float) -> dict:
    return {"score": score, "confidence": 1.0, "evidence": []}


def resolved_labels(resolver, scores: dict) -> tuple[str, str | None]:
    main_diag, secondary_diag = resolver.resolve(scores)
    return main_diag[0], secondary_diag[0] if secondary_diag else None


def main() -> int:
    args = parse_args()
    root = args.rule_engine_dir.resolve()
    sys.path.insert(0, str(root))

    from engine.resolver import Resolver

    resolver = Resolver()
    cases = {
        "below_abnormal_threshold": (
            {"normal": result(20.0), "cold": result(44.99)},
            ("normal", None),
        ),
        "gray_lead_just_below_margin": (
            {"normal": result(47.99), "cold": result(45.0)},
            ("cold", None),
        ),
        "gray_lead_exact_margin": (
            {"normal": result(48.0), "cold": result(45.0)},
            ("normal", "cold"),
        ),
        "gray_upper_lead_exact_margin": (
            {"normal": result(62.99), "cold": result(59.99)},
            ("normal", "cold"),
        ),
        "strong_abnormal_cannot_be_overridden": (
            {"normal": result(100.0), "cold": result(60.0)},
            ("cold", None),
        ),
        "abnormal_secondary_rule_unchanged": (
            {
                "normal": result(40.0),
                "cold": result(65.0),
                "hot": result(58.0),
            },
            ("cold", "hot"),
        ),
    }

    actual = {}
    for name, (scores, expected) in cases.items():
        labels = resolved_labels(resolver, scores)
        if labels != expected:
            raise AssertionError(f"{name}: expected {expected}, got {labels}")
        actual[name] = {"main": labels[0], "secondary": labels[1]}

    print(
        json.dumps(
            {
                "ok": True,
                "rule_engine_dir": str(root),
                "main_candidate_threshold": resolver.main_candidate_threshold,
                "strong_abnormal_threshold": resolver.strong_abnormal_threshold,
                "normal_lead_margin": resolver.normal_lead_margin,
                "cases": actual,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import pytest

from si_semantic_engine.train_v17 import reconstruct_v13_recipes


def _blocks() -> dict:
    return {
        "base_history": ["history_a"],
        "chemistry_columns": ["chemistry_a"],
    }


def _audit() -> dict:
    return {
        "training_rows": 10,
        "all_new_importance350": ["lag_a"],
        "recipe_counts": {"v13_allnew_importance350": 4},
        "v10_selection": {
            "recipe_counts": {"v9_reference": 3},
            "old_feature_selection": {
                "derived_ranking_top300": [
                    {"feature": "derived_a"},
                ]
            },
        },
    }


def test_reconstruct_v13_recipe_from_verified_audit() -> None:
    recipes = reconstruct_v13_recipes(
        _blocks(),
        _audit(),
        expected_training_rows=10,
        available_columns=[
            "history_a",
            "chemistry_a",
            "derived_a",
            "lag_a",
        ],
    )
    assert recipes["v9_reference"] == [
        "history_a",
        "chemistry_a",
        "derived_a",
    ]
    assert recipes["v13_reference"][-1] == "lag_a"


def test_reconstruct_rejects_training_row_mismatch() -> None:
    with pytest.raises(RuntimeError, match="训练行数"):
        reconstruct_v13_recipes(
            _blocks(),
            _audit(),
            expected_training_rows=11,
            available_columns=[
                "history_a",
                "chemistry_a",
                "derived_a",
                "lag_a",
            ],
        )


def test_reconstruct_rejects_missing_feature() -> None:
    with pytest.raises(RuntimeError, match="缺失"):
        reconstruct_v13_recipes(
            _blocks(),
            _audit(),
            expected_training_rows=10,
            available_columns=[
                "history_a",
                "chemistry_a",
                "derived_a",
            ],
        )

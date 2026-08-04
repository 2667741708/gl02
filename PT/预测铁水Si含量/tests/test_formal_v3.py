from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.formal_dataset import (  # noqa: E402
    assign_heat_time_splits,
    attach_available_si_history,
    canonicalize_history_features,
)
from si_semantic_engine.formal_labels import (  # noqa: E402
    NEXT_SAMPLE_TASK,
    build_label_contract,
    validate_training_task,
)


def sample_row(**overrides):
    row = {
        "official_meltno": "2#20260726-001",
        "batchno": "B001",
        "sample_no": "22607-001-001",
        "si_pct": 0.20,
        "c_pct": 4.5,
        "mn_pct": 0.2,
        "result_ts": "2026-07-26 12:00:00",
        "sample_ts": None,
        "open_ts": "2026-07-26 10:00:00",
        "close_ts": "2026-07-26 11:00:00",
        "tank_no": "T01",
        "taphole_id": None,
    }
    row.update(overrides)
    return row


class FormalLabelContractTests(unittest.TestCase):
    def test_missing_official_meltno_is_not_repaired_from_sample_no(self) -> None:
        frame = pd.DataFrame(
            [sample_row(official_meltno=None, sample_no="22607-001-001")]
        )
        with self.assertRaisesRegex(ValueError, "正式meltno"):
            build_label_contract(frame)

    def test_result_time_never_replaces_missing_sample_time(self) -> None:
        result = build_label_contract(pd.DataFrame([sample_row()]))
        sample = result.samples.iloc[0]
        self.assertTrue(pd.isna(sample["sample_ts"]))
        self.assertEqual(sample["sample_time_status"], "missing_source")
        self.assertFalse(bool(sample["sample_time_fallback_used"]))
        self.assertEqual(len(result.next_sample_targets), 0)
        with self.assertRaisesRegex(RuntimeError, "takesampletime"):
            validate_training_task(result.audit, NEXT_SAMPLE_TASK)

    def test_actual_sample_time_enables_stage_and_next_sample_target(self) -> None:
        frame = pd.DataFrame(
            [
                sample_row(
                    batchno="B001",
                    sample_ts="2026-07-26 10:10:00",
                    si_pct=0.20,
                ),
                sample_row(
                    batchno="B002",
                    sample_ts="2026-07-26 10:40:00",
                    result_ts="2026-07-26 12:30:00",
                    si_pct=0.30,
                ),
            ]
        )
        result = build_label_contract(frame)
        self.assertEqual(set(result.samples["tapping_stage"]), {"tapping"})
        self.assertEqual(len(result.next_sample_targets), 1)
        self.assertAlmostEqual(
            result.next_sample_targets.iloc[0]["target__next_sample_Si"],
            0.30,
        )

    def test_representative_and_distribution_targets_are_explicit(self) -> None:
        result = build_label_contract(
            pd.DataFrame(
                [
                    sample_row(batchno="B001", si_pct=0.20),
                    sample_row(batchno="B002", si_pct=0.40),
                ]
            )
        )
        target = result.heat_targets.iloc[0]
        self.assertAlmostEqual(target["target__Si_representative"], 0.30)
        self.assertAlmostEqual(target["target__Si_p10"], 0.22)
        self.assertAlmostEqual(target["target__Si_p50"], 0.30)
        self.assertAlmostEqual(target["target__Si_p90"], 0.38)
        self.assertAlmostEqual(target["target__Si_spread"], 0.20)
        self.assertEqual(target["target__Si_sample_count"], 2)

    def test_fully_pre_cutoff_target_is_not_contract_ready(self) -> None:
        result = build_label_contract(
            pd.DataFrame(
                [
                    sample_row(
                        result_ts="2026-07-26 09:00:00",
                        open_ts="2026-07-26 10:00:00",
                    )
                ]
            )
        )
        timing = result.audit["label_timing"]
        self.assertEqual(timing["result_at_or_before_cutoff_rows"], 1)
        self.assertEqual(
            timing["fully_available_at_or_before_cutoff_heats"], 1
        )
        self.assertEqual(
            result.audit["task_readiness"]["heat_representative_si"][
                "eligible_rows"
            ],
            0,
        )


class FormalDatasetTests(unittest.TestCase):
    def test_history_float_contract_survives_csv_round_trip(self) -> None:
        frame = pd.DataFrame(
            {
                "history__previous_Si_slope_3": [
                    0.004999999999999995
                ],
                "history__previous_Si_median_6": [
                    0.28500000000000003
                ],
            }
        )
        canonical = canonicalize_history_features(frame)
        buffer = io.StringIO()
        canonical.to_csv(buffer, index=False)
        buffer.seek(0)
        restored = pd.read_csv(buffer)
        pd.testing.assert_frame_equal(canonical, restored)

    def test_same_cutoff_heat_is_not_available_history(self) -> None:
        rows = pd.DataFrame(
            {
                "official_meltno": ["H1", "H2"],
                "prediction_cutoff_ts": [
                    "2026-07-27 10:00:00",
                    "2026-07-27 10:00:00",
                ],
                "label_available_ts": [
                    "2026-07-27 09:00:00",
                    "2026-07-27 11:00:00",
                ],
                "target__Si_representative": [0.30, 0.50],
            }
        )
        history = attach_available_si_history(rows)
        self.assertEqual(
            history["history__available_heat_count"].tolist(), [0, 0]
        )
        self.assertTrue(history["history__previous_Si_1"].isna().all())

    def test_previous_si_requires_earlier_heat_and_published_label(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "official_meltno": "2#20260726-001",
                    "prediction_cutoff_ts": "2026-07-26 10:00:00",
                    "label_available_ts": "2026-07-26 12:00:00",
                    "target__Si_representative": 0.20,
                },
                {
                    "official_meltno": "2#20260726-002",
                    "prediction_cutoff_ts": "2026-07-26 11:00:00",
                    "label_available_ts": "2026-07-26 13:00:00",
                    "target__Si_representative": 9.99,
                },
                {
                    "official_meltno": "2#20260726-003",
                    "prediction_cutoff_ts": "2026-07-26 12:30:00",
                    "label_available_ts": "2026-07-26 14:00:00",
                    "target__Si_representative": 0.30,
                },
            ]
        )
        output = attach_available_si_history(frame)
        second = output.loc[
            output["official_meltno"] == "2#20260726-002"
        ].iloc[0]
        third = output.loc[
            output["official_meltno"] == "2#20260726-003"
        ].iloc[0]
        self.assertTrue(pd.isna(second["history__previous_Si_1"]))
        self.assertAlmostEqual(third["history__previous_Si_1"], 0.20)
        self.assertNotEqual(third["history__previous_Si_1"], 9.99)

    def test_official_heat_splits_are_disjoint_and_chronological(self) -> None:
        frame = pd.DataFrame(
            {
                "official_meltno": [
                    f"2#20260726-{index:03d}" for index in range(40)
                ],
                "prediction_cutoff_ts": pd.date_range(
                    "2026-01-01", periods=40, freq="h"
                ),
            }
        )
        output = assign_heat_time_splits(frame)
        self.assertEqual(output["official_meltno"].nunique(), len(output))
        train_max = output.loc[
            output["experiment_split"] == "train", "prediction_cutoff_ts"
        ].max()
        validation_min = output.loc[
            output["experiment_split"] == "validation",
            "prediction_cutoff_ts",
        ].min()
        test_min = output.loc[
            output["experiment_split"] == "test", "prediction_cutoff_ts"
        ].min()
        validation_max = output.loc[
            output["experiment_split"] == "validation",
            "prediction_cutoff_ts",
        ].max()
        self.assertLess(train_max, validation_min)
        self.assertLess(validation_max, test_min)


if __name__ == "__main__":
    unittest.main()

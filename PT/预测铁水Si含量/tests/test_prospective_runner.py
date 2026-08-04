from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from si_semantic_engine.prospective import (  # noqa: E402
    _available_history_for_predictions,
    append_prediction_ledger,
    settle_ledger,
)


PROTOCOL_PATH = ROOT / "configs" / "prospective_blind_protocol.v1.json"
CURRENT_PROTOCOL_PATH = (
    ROOT / "configs" / "prospective_blind_protocol.v4.json"
)


class ProspectiveRunnerTests(unittest.TestCase):
    def test_history_uses_only_prior_published_labels(self) -> None:
        predictions = pd.DataFrame(
            {
                "official_meltno": ["H3"],
                "prediction_cutoff_ts": ["2026-08-01 12:00:00"],
            }
        )
        targets = pd.DataFrame(
            {
                "official_meltno": ["H1", "H2", "H3"],
                "prediction_cutoff_ts": [
                    "2026-08-01 08:00:00",
                    "2026-08-01 10:00:00",
                    "2026-08-01 12:00:00",
                ],
                "label_available_ts": [
                    "2026-08-01 09:00:00",
                    "2026-08-01 13:00:00",
                    "2026-08-01 11:00:00",
                ],
                "target__Si_representative": [0.30, 0.50, 9.99],
            }
        )
        history = _available_history_for_predictions(
            predictions, targets
        )
        self.assertEqual(history.loc[0, "history__available_heat_count"], 1)
        self.assertAlmostEqual(
            history.loc[0, "history__previous_Si_1"], 0.30
        )

    def test_append_is_idempotent_and_contains_no_target(self) -> None:
        protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        predictions = pd.DataFrame(
            {
                "official_meltno": ["H-FUTURE-1"],
                "prediction_cutoff_ts": ["2026-08-01 12:00:00"],
                "prediction__v9_point": [0.31],
                "prediction__v10_point": [0.32],
                "prediction__v10_p10": [0.25],
                "prediction__v10_p50": [0.31],
                "prediction__v10_p90": [0.38],
            }
        )
        recorded_at = datetime(
            2026, 8, 1, 12, 1, tzinfo=timezone.utc
        )
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "predictions.jsonl"
            first = append_prediction_ledger(
                ledger,
                predictions,
                protocol,
                recorded_at=recorded_at,
                source_fingerprint="fixture",
            )
            second = append_prediction_ledger(
                ledger,
                predictions,
                protocol,
                recorded_at=recorded_at,
                source_fingerprint="fixture",
            )
            self.assertEqual(first["appended"], 1)
            self.assertEqual(second["idempotent_skipped"], 1)
            record = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertFalse(record["contains_current_heat_label"])
            self.assertNotIn("actual", record)
            self.assertNotIn("target", json.dumps(record))

    def test_settlement_waits_for_gate_and_requires_earlier_prediction(
        self,
    ) -> None:
        protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        predictions = pd.DataFrame(
            {
                "official_meltno": ["H-FUTURE-2"],
                "prediction_cutoff_ts": ["2026-08-02 12:00:00"],
                "prediction__v9_point": [0.31],
                "prediction__v10_point": [0.32],
                "prediction__v10_p10": [0.25],
                "prediction__v10_p50": [0.31],
                "prediction__v10_p90": [0.38],
            }
        )
        targets = pd.DataFrame(
            {
                "official_meltno": ["H-FUTURE-2"],
                "prediction_cutoff_ts": ["2026-08-02 12:00:00"],
                "label_available_ts": ["2026-08-02 15:00:00"],
                "target__Si_representative": [0.33],
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "predictions.jsonl"
            append_prediction_ledger(
                ledger,
                predictions,
                protocol,
                recorded_at=datetime.fromisoformat(
                    "2026-08-02T12:01:00+08:00"
                ),
                source_fingerprint="fixture",
            )
            result = settle_ledger(
                ledger,
                targets,
                PROTOCOL_PATH,
                as_of=datetime.fromisoformat(
                    "2026-08-03T00:00:00+08:00"
                ),
            )
            self.assertEqual(result["settled_rows"], 1)
            self.assertFalse(result["evaluation_ready"])
            self.assertEqual(result["metrics"], {})

    def test_v13_point_and_distribution_are_settled_when_ready(
        self,
    ) -> None:
        protocol = json.loads(
            CURRENT_PROTOCOL_PATH.read_text(encoding="utf-8")
        )
        protocol["prospective_eligibility"][
            "minimum_completed_heats"
        ] = 1
        protocol["prospective_eligibility"][
            "minimum_calendar_span_days"
        ] = 0
        predictions = pd.DataFrame(
            {
                "official_meltno": ["H-FUTURE-V13"],
                "prediction_cutoff_ts": ["2026-08-04 12:00:00"],
                "prediction__v9_point": [0.31],
                "prediction__v10_point": [0.32],
                "prediction__v10_p10": [0.25],
                "prediction__v10_p50": [0.31],
                "prediction__v10_p90": [0.38],
                "prediction__v13_point": [0.33],
                "prediction__v13_p10": [0.27],
                "prediction__v13_p50": [0.32],
                "prediction__v13_p90": [0.37],
            }
        )
        targets = pd.DataFrame(
            {
                "official_meltno": ["H-FUTURE-V13"],
                "prediction_cutoff_ts": ["2026-08-04 12:00:00"],
                "label_available_ts": ["2026-08-04 15:00:00"],
                "target__Si_representative": [0.34],
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            protocol_path = root / "protocol.json"
            protocol_path.write_text(
                json.dumps(protocol, ensure_ascii=False),
                encoding="utf-8",
            )
            ledger = root / "predictions.jsonl"
            append_prediction_ledger(
                ledger,
                predictions,
                protocol,
                recorded_at=datetime.fromisoformat(
                    "2026-08-04T12:01:00+08:00"
                ),
                source_fingerprint="fixture-v13",
            )
            result = settle_ledger(
                ledger,
                targets,
                protocol_path,
                as_of=datetime.fromisoformat(
                    "2026-08-05T00:00:00+08:00"
                ),
            )
            self.assertTrue(result["evaluation_ready"])
            self.assertIn("v13_point", result["metrics"])
            self.assertEqual(
                result["metrics"]["v13_distribution"][
                    "p10_p90_coverage"
                ],
                1.0,
            )


if __name__ == "__main__":
    unittest.main()

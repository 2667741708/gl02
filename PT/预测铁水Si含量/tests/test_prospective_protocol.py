from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATHS = sorted(
    (ROOT / "configs").glob("prospective_blind_protocol.v*.json")
)
CURRENT_PROTOCOL_PATH = (
    ROOT / "configs" / "prospective_blind_protocol.v4.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ProspectiveBlindProtocolTests(unittest.TestCase):
    def test_frozen_candidate_hashes_match_model_artifacts(self) -> None:
        for protocol_path in PROTOCOL_PATHS:
            protocol = json.loads(
                protocol_path.read_text(encoding="utf-8")
            )
            for candidate in protocol["frozen_candidates"]:
                path = (
                    protocol_path.parent / candidate["model_path"]
                ).resolve()
                self.assertTrue(path.is_file())
                self.assertEqual(
                    _sha256(path), candidate["model_sha256"]
                )

    def test_future_boundary_is_after_historical_cutoff(self) -> None:
        protocol = json.loads(
            CURRENT_PROTOCOL_PATH.read_text(encoding="utf-8")
        )
        historical = datetime.fromisoformat(
            protocol["historical_data_max_prediction_cutoff"]
        )
        future = datetime.fromisoformat(
            protocol["prospective_eligibility"][
                "prediction_cutoff_strictly_after"
            ]
        )
        self.assertGreater(future, historical)
        self.assertTrue(
            protocol["prospective_eligibility"][
                "no_interim_model_selection"
            ]
        )
        self.assertEqual(
            protocol["status"], "frozen_waiting_for_future_heats"
        )


if __name__ == "__main__":
    unittest.main()

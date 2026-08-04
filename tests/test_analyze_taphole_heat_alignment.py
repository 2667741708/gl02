from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from tools.analyze_taphole_heat_alignment import (
    Heat,
    Point,
    classify_temperature_dominance,
    detect_transitions,
    estimate_floor,
    nearest_transition,
)


class TapholeHeatAlignmentTests(unittest.TestCase):
    def test_detects_large_contiguous_jump_only(self) -> None:
        start = datetime(2026, 7, 18, 0, 0)
        points = [
            Point("T_taphole_1", start, 1200.0),
            Point("T_taphole_1", start + timedelta(minutes=1), 1500.0),
            Point("T_taphole_1", start + timedelta(minutes=2), 1501.0),
            Point("T_taphole_1", start + timedelta(minutes=10), 1200.0),
        ]
        transitions = detect_transitions(points)
        self.assertEqual(1, len(transitions))
        self.assertEqual("rise", transitions[0].direction)

    def test_matches_nearest_transition_within_window(self) -> None:
        start = datetime(2026, 7, 18, 0, 0)
        points = [
            Point("T_taphole_1", start, 1200.0),
            Point("T_taphole_1", start + timedelta(minutes=1), 1500.0),
        ]
        transition = detect_transitions(points)[0]
        match, error = nearest_transition(
            start + timedelta(minutes=8),
            [transition],
            window_minutes=10,
        )
        self.assertEqual(transition, match)
        self.assertEqual(7.0, error)

    def test_floor_and_dominance_are_explicitly_signal_only(self) -> None:
        start = datetime(2026, 7, 18, 0, 0)
        points = [
            Point("T_taphole_1", start + timedelta(minutes=index), value)
            for index, value in enumerate([1200.0, 1200.0, 1200.0, 1500.0])
        ]
        self.assertEqual(1200.0, estimate_floor(points))
        self.assertEqual(
            "T_taphole_1",
            classify_temperature_dominance(
                {"T_taphole_1": 1500.0, "T_taphole_2": 1210.0},
                {"T_taphole_1": 1200.0, "T_taphole_2": 1200.0},
            ),
        )
        self.assertEqual(
            "ambiguous",
            classify_temperature_dominance(
                {"T_taphole_1": 1500.0, "T_taphole_2": 1490.0},
                {"T_taphole_1": 1200.0, "T_taphole_2": 1200.0},
            ),
        )


if __name__ == "__main__":
    unittest.main()

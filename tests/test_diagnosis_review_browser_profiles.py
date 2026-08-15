from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "verify_diagnosis_review_local.py"
SPEC = importlib.util.spec_from_file_location("diagnosis_review_browser", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_risk_tier_matrix_sizes_are_bounded() -> None:
    assert (
        sum(
            len(MODULE.validation_matrix("quick", engine))
            for engine in ("chromium", "firefox", "webkit")
        )
        == 4
    )
    assert (
        sum(
            len(MODULE.validation_matrix("standard", engine))
            for engine in ("chromium", "firefox", "webkit")
        )
        == 17
    )
    assert (
        sum(
            len(MODULE.validation_matrix("full", engine))
            for engine in ("chromium", "firefox", "webkit")
        )
        == 85
    )


def test_quick_profile_only_targets_the_changed_diagnosis_surface() -> None:
    for engine in ("chromium", "firefox", "webkit"):
        assert {route for route, _ in MODULE.validation_matrix("quick", engine)} == {
            "diagnosis"
        }


def test_full_profile_preserves_all_routes_and_exact_1546_viewport() -> None:
    chromium = MODULE.validation_matrix("full", "chromium")
    assert {route for route, _ in chromium} == set(MODULE.ROUTES)
    assert ("overview", (1546, 864)) in chromium

"""Canonical adapter package for audited policy and scoped production advice."""

from __future__ import annotations

from typing import Any

import recommendation_adapter_full as _full
from foreman_dual_control import build_foreman_control_context, scope_bundle
from recommendation_adapter_full import *  # noqa: F401,F403


ENGINE_VERSION = f"{_full.ENGINE_VERSION}-foreman-dual-control-v2"


def generate_recommendation_bundle(
    diagnosis: dict[str, Any], current_values: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return the production bundle restricted to P_blast_cold and PCI_set."""
    base_features = _full.build_features_snapshot(diagnosis, current_values)
    context = build_foreman_control_context(base_features, current_values, diagnosis)
    bundle = _full.generate_recommendation_bundle(diagnosis, current_values)
    return scope_bundle(bundle, context, ENGINE_VERSION)


def generate_recommendation(
    diagnosis: dict[str, Any], current_values: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return the complete policy result for rule audit and regression tests."""
    recommendation = _full.generate_recommendation(diagnosis, current_values)
    recommendation.setdefault("engine_meta", {})["version"] = ENGINE_VERSION
    return recommendation

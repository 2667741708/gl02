"""Compatibility package that exposes the dual-control core with final counts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


_CORE_PATH = Path(__file__).resolve().parent.parent / "foreman_dual_control.py"
_SPEC = importlib.util.spec_from_file_location("_foreman_dual_control_core", _CORE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load foreman dual-control core: {_CORE_PATH}")
_CORE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CORE)

SCOPE_VERSION = _CORE.SCOPE_VERSION
ALLOWED_CONTROL_VARIABLES = _CORE.ALLOWED_CONTROL_VARIABLES
ACTION_CONTROL_MAP = _CORE.ACTION_CONTROL_MAP
build_foreman_control_context = _CORE.build_foreman_control_context
scope_recommendation = _CORE.scope_recommendation


def scope_bundle(
    bundle: dict[str, Any], context: dict[str, Any], engine_version: str
) -> dict[str, Any]:
    """Return the scoped bundle with post-scope action counts."""
    scoped = _CORE.scope_bundle(bundle, context, engine_version)
    for condition in scoped.get("conditions") or []:
        recommendation = condition.get("recommendation") or {}
        condition["action_count"] = len(recommendation.get("actions") or [])
    return scoped

# -*- coding: utf-8 -*-
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml


CONFIG_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def load_thresholds() -> Dict[str, Any]:
    path = CONFIG_DIR / "thresholds.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def load_rule_weights() -> Dict[str, Any]:
    path = CONFIG_DIR / "rule_weights.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def threshold(rule: str, key: str, default: Any = None, section: str | None = None) -> Any:
    rules = load_thresholds().get("rules", {})
    node = rules.get(rule, {})
    if section:
        for part in section.split("."):
            node = node.get(part, {})
    return node.get(key, default)


def weight(rule: str, item_name: str, default: float = 0.0, section: str | None = None) -> float:
    rules = load_rule_weights().get("rules", {})
    node = rules.get(rule, {})
    if section:
        for part in section.split("."):
            node = node.get(part, {})
    return float(node.get(item_name, default))

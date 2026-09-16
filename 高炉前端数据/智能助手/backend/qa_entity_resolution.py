"""Deterministic multi-entity resolution for GL02 assistant requests.

REQ-QA-FULL-ISSUE-INVENTORY-20260916 / QAOPT-R03

The model may explain ambiguous language, but it must not silently shrink an
explicit object list.  This module expands only reviewed aliases and ranges and
returns an ordered, auditable set that both TaskPlan and the executor can use.
"""
from __future__ import annotations

import re
from typing import Any


VERSION = "qa-entity-resolution-v1"

_CHEMICAL_TOKEN_RE = re.compile(r"(?<![a-z0-9_])(co2|co|h2)(?![a-z0-9_])", re.I)
_LETTER_RANGE_RE = re.compile(
    r"(?<![a-z])([a-f])\s*(?:-|－|—|–|~|～|至|到)\s*([a-f])(?![a-z])",
    re.I,
)
_CHEMICAL_VARIABLES = {
    "co": "CO_top",
    "co2": "CO2_top",
    "h2": "H2_top",
}


def _ordered_unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _expand_range(start: str, end: str) -> list[str]:
    left = ord(start.upper())
    right = ord(end.upper())
    step = 1 if right >= left else -1
    return [chr(value) for value in range(left, right + step, step)]


def _letter_ranges(text: str) -> list[tuple[int, list[str], str]]:
    ranges: list[tuple[int, list[str], str]] = []
    for match in _LETTER_RANGE_RE.finditer(text):
        ranges.append((match.start(), _expand_range(match.group(1), match.group(2)), match.group(0)))
    return ranges


def resolve_requested_entities(question: str) -> dict[str, Any]:
    """Return reviewed canonical IDs without guessing unknown plant objects."""

    text = str(question or "")
    lowered = text.lower()
    compact = re.sub(r"[\s，,、。；;：:？?！!（）()]", "", lowered)
    matches: list[tuple[int, int, str, str, str]] = []

    def add(position: int, order: int, variable: str, mention: str, rule: str) -> None:
        matches.append((max(position, 0), order, variable, mention, rule))

    if any(term in compact for term in ("炉顶", "煤气成分", "煤气组分")):
        for order, match in enumerate(_CHEMICAL_TOKEN_RE.finditer(lowered)):
            token = match.group(1).lower()
            add(match.start(), order, _CHEMICAL_VARIABLES[token], match.group(0), "chemical_list")

    ranges = _letter_ranges(lowered)
    family_specs = (
        (("炉喉温度", "炉喉"), "T_throat_", "throat_temperature_range"),
        (("顶温", "上升管煤气温度"), "T_top_", "top_temperature_range"),
        (("顶压", "上升管煤气压力"), "P_top_", "top_pressure_range"),
    )
    for terms, prefix, rule in family_specs:
        if not any(term in compact for term in terms):
            continue
        for position, letters, mention in ranges:
            for order, letter in enumerate(letters):
                add(position, order, f"{prefix}{letter}", mention, rule)

    paired_term = "探尺" in compact or "料线" in compact
    if paired_term:
        south = lowered.find("南")
        north = lowered.find("北")
        if south >= 0 and north >= 0 and abs(south - north) <= 6:
            if south < north:
                add(south, 0, "L_south", "南北", "paired_stock_rods")
                add(north, 1, "L_north", "南北", "paired_stock_rods")
            else:
                add(north, 0, "L_north", "北南", "paired_stock_rods")
                add(south, 1, "L_south", "北南", "paired_stock_rods")

    paired_tapholes = any(term in compact for term in ("两铁口", "两个铁口", "俩铁口", "两座铁口"))
    if paired_tapholes and "温度" in compact:
        position = min((value for value in (lowered.find("两"), lowered.find("俩"), lowered.find("2")) if value >= 0), default=0)
        add(position, 0, "T_taphole_1", "两铁口", "paired_tapholes")
        add(position, 1, "T_taphole_2", "两铁口", "paired_tapholes")

    matches.sort(key=lambda item: (item[0], item[1]))
    entities: list[dict[str, str]] = []
    variables: list[str] = []
    for _, _, variable, mention, rule in matches:
        if variable in variables:
            continue
        variables.append(variable)
        entities.append({"canonical_id": variable, "mention": mention, "rule": rule})

    return {
        "schema": VERSION,
        "variables": _ordered_unique(variables),
        "entities": entities,
        "unresolved": [],
    }

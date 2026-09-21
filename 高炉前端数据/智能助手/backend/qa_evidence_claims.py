"""Field-aware validation for numbers synthesized from verified evidence.

REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916 / QAOPT-E03
"""
from __future__ import annotations

import math
import re
from typing import NamedTuple


_NUMBER_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_OBJECT_ALIASES = {
    "p_top": ("p_top", "top_pressure", "炉顶压力", "顶压"),
    "t_top": ("t_top", "top_temperature", "炉顶温度", "顶温"),
    "dp_total": ("dp_total", "total_dp", "全压差", "总压差", "压差"),
    "q_blast": ("q_blast", "blast_volume", "鼓风量", "风量"),
    "t_blast": ("t_blast", "blast_temperature", "风温"),
    "gasutil": ("gasutil", "煤气利用率"),
    "pci": ("pci", "喷煤量", "煤比"),
}
_STAT_ALIASES = {
    "avg": ("average", "mean", "avg", "平均值", "平均", "均值"),
    "max": ("maximum", "max", "最大值", "最大"),
    "min": ("minimum", "min", "最小值", "最小"),
    "count": ("sample_count", "count", "样本数", "数量", "条数"),
}


class NumericClaim(NamedTuple):
    raw: str
    value: float
    object_field: str | None
    statistic: str | None


def _alias_near(
    text: str,
    start: int,
    end: int,
    aliases_by_field: dict[str, tuple[str, ...]],
) -> str | None:
    before = text[max(0, start - 40):start].lower()
    after = text[end:min(len(text), end + 16)].lower()
    best: tuple[int, str] | None = None
    for field, aliases in aliases_by_field.items():
        for alias in aliases:
            alias_lower = alias.lower()
            position = before.rfind(alias_lower)
            if position >= 0 and (best is None or position > best[0]):
                best = (position, field)
            if alias_lower in after and best is None:
                best = (-1, field)
    return best[1] if best else None


def numeric_claims(text: str) -> list[NumericClaim]:
    source = str(text or "")
    claims: list[NumericClaim] = []
    for match in _NUMBER_RE.finditer(source):
        try:
            value = float(match.group(0))
        except ValueError:
            continue
        if math.isfinite(value):
            claims.append(
                NumericClaim(
                    match.group(0),
                    value,
                    _alias_near(source, *match.span(), _OBJECT_ALIASES),
                    _alias_near(source, *match.span(), _STAT_ALIASES),
                )
            )
    return claims


def _rounding_tolerance(rendered: str, value: float) -> float:
    lowered = rendered.lower()
    if "e" in lowered:
        mantissa, exponent = lowered.split("e", 1)
        decimals = len(mantissa.split(".", 1)[1]) if "." in mantissa else 0
        return 0.5 * (10 ** (int(exponent) - decimals))
    decimals = len(rendered.split(".", 1)[1]) if "." in rendered else 0
    return max(0.5 * (10 ** (-decimals)), abs(value) * 1e-12)


def _matches(answer: NumericClaim, evidence: NumericClaim) -> bool:
    if answer.object_field and evidence.object_field and answer.object_field != evidence.object_field:
        return False
    if answer.statistic and evidence.statistic and answer.statistic != evidence.statistic:
        return False
    tolerance = _rounding_tolerance(answer.raw, answer.value)
    return math.isclose(answer.value, evidence.value, rel_tol=0.0, abs_tol=tolerance)


def answer_numbers_are_grounded(answer: str, evidence: str, question: str = "") -> bool:
    """Accept declared rounding while rejecting a value attached to another field."""

    evidence_claims = numeric_claims(f"{evidence}\n{question}")
    for claim in numeric_claims(answer):
        candidates = evidence_claims
        if claim.object_field:
            same_object = [item for item in evidence_claims if item.object_field == claim.object_field]
            if not same_object:
                return False
            candidates = same_object
        if claim.statistic:
            same_statistic = [item for item in candidates if item.statistic == claim.statistic]
            if not same_statistic:
                return False
            candidates = same_statistic
        if not any(_matches(claim, item) for item in candidates):
            return False
    return True

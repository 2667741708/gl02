"""Cross-source MCP plan and snapshot contracts.

Requirement: REQ-8093-CROSS-SOURCE-MCP-20260805
ADR: docs/adr/0002-8093-cross-source-partial-facts.md

These frozen dataclasses define the contract between the deterministic
plan builder, the DAG executor, and the answer formatter.  Every field
is intentional — do not add "convenience" fields without updating the
corresponding test contract.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Step (one tool call in a larger plan)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrossSourceStep:
    """One MCP tool invocation within a cross-source plan."""

    step_id: str
    server_id: str
    source_domain: str  # "imes" | "gl02"
    tool: str
    arguments: dict[str, Any]
    depends_on: tuple[str, ...] = ()
    argument_bindings: dict[str, str] = field(default_factory=dict)
    produces_fact_ids: tuple[str, ...] = ()
    required_for_answer: bool = True
    required_for_analysis: bool = False

    def __post_init__(self):
        if not self.step_id.strip():
            raise ValueError("step_id must be non-empty")
        if not self.server_id.strip():
            raise ValueError("server_id must be non-empty")
        if self.source_domain not in ("imes", "gl02"):
            raise ValueError(f"source_domain must be 'imes' or 'gl02', got {self.source_domain!r}")
        if not self.tool.strip():
            raise ValueError("tool must be non-empty")
        # Validate argument_bindings paths are well-formed
        for key, path in self.argument_bindings.items():
            if not path.startswith("steps."):
                raise ValueError(
                    f"argument_binding path must start with 'steps.', got {path!r}"
                )


@dataclass(frozen=True)
class FactRequest:
    """Normalized business fact request compiled from colloquial input.

    This is intentionally host-side: MCP servers expose read-only atomic
    tools, while the host owns intent-to-capability routing and safety gates.
    """

    fact_id: str
    object_id: str
    source_domain: str
    server_id: str
    tool: str
    arguments: dict[str, Any]
    required_for_answer: bool = True
    required_for_analysis: bool = False

    def __post_init__(self):
        if not self.fact_id.strip() or not self.object_id.strip():
            raise ValueError("fact_id and object_id must be non-empty")
        if self.source_domain not in ("imes", "gl02"):
            raise ValueError("source_domain must be 'imes' or 'gl02'")


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrossSourcePlan:
    """Deterministic plan for a cross-source MCP question.

    Built by build_cross_source_plans() and consumed by the DAG executor.
    """

    schema_version: str = "1.0"
    steps: tuple[CrossSourceStep, ...] = ()
    requested_fact_ids: tuple[str, ...] = ()
    analysis_requested: bool = False
    requested_heat_reference: dict[str, Any] | str | None = None

    def __post_init__(self):
        step_ids = {s.step_id for s in self.steps}
        if len(step_ids) != len(self.steps):
            raise ValueError("Duplicate step_id in plan")

        # Verify depends_on references exist
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise ValueError(
                        f"Step {step.step_id!r} depends on unknown step {dep!r}"
                    )

        # Verify produces_fact_ids are unique across steps
        all_facts: list[str] = []
        for step in self.steps:
            all_facts.extend(step.produces_fact_ids)
        if len(all_facts) != len(set(all_facts)):
            seen: set[str] = set()
            dups: set[str] = set()
            for fid in all_facts:
                if fid in seen:
                    dups.add(fid)
                seen.add(fid)
            raise ValueError(f"Duplicate fact_ids across steps: {sorted(dups)}")

    @property
    def server_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(s.server_id for s in self.steps))

    @property
    def source_count(self) -> int:
        return len({s.source_domain for s in self.steps})


# ---------------------------------------------------------------------------
# Fact (one user-requested datum)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrossSourceFact:
    """One requested fact from a cross-source execution."""

    fact_id: str
    label: str
    value: Any
    unit: str | None = None
    data_time: str | None = None
    quality: str | None = None
    source_service: str = ""
    source_object: str | None = None
    missing: bool = False
    error_code: str | None = None

    def __post_init__(self):
        if not self.fact_id.strip():
            raise ValueError("fact_id must be non-empty")
        if self.missing and self.error_code is None:
            object.__setattr__(self, "error_code", "DATA_MISSING")


# ---------------------------------------------------------------------------
# Snapshot (the execution result)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrossSourceSnapshot:
    """Standardised result from a cross-source MCP execution."""

    schema_version: str = "1.0"
    orchestration_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    ok: bool = False
    complete: bool = False
    partial: bool = False
    analysis_allowed: bool = False
    facts: tuple[CrossSourceFact, ...] = ()
    requested_fact_ids: tuple[str, ...] = ()
    missing_fact_ids: tuple[str, ...] = ()
    source_status: tuple[dict[str, Any], ...] = ()
    heat_reference: dict[str, Any] | None = None
    total_elapsed_ms: float = 0.0
    error_code: str | None = None

    # ------------------------------------------------------------------
    # State definitions (immutable — enforced at construction)
    # ------------------------------------------------------------------
    # complete=true    → every requested fact succeeded
    # partial=true     → at least one fact succeeded AND at least one missing
    # analysis_allowed → every required_for_analysis fact succeeded
    # ok=false         → zero successful facts
    #
    # Display-step failures (charts, matrices) can make complete=false
    # but only missing EVIDENCE facts block analysis.

    def __post_init__(self):
        if self.ok and not self.facts:
            raise ValueError("ok=true requires at least one fact")
        if self.complete and self.partial:
            raise ValueError("complete and partial are mutually exclusive")
        if self.complete and self.missing_fact_ids:
            raise ValueError("complete=true but missing_fact_ids is non-empty")
        if self.partial and not self.missing_fact_ids:
            raise ValueError("partial=true but missing_fact_ids is empty")
        if self.analysis_allowed and not self.complete and not self.partial:
            raise ValueError("analysis_allowed requires complete or partial")


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def success_snapshot(
    facts: tuple[CrossSourceFact, ...],
    source_status: tuple[dict[str, Any], ...],
    heat_reference: dict[str, Any] | None = None,
    total_elapsed_ms: float = 0.0,
) -> CrossSourceSnapshot:
    """Create a complete-success snapshot (all requested facts present)."""
    requested = tuple(f.fact_id for f in facts)
    return CrossSourceSnapshot(
        ok=True,
        complete=True,
        partial=False,
        analysis_allowed=True,
        facts=facts,
        requested_fact_ids=requested,
        missing_fact_ids=(),
        source_status=source_status,
        heat_reference=heat_reference,
        total_elapsed_ms=total_elapsed_ms,
    )


def partial_snapshot(
    facts: tuple[CrossSourceFact, ...],
    missing_fact_ids: tuple[str, ...],
    source_status: tuple[dict[str, Any], ...],
    analysis_allowed: bool = False,
    heat_reference: dict[str, Any] | None = None,
    total_elapsed_ms: float = 0.0,
) -> CrossSourceSnapshot:
    """Create a partial-result snapshot."""
    if not facts:
        raise ValueError("partial_snapshot requires at least one fact")
    requested = tuple(f.fact_id for f in facts) + missing_fact_ids
    return CrossSourceSnapshot(
        ok=True,
        complete=False,
        partial=True,
        analysis_allowed=analysis_allowed,
        facts=facts,
        requested_fact_ids=requested,
        missing_fact_ids=missing_fact_ids,
        source_status=source_status,
        heat_reference=heat_reference,
        total_elapsed_ms=total_elapsed_ms,
    )


def failed_snapshot(
    error_code: str,
    source_status: tuple[dict[str, Any], ...] = (),
    heat_reference: dict[str, Any] | None = None,
    total_elapsed_ms: float = 0.0,
) -> CrossSourceSnapshot:
    """Create a total-failure snapshot (zero successful facts)."""
    return CrossSourceSnapshot(
        ok=False,
        complete=False,
        partial=False,
        analysis_allowed=False,
        facts=(),
        requested_fact_ids=(),
        missing_fact_ids=(),
        source_status=source_status,
        heat_reference=heat_reference,
        total_elapsed_ms=total_elapsed_ms,
        error_code=error_code,
    )

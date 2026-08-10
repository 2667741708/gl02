#!/usr/bin/env python3
"""Build an isolated r4 payload using the audited recommendation package builder."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "build_8093_8094_recommendation_sync.py"
source = SOURCE.read_text(encoding="utf-8")
source = source.replace(
    'OUTPUT = ROOT / "logs" / "deployment" / "8093_8094_recommendation_sync_20260806_r3"',
    'OUTPUT = ROOT / "logs" / "deployment" / "8093_8094_recommendation_sync_20260806_r4"',
    1,
)
source = source.replace(
    'ARCHIVE = OUTPUT / "recommendation_sync.zip"',
    'ARCHIVE = OUTPUT / "recommendation_sync_20260807_r4.zip"',
    1,
)
exec(compile(source, str(SOURCE), "exec"), {"__name__": "__main__", "__file__": str(SOURCE)})

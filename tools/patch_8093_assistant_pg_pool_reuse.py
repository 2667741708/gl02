"""Patch 8093 knowledge retrieval to reuse the active assistant PG lease.

ERR-8093-ASSISTANT-PG-POOL-NESTED-LEASE-20260805

The patch is deliberately textual and hash-bounded by the PowerShell deployer.
It preserves the source file's BOM and newline convention and refuses partial or
ambiguous matches.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


RAG_RELATIVE = Path("高炉前端数据/智能助手/backend/bf_knowledge_rag.py")
PROXY_RELATIVE = Path("高炉前端数据/智能助手/backend/ollama_proxy_server.py")
PATCH_ID = "ERR-8093-ASSISTANT-PG-POOL-NESTED-LEASE-20260805"


def sha256(payload: bytes) -> str:
    """Return an uppercase SHA-256 digest."""

    return hashlib.sha256(payload).hexdigest().upper()


def decode_source(path: Path) -> tuple[str, str, bool]:
    """Read UTF-8 source while retaining newline and BOM metadata."""

    payload = path.read_bytes()
    has_bom = payload.startswith(b"\xef\xbb\xbf")
    if has_bom:
        payload = payload[3:]
    text = payload.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text, newline, has_bom


def encode_source(text: str, has_bom: bool) -> bytes:
    """Encode source using its original UTF-8 BOM policy."""

    payload = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + payload) if has_bom else payload


def exact_replace(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    """Apply one idempotent replacement or reject an ambiguous baseline."""

    old_variants = tuple(dict.fromkeys((old, old.replace("\n", "\r\n"))))
    new_variants = tuple(dict.fromkeys((new, new.replace("\n", "\r\n"))))
    if any(new_variant in text for new_variant in new_variants):
        return text, False
    matches = [old_variant for old_variant in old_variants if old_variant in text]
    total = sum(text.count(old_variant) for old_variant in matches)
    if total != 1:
        raise RuntimeError(f"{label}: expected exactly one old marker, found {total}")
    old_variant = matches[0]
    if "\r\n" in old_variant:
        new_variant = new.replace("\n", "\r\n")
    elif "\n" in old_variant:
        new_variant = new
    else:
        marker_end = text.index(old_variant) + len(old_variant)
        new_variant = new.replace("\n", "\r\n") if text[marker_end : marker_end + 2] == "\r\n" else new
    return text.replace(old_variant, new_variant, 1), True


def patch_rag(text: str, newline: str) -> tuple[str, bool]:
    """Add an optional caller-owned connection to search_knowledge()."""

    del newline
    changed = False
    # The source-scoped retriever already includes the caller-owned connection
    # contract; do not reapply the historical connection-only patch.
    if (
        "source_doc_ids: Sequence[str] | None = None" in text
        and "connection: Any | None = None" in text
    ):
        return text, False
    replacements = [
        (
            "import zipfile\nfrom datetime import datetime, timezone",
            "import zipfile\nfrom contextlib import nullcontext\nfrom datetime import datetime, timezone",
            "rag nullcontext import",
        ),
        (
            "    mode: str | None = None,\n) -> dict[str, Any]:\n    del db_path",
            "    mode: str | None = None,\n    connection: Any | None = None,\n) -> dict[str, Any]:\n    del db_path",
            "rag connection parameter",
        ),
        (
            "    try:\n        with raw_pg_connect() as conn:\n            ensure_schema(conn)\n            if search_mode in {\"keyword\", \"hybrid\"}:",
            "    try:\n        connection_context = nullcontext(connection) if connection is not None else raw_pg_connect()\n        with connection_context as conn:\n            ensure_schema(conn)\n            if search_mode in {\"keyword\", \"hybrid\"}:",
            "rag connection context",
        ),
    ]
    for old, new, label in replacements:
        text, item_changed = exact_replace(
            text,
            old,
            new,
            label,
        )
        changed = changed or item_changed
    return text, changed


def patch_proxy(text: str, newline: str) -> tuple[str, bool]:
    """Pass the active assistant DB lease into knowledge retrieval."""

    del newline
    changed = False
    old_pg_context = """            try:
                with self.pg_connect() as pg_conn:
                    latest_pg_started = time.perf_counter()
                    pg_snapshot = self.latest_pg_snapshot_for_qa(pg_conn)
                    timing_ms["pg_latest"] = round((time.perf_counter() - latest_pg_started) * 1000, 1)
                    same_trend_window = (pg_snapshot or {}).get("pg_window_minutes") == QA_TREND_WINDOW_MINUTES
                    latest_diagnosis_ts = (
                        ((pg_snapshot or {}).get("diagnosis") or {}).get("diagnosis_ts")
                        if same_trend_window
                        else None
                    )
                    trend_pg_started = time.perf_counter()
                    trend_snapshots, trend_meta = self.recent_pg_diagnosis_snapshots_for_qa(
                        hours=QA_TREND_HOURS,
                        limit=QA_TREND_DIAGNOSIS_LIMIT,
                        conn=pg_conn,
                        latest_ts=latest_diagnosis_ts,
                        context_version=(pg_snapshot or {}).get("pg_context_version") if same_trend_window else None,
                    )
                    timing_ms["pg_trend"] = round((time.perf_counter() - trend_pg_started) * 1000, 1)
            except Exception as exc:  # noqa: BLE001"""
    new_pg_context = """            try:
                latest_pg_started = time.perf_counter()
                pg_snapshot = self.latest_pg_snapshot_for_qa(conn)
                timing_ms["pg_latest"] = round((time.perf_counter() - latest_pg_started) * 1000, 1)
                same_trend_window = (pg_snapshot or {}).get("pg_window_minutes") == QA_TREND_WINDOW_MINUTES
                latest_diagnosis_ts = (
                    ((pg_snapshot or {}).get("diagnosis") or {}).get("diagnosis_ts")
                    if same_trend_window
                    else None
                )
                trend_pg_started = time.perf_counter()
                trend_snapshots, trend_meta = self.recent_pg_diagnosis_snapshots_for_qa(
                    hours=QA_TREND_HOURS,
                    limit=QA_TREND_DIAGNOSIS_LIMIT,
                    conn=conn,
                    latest_ts=latest_diagnosis_ts,
                    context_version=(pg_snapshot or {}).get("pg_context_version") if same_trend_window else None,
                )
                timing_ms["pg_trend"] = round((time.perf_counter() - trend_pg_started) * 1000, 1)
            except Exception as exc:  # noqa: BLE001"""
    replacements = [
        (
            "def qa_search_knowledge(question: str, mode: str | None = None, mcp_prefetch: dict[str, Any] | None = None) -> dict[str, Any]:",
            "def qa_search_knowledge(\n    question: str,\n    mode: str | None = None,\n    mcp_prefetch: dict[str, Any] | None = None,\n    connection: Any | None = None,\n) -> dict[str, Any]:",
            "proxy knowledge signature",
        ),
        (
            "        mode=mode or QA_KNOWLEDGE_SEARCH_MODE,\n    )",
            "        mode=mode or QA_KNOWLEDGE_SEARCH_MODE,\n        connection=connection,\n    )",
            "proxy knowledge forwarding",
        ),
        (
            "            knowledge_pack = qa_search_knowledge(question, mcp_prefetch=mcp_prefetch)",
            "            knowledge_pack = qa_search_knowledge(\n                question,\n                mcp_prefetch=mcp_prefetch,\n                connection=conn,\n            )",
            "proxy active lease reuse",
        ),
        (
            old_pg_context,
            new_pg_context,
            "proxy process data lease reuse",
        ),
    ]
    for old, new, label in replacements:
        text, item_changed = exact_replace(
            text,
            old,
            new,
            label,
        )
        changed = changed or item_changed
    return text, changed


def atomic_write(path: Path, payload: bytes) -> None:
    """Atomically replace one source file in its existing directory."""

    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def apply(root: Path, check_only: bool = False) -> dict[str, object]:
    """Validate or apply the two-file nested-lease repair."""

    result: dict[str, object] = {"patch_id": PATCH_ID, "check_only": check_only, "files": []}
    for relative, patcher in ((RAG_RELATIVE, patch_rag), (PROXY_RELATIVE, patch_proxy)):
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        before = path.read_bytes()
        text, newline, has_bom = decode_source(path)
        patched, changed = patcher(text, newline)
        after = encode_source(patched, has_bom)
        if changed and not check_only:
            atomic_write(path, after)
        result["files"].append(
            {
                "path": str(relative).replace("/", "\\"),
                "changed": changed,
                "sha256_before": sha256(before),
                "sha256_after": sha256(after),
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch 8093 nested assistant PG pool leases.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply(args.root.resolve(), check_only=args.check), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

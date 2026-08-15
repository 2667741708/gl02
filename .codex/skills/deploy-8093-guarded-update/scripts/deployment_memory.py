"""Record local deployment timing and repeated failure fingerprints safely."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "Codex" / "deploy-8093-guarded-update"
SECRET_PATTERN = re.compile(r"(?i)(password|passwd|token|secret|cookie|authorization)\s*[:=]\s*\S+")
PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\|/)[^\s'\"]+")
VOLATILE_PATTERN = re.compile(r"\b(?:0x)?[0-9a-f]{8,}\b|\b\d+\b", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_message(value: str) -> str:
    text = SECRET_PATTERN.sub(r"\1=<redacted>", str(value or ""))
    return text[:2000]


def normalized_error(phase: str, error_type: str, message: str) -> str:
    text = sanitize_message(message).lower()
    text = PATH_PATTERN.sub("<path>", text)
    text = VOLATILE_PATTERN.sub("<n>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return f"{phase.strip().lower()}|{error_type.strip().lower()}|{text}"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def record_event(root: Path, event: dict[str, Any]) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    events_path = root / "deployment-events.jsonl"
    patterns_path = root / "failure-patterns.json"
    event = {**event, "recorded_at": utc_now()}
    event["error_message"] = sanitize_message(str(event.get("error_message") or ""))
    with events_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    response: dict[str, Any] = {"ok": True, "events_path": str(events_path), "candidate_lesson": False}
    if event.get("status") != "failure":
        return response

    normalized = normalized_error(
        str(event.get("phase") or "unknown"),
        str(event.get("error_type") or "Error"),
        str(event.get("error_message") or ""),
    )
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    patterns = load_json(patterns_path, {"schema": "bf.deploy.failure-patterns.v1", "patterns": {}})
    item = patterns.setdefault("patterns", {}).setdefault(
        fingerprint,
        {
            "phase": event.get("phase") or "unknown",
            "error_type": event.get("error_type") or "Error",
            "normalized_error": normalized,
            "occurrences": 0,
            "first_seen": event["recorded_at"],
            "status": "observed",
        },
    )
    item["occurrences"] = int(item.get("occurrences") or 0) + 1
    item["last_seen"] = event["recorded_at"]
    if event.get("remediation_id"):
        item["last_remediation_id"] = event["remediation_id"]
    if item["occurrences"] >= 3:
        item["status"] = "candidate_review"
        response["candidate_lesson"] = True
    atomic_json(patterns_path, patterns)
    response.update(
        {
            "patterns_path": str(patterns_path),
            "fingerprint": fingerprint,
            "occurrences": item["occurrences"],
            "learning_status": item["status"],
            "automatic_skill_rewrite": False,
        }
    )
    return response


def read_events(root: Path) -> list[dict[str, Any]]:
    path = root / "deployment-events.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return round(float(ordered[index]), 1)


def summarize(root: Path, window: int) -> dict[str, Any]:
    rows = read_events(root)[-window:]
    successes = [row for row in rows if row.get("status") == "success"]
    durations = [float(row["duration_ms"]) for row in successes if row.get("duration_ms") is not None]
    reused = [float(row["duration_ms"]) for row in successes if row.get("connection_mode") == "reused" and row.get("duration_ms") is not None]
    cold = [float(row["duration_ms"]) for row in successes if row.get("connection_mode") == "cold" and row.get("duration_ms") is not None]
    reused_median = round(statistics.median(reused), 1) if reused else None
    cold_median = round(statistics.median(cold), 1) if cold else None
    saved = round(cold_median - reused_median, 1) if cold_median is not None and reused_median is not None else None
    patterns = load_json(root / "failure-patterns.json", {"patterns": {}}).get("patterns", {})
    candidates = sorted(
        (dict(value, fingerprint=key) for key, value in patterns.items() if value.get("status") == "candidate_review"),
        key=lambda item: int(item.get("occurrences") or 0),
        reverse=True,
    )
    return {
        "ok": True,
        "schema": "bf.deploy.telemetry-summary.v1",
        "window": window,
        "events": len(rows),
        "successes": len(successes),
        "failures": len(rows) - len(successes),
        "duration_p50_ms": percentile(durations, 0.5),
        "duration_p90_ms": percentile(durations, 0.9),
        "cold_median_ms": cold_median,
        "reused_median_ms": reused_median,
        "saved_median_ms": saved,
        "candidate_lessons": candidates[:10],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")
    record = sub.add_parser("record")
    record.add_argument("--status", choices=("success", "failure"), required=True)
    record.add_argument("--phase", required=True)
    record.add_argument("--duration-ms", type=float)
    record.add_argument("--requirement-id", default="")
    record.add_argument("--connection-mode", choices=("cold", "reused", "unknown"), default="unknown")
    record.add_argument("--error-type", default="")
    record.add_argument("--error-message", default="")
    record.add_argument("--remediation-id", default="")
    summary = sub.add_parser("summary")
    summary.add_argument("--window", type=int, default=50)
    return parser


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        result = None
        for attempt in range(3):
            result = record_event(
                root,
                {
                    "status": "failure",
                    "phase": "staging",
                    "error_type": "TimeoutError",
                    "error_message": f"request 123{attempt} timed out at C:\\Temp\\stage-{attempt}",
                    "duration_ms": 10,
                    "connection_mode": "reused",
                },
            )
        assert result and result["candidate_lesson"] is True
        assert result["occurrences"] == 3
        summary = summarize(root, 10)
        assert summary["failures"] == 3
    return {"ok": True, "self_test": True}


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        result = self_test()
    elif args.command == "record":
        result = record_event(
            args.root,
            {
                "status": args.status,
                "phase": args.phase,
                "duration_ms": args.duration_ms,
                "requirement_id": args.requirement_id,
                "connection_mode": args.connection_mode,
                "error_type": args.error_type,
                "error_message": args.error_message,
                "remediation_id": args.remediation_id,
            },
        )
    elif args.command == "summary":
        result = summarize(args.root, max(1, args.window))
    else:
        raise SystemExit("choose record or summary")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only verifier for the 8093/8094 diagnosis core-variable contract.

Requirement: REQ-8093-8094-DIAGNOSIS-CORE-19-TRENDS-20260806
"""

from __future__ import annotations

import argparse
import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request


EXPECTED_IDS = [
    "P_top_gas_A",
    "P_top_gas_B",
    "P_top_gas_C",
    "P_top_gas_D",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "P_top",
    "T_top",
    "Q_blast",
    "P_blast_cold",
    "P_blast",
    "T_blast",
    "PI",
    "DP_total",
    "DP_upper",
    "DP_lower",
    "GasUtil",
]


def fetch_json(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def validate_core_rows(base_url: str, rows: list, count: object, scope: str) -> int:
    actual_ids = [str(item.get("id") or "") for item in rows]
    series_count = sum(bool(item.get("series_60m")) for item in rows)
    if actual_ids != EXPECTED_IDS:
        raise RuntimeError(f"{base_url}: {scope} core variable IDs do not match")
    if int(count or 0) != 19:
        raise RuntimeError(f"{base_url}: {scope} core variable count is not 19")
    if series_count != 19:
        raise RuntimeError(
            f"{base_url}: only {series_count}/19 {scope} series have data"
        )
    return series_count


def wait_for_contract(
    base_url: str, label: str, timeout: float, *, accept_incomplete: bool = False
) -> dict:
    deadline = time.monotonic() + timeout
    endpoint = (
        base_url.rstrip("/")
        + "/api/diagnosis-ai-analysis?"
        + urllib.parse.urlencode({"label": label})
    )
    last: dict = {}
    last_error = ""
    while time.monotonic() < deadline:
        try:
            last = fetch_json(endpoint, timeout=min(30.0, timeout))
            last_error = ""
        except (OSError, http.client.HTTPException, urllib.error.URLError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(2.0)
            continue
        analysis = last.get("analysis") or {}
        if analysis.get("schema_version") != "diagnosis_ai_analysis.v4":
            raise RuntimeError(f"{base_url}: schema is not v4")
        early_rows = analysis.get("core_variable_evidence") or []
        early_series_count = validate_core_rows(
            base_url,
            early_rows,
            analysis.get("core_variable_count"),
            "early",
        )
        if accept_incomplete and analysis.get("state") in {
            "preparing",
            "reasoning",
            "completed",
            "failed",
        }:
            return {
                "base_url": base_url,
                "state": analysis.get("state"),
                "schema_version": analysis.get("schema_version"),
                "bucket_ts": analysis.get("bucket_ts"),
                "target_label": analysis.get("target_label"),
                "core_variable_count": 19,
                "core_series_count": early_series_count,
                "ids_match": True,
                "available_before_model_completion": True,
            }
        if analysis.get("state") == "completed":
            payload = analysis.get("analysis") or {}
            rows = payload.get("core_variable_evidence") or []
            series_count = validate_core_rows(
                base_url,
                rows,
                payload.get("core_variable_count"),
                "completed",
            )
            return {
                "base_url": base_url,
                "state": analysis.get("state"),
                "schema_version": analysis.get("schema_version"),
                "bucket_ts": analysis.get("bucket_ts"),
                "target_label": analysis.get("target_label"),
                "core_variable_count": 19,
                "core_series_count": series_count,
                "ids_match": True,
                "available_before_model_completion": early_series_count == 19,
            }
        time.sleep(2.0)
    state = (last.get("analysis") or {}).get("state")
    raise TimeoutError(
        f"{base_url}: analysis did not complete; "
        f"last state={state!r}; last error={last_error!r}"
    )


def verify_lightweight_contract(base_url: str, label: str, timeout: float) -> dict:
    endpoint = (
        base_url.rstrip("/")
        + "/api/diagnosis-core-evidence?"
        + urllib.parse.urlencode({"label": label})
    )
    response = fetch_json(endpoint, timeout=min(30.0, timeout))
    evidence = response.get("evidence") or {}
    if evidence.get("schema_version") != "diagnosis_core_evidence.v1":
        raise RuntimeError(f"{base_url}: lightweight schema is not v1")
    rows = evidence.get("core_variable_evidence") or []
    series_count = validate_core_rows(
        base_url,
        rows,
        evidence.get("core_variable_count"),
        "lightweight",
    )
    return {
        "base_url": base_url,
        "state": evidence.get("state"),
        "schema_version": evidence.get("schema_version"),
        "diagnosis_ts": evidence.get("diagnosis_ts"),
        "target_label": evidence.get("target_label"),
        "core_variable_count": 19,
        "core_series_count": series_count,
        "ids_match": True,
        "read_only": bool(evidence.get("read_only")),
        "independent_of_model_completion": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", action="append", required=True)
    parser.add_argument("--label", default="normal")
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--accept-incomplete", action="store_true")
    parser.add_argument("--lightweight", action="store_true")
    args = parser.parse_args()
    results = [
        (
            verify_lightweight_contract(base_url, args.label, args.timeout)
            if args.lightweight
            else wait_for_contract(
                base_url,
                args.label,
                args.timeout,
                accept_incomplete=args.accept_incomplete,
            )
        )
        for base_url in args.base_url
    ]
    print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

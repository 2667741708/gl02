"""Freeze the authorized 822-case V52 scheduled retest plan without exposing prompts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "chiqiongblastfuenace:latest"
MODEL_DIGEST = "e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124"
FORBIDDEN_CASE = "TPL-10C8C8FAF2C694EF"
APPROVED_LIVE_RUNTIME_DELTA = {
    "proxy": {
        "relative": "高炉前端数据/智能助手/backend/ollama_proxy_server.py",
        "base_sha256": "a6da5b84ddab29bd05fc51c23f6a181338e0d5bed446ee9fb99860f5dd5b12fa",
        "live_sha256": "9d842f276aa9dfb2828490d211f61bfa49cdfb18bd09e32288592fc50d02ca45",
        "working_tree_diff_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    },
    "added_module": {
        "relative": "高炉前端数据/智能助手/backend/same_port_websocket_proxy.py",
        "live_sha256": "3ab7dbf96498afda4aed7940aeb27fdd593beb0666303d92870f20f47b931241",
    },
    "reason": "same_port_websocket_and_shared_guest_owner_fix_committed_20260921",
}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def prior_completed_records(values: list[str]) -> list[dict]:
    records = []
    for value in values:
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError("prior completed record must be CASE_ID:CLAIM_SHA256:RESULT_SHA256")
        case_id, claim_hash, result_hash = parts
        if not case_id or any(len(item) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in item)
                              for item in (claim_hash, result_hash)):
            raise ValueError("invalid prior completed record")
        records.append({
            "case_id": case_id,
            "claim_sha256": claim_hash.lower(),
            "result_sha256": result_hash.lower(),
            "request_count": 1,
            "automatic_retries": 0,
            "http_status": 200,
            "transport_error": False,
            "terminated": True,
            "done": True,
            "proven_complete": True,
        })
    return records


def build(args: argparse.Namespace) -> dict:
    if sha(args.source_plan) != args.source_sha256:
        raise ValueError("source failure plan hash changed")
    source = read(args.source_plan)
    cases = source.get("cases")
    if not isinstance(cases, list) or len(cases) != 822:
        raise ValueError("authorized 822-case failure cohort required")
    ids = [case.get("case_id") for case in cases]
    if len(set(ids)) != 822 or FORBIDDEN_CASE in ids:
        raise ValueError("duplicate or uncertain-send case in source plan")
    prior = prior_completed_records(args.prior_completed)
    prior_ids = [record["case_id"] for record in prior]
    if len(set(prior_ids)) != len(prior_ids) or any(case_id not in set(ids) for case_id in prior_ids):
        raise ValueError("prior completed cases must be unique members of the authorized cohort")
    remaining_cases = [case for case in cases if case.get("case_id") not in set(prior_ids)]

    recipe = read(ROOT / "tools/qa_routing_release_extensions.json")["v52"]
    package = read(args.candidate_manifest)
    runtime_hashes = dict(recipe["read_files"])
    for name, spec in recipe["artifacts"].items():
        candidate = package["files"].get(name)
        if not candidate or len(str(candidate.get("sha256") or "")) != 64:
            raise ValueError(f"candidate manifest missing {name}")
        relative = spec["relative"]
        expected = str(candidate["sha256"]).lower()
        if relative in runtime_hashes and runtime_hashes[relative].lower() != expected:
            raise ValueError(f"conflicting runtime pin for {relative}")
        runtime_hashes[relative] = expected

    if runtime_hashes.get("数据库同步和存取/config/点位语义目录.json"):
        raise ValueError("point catalog must use its dedicated pin")
    proxy_delta = APPROVED_LIVE_RUNTIME_DELTA["proxy"]
    if runtime_hashes.get(proxy_delta["relative"]) != proxy_delta["base_sha256"]:
        raise ValueError("approved live delta no longer descends from the reviewed V52 bytes")
    runtime_hashes[proxy_delta["relative"]] = proxy_delta["live_sha256"]
    added_module = APPROVED_LIVE_RUNTIME_DELTA["added_module"]
    runtime_hashes[added_module["relative"]] = added_module["live_sha256"]
    catalog_hash = recipe["read_files"]["高炉前端数据/智能助手/mcp/gl02_static_pressure_points.json"]
    point_catalog = args.point_catalog
    if sha(point_catalog) != args.point_catalog_sha256:
        raise ValueError("point catalog hash changed")

    return {
        "schema": "bf.qa.v52-scheduled-retest-plan.v1",
        "requirement_id": "REQ-QA-V52-SCHEDULED-FAILURE-RETEST-20260921",
        "execution_id": args.execution_id,
        "phase": "after-v52",
        "application_version": "V52",
        "production_commit": args.production_commit,
        "immutable_ref": "refs/prod-8093/20260921/qa-routing-v52-20260921-r1",
        "source_failure_plan_sha256": args.source_sha256,
        "authorized_case_count": 822,
        "prior_completed_records": prior,
        "collector_sha256": sha(args.collector),
        "catalog_sha256": args.point_catalog_sha256,
        "static_pressure_catalog_sha256": catalog_hash,
        "runtime_hashes": dict(sorted(runtime_hashes.items())),
        "approved_live_runtime_delta": APPROVED_LIVE_RUNTIME_DELTA,
        "process_identity": {
            "port": 8093,
            "pid": args.service_pid,
            "create_time": args.service_create_time,
        },
        "model_identity": {
            "name": MODEL_NAME,
            "digest": MODEL_DIGEST,
            "approved_digests": [MODEL_DIGEST],
            "switch_allowed": False,
            "fallback_allowed": False,
            "same_name_replacement_allowed": False,
        },
        "schedule": {
            "timezone": "Asia/Shanghai",
            "start": args.start,
            "end": args.end,
            "poll_seconds": args.poll_seconds,
            "stable_observations": args.stable_observations,
            "external_user_quiet_seconds": args.external_user_quiet_seconds,
            "gpu_utilization_max_percent": args.gpu_utilization_max_percent,
            "test_conversation_title_prefix": "回归基线 ",
        },
        "cases": remaining_cases,
        "policy": {
            "one_post_per_case": True,
            "automatic_replay": False,
            "uncertain_request_action": "stop_and_preserve_evidence",
            "outside_schedule_action": "wait_without_claim",
            "external_user_activity_action": "wait_without_claim",
            "semantic_acceptance": "required_after_collection",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--point-catalog", type=Path, required=True)
    parser.add_argument("--point-catalog-sha256", required=True)
    parser.add_argument("--collector", type=Path, required=True)
    parser.add_argument("--production-commit", required=True)
    parser.add_argument("--service-pid", type=int, required=True)
    parser.add_argument("--service-create-time", type=float, required=True)
    parser.add_argument("--prior-completed", action="append", default=[])
    parser.add_argument("--execution-id", default="qa-v52-scheduled-retest-20260921-r1")
    parser.add_argument("--start", default="22:30")
    parser.add_argument("--end", default="07:30")
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--stable-observations", type=int, default=3)
    parser.add_argument("--external-user-quiet-seconds", type=int, default=300)
    parser.add_argument("--gpu-utilization-max-percent", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = build(args)
    write_new(args.output, plan)
    print(json.dumps({
        "ok": True,
        "output": str(args.output),
        "plan_sha256": sha(args.output),
        "case_count": len(plan["cases"]),
        "prior_completed_count": len(plan["prior_completed_records"]),
        "runtime_pin_count": len(plan["runtime_hashes"]),
        "schedule": plan["schedule"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

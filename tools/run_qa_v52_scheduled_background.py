"""Timer-driven V52 failure retest supervisor with durable no-replay evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo


MODEL_NAME = "chiqiongblastfuenace:latest"
MODEL_DIGEST = "e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124"
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
EXPECTED_FILES = {
    "worker.py", "batch.py", "collector.py", "plan.private.json", "summary.py", "start.ps1"
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".next")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def runtime_hash_matches(path: Path, expected: str | set[str], hash_reader=sha, pause=time.sleep) -> bool:
    """Tolerate one partial read, then require three consecutive expected bytes."""
    allowed = {expected} if isinstance(expected, str) else set(expected)
    if hash_reader(path) in allowed:
        return True
    consecutive = 0
    for _ in range(5):
        pause(1)
        if hash_reader(path) in allowed:
            consecutive += 1
            if consecutive == 3:
                return True
        else:
            consecutive = 0
    return False


def clock_minutes(value: str) -> int:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(value)):
        raise ValueError("invalid schedule clock")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def inside_window(now: datetime, start: str, end: str) -> bool:
    current = now.hour * 60 + now.minute
    first, last = clock_minutes(start), clock_minutes(end)
    if first == last:
        return True
    if first < last:
        return first <= current < last
    return current >= first or current < last


def identity_matches(tags: dict, resident: dict) -> bool:
    if not isinstance(tags, dict) or not isinstance(resident, dict):
        return False
    installed = tags.get("models")
    loaded = resident.get("models")
    if not isinstance(installed, list) or not isinstance(loaded, list):
        return False
    if any(not isinstance(row, dict) for row in installed + loaded):
        return False
    alias = [row for row in installed if row.get("name") == MODEL_NAME]
    version = [row for row in installed if row.get("name") == "chiqiongblastfuenace:1"]
    return (
        len(alias) == len(version) == len(loaded) == 1
        and alias[0].get("digest") == version[0].get("digest") == loaded[0].get("digest") == MODEL_DIGEST
        and loaded[0].get("name") == MODEL_NAME
    )


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def exact_model_ready() -> bool:
    try:
        status = get_json("http://127.0.0.1:8093/api/ollama/status")
        if not all(status.get(key) is True for key in ("ok", "proxy_ok", "ollama_ok", "model_ok")):
            return False
        return identity_matches(
            get_json("http://127.0.0.1:11434/api/tags"),
            get_json("http://127.0.0.1:11434/api/ps"),
        )
    except Exception:
        return False


def gpu_utilization_percent() -> int | None:
    executable = shutil.which("nvidia-smi")
    if not executable:
        for candidate in (
            Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/nvidia-smi.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "NVIDIA Corporation/NVSMI/nvidia-smi.exe",
        ):
            if candidate.is_file():
                executable = str(candidate)
                break
    if not executable:
        return None
    result = subprocess.run(
        [executable, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode:
        return None
    values = [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]
    return max(values) if values else None


def production_listener_process(psutil_module, root: Path):
    listener_pids = {
        connection.pid
        for connection in psutil_module.net_connections(kind="tcp")
        if connection.status == "LISTEN" and connection.laddr.port == 8093 and connection.pid is not None
    }
    listeners = []
    for pid in listener_pids:
        try:
            candidate = psutil_module.Process(pid)
            if any(str(root).casefold() in part.casefold() for part in candidate.cmdline()):
                listeners.append(candidate)
        except (psutil_module.AccessDenied, psutil_module.NoSuchProcess):
            continue
    if len(listeners) != 1:
        raise RuntimeError("ambiguous 8093 listener")
    return listeners[0]


def verify_process_identity(plan: dict, root: Path, psutil_module=None) -> None:
    if psutil_module is None:
        import psutil as psutil_module
    expected = plan["process_identity"]
    process = production_listener_process(psutil_module, root)
    if process.pid != expected["pid"] or abs(process.create_time() - expected["create_time"]) > 0.001:
        raise ValueError("8093 process identity changed")


def latest_external_user_epoch(root: Path, title_prefix: str) -> float | None:
    """Read the latest non-retest user message using the production process environment."""
    import psutil
    process = production_listener_process(psutil, root)
    process_env = process.environ()
    backend = root / "高炉前端数据/智能助手/backend"
    module_path = backend / "assistant_pg.py"
    original = dict(os.environ)
    module_name = "qa_v52_schedule_assistant_pg"
    try:
        os.environ.update(process_env)
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        params = module.pg_params()
        schema = module.schema_name()
    finally:
        os.environ.clear()
        os.environ.update(original)
        sys.modules.pop(module_name, None)
    import psycopg
    connection = psycopg.connect(**params)
    params["password"] = ""
    try:
        connection.execute("SET TRANSACTION READ ONLY")
        row = connection.execute(
            f'''SELECT m.created_at
                FROM "{schema}".qa_messages m
                JOIN "{schema}".qa_conversations c ON c.id=m.conversation_id
                WHERE m.role='user' AND c.title NOT LIKE %s
                ORDER BY m.id DESC LIMIT 1''',
            (title_prefix + "%",),
        ).fetchone()
    finally:
        connection.rollback()
        connection.close()
    if not row or not row[0]:
        return None
    observed = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return observed.timestamp()


def validate_plan(plan: dict) -> None:
    if plan.get("schema") != "bf.qa.v52-scheduled-retest-plan.v1":
        raise ValueError("unexpected plan schema")
    if plan.get("application_version") != "V52":
        raise ValueError("V52 plan required")
    identity = plan.get("model_identity")
    if not isinstance(identity, dict) or identity.get("name") != MODEL_NAME:
        raise ValueError("fixed model name required")
    if identity.get("digest") != MODEL_DIGEST or identity.get("approved_digests") != [MODEL_DIGEST]:
        raise ValueError("single fixed model digest required")
    if plan.get("approved_live_runtime_delta") != APPROVED_LIVE_RUNTIME_DELTA:
        raise ValueError("unreviewed live runtime delta")
    process_identity = plan.get("process_identity")
    if not isinstance(process_identity, dict) or process_identity.get("port") != 8093:
        raise ValueError("8093 process identity required")
    if not isinstance(process_identity.get("pid"), int) or process_identity["pid"] <= 0:
        raise ValueError("invalid 8093 process pid")
    if not isinstance(process_identity.get("create_time"), (int, float)):
        raise ValueError("invalid 8093 process create time")
    cases = plan.get("cases")
    prior = plan.get("prior_completed_records") or []
    if not isinstance(cases, list) or not isinstance(prior, list):
        raise ValueError("authorized cohort required")
    if plan.get("authorized_case_count") != 822 or len(cases) + len(prior) != 822:
        raise ValueError("authorized 822-case cohort required")
    ids = [case.get("case_id") for case in cases]
    prior_ids = [record.get("case_id") for record in prior if isinstance(record, dict)]
    if len(prior_ids) != len(prior) or len(set(ids + prior_ids)) != 822 or "TPL-10C8C8FAF2C694EF" in ids + prior_ids:
        raise ValueError("duplicate or uncertain case forbidden")
    for record in prior:
        if record.get("proven_complete") is not True:
            raise ValueError("unproven prior case forbidden")
        if any(record.get(key) != value for key, value in {
            "request_count": 1, "automatic_retries": 0, "http_status": 200,
            "transport_error": False, "terminated": True, "done": True,
        }.items()):
            raise ValueError("invalid prior transport evidence")
        for key in ("claim_sha256", "result_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(record.get(key) or "")):
                raise ValueError("invalid prior evidence hash")
    schedule = plan.get("schedule")
    if not isinstance(schedule, dict):
        raise ValueError("schedule required")
    clock_minutes(schedule.get("start"))
    clock_minutes(schedule.get("end"))
    if schedule.get("timezone") != "Asia/Shanghai":
        raise ValueError("controlled timezone required")


def verify_inputs(stage: Path, root: Path, manifest: dict, manifest_sha: str) -> dict:
    if sha(stage / "manifest.private.json") != manifest_sha:
        raise ValueError("manifest changed")
    if set(manifest.get("files") or {}) != EXPECTED_FILES:
        raise ValueError("sealed file set changed")
    for name, expected in manifest["files"].items():
        if sha(stage / name) != expected:
            raise ValueError(f"sealed file changed: {name}")
    plan = read(stage / "plan.private.json")
    validate_plan(plan)
    if sha(stage / "collector.py") != plan["collector_sha256"]:
        raise ValueError("collector changed")
    if not runtime_hash_matches(root / "数据库同步和存取/config/点位语义目录.json", plan["catalog_sha256"]):
        raise ValueError("point catalog changed")
    verify_process_identity(plan, root)
    for relative, expected in plan["runtime_hashes"].items():
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()) or not runtime_hash_matches(target, expected):
            raise ValueError(f"production runtime changed: {relative}")
    proxy_delta = plan["approved_live_runtime_delta"]["proxy"]
    diff = subprocess.run(
        ["git", "diff", "--binary", "--", proxy_delta["relative"]],
        cwd=root,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if diff.returncode or hashlib.sha256(diff.stdout).hexdigest() != proxy_delta["working_tree_diff_sha256"]:
        raise ValueError("approved live proxy delta changed")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", plan["production_commit"], "HEAD"],
        cwd=root,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if ancestry.returncode:
        raise ValueError("production no longer descends from V52 commit")
    return plan


def gate_status(plan: dict, root: Path, now_epoch: float | None = None) -> tuple[bool, str, dict]:
    schedule = plan["schedule"]
    now_epoch = time.time() if now_epoch is None else now_epoch
    now = datetime.fromtimestamp(now_epoch, ZoneInfo(schedule["timezone"]))
    evidence = {"observed_at": now.isoformat()}
    if not inside_window(now, schedule["start"], schedule["end"]):
        return False, "outside_schedule", evidence
    latest = latest_external_user_epoch(root, schedule["test_conversation_title_prefix"])
    evidence["latest_external_user_age_seconds"] = None if latest is None else round(now_epoch - latest, 3)
    if latest is not None and now_epoch - latest < int(schedule["external_user_quiet_seconds"]):
        return False, "recent_external_user_activity", evidence
    utilization = gpu_utilization_percent()
    evidence["gpu_utilization_percent"] = utilization
    if utilization is None:
        return False, "gpu_utilization_unavailable", evidence
    if utilization > int(schedule["gpu_utilization_max_percent"]):
        return False, "gpu_busy", evidence
    if not exact_model_ready():
        return False, "fixed_model_or_assistant_not_ready", evidence
    return True, "scheduled_gate_ready", evidence


def run(args: argparse.Namespace) -> None:
    stage, root, output = args.stage.resolve(), args.root.resolve(), args.output.resolve()
    if not output.is_relative_to((root / "logs").resolve()) or output == (root / "logs").resolve():
        raise ValueError("output must be a dedicated directory below production logs")
    manifest = read(stage / "manifest.private.json")
    plan = verify_inputs(stage, root, manifest, args.manifest_sha256)
    launch = read(output / "launch.claim")
    if launch.get("manifest_sha256") != args.manifest_sha256 or launch.get("automatic_replay") is not False:
        raise ValueError("launch claim invalid")
    with (output / "worker.claim").open("x", encoding="utf-8") as stream:
        json.dump({"pid": os.getpid(), "manifest_sha256": args.manifest_sha256, "created_at": time.time()}, stream)
    state = {
        "schema": "bf.qa.v52-scheduled-supervisor.v1",
        "requirement_id": plan["requirement_id"],
        "execution_id": plan["execution_id"],
        "pid": os.getpid(),
        "state": "waiting_for_schedule",
        "total": len(plan["cases"]),
        "completed": 0,
        "requests": 0,
        "automatic_replay": False,
        "model_management_operations": 0,
        "application_version": "V52",
        "production_commit": plan["production_commit"],
        "manifest_sha256": args.manifest_sha256,
        "plan_sha256": sha(stage / "plan.private.json"),
        "schedule": plan["schedule"],
        "batch_progress_path": str(output / "batch/progress.json"),
        "started_at": time.time(),
        "stable_observations": 0,
    }
    progress = output / "progress.json"
    stop = output / "STOP"
    write(progress, state)
    def wait_for_gate(_deadline=None, _now=None):
        stable = 0
        while stable < int(plan["schedule"]["stable_observations"]):
            if stop.exists():
                raise RuntimeError("operator stop; no next request sent")
            verify_inputs(stage, root, manifest, args.manifest_sha256)
            ready, reason, evidence = gate_status(plan, root)
            stable = stable + 1 if ready else 0
            state.update(
                state="gate_stabilizing" if ready else "waiting_for_schedule_or_idle",
                reason=reason,
                gate_evidence=evidence,
                stable_observations=stable,
                updated_at=time.time(),
            )
            write(progress, state)
            if stable < int(plan["schedule"]["stable_observations"]):
                time.sleep(int(plan["schedule"]["poll_seconds"]))

    try:
        spec = importlib.util.spec_from_file_location("sealed_v52_scheduled_batch", stage / "batch.py")
        batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(batch)
        original_verify = batch.verify
        verify_call_count = 0

        def guarded_verify(batch_plan, batch_root, collector):
            nonlocal verify_call_count
            verify_call_count += 1
            verify_inputs(stage, root, manifest, args.manifest_sha256)
            if not exact_model_ready():
                raise RuntimeError("fixed model identity changed; no next request sent")
            identity = original_verify(batch_plan, batch_root, collector)
            # The sealed batch calls verify once before the loop, then before readiness,
            # immediately before claim, and after every completed turn. Calls divisible
            # by three are therefore the per-case pre-claim boundary.
            if verify_call_count % 3 == 0:
                wait_for_gate()
                verify_inputs(stage, root, manifest, args.manifest_sha256)
                identity = original_verify(batch_plan, batch_root, collector)
            if not exact_model_ready():
                raise RuntimeError("fixed model identity changed; no next request sent")
            return identity

        batch.verify = guarded_verify
        batch.model_ready = exact_model_ready
        wait_for_gate()
        state.update(state="running", reason="scheduled_serial_v52_retest", updated_at=time.time())
        write(progress, state)
        previous_argv = sys.argv
        try:
            sys.argv = [
                str(stage / "batch.py"), "--root", str(root), "--plan", str(stage / "plan.private.json"),
                "--collector", str(stage / "collector.py"), "--output", str(output / "batch"), "--execute",
            ]
            with (output / "worker.stdout").open("x", encoding="utf-8", newline="\n") as out:
                with (output / "worker.stderr").open("x", encoding="utf-8", newline="\n") as err:
                    old_out, old_err = sys.stdout, sys.stderr
                    try:
                        sys.stdout, sys.stderr = out, err
                        batch.main()
                    finally:
                        sys.stdout, sys.stderr = old_out, old_err
        finally:
            sys.argv = previous_argv
        result = read(output / "batch/progress.json")
        state.update({key: result[key] for key in ("completed", "requests")})
        if result.get("state") != "completed":
            raise RuntimeError("batch stopped; readonly recovery required")
        summary_spec = importlib.util.spec_from_file_location("sealed_v52_summary", stage / "summary.py")
        summary = importlib.util.module_from_spec(summary_spec)
        summary_spec.loader.exec_module(summary)
        receipt = summary.summarize(stage / "plan.private.json", output / "batch")
        write(output / "collection-summary.json", receipt)
        if not receipt["transport_gate_passed"]:
            raise RuntimeError("collection transport gate failed; semantic review not started")
        state.update(
            state="collection_completed_pending_acceptance",
            reason="all_cases_collected_once_semantic_review_required",
            transport_gate_passed=True,
            semantic_acceptance="pending_full_answer_review",
        )
    except Exception as exc:
        batch_progress = output / "batch/progress.json"
        if batch_progress.exists():
            try:
                result = read(batch_progress)
                state.update({key: result[key] for key in ("completed", "requests")})
            except Exception:
                state["batch_progress_unavailable"] = True
        state.update(
            state="blocked_no_replay",
            error_type=type(exc).__name__,
            reason=str(exc),
            semantic_acceptance="not_started",
        )
    finally:
        state["updated_at"] = time.time()
        write(progress, state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required; no questions sent")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

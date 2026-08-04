from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path


TASK_PATH = "\\BlastFurnaceServices\\"
TASK_NAME = "V3AutoPreviewProxy8094"
PROXY_MARKERS = ("V4_8093_PREVIEW", "ollama_proxy_server.py")
RUNNER_MARKER = "run_22012_8094_preview.ps1"


def run_ps(script: str, timeout: int = 5, check: bool = True) -> str:
    prefix = (
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "$OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "$ProgressPreference='SilentlyContinue';"
        "$ErrorActionPreference='Stop';"
    )
    encoded = base64.b64encode((prefix + script).encode("utf-16le")).decode("ascii")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        capture_output=True,
        timeout=timeout,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace").strip()
    stderr = completed.stderr.decode("utf-8", errors="replace").strip()
    if check and completed.returncode != 0:
        raise RuntimeError(stderr or stdout or f"PowerShell exit {completed.returncode}")
    return stdout


def snapshot() -> dict:
    script = rf"""
$connections=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)
$processes=@(Get-CimInstance Win32_Process -ErrorAction Stop)
$matches=@($processes | Where-Object {{
  $_.Name -eq 'python.exe' -and $_.CommandLine -and
  $_.CommandLine.Contains('V4_8093_PREVIEW') -and
  $_.CommandLine.Contains('ollama_proxy_server.py')
}} | ForEach-Object {{
  $item=$_
  $parent=$processes | Where-Object ProcessId -eq $item.ParentProcessId | Select-Object -First 1
  [ordered]@{{
    pid=[int]$item.ProcessId
    parentPid=[int]$item.ParentProcessId
    parentExists=[bool]$parent
    parentCommand=if($parent){{$parent.CommandLine}}else{{$null}}
    listenPorts=@($connections | Where-Object OwningProcess -eq $item.ProcessId |
      Select-Object -ExpandProperty LocalPort)
  }}
}})
$runners=@($processes | Where-Object {{
  $_.CommandLine -and $_.CommandLine.Contains('{RUNNER_MARKER}')
}} | ForEach-Object {{[int]$_.ProcessId}})
$task=Get-ScheduledTask -TaskPath '{TASK_PATH}' -TaskName '{TASK_NAME}' -ErrorAction Stop
[ordered]@{{
  taskState=$task.State.ToString()
  ports=[ordered]@{{
    p8093=@($connections | Where-Object LocalPort -eq 8093 | Select-Object -ExpandProperty OwningProcess)
    p8094=@($connections | Where-Object LocalPort -eq 8094 | Select-Object -ExpandProperty OwningProcess)
    p8768=@($connections | Where-Object LocalPort -eq 8768 | Select-Object -ExpandProperty OwningProcess)
    p8770=@($connections | Where-Object LocalPort -eq 8770 | Select-Object -ExpandProperty OwningProcess)
  }}
  matches=$matches
  runners=$runners
}} | ConvertTo-Json -Compress -Depth 7
"""
    return json.loads(run_ps(script))


def ensure_dependencies(state: dict) -> None:
    for key in ("p8093", "p8768", "p8770"):
        if not state["ports"].get(key):
            raise RuntimeError(f"Required listener missing: {key}")


def stop_task() -> None:
    run_ps(
        f"Stop-ScheduledTask -TaskPath '{TASK_PATH}' -TaskName '{TASK_NAME}';"
        "'stopped'"
    )


def start_task() -> None:
    run_ps(
        f"Start-ScheduledTask -TaskPath '{TASK_PATH}' -TaskName '{TASK_NAME}';"
        "'started'"
    )


def stop_pids(pids: list[int]) -> None:
    unique = sorted({int(pid) for pid in pids if int(pid) > 0})
    if not unique:
        return
    joined = ",".join(str(pid) for pid in unique)
    run_ps(
        f"Stop-Process -Id @({joined}) -Force -ErrorAction SilentlyContinue;"
        f"@({joined}) | ConvertTo-Json -Compress"
    )


def is_8094_candidate(item: dict) -> bool:
    ports = {int(port) for port in item.get("listenPorts") or []}
    parent_command = item.get("parentCommand") or ""
    if 8093 in ports:
        return False
    return (
        8094 in ports
        or not item.get("parentExists")
        or RUNNER_MARKER in parent_command
    )


def wait_for_clean_port(timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    state = snapshot()
    while state["ports"].get("p8094") and time.monotonic() < deadline:
        time.sleep(0.5)
        state = snapshot()
    return state


def wait_for_fresh_listener(old_pids: set[int], timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    state = snapshot()
    while time.monotonic() < deadline:
        listeners = {int(pid) for pid in state["ports"].get("p8094") or []}
        fresh = listeners - old_pids
        if fresh:
            return state
        time.sleep(0.5)
        state = snapshot()
    raise RuntimeError("8094 did not obtain a fresh listener within 30 seconds")


def http_get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read(200_000).decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status": int(response.status),
                "body": body[:4000],
            }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    before = snapshot()
    ensure_dependencies(before)
    old_8094_pids = {int(pid) for pid in before["ports"].get("p8094") or []}
    protected_8093_pids = {int(pid) for pid in before["ports"].get("p8093") or []}

    stop_task()
    time.sleep(0.8)
    stopped = snapshot()
    ensure_dependencies(stopped)

    candidates = [
        int(item["pid"])
        for item in stopped.get("matches") or []
        if is_8094_candidate(item)
    ]
    candidates.extend(int(pid) for pid in stopped.get("runners") or [])
    candidates = [
        pid for pid in sorted(set(candidates)) if pid not in protected_8093_pids
    ]
    stop_pids(candidates)

    clean = wait_for_clean_port()
    ensure_dependencies(clean)
    if clean["ports"].get("p8094"):
        raise RuntimeError(
            f"8094 remains occupied by {clean['ports']['p8094']} after targeted cleanup"
        )

    start_task()
    after = wait_for_fresh_listener(old_8094_pids)
    ensure_dependencies(after)
    listeners = {int(pid) for pid in after["ports"].get("p8094") or []}
    fresh_listeners = sorted(listeners - old_8094_pids)
    if len(fresh_listeners) != 1:
        raise RuntimeError(f"Expected one fresh 8094 listener, got {fresh_listeners}")
    fresh_pid = fresh_listeners[0]
    fresh_match = next(
        (item for item in after.get("matches") or [] if int(item["pid"]) == fresh_pid),
        None,
    )
    if not fresh_match:
        raise RuntimeError("Fresh 8094 listener is not the expected V4 proxy")
    if RUNNER_MARKER not in (fresh_match.get("parentCommand") or ""):
        raise RuntimeError("Fresh 8094 listener is not owned by the managed runner")

    root_health = http_get("http://127.0.0.1:8094/")
    ollama_health = http_get("http://127.0.0.1:8094/api/ollama/status")
    result = {
        "ok": bool(root_health.get("ok") and ollama_health.get("ok")),
        "recoveredAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "removedPids": candidates,
        "protected8093Pids": sorted(protected_8093_pids),
        "old8094Pids": sorted(old_8094_pids),
        "fresh8094Pid": fresh_pid,
        "taskState": after["taskState"],
        "ports": after["ports"],
        "rootHealth": root_health,
        "ollamaHealth": ollama_health,
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            Path(__file__).unlink()
        except OSError:
            pass

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REQUIREMENT_ID = "BUG-8093-GUEST-UI-RECOVERY-20260814"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def find_line(lines: list[str], marker: str, start: int = 0, end: int | None = None) -> int:
    limit = len(lines) if end is None else end
    matches = [index for index in range(start, limit) if marker in lines[index]]
    if len(matches) != 1:
        raise RuntimeError(f"expected one line for {marker!r}, found {len(matches)}")
    return matches[0]


def normalize_downloaded_baseline(raw: bytes, expected_sha256: str) -> bytes:
    if sha256_bytes(raw) == expected_sha256:
        return raw
    if raw.endswith(b"\n") and sha256_bytes(raw[:-1]) == expected_sha256:
        return raw[:-1]
    raise RuntimeError(
        f"production baseline mismatch: expected={expected_sha256} actual={sha256_bytes(raw)}"
    )


def build_artifact(baseline_text: str, local_text: str) -> str:
    baseline = baseline_text.splitlines(keepends=True)
    local = local_text.splitlines(keepends=True)

    baseline_login_start = find_line(baseline, "function qaEnsureSessionLoginStyle()")
    baseline_login_end = find_line(baseline, "function QaProjectNavMenuV2(", baseline_login_start)
    local_login_start = find_line(local, "function qaEnsureSessionLoginStyle()")
    local_login_end = find_line(local, "function QaProjectNavMenuV2(", local_login_start)
    baseline[baseline_login_start:baseline_login_end] = local[local_login_start:local_login_end]

    baseline_tab_start = find_line(baseline, "function QaTab({ buf, diagnosis })")
    baseline_tab_end = find_line(baseline, "function reportEnsureStyle()", baseline_tab_start)
    local_tab_start = find_line(local, "function QaTab({ buf, diagnosis })")
    local_tab_end = find_line(local, "function reportEnsureStyle()", local_tab_start)

    baseline_state = find_line(baseline, "const [conversations, setConversations]", baseline_tab_start, baseline_tab_end)
    local_state = find_line(local, "const [conversations, setConversations]", local_tab_start, local_tab_end)
    state_line = local[local_state].replace(", executionTraceRef = useRef([])", "")
    baseline[baseline_state] = state_line

    baseline_bootstrap = find_line(baseline, "const loadBootstrap = async", baseline_tab_start, baseline_tab_end)
    local_bootstrap = find_line(local, "const loadBootstrap = async", local_tab_start, local_tab_end)
    baseline[baseline_bootstrap] = local[local_bootstrap]

    baseline_initial_effect = find_line(
        baseline,
        "useEffect(() => { loadBootstrap(false); checkHealth(); loadShortConversations();",
        baseline_tab_start,
        baseline_tab_end,
    )
    local_initial_effect = find_line(
        local,
        "useEffect(() => { loadBootstrap(false); checkHealth() }, []);",
        local_tab_start,
        local_tab_end,
    )
    local_context_effect = find_line(
        local,
        "document.addEventListener('bf:qa-open-conversation'",
        local_initial_effect,
        local_tab_end,
    )
    baseline[baseline_initial_effect : baseline_initial_effect + 1] = local[
        local_initial_effect:local_context_effect
    ]

    baseline_tab_end = find_line(baseline, "function reportEnsureStyle()", baseline_tab_start)
    baseline_send = find_line(baseline, "const send = async () =>", baseline_tab_start, baseline_tab_end)
    send_line = baseline[baseline_send]
    context_start = send_line.index("const currentSnapshot =")
    callbacks_start = send_line.index(", { onStart:", context_start)
    guest_request = (
        "const currentSnapshot = qaBuildContextSnapshot({ diagnosis, buf, rangeMinutes: 480, "
        "mode: 'hidden_8h_fallback' }), guestMode = accessMode === 'guest_shared', "
        "context_assets = guestMode ? [] : basket.map(x => qaAssetPayload(x.asset, x.mode, "
        "x.selectedText)), request = guestMode ? { conversation_id: activeId, message: text, "
        "current_snapshot: currentSnapshot } : { conversation_id: activeId, "
        "project_id: selectedProject?.id || null, message: text, current_snapshot: currentSnapshot, "
        "context_assets, context_mode: 'operator_selected', manual_context_text: manualText }; "
        "await qaServerChatStream(request"
    )
    baseline[baseline_send] = send_line[:context_start] + guest_request + send_line[callbacks_start:]

    baseline_tab_end = find_line(baseline, "function reportEnsureStyle()", baseline_tab_start)
    baseline_return = find_line(
        baseline,
        'return <div className="qa-server-shell qa-project-shell"',
        baseline_tab_start,
        baseline_tab_end,
    )
    local_guest_mode = find_line(local, "const guestMode = accessMode === 'guest_shared';", local_tab_start, local_tab_end)
    local_return = find_line(
        local,
        'return <div className="qa-server-shell qa-project-shell"',
        local_guest_mode,
        local_tab_end,
    )
    baseline[baseline_return : baseline_return + 1] = [local[local_guest_mode], local[local_return]]

    artifact = "".join(baseline)
    required_markers = (
        "function QaGuestNav",
        "access_mode || 'authenticated'",
        "登录私有会话（可选）",
        "继续匿名使用",
        "guestMode ? { conversation_id: activeId, message: text, current_snapshot: currentSnapshot }",
        "setInterval(refreshGuest, 5000)",
        "abc33-initial-question-20260814-r1",
    )
    for marker in required_markers:
        if marker not in artifact:
            raise RuntimeError(f"required marker missing from artifact: {marker}")
    if "function qaMergeExecutionTrace" in artifact:
        raise RuntimeError("unrelated execution-trace feature entered the minimal artifact")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--local-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-baseline-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    expected = args.expected_baseline_sha256.upper()
    baseline_bytes = normalize_downloaded_baseline(args.baseline.read_bytes(), expected)
    local_text = args.local_source.read_text(encoding="utf-8")
    artifact_text = build_artifact(baseline_bytes.decode("utf-8"), local_text)
    artifact_bytes = artifact_text.encode("utf-8")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(artifact_bytes)
    report = {
        "schema": "bf.8093.guest-frontend-artifact.v1",
        "requirement_id": REQUIREMENT_ID,
        "baseline_sha256": expected,
        "artifact_sha256": sha256_bytes(artifact_bytes),
        "artifact_bytes": len(artifact_bytes),
        "excluded_unrelated_execution_trace": True,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

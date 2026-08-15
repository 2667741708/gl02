# 8093 guarded deployment project contract

## Canonical identities

- Remote host: the configured 220.12 target used by `tools/remote_22012_exec.py`.
- Production root: `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW`.
- Managed 8093 service/guard: `BFV4PreviewProxy8093`.
- Supporting WebSocket service: `BFV4PreviewWs8768`.
- Service manager on 220.12: `tools\manage_22012_managed_services.ps1`.
- 8093 service config on 220.12: `tools\service_configs\22012_BFV4PreviewProxy8093.json`.
- Deployment mutex: `Global\BFV4PreviewProxy8093Deployment`.
- Required remote shell: `C:\Program Files\PowerShell\7\pwsh.exe`, PowerShell 7 Core.
- Required encoding: UTF-8 without BOM for console, pipeline, and PowerShell file operations.

The “guard” wording refers to the managed 8093 service contract. The page and static JavaScript do not have an independent rollback/file-lock daemon. The health-check task may supervise service health, but production installation must still use the managed service tool and deployment mutex.

## Protected boundaries

For an 8093-only update, preserve these listeners and processes unless a separate requirement explicitly authorizes them:

| Port | Role | Default treatment |
|---:|---|---|
| 8094 | independent preview page | PID unchanged |
| 8768 | diagnostic/WebSocket source | service running, PID unchanged |
| 8770 | pSpace realtime bridge | PID unchanged |
| 5432 | PostgreSQL | PID unchanged; no schema/data mutation |
| 11434 | approved Ollama runtime | PID unchanged |
| 8892 | soft-zone replay when present | PID unchanged |

Never stop the database, terminate Python by process name, or replace the 8094 page as a side effect of an 8093 deployment.

## Repository implementations to prefer

- Persistent local transport broker: `tools/remote_22012_session.py`; it reuses one authenticated Paramiko transport and delegates request semantics to `tools/remote_22012_exec.py`.
- Current full example with PowerShell 7, UTF-8, staged files, backup, atomic replacement, restart, API verification, protected PID checks, and rollback: `tools/remote_guarded_deploy_hcz_upward_rule_8093.ps1`.
- Matching local upload/run wrapper: `tools/deploy_hcz_upward_rule_22012.ps1`.
- Historical tooltip guard closure: `tools/remote_guarded_redeploy_8093_tooltip.ps1`. Treat its `powershell.exe` calls as historical compatibility debt; migrate copied logic to PowerShell 7 before reuse.
- Service recovery collision guidance: `docs/troubleshooting.md`, especially the `Global\BFV4PreviewProxy8093Deployment` contract.
- Long-term deployment flow: `docs/automation_traceability.md`.

Do not reuse a deployer merely because its name contains `8093`; confirm its file allowlist, protected ports, expected hashes, PowerShell runtime, API checks, and restart scope match the requested change.

## Required local wrapper sequence

The local wrapper must execute short, separately checkable stages:

1. In preparation, resolve exact files, run required checks once, and seal `bf.deploy.prepared-release.v1` with `scripts/release_manifest.py`.
2. Immediately before deployment, refresh the read-only remote state and verify the prepared manifest.
3. Generate `bf.deploy.delta-plan.v1`; stop without a service restart when it contains no changes.
4. Call `remote_22012_session.py ensure --allow-agents-password --workdir <production-root>` and prove `ssh_active=true`.
5. Call `remote_22012_session.py run -- --upload-only` for only delta artifacts plus the plan.
6. Stop immediately if staging fails.
7. Call `remote_22012_session.py run -- --script <remote-guarded-payload.ps1>` as a separate request over the same connection.
8. Stop immediately if remote structured acceptance reports failure.
9. Check broker status and leave it alive for the next operation.

Do not repeat preparation checks when the manifest seal, bound source/artifact hashes, validation results, scope, and live baseline still verify. Return to preparation after any mismatch or expanded scope. Run the semantic Luna `low` diff review and read-only remote preflight concurrently when both are required; neither branch may upload or mutate production.

Use the existing configured credential path through `--allow-agents-password`; never place a password in a script, command, log, or skill. Under the explicit standing authorization
`OPS-22012-WINDOWS-CREDENTIAL-SSH-RECOVERY-20260814`, a missing/empty/redaction-marker password file may be
restored only by `tools/restore_22012_ssh_secret_from_windows_credential.ps1` from the exact local Windows
Credential Manager target `TERMSRV/10.30.220.12`, after validating the leaf username `administrator`. The
helper may write only `%LOCALAPPDATA%\Codex\secrets\reliable-ssh\22012.pw`; it must never emit the password,
length, hash, or decrypted value to model context, logs, Git, reports, manifests, or another host/protocol.
If Windows refuses to export the secret, the helper may fall back only to the ACL-validated password file already
referenced by the fixed 220.12 Reliable SSH MCP configuration; no other credential search or inference is allowed.
Recovery is accepted only after two independent `pwsh -File` configurator runs and one fresh SSH authentication.
Reliable SSH MCP is an approved transport after identity verification, but it does not expand the task's remote-write scope and must keep automatic replay disabled.

The broker must bind only to localhost, keep its token below the current user's local application-data directory, send a 30-second SSH protocol keepalive, and serialize deployment requests. Reliable SSH MCP separates that from a 60-second read-only application identity heartbeat. A disconnected transport may be re-established between requests. A request that fails during remote execution is uncertain and must never be automatically replayed. Keep `session_id` stable for the broker lifetime; change `connection_id` and increment `reconnect_count` only after a real reconnect.

Verify transport reuse with repository files, not inline commands: run `tools\verify_22012_persistent_ssh_reuse.ps1` through local `pwsh.exe -File`; it must send `tools\remote_probe_22012_persistent_session.ps1` twice as independent UTF-8 payloads and the remote wrapper must execute each with PowerShell 7 `pwsh -File`. Accept only identical session/connection IDs and consecutive request counts.

When Python source confidentiality is requested, apply `python-artifact-protection.md` before staging. Compile locally and stage only the accepted native artifact; do not first upload source and compile it on 220.12.

Before each deployment, apply the reviewed preflights in `learned-failure-playbook.json`. After each deployment, record sanitized phase timing and error fingerprints through `deployment_memory.py`. Dynamic observations may become candidate lessons but cannot rewrite the Skill or authorize a production mutation until the promotion gates in `deployment-performance-and-learning.md` pass.

The prepared manifest and delta plan contract is defined in `two-phase-fast-deployment.md`. The remote payload must consume the exact sealed delta rather than a broader candidate file list. A local manifest never replaces the remote baseline check, deployment mutex, backup, rollback, or protected-PID validation.

When a displayed 8093 score overlaps ABC33, apply `abc33-score-source-and-archive.md`: display the time-aligned released ABC33 item, keep the replaced legacy value read-only for audit, and fail closed rather than falling back to a conflicting score.

## Required remote payload sequence

The remote payload owns a single critical section:

1. PowerShell 7/UTF-8 runtime assertion.
2. Stage, target, baseline hash, and marker validation.
3. Non-blocking global deployment mutex.
4. Protected service/listener snapshot.
5. Timestamped backup.
6. Managed stop of `BFV4PreviewProxy8093`.
7. Proof that port 8093 is down while protected listeners remain up.
8. Target-adjacent temporary copy and atomic move.
9. Installed/staged SHA-256 equality.
10. Managed start of `BFV4PreviewProxy8093` in `finally`.
11. HTTP/API/asset marker checks with cache busting.
12. Protected PID equality.
13. Structured JSON result and mutex release.

If any post-install check fails, restore the backup under the same mutex and re-run service/listener/isolation checks. Do not auto-retry a failed version.

## PowerShell runtime contract

Every new or modified `.ps1` must begin by rejecting non-Core or pre-7 runtimes and setting UTF-8 without BOM:

```powershell
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
```

Run repository PowerShell verification after changing a PowerShell entrypoint:

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1
```

## Minimum acceptance record

Require machine-readable fields:

```json
{
  "ok": true,
  "requirement_id": "REQ-...",
  "backup": "F:\\...\\backups\\...",
  "guard_paused": true,
  "guard_restored": true,
  "rollback_applied": false,
  "old_8093_pid": 0,
  "new_8093_pid": 0,
  "protected_before": {},
  "protected_after": {},
  "installed_hashes": {},
  "http_8093": 200
}
```

Add feature-specific API, version, marker, browser, and data checks; this minimum does not replace them. Select browser scope through `validation-tiers.md`: small isolated changes default to `quick`, single-route component changes use `standard`, and shared/high-risk UI changes use `full`. Never weaken the deployment critical-section checks based on the browser tier.

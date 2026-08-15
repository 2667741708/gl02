---
name: deploy-8093-guarded-update
description: Safely reconcile remote Git history with local work, deploy reviewed code/config/backend/static assets to 220.12:8093, verify the managed service, and record the accepted production Git version. Automatically use for requests to update, fix, upload, activate, restart, synchronize, merge, preserve a Git version, or verify anything served by 220.12:8093, even when the Skill is not named. Covers remote-first Git log/drift review, bidirectional reviewed synchronization, sealed manifests and delta uploads, native Python artifacts, BFV4PreviewProxy8093 guarding, atomic installation, rollback, protected-port validation, and post-acceptance version recording. Also use when designing or reviewing an 8093 deployment script. Do not use for 8768-only, 8094-only, database-only, or strictly read-only diagnosis tasks.
---

# Deploy 8093 Guarded Update

Execute one low-freedom two-phase workflow: prepare and seal validated artifacts once, then delta-stage, acquire the deployment mutex, pause only the managed 8093 service, back up and atomically install reviewed files, start 8093, verify the new behavior and isolation boundaries, and roll back on failure.

Keep one local persistent authenticated SSH transport to 220.12 for the staging and deployment calls. Open a fresh SSH channel per request, but do not reconnect and re-authenticate for every command.

## Read the project contract

Read `references/project-contract.md` before changing or running any deployment file. Read the repository `AGENTS.md` and the relevant requirement, automation, test, and handoff documents before modifying production.

Read `references/two-phase-fast-deployment.md` whenever preparing a release, skipping duplicate build/test work, computing a delta upload, running Luna beside a read-only remote preflight, or reporting deployment latency.

Read `references/remote-git-bidirectional-sync.md` for every 220.12 deployment. Its order is mandatory:
inspect remote Git history and worktree drift, review and merge legitimate remote functionality locally,
deploy the combined local version, accept the running service, and only then record the production Git version.

Treat the repository copy at `.codex/skills/deploy-8093-guarded-update` as the version-controlled source of truth. Treat `C:\Users\<user>\.codex\skills\deploy-8093-guarded-update` as the Codex runtime mirror. Edit only the repository copy, validate it there, then publish it with `pwsh.exe -NoLogo -NoProfile -File .\tools\sync_deploy_8093_guarded_update_skill.ps1 -Action PublishProjectToGlobal` and prove equality with `-Action Verify`. Use `ImportGlobalToProject` only for initial bootstrap or explicit recovery; never edit both copies independently.

Treat the user's “8093持续回滚服务/守卫” as the managed Windows service `BFV4PreviewProxy8093`. Do not invent a separate HTML/JavaScript file-lock daemon. Use the repository service manager and configuration on 220.12 so the existing management contract remains authoritative.

## Respect authorization

- Perform remote writes or service restarts only when the user explicitly requests deployment or production activation.
- Keep review, explanation, planning, and diagnosis requests read-only.
- Stop when credentials, network access, baseline identity, target paths, or production scope cannot be proven.
- Split changes that also require 8768, 8094, 8770, 8892, 11434, a database, or a scheduled task into separately authorized and separately verified operations.

## Apply the automatic trigger

Treat “更新8093”“修复8093页面/弹窗/接口”“把本地程序传到220.12并生效”“重启8093新版” and equivalent wording as an automatic trigger. The user does not need to type the Skill name. Diagnosis alone stays read-only, but once the requested outcome includes an 8093 code/config/artifact change or production activation, use this Skill before editing or deploying.

## Use this fixed workflow

### 1. Discover and freeze scope

1. Identify a requirement or operations ID.
2. List every local source, remote stage path, production target, expected baseline SHA-256, required marker, local test, and post-deploy check.
3. Record the services and ports that must remain unchanged.
4. Refuse wildcard targets, whole-tree copies, direct repository mirroring, and unbounded deletes.

Before freezing the release scope, execute the read-only remote Git gate in
`references/remote-git-bidirectional-sync.md`. Do not upload local files until remote commits,
tracked modifications, and relevant untracked source files have been classified. If the remote contains a
legitimate newer feature, bring its exact diff/files into a separate local integration surface, review it,
merge it with the local work, and rerun local validation. Never use `git pull` directly in the production
worktree and never discard either side merely because its timestamp or commit is newer.

Use an explicit manifest such as:

| Field | Required content |
|---|---|
| requirement | `REQ-*`, `BUG-*`, or `OPS-*` |
| local | reviewed absolute or repository-relative file |
| stage | unique file below the remote user temp directory |
| target | exact file below the 8093 production root |
| baseline | approved target SHA-256, or explicit `allow_create` |
| markers | version/requirement strings proving the intended artifact |
| validation | syntax, unit, API, page, and isolation checks |

### 2. Modify and validate locally

1. Use `apply_patch` for source edits and preserve unrelated dirty-worktree changes.
2. Run the narrowest relevant unit, syntax, and contract tests.
3. Read `references/validation-tiers.md` and select `quick`, `standard`, or `full` from the actual changed surface. Run only that browser tier and verify cache-busted URLs. Escalate on an unclear boundary or failure; never run 85 production page loads merely because a file is frontend-facing.
4. For any PowerShell change, require PowerShell 7 Core, UTF-8 without BOM, and run the repository PowerShell runtime verifier.
5. Do not continue after a failed local test.
6. After all required checks pass, seal the exact source bytes, artifact bytes, targets, stages, baselines, markers, tier, and validation evidence with `scripts/release_manifest.py`. Any later byte or contract change invalidates the prepared release.

### 2b. Prepare once, then deploy fast

Use the two phases in `references/two-phase-fast-deployment.md`:

1. **Phase A — prepare:** build and test once; run deterministic checks without a model; run one bounded read-only Luna `low` diff review for semantic source changes; run the production hash/service preflight concurrently; await both; then create `bf.deploy.prepared-release.v1`.
2. **Phase B — deploy:** immediately refresh the read-only remote hash snapshot, verify the prepared manifest, create `bf.deploy.delta-plan.v1`, upload only changed artifacts plus the plan, and execute the guarded payload. Do not rebuild or rerun the same validation when the manifest still verifies exactly.

An invalid/stale manifest, changed artifact, failed validation, unreviewed live baseline, expanded scope, or lower-tier failure returns to Phase A. The manifest is integrity evidence, not production authorization. If the delta is empty, report a verified no-op and do not stop 8093.

### 2a. Build a protected Python artifact when requested

Read `references/python-artifact-protection.md` whenever the user requests hidden Python source, `.pyb`, `.pyc`, `.pyd`, Cython, Nuitka, executable packaging, or source-free server deployment.

- Do not call the result `.pyb`; Python has no standard protected `.pyb` runtime format.
- Treat `.pyc` as bytecode compatibility packaging, not source confidentiality.
- For source confidentiality, compile locally to a reviewed native `.exe`/standalone directory or importable `.pyd`, then upload only the compiled artifact and its explicit runtime manifest.
- Never upload `.py` first and compile it on 220.12 when the purpose is to keep source off that host.
- Do not enable native packaging until the exact Python 3.11 x64 entrypoint, imports, resource files, service command, local smoke test, and rollback target are defined.
- State that native compilation raises the reverse-engineering cost but cannot make code impossible to inspect.
- Use the repository `tools/build_python_native_artifact.ps1` plan/build entrypoint and its generated artifact manifest. Bootstrap the controlled Python 3.11 x64 conda environment or install build dependencies only through explicit switches.

### 3. Build a dedicated two-layer deployer

Create or update two reviewed repository scripts:

1. A local `tools/prepare_<feature>_8093_release.ps1` or equivalent preparation entrypoint that runs feature-specific build/tests once and seals the prepared manifest.
2. A local `tools/deploy_<feature>_22012.ps1` wrapper that verifies the sealed manifest, refreshes read-only remote state, computes the delta, ensures `tools/remote_22012_session.py` is healthy, performs upload-only staging through that session, then executes the remote payload through the same session in a separate call. It must not repeat Phase A checks while the seal remains valid.
3. A remote `tools/remote_guarded_deploy_<feature>_8093.ps1` payload that consumes the exact delta plan and owns the production critical section, backup, service stop/start, atomic install, verification, and rollback.

Start from the templates in `assets/` when no approved feature-specific deployer exists. Replace every placeholder, narrow the file allowlist, and add feature-specific API/page assertions before use. Prefer an existing current PowerShell 7 deployer when it already covers exactly the requested files and behavior.

Never place the full PowerShell payload in `-Command`, an encoded command, SSH quoting, or Python `-c`. Run it as an independent UTF-8 `.ps1` payload through `remote_22012_session.py run -- --script`.

### 3a. Ensure and retain the persistent SSH session

1. Run `tools/remote_22012_session.py ensure --allow-agents-password --workdir <production-root>` before staging.
2. If the protected 220.12 password file is missing, empty, or contains the redaction marker, apply
   `OPS-22012-WINDOWS-CREDENTIAL-SSH-RECOVERY-20260814`: only the local PowerShell 7 helper
   `tools/restore_22012_ssh_secret_from_windows_credential.ps1` may read the exact Windows Credential
   Manager target `TERMSRV/10.30.220.12`, validate the `administrator` username, and restore only the
   LocalAppData password file. Never emit the secret, its length, or its hash, and never reuse that credential
   for another host or protocol. If Windows does not expose the secret, the same helper may use only the
   ACL-validated password file already referenced by the fixed 220.12 Reliable SSH MCP configuration. Run the
   configurator twice as independent `pwsh -File` calls and prove a fresh SSH authentication before treating
   recovery as complete.
3. Require a localhost-only broker, an authenticated active Paramiko transport, a 30-second SSH protocol keepalive, and a state file below the current user's local application-data directory rather than the repository.
4. Use `remote_22012_session.py run -- <remote_22012_exec arguments>` for upload-only staging and remote payload execution. Confirm the same `session_id` and `connection_id` are reported with increasing `request_count`.
5. Leave the broker running after deployment so the next operation can reuse it. Stop it only on explicit request, local shutdown, credential rotation, or an intentional host/user/workdir identity change.
6. If the transport dies between requests, reconnect before the next request and increment `reconnect_count`. If it fails during a command, report `uncertain_execution=true`; never automatically replay that command or deployment.
7. Do not silently fall back to a fresh `remote_22012_exec.py` process inside this skill. A broker failure is a visible preflight or transport failure.

The persistent object is an authenticated SSH transport, not a long-lived interactive PowerShell prompt. Each operation still receives an isolated PowerShell 7 script and a new SSH channel, avoiding cross-command shell-state contamination.

### 3b. Prove reuse with independent PowerShell files

Before the first production deployment of a session implementation, after changing SSH/MCP transport behavior, and whenever reuse is disputed, run the repository verifier as an independent UTF-8 PowerShell file:

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_22012_persistent_ssh_reuse.ps1 -IncludeColdBaseline
```

The verifier must execute `tools/remote_probe_22012_persistent_session.ps1` twice through `remote_22012_session.py run -- --script`; each remote request must therefore use remote PowerShell 7 `pwsh -File`. Require the same `session_id` and `connection_id`, exactly increasing `request_count`, `reused_connection=true`, PowerShell Core/UTF-8 evidence, and no production write or service restart. Do not substitute inline `--command`, `-Command`, or an encoded payload for this acceptance test.

### 3c. Measure performance and learn safely

Read `references/deployment-performance-and-learning.md` before benchmarking deployment time or changing behavior based on repeated errors. Read `references/learned-failure-playbook.json` at the start of every deployment and run applicable preflights.

Read `references/reusable-artifact-retention.md` before creating a local snapshot, generated helper, browser authentication state, downloaded remote configuration, or other file that may be requested again. Reuse verified canonical tools and non-secret deterministic artifacts instead of regenerating equivalent code. Never treat raw cookies, tokens, passwords, or credential-bearing remote service configuration as an ordinary reusable cache.

1. Record per-phase and total durations locally with `scripts/deployment_memory.py`.
2. Compare at least five cold and five reused samples with identical files, checks, restart scope, network route, and comparable server load. Use median and p90; do not claim total deployment savings from one SSH probe.
3. Normalize and count failure fingerprints without storing secrets or command output. Mark the third recurrence as a candidate lesson.
4. Promote only a reproduced pattern with two successful remediations and a deterministic test into the reviewed playbook.
5. Never let remote output automatically rewrite the Skill or trigger a production mutation. Automatic learning may add read-only/local preflights; deployment writes stay under this guarded workflow.
6. If a transport failure makes command completion uncertain, record it and inspect actual remote state. Never replay it automatically.

Run `tools/benchmark_22012_ssh_command_latency.ps1` only after changing transport/heartbeat/session behavior, when the previous baseline is stale, or when the user explicitly asks for a new speed claim. Ordinary small deployments reuse the latest valid baseline and record only their own phase timing. Attribute a new benchmark to connection/authentication, prestage upload, wrapper staging, remote command, cleanup, download, broker lock wait, and total request duration.

### 3d. Coordinate subagents and persistent MCP observation safely

When the user authorizes subagents or a separate Codex task, delegate only bounded, conflict-free work with explicit file ownership. A dedicated task may keep calling the read-only `connection_status` tool, collect timing samples, or watch the existing MCP process across a long validation window.

- Keep the MCP process owned by Codex MCP configuration or an operating-system service. Do not rely on a chat/task lifetime as the daemon owner.
- Configure the 220.12 Reliable SSH MCP with one pooled session, a 30-second SSH protocol keepalive, and a 60-second read-only application heartbeat.
- Do not let a monitoring task upload, stop/start a service, replace a file, roll back, change a database/task, or replay an uncertain command.
- Require the primary task to own the production manifest, deployment mutex, authorization gate, and final acceptance.
- Pass back the task/thread identifier, last `connection_status`, sample cursor, and any attention request so monitoring can be resumed without duplicating work.

When the user asks to reduce model/token cost, use `C:\Users\hmw20\.codex\skills\codex-economical-delegation\SKILL.md` for bounded local or read-only support. A Luna/Terra worker may inspect local files, classify sanitized failures, propose tests, or update an explicitly owned local document. It must never own credentials, remote upload, the deployment mutex, service stop/start, atomic replacement, rollback, or production acceptance.

For semantic source changes, default the preparation review to one ephemeral read-only `gpt-5.6-luna` call with `low` reasoning. Give it only the changed diff, related tests, acceptance criteria, and minimum project instructions; never the whole repository or conversation. Start that call and the read-only remote preflight concurrently, await both before sealing, and do not repeatedly retry a failed cheap-model review. Do not call any model for hashes, manifests, PowerShell parsing, cache versions, file inventory, uploads, or schema checks.

### 3e. Preserve one canonical ABC33 display score

Read `references/abc33-score-source-and-archive.md` when an 8093 popup, card, API, or report shows a score that overlaps an ABC33 rule. Use the released ABC33 rule item as the only displayed value for that concept. Preserve the replaced legacy score in read-only archive metadata or its existing historical table, never silently delete it, and fail closed with an unavailable marker instead of falling back to the conflicting legacy value.

### 3f. Retain reusable artifacts without retaining secrets

Apply `OPS-22012-REUSABLE-ARTIFACT-RETENTION-20260812` from `references/reusable-artifact-retention.md`:

1. Search the repository, the approved local reuse cache, and the persistent-session state before writing a functionally equivalent file.
2. Keep reviewed scripts, templates, schemas, credential-free test fixtures, and deterministic generated artifacts whose source hash and contract are still valid. Prefer a canonical named file over an ad-hoc task-directory copy.
3. Store reusable non-secret runtime artifacts outside disposable task directories, with a small manifest containing purpose, producer, source SHA-256, creation time, validation command, expiry or invalidation rule, and sensitivity class. Revalidate before reuse; never assume a cached remote baseline is current.
4. Keep the localhost SSH broker and its protected LocalAppData state through `remote_22012_session.py`; do not recreate project-local connection files for every request.
5. Do not preserve raw Playwright `storageState`, cookies, bearer tokens, passwords, decrypted credentials, or downloaded service configurations containing environment secrets in the repository or ordinary reuse cache. Preserve the generator, field-redacted schema, remote canonical path, and refresh command instead. If a credential-bearing runtime file is operationally required, use the approved OS-protected credential/session location, least-privilege ACL, explicit expiry, and identity validation; never expose it to model context, Git, logs, reports, or manifests.
6. Delete only proven disposable or secret-bearing task copies after their consuming operation. Do not broadly delete a task directory, and do not delete canonical tools or a valid non-secret reuse artifact merely because the current task ended.
7. File reuse reduces repeated coding, validation, upload preparation, and wall-clock time. Do not claim an exact token saving without measurement; reading a large cached file may still consume model context.

### 4. Pre-stage without touching production

1. Probe the remote root, PowerShell 7, Python, managed service, protected listeners, and the current SHA-256/existence of every manifest target.
2. Verify the prepared manifest and compute the delta from the fresh remote state. Reject baselines outside the manifest allowlist.
3. Upload only delta artifacts and the sealed delta plan to a unique remote staging directory with `remote_22012_session.py run -- --upload-only`.
4. Verify staged file existence, desired SHA-256, syntax, required markers, and plan seal.
5. Do not stop 8093 during upload or staging validation.
6. Abort if the delta is empty without stopping the service; report the no-op separately.

### 5. Enter the guarded critical section

Require the remote payload to:

1. Acquire `Global\BFV4PreviewProxy8093Deployment` without waiting. Exit if another deployment or recovery owns it.
2. Snapshot `BFV4PreviewProxy8093`, port 8093, and every protected listener/PID.
3. Confirm 8093 and required supporting services are healthy before mutation.
4. Create a timestamped backup below the production root before stopping the service.
5. Stop 8093 only through remote `manage_22012_managed_services.ps1` with `22012_BFV4PreviewProxy8093.json`.
6. Prove the service is `Stopped`, port 8093 has no listener, and protected ports remain present.
7. Set `guard_paused=true` only after those checks pass.

Do not stop 8768, 8094, 8770, 8892, 11434, PostgreSQL, or unrelated Python processes. Do not kill processes by name.

### 6. Install atomically and start the updated program

1. Copy each staged file to a target-adjacent temporary name.
2. Move the temporary file over the exact target atomically.
3. Recompute the installed SHA-256 and compare it with the staged SHA-256.
4. Update immutable asset version query strings when a static asset changed.
5. Start 8093 through the managed service tool.
6. Prove `BFV4PreviewProxy8093=Running`, port 8093 is listening, and a new listener PID exists when a restart was required.
7. Set `guard_restored=true` only after service and listener checks pass.

Keep service restoration inside `finally`; an exception must never leave the guard/service intentionally stopped.

### 7. Verify behavior and isolation

Require all of the following before success:

- Run deterministic cache-busted HTTP/API/asset checks first; 8093 main HTTP returns 200.
- Every changed asset/API/page returns its requirement or version marker and expected contract fields.
- Installed hashes equal staged hashes.
- Protected listener PIDs are unchanged.
- The managed 8093 service is `Running` and port 8093 listens.
- `guard_paused=true`, `guard_restored=true`, and `rollback_applied=false` are present in structured output.
- Relevant browser console/page errors are zero for actual UI/DOM/style/runtime changes.
- Browser evidence matches the selected risk tier only when served UI behavior changed. Pure backend/API changes or a verified no-op may omit browser automation. Run `full` locally or on preview; use a targeted production smoke unless a production-wide matrix is explicitly justified.

Do not treat `Start-Service` success, file existence, or HTTP 200 alone as acceptance.

### 7a. Record the accepted production Git version last

Follow `references/remote-git-bidirectional-sync.md` only after Section 7 proves the deployed runtime is
accepted. Stage only the exact deployed source targets from the sealed manifest; never use `git add -A`,
`git add .`, or include service configurations, credentials, logs, backups, runtime state, generated secrets,
or unrelated remote edits. Verify the staged path set and blob hashes against the accepted installation,
commit with the requirement/deployment ID, and create the controlled production version reference.

Do not create a production commit or tag before runtime acceptance. Do not push to an external Git remote
unless the user separately authorizes that push. After version recording, prove `HEAD`, the version reference,
the accepted file hashes, and the running HTTP/API behavior still agree. A Git metadata failure after runtime
acceptance must be reported as `deployed_version_record_failed`; do not roll back healthy accepted code merely
to hide a version-recording failure.

### 8. Roll back on any failure

On install, start, HTTP, marker, API, PID, or hash failure:

1. Preserve the first failure message.
2. Stop only 8093 if required for safe restoration.
3. Restore every pre-existing target from the timestamped backup.
4. Remove only newly created, explicitly allowlisted targets whose resolved paths remain below the production root.
5. Start 8093 in `finally` and verify service, listener, and protected ports.
6. Return structured evidence with `ok=false`, `rollback_applied`, `guard_restored`, backup path, listener state, and failure reason.
7. Never retry the same deployment automatically after rollback.

### 9. Record evidence and documentation

Capture JSON output containing requirement ID, staged and installed hashes, backup path, old/new 8093 PID, protected PID maps, HTTP/API results, `guard_paused`, `guard_restored`, and `rollback_applied`.

Also capture the remote Git baseline HEAD/branch, reviewed remote commits and dirty paths, local integration
commit or evidence, accepted production commit, production version reference, exact Git-staged paths, and the
post-record hash/runtime recheck. Use `<redacted>` for credential-bearing remote URLs and never copy Git
credential helpers, tokens, or embedded-auth remotes into reports.

Update the repository requirement, program index, automation traceability, test reference, troubleshooting/handoff record, and automation index when the deployment changes a long-lived contract. Never write passwords, tokens, cookies, or protected credentials into these records.

Record local timing/failure telemetry after success or failure. Run `scripts/deployment_memory.py summary --window 50` before reporting acceleration or proposing a new learned preflight.

Immediately after structured remote acceptance proves the new version is served, protection is restored, rollback is false, and isolation checks passed, require the local wrapper to emit `notify_immediately=true` and send a concise `deployed` commentary update with the new PID/HTTP/backup. Continue traceability documents and the detailed final report afterward; do not delay the production-success signal for documentation work.

## Reject unsafe shortcuts

- Reject direct overwrite of production files while 8093 is running when the user requested the guarded flow.
- Reject skipping Phase A from an absent, stale, tampered, failed-validation, or hash-mismatched prepared manifest.
- Reject broad Luna prompts containing the whole repository/conversation, sequential Luna/preflight waiting when safe concurrency is available, or model calls for deterministic mechanical work.
- Reject uploading unchanged artifacts or stopping 8093 for an empty verified delta.
- Reject `powershell.exe`, Windows PowerShell 5.1 fallback, `-EncodedCommand`, and multiline payloads inside `-Command`.
- Reject a deployment payload that lacks backup, rollback, `finally` restoration, baseline hashes, explicit targets, or protected-port checks.
- Reject commands that combine probing, upload, mutation, restart, and validation into one opaque shell line.
- Reject successful completion if the output cannot prove the updated artifact is the one served by 8093.
- Reject uploading before the remote Git log/worktree gate, blindly preferring local or remote files, direct
  `git pull` in production, broad Git staging, or creating the production version before acceptance.
- Reject external `git push`, force-push, history rewrite, reset, checkout-based discard, or tag replacement
  without separate explicit authorization.
- Reject automatic replay of any command whose SSH completion state is uncertain.
- Reject `.pyc` or a renamed `.pyb` as proof that Python source is protected.

## Report the outcome

Lead with one of three states:

- `deployed`: new version is served, protection restored, isolation checks passed;
- `rolled_back`: deployment failed, old version restored, protection restored;
- `not_started`: a preflight or authorization gate prevented production mutation.

Name the changed targets, backup path, validation results, protected services, and any remaining risk. Do not claim production activation from local tests or upload-only staging.

## Validate this skill after editing it

Run the bundled read-only contract validator and the standard skill validator against the repository source copy, publish that validated copy to the global runtime mirror, and run the sync verifier. Do not connect to 220.12 during skill validation or synchronization.

```powershell
pwsh.exe -NoLogo -NoProfile -File .\.codex\skills\deploy-8093-guarded-update\scripts\validate_skill.ps1
```

```powershell
$env:PYTHONUTF8='1'
python C:\Users\hmw20\.codex\skills\.system\skill-creator\scripts\quick_validate.py .\.codex\skills\deploy-8093-guarded-update
```

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\sync_deploy_8093_guarded_update_skill.ps1 -Action PublishProjectToGlobal
pwsh.exe -NoLogo -NoProfile -File .\tools\sync_deploy_8093_guarded_update_skill.ps1 -Action Verify
```

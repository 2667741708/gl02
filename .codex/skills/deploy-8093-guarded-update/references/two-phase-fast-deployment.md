# Two-phase prepared release and fast deployment

Use this contract for repeatable small 8093 changes. It reduces duplicate work without weakening baseline, rollback, service, or protected-PID checks.

## Phase A: prepare once

1. Freeze the exact source diff and classify `quick`, `standard`, or `full`.
2. Run the required build, syntax, unit, contract, and local/preview browser checks once.
3. For a semantic source change, start one read-only `gpt-5.6-luna` review with `low` reasoning. Give it only the changed diff, related tests, acceptance criteria, and a 4 KB project-instruction cap. Never give it credentials or remote mutation tools.
4. Start the production hash/service preflight concurrently with the Luna review. The remote branch is read-only and must not upload, acquire the deployment mutex, or stop a service.
5. Await both branches. A failed or ambiguous review/preflight prevents sealing; do not retry Luna repeatedly.
6. Write a `bf.deploy.release-spec.v1` file and seal it with `scripts/release_manifest.py prepare` as `bf.deploy.prepared-release.v1`. The output binds every source and artifact byte, validation result, exact stage/target, approved baseline hashes, markers, validation tier, and requirement ID.

Do not call a model for hashing, JSON generation, PowerShell parsing, cache-version replacement, file inventory, or schema validation. Keep those operations deterministic.

Example spec:

```json
{
  "schema": "bf.deploy.release-spec.v1",
  "requirement_id": "REQ-EXAMPLE",
  "validation_tier": "quick",
  "production_root": "F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW",
  "sources": ["D:\\workspace\\src\\feature.js"],
  "artifacts": [
    {
      "local_path": "D:\\workspace\\dist\\feature.js",
      "stage": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\REQ-EXAMPLE\\feature.js",
      "target": "F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\\高炉前端数据\\assets\\feature.js",
      "baseline_sha256": ["<64-HEX-SHA256>"],
      "allow_create": false,
      "markers": ["REQ-EXAMPLE"]
    }
  ],
  "validations": [
    {"id": "unit", "kind": "deterministic", "status": "passed", "evidence": "focused tests passed"},
    {"id": "luna-diff-review", "kind": "semantic", "status": "passed", "model": "gpt-5.6-luna", "reasoning_effort": "low"},
    {"id": "remote-readonly-preflight", "kind": "readonly_remote", "status": "passed"}
  ]
}
```

Run:

```powershell
python C:\Users\hmw20\.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py prepare --spec .\release-spec.json --output .\prepared-release.json
```

## Phase B: deploy only the sealed delta

1. Re-run the read-only remote hash preflight immediately before deployment and save `bf.deploy.remote-state.v1` with an entry for every manifest target.
2. Run `release_manifest.py verify`. Any changed/missing source or artifact, failed validation, marker mismatch, or manifest seal mismatch invalidates the prepared release and returns to Phase A.
3. Run `release_manifest.py plan-delta` to create `bf.deploy.delta-plan.v1`. It rejects an unreviewed live baseline and returns only artifacts whose desired hash differs from production.
4. If the delta is empty, do not upload or restart 8093; report a verified no-op.
5. Upload only delta artifacts plus the sealed delta plan while 8093 remains online. Typical small changes should contain one or two files; never force that count when correctness requires more.
6. Make the remote payload consume the exact delta plan under the existing mutex. It must still back up every changed target, stop only 8093, install atomically, restore in `finally`, verify installed hashes/markers/HTTP/API/protected PIDs, and roll back on failure.
7. Run deterministic cache-busted HTTP/API checks first. Run the selected browser tier only for an actual UI/DOM/style/runtime change; pure backend/API or identical served bytes do not need a browser.
8. As soon as structured remote acceptance proves `guard_restored=true`, `rollback_applied=false`, installed hashes, HTTP/API success, and protected PID equality, send a concise `deployed` commentary update. Continue documentation and extended reporting afterward; never delay the production-success signal for documentation work.

Remote-state shape:

```json
{
  "schema": "bf.deploy.remote-state.v1",
  "requirement_id": "REQ-EXAMPLE",
  "targets": {
    "F:\\...\\feature.js": {"exists": true, "sha256": "<64-HEX-SHA256>"}
  }
}
```

Commands:

```powershell
python C:\Users\hmw20\.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py verify --manifest .\prepared-release.json
python C:\Users\hmw20\.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py plan-delta --manifest .\prepared-release.json --remote-state .\remote-state.json --output .\delta-plan.json
```

The prepared manifest is a local integrity seal, not authorization and not a replacement for the live remote baseline gate. Never reuse it after any bound byte or validation contract changes.

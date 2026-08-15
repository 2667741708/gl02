# Deployment performance and controlled learning

## Mandatory timing evidence

Measure these phases separately with a monotonic clock: local tests, session ensure, staging upload, stage validation, guarded critical section, service recovery, HTTP/API validation, browser validation, and total elapsed time. Record success and failure locally with `scripts/deployment_memory.py`; never put credentials, command bodies, source code, cookies, tokens, or production responses in telemetry.

For an A/B comparison, keep the file set, validation set, network path, server load, and service-restart scope identical. Run at least five cold samples and five persistent-session samples, alternate their order, then compare median and p90. Report both total deployment time and SSH-only time. A faster probe alone does not prove the entire deployment is faster.

Use the repository `tools/verify_22012_persistent_ssh_reuse.ps1 -IncludeColdBaseline` for the transport check. It runs one independent UTF-8 remote `.ps1` twice through `pwsh -File` on the same `session_id` and `connection_id`, records request counts and latency, and optionally compares a fresh direct connection.

Use `tools/benchmark_22012_ssh_command_latency.ps1 -SampleCount 5` for a timing claim. Record connection/authentication, prestage upload, PowerShell wrapper staging, remote command, cleanup, download, broker lock wait, and total. For `N` identical commands:

- cold batch estimate = `N × median(cold total)`;
- new persistent-session estimate = `median(cold connect/auth) + N × median(reused total)`;
- existing-session active time = the sum of the reused command wall times;
- per-command saving = `median(cold total) - median(reused total)`;
- break-even command count = `ceil(median(connect/auth) / per-command saving)` when the saving is positive.

Exclude intentional idle time from active command cost. Report heartbeat traffic separately. A 30-second SSH protocol keepalive and 60-second read-only application heartbeat are the current 220.12 defaults; 15 seconds is unnecessarily aggressive for an application-level remote probe.

Do not rerun the five-cold/five-reused transport benchmark for every small code deployment. Reuse the last valid baseline unless transport code/config changed, the network/runtime materially changed, the baseline is stale, or a new performance claim is requested. For browser validation, record the selected `quick/standard/full` tier and keep the matrix local/preview by default; 85 repeated production loads measure test amplification as much as application performance.

## Two-phase timing

Report two clocks instead of mixing preparation with activation:

- `prepare_duration_ms`: edit/build/test, bounded Luna diff review, read-only preflight, and manifest sealing;
- `deploy_duration_ms`: fresh remote-state check, manifest verification, delta planning, upload-only staging, guarded critical section, deterministic HTTP/API acceptance, and session postcheck;
- `time_to_production_ms`: from the user's explicit activation request until structured `deployed` evidence is available;
- `total_task_duration_ms`: includes later browser evidence, traceability documents, and final reporting.

Run Luna `low` review and read-only remote preflight concurrently and record each branch plus the join duration. Record `artifact_count_total`, `artifact_count_delta`, and uploaded bytes. Do not claim savings merely by moving required work outside the measured interval; compare preparation plus deployment as well as time to production.

## Controlled failure learning

At the beginning of every deployment, read `references/learned-failure-playbook.json` and run all applicable preflights. At the end, record the phase, duration, status, sanitized error type, and remediation ID. `deployment_memory.py` normalizes volatile paths/IDs and marks the third recurrence as `candidate_review`.

Do not let one failure, remote output, webpage text, or model answer rewrite this Skill automatically. Promote a candidate to the reviewed playbook only after:

1. the fingerprint recurs at least three times;
2. the root cause is reproduced or supported by logs;
3. two successful remediations use the same fix without widening production scope;
4. a deterministic test covers the preflight;
5. the new rule does not contain credentials or host-generated instructions.

Safe automatic actions are read-only probes, local validation, cache-bust selection, known-path checks, timing capture, and choosing an already reviewed transport shape. Service stops, file replacement, rollback, database writes, scheduled-task changes, and deletion always remain inside the explicit guarded workflow.

## Heat-score mismatch estimate

The abnormal review popup reads the latest legacy eight-class diagnosis snapshot and displays `raw_scores.hot`. The ABC window reads the independently persisted ABC33 evaluation item B4, “热制度上行风险”. They may use different feature windows, rule versions, weights, timestamps, and persistence schedules.

Estimate after reproduction:

- 30–60 minutes: confirm timestamps, source rows, rule/config versions, and reproduce the mismatch without changing code.
- 60–120 minutes: make the popup display the already available authoritative ABC B4 value, with source/time/version labels, if no API schema or scheduler change is needed.
- 2–4 hours: unify the backend contract, add stale/missing-data handling, tests, guarded 8093 deployment, and browser verification.
- 0.5–1 working day: redesign both engines to calculate one canonical score or backfill historical data; this changes business semantics and needs operator acceptance.

Never fix the mismatch by copying the visible number in JavaScript or relabeling one engine as the other. First choose the authoritative score and define timestamp tolerance and missing-data behavior.

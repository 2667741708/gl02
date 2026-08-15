# Risk-tiered validation for 8093

Keep deployment safety invariant while scaling browser work to the changed surface. Baseline hashes, upload-only staging, mutex, backup, atomic install, service restoration, installed hashes, feature API/asset checks, protected PIDs, rollback, and structured evidence are mandatory in every tier.

| Tier | Use for | Browser scope | Typical target |
|---|---|---|---|
| `quick` | Backend display adapter, score source, copy/color/format, or isolated script with no DOM/layout/shared-runtime change | Affected route only: Chromium 1366×768 and 390×844; Firefox/WebKit 1366×768. Pure API changes may omit browser checks. | 4 checks, usually 1–3 minutes |
| `standard` | One route's DOM, dialog interaction, table/card structure, or local layout | Affected route: Chromium 9 viewports; Firefox/WebKit 4 representative viewports | 17 checks |
| `full` | New/shared routes, global CSS/navigation, 3D/GLB, shared adapters, runtime/build changes, responsive-system changes, or multiple affected routes | Five core routes across the existing 17 engine/viewport combinations | 85 checks |

Escalate one tier when the changed surface is uncertain, a lower-tier check fails, a shared selector/module is touched, or console/layout evidence points outside the declared route. Do not downgrade security, authentication, service, database, deployment, rollback, hash, or protected-PID validation.

Run the full matrix on local/preview infrastructure. Production acceptance should load the affected route once in the onsite Chromium/Edge viewport, verify its feature marker and console, and stop. Repeat a production-wide matrix only after an explicit performance-safe justification.

For the diagnosis review verifier:

```powershell
python .\tools\verify_diagnosis_review_local.py --profile quick
python .\tools\verify_diagnosis_review_local.py --profile standard --check-manual-score
python .\tools\verify_diagnosis_review_local.py --profile full --check-manual-score
```

Reuse one browser context per engine so immutable libraries and assets stay cached between checks. Keep a new page per case to isolate DOM state. Record profile, check count, navigation time, total elapsed time, failures, and screenshots.

## Small-change fast lane

Use the fast lane when the change is 8093-only, has exact targets and baseline hashes, does not alter a service command/database/task/shared runtime, has a current feature-specific deployer, and qualifies for `quick` validation. Reuse the existing SSH broker and reviewed deployer; do not rerun cold-connection benchmarks, regenerate unchanged deployment infrastructure, or run the 85-case matrix.

Keep the sequence explicit: narrow local test, quick browser/API check, upload-only staging while 8093 stays online, one guarded stop/install/start transaction, and one targeted production smoke. Record local-test, staging, mutex, downtime, restart, smoke, and total durations. Escalate out of the fast lane after any failed check, uncertain transport state, baseline mismatch, rollback, shared-module discovery, or added production scope.

For the two-phase fast lane, bind the selected tier and its passed evidence into the prepared manifest. Re-run deterministic cache-busted HTTP/API/asset checks after deployment. Run browser automation only when the served UI/DOM/style/runtime changed; a backend/API-only delta may omit it, while any visual or console uncertainty escalates to the tier's browser scope.

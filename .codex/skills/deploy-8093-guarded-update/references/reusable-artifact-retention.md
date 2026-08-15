# Reusable artifact retention and sensitive-state boundary

Requirement: `OPS-22012-REUSABLE-ARTIFACT-RETENTION-20260812`.

## Purpose

Avoid repeatedly coding, validating, or reconstructing the same deployment support file while preventing a performance shortcut from turning cookies, credentials, or stale production snapshots into durable project data.

Before creating a helper or cache file, classify it and search for an existing canonical implementation.

## Retention classes

| Class | Examples | Default action |
|---|---|---|
| Canonical reusable source | reviewed `.ps1`, `.py`, template, schema, validator, redacted fixture | keep in the repository, test it, and reuse by path |
| Deterministic non-secret artifact | sealed package, generated manifest, compiled helper, sanitized browser fixture | keep in an approved local reuse cache while its hashes and invalidation rules remain valid |
| Durable protected runtime state | localhost SSH broker token/state and authenticated Paramiko transport | keep only in the approved current-user LocalAppData location; reuse through `remote_22012_session.py` |
| Volatile remote evidence | current PID map, listener state, remote hash snapshot, downloaded configuration | refresh before a mutation; keep only redacted evidence when needed for audit |
| Secret-bearing state | Playwright `storageState`, cookies, bearer tokens, passwords, private keys, service configuration with credential environment values | do not keep in the repository or ordinary reuse cache; use approved OS-protected credential/session storage only when operationally required |

## Reuse decision

Reuse an existing file only when all of these are true:

1. its purpose and producer are known;
2. its sensitivity classification permits retention;
3. its SHA-256 and source inputs match the recorded manifest;
4. its target host, user, workdir, runtime, and requirement scope still match;
5. its validation command still passes;
6. its expiry or invalidation condition has not been reached;
7. reuse does not skip a fresh production-state check, authorization gate, mutex, backup, or rollback boundary.

When any check fails, regenerate from the canonical source. Do not patch an unknown cached copy until it merely appears to work.

## Approved metadata

A reusable non-secret artifact should have adjacent metadata or an index entry containing only:

- stable artifact ID and requirement ID;
- canonical producer path and producer version/hash;
- artifact SHA-256;
- sensitivity class (`public`, `internal_non_secret`, or `protected_runtime_reference`);
- target identity without credentials;
- creation time and last validation time;
- validation command and result;
- expiry/invalidation rule;
- replacement artifact ID when superseded.

Never place password values, cookies, tokens, private keys, authorization headers, database connection strings, or unredacted remote service environments in this metadata.

## Two commonly confused files

- A Playwright viewport `storageState` JSON is an authentication fixture, not an SSH connection prerequisite. Preserve the viewport test tool and the command that creates fresh authenticated state; do not retain the raw cookie-bearing JSON in a task directory.
- A locally downloaded `22012_BFV4PreviewProxy8093` service JSON is a point-in-time remote configuration snapshot and may contain credentials in its environment section. The canonical configuration remains on the controlled host. Preserve its remote path, redacted schema, probe script, and hash evidence; refresh it when needed instead of treating an old raw copy as current configuration.

Neither file is created for every 220.12 connection. SSH connection reuse is provided by the persistent broker in `remote_22012_session.py`, whose protected runtime state already lives outside the repository.

## Cleanup rule

At task completion:

1. retain canonical reusable source and valid non-secret artifacts;
2. retain approved protected runtime state in its designated OS location;
3. remove secret-bearing task copies and stale or unverifiable cache entries by exact path;
4. record what was retained or removed and why, without recording secret content;
5. never recursively purge the repository, reuse-cache root, LocalAppData root, or an unresolved path.

This policy reduces repeated implementation and setup time. It does not guarantee a fixed model-token reduction because reading and reasoning over retained files can still consume context.

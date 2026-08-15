# Python artifact protection for 8093 deployments

## Decision

Python does not define a protected `.pyb` deployment format. Use one explicit mode per manifest:

| Mode | Artifact | Meaning |
|---|---|---|
| `source` | `.py` | Normal maintainable deployment; source is visible on 220.12. |
| `bytecode` | `.pyc` | Interpreter bytecode only; casual concealment, not a confidentiality boundary. |
| `native` | `.exe`, standalone directory, or `.pyd` | Preferred when source must not be copied to 220.12; harder, but not impossible, to reverse engineer. |

Do not rename `.py`, `.pyc`, or an archive to `.pyb`. A renamed file does not add protection and creates an undocumented runtime contract.

## Fixed native-build gate

1. Identify the exact Python entrypoint or importable module and every dynamically loaded module, data file, model, DLL, certificate, and configuration file.
2. Probe and record the 220.12 target runtime. The current controlled target is Windows x64 with Python 3.11; rebuild when its Python ABI or architecture changes.
3. Keep credentials, connection strings, tokens, and mutable environment configuration outside the compiled artifact.
4. Build locally from the controlled source tree. Use Nuitka standalone mode first for an application entrypoint; use a Nuitka module or Cython extension for an importable module. Validate standalone before considering onefile packaging.
5. Run syntax, unit, import, cold-start, API, shutdown, and resource-path tests against the compiled artifact locally.
6. Produce a manifest containing build tool and version, Python ABI, architecture, source revision/hash, output hashes, entrypoint, runtime files, service command, markers, and rollback target.
7. Stage only the compiled artifact, manifest, and required non-source runtime files. If confidentiality was requested, assert that no `.py` files appear in the stage allowlist or target directory.
8. Treat any service command or module-import change as a separately reviewed deployment target. Back up its previous configuration and validate it inside the guarded critical section.
9. After start, prove process command line, loaded entrypoint/version marker, API behavior, installed hashes, and protected PID boundaries.
10. Roll back the artifact and service entrypoint together on failure.

## Repository automation

Use `tools/build_python_native_artifact.ps1` as the only local entrypoint. It validates a UTF-8 JSON build spec and delegates to `tools/build_python_native_artifact.py`.

1. Create a feature-specific JSON spec with `mode`, `entrypoint`, `output_dir`, `source_confidential`, `data_files`, `stage_files`, `build_args`, and the service command/marker/rollback target.
2. Review the plan without installing or compiling:

   `pwsh.exe -NoLogo -NoProfile -File .\tools\build_python_native_artifact.ps1 -Spec <spec.json> -PlanOnly`

3. Build with the controlled local Python 3.11 x64 conda environment. The first build may explicitly bootstrap the environment and dependencies:

   `pwsh.exe -NoLogo -NoProfile -File .\tools\build_python_native_artifact.ps1 -Spec <spec.json> -Build -BootstrapPython311 -InstallBuildDeps -Manifest <manifest.json>`

4. Later builds reuse the same environment and omit `-BootstrapPython311`; omit `-InstallBuildDeps` when dependencies are already present.
5. Require an empty output directory so stale binaries cannot enter the manifest. The builder refuses a non-3.11/x64 runtime, missing dependencies without explicit installation, unsafe stage paths, `.py/.pyw` in a confidential stage/output, and empty build output.
6. Stage only files listed by the generated manifest. Recompute every output SHA-256 before install and after install.

Use `nuitka-standalone` for an application/service entrypoint, `nuitka-module` for an importable Nuitka extension, and `cython-extension` for a narrowly defined importable module. Do not automatically switch an existing `.py` service command to a native artifact until the compiled cold start, imports, dynamic resources, shutdown, and rollback command have passed locally.

## Limits and exclusions

- Native compilation increases the cost of inspection; it does not make reverse engineering impossible.
- `.pyc` usually remains tied to a Python bytecode version and can be inspected or decompiled; do not present it as encryption.
- HTML, JavaScript, CSS, JSON, YAML, SQL, and PowerShell are not made private by a Python compiler. Minification or obfuscation is a different, weaker control.
- Dynamic imports, reflection, plugin discovery, filesystem-relative assets, multiprocessing, antivirus scanning, startup time, and native DLL dependencies require feature-specific tests.
- Existing remote backups may still contain historical source. Do not delete backups automatically; define an explicitly authorized retention and secure-erasure policy if that risk must be removed.
- Keep the authoritative source and debug symbols in the controlled local repository and never embed secrets in the binary.

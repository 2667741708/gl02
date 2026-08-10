$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$Python = "D:\ProgramData\anaconda3\python.exe"
$RemoteExec = ".\tools\remote_22012_exec.py"
$Root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$RemoteTemp = "C:\Users\Administrator\AppData\Local\Temp\abc33_hotfix_20260808"
$Common = @("--allow-agents-password", "--no-profile", "--timeout", "180", "--workdir", $Root)

$Uploads = @(
    ".\tools\patch_remote_abc33_runtime.py=$RemoteTemp\patch_remote_abc33_runtime.py",
    ".\.tmp_abc33_payload\abc-furnace-rules-production.js=$RemoteTemp\abc-furnace-rules-production.js",
    ".\.tmp_abc33_payload\furnace-rule-admin.html=$RemoteTemp\furnace-rule-admin.html",
    ".\.tmp_abc33_payload\abc_rule_catalog.py=$RemoteTemp\abc_rule_catalog.py",
    ".\.tmp_abc33_payload\abc_feature_builder.py=$RemoteTemp\abc_feature_builder.py",
    ".\.tmp_abc33_payload\abc_rule_engine.py=$RemoteTemp\abc_rule_engine.py",
    ".\.tmp_abc33_payload\abc_runtime_store.py=$RemoteTemp\abc_runtime_store.py",
    ".\.tmp_abc33_payload\abc_furnace_rules.v1.json=$RemoteTemp\abc_furnace_rules.v1.json"
)

$UploadArgs = @($RemoteExec) + $Common
foreach ($Item in $Uploads) {
    $UploadArgs += @("--upload", $Item)
}
$UploadArgs += "--upload-only"
& $Python @UploadArgs
if ($LASTEXITCODE -ne 0) { throw "ABC33 hotfix upload failed" }

$RemotePython = "$RemoteTemp\patch_remote_abc33_runtime.py --root . --payload `"$RemoteTemp`""
& $Python $RemoteExec @Common --python $RemotePython
if ($LASTEXITCODE -ne 0) { throw "ABC33 hotfix patch failed" }

& $Python $RemoteExec @Common --script ".\tools\restart_22012_8768_abc33.ps1"
if ($LASTEXITCODE -ne 0) { throw "8768 restart failed" }

& $Python $RemoteExec @Common --script ".\tools\verify_remote_abc33_runtime_final.ps1"
if ($LASTEXITCODE -ne 0) { throw "ABC33 runtime verification failed" }

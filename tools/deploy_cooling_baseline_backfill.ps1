$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = 'python'
$remote = Join-Path $root 'tools\remote_22012_exec.py'
$workdir = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$remoteAutoDiag = "$workdir\自动诊断服务"

$uploads = @(
    "$(Join-Path $root '自动诊断服务\baseline_maintainer.py')=$remoteAutoDiag\baseline_maintainer.py",
    "$(Join-Path $root '自动诊断服务\store.py')=$remoteAutoDiag\store.py",
    "$(Join-Path $root '自动诊断服务\service_config.py')=$remoteAutoDiag\service_config.py",
    "$(Join-Path $root '自动诊断服务\schema.sql')=$remoteAutoDiag\schema.sql",
    "$(Join-Path $root '自动诊断服务\abc_rule_schema.sql')=$remoteAutoDiag\abc_rule_schema.sql"
)

foreach($path in @($remote) + ($uploads | ForEach-Object { ($_ -split '=',2)[0] })){
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "required local file missing: $path"}
}

Write-Host "Uploading baseline_maintainer + dependencies to 220.12..."
& $python $remote --allow-agents-password --no-profile --timeout 40 --workdir $workdir --upload-only @($uploads | ForEach-Object { '--upload'; $_ })
if($LASTEXITCODE -ne 0){throw 'remote staging failed'}

Write-Host "Running cooling baseline backfill (30 days)..."
$pythonArgs = "`"$remoteAutoDiag\baseline_maintainer.py`" --backfill-days 30 --cooling-only --write"
& $python $remote --allow-agents-password --no-profile --timeout 600 --workdir $workdir --python $pythonArgs
if($LASTEXITCODE -ne 0){throw 'remote cooling baseline backfill failed'}

Write-Host "Cooling baseline backfill complete."

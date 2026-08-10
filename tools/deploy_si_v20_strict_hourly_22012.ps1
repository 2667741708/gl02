param([Parameter(Mandatory=$true)][string]$RemoteRoot)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required'
}

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$remote = Join-Path $root 'tools\remote_22012_exec.py'
$remoteScript = Join-Path $root 'tools\remote_guarded_deploy_si_v20_strict_hourly.ps1'
$serverFile = Get-ChildItem -LiteralPath $root -Recurse -Filter 'ollama_proxy_server.py' -File |
    Where-Object { $_.Directory.Name -eq 'backend' -and $_.FullName -notmatch '\\.tmp_|\\backups\\' } |
    Sort-Object { $_.FullName.Length } |
    Select-Object -First 1
if(-not $serverFile){throw 'canonical frontend backend was not found'}
$backend = $serverFile.Directory.FullName
$frontend = Split-Path -Parent (Split-Path -Parent $backend)
$abcTermFile = Get-ChildItem -LiteralPath $root -Recurse -Filter 'abc_term_semantics.py' -File |
    Where-Object { $_.FullName -notmatch '\\.tmp_|\\backups\\' } |
    Sort-Object { $_.FullName.Length } |
    Select-Object -First 1
if(-not $abcTermFile){throw 'abc_term_semantics.py was not found'}
$uploads = @(
    "$($serverFile.FullName)=C:\Users\Administrator\AppData\Local\Temp\si_v20_strict_ollama_proxy_server.py",
    "$(Join-Path $backend 'si_v20_shadow.py')=C:\Users\Administrator\AppData\Local\Temp\si_v20_strict_si_v20_shadow.py",
    "$(Join-Path $backend 'si_v20_strict_context.py')=C:\Users\Administrator\AppData\Local\Temp\si_v20_strict_context.py",
    "$(Join-Path $backend 'heat_performance_quality.py')=C:\Users\Administrator\AppData\Local\Temp\si_v20_strict_heat_performance_quality.py",
    "$(Join-Path $backend 'models\si_v20_strict_context_lgbm_v1.json.gz')=C:\Users\Administrator\AppData\Local\Temp\si_v20_strict_context_lgbm_v1.json.gz",
    "$(Join-Path $frontend 'si_v20_workbench.html')=C:\Users\Administrator\AppData\Local\Temp\si_v20_strict_workbench.html",
    "$(Join-Path $frontend 'assets\bf-si-v20-workbench.js')=C:\Users\Administrator\AppData\Local\Temp\si_v20_strict_workbench.js",
    "$($abcTermFile.FullName)=C:\Users\Administrator\AppData\Local\Temp\si_v20_strict_abc_term_semantics.py",
    "$(Join-Path $root 'tools\run_si_v20_strict_hourly_dispatcher.py')=C:\Users\Administrator\AppData\Local\Temp\run_si_v20_strict_hourly_dispatcher.py",
    "$(Join-Path $root 'tools\run_22012_si_v20_strict_hourly.ps1')=C:\Users\Administrator\AppData\Local\Temp\run_22012_si_v20_strict_hourly.ps1",
    "$(Join-Path $root 'tools\register_22012_si_v20_strict_hourly_task.ps1')=C:\Users\Administrator\AppData\Local\Temp\register_22012_si_v20_strict_hourly_task.ps1"
    "$(Join-Path $root 'tools\restart_22012_8094_preview.ps1')=C:\Users\Administrator\AppData\Local\Temp\restart_22012_8094_preview.ps1"
)

foreach($path in @($remote,$remoteScript) + ($uploads | ForEach-Object { ($_ -split '=',2)[0] })){
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "required local file missing: $path"}
}

$arguments=@($remote,'--allow-agents-password','--no-profile','--timeout','60','--workdir',$RemoteRoot,'--upload-only')
foreach($upload in $uploads){$arguments += @('--upload',$upload)}
& python @arguments
if($LASTEXITCODE -ne 0){throw 'strict-hourly staging failed; production was not changed'}

& python $remote --allow-agents-password --no-profile --timeout 240 --workdir $RemoteRoot --script $remoteScript
if($LASTEXITCODE -ne 0){throw 'strict-hourly deployment failed; inspect rollback and service output'}

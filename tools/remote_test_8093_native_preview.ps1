[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [ValidateRange(1024, 65535)]
    [int]$Port = 18095,
    [string]$AcceptanceScript = 'F:\high-furnace-deploy-staging\assistant-native-preview\remote_accept_abc33_contextual_assistant.ps1'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$configPath = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$exePath = (Resolve-Path -LiteralPath $Executable).Path
$acceptPath = (Resolve-Path -LiteralPath $AcceptanceScript).Path
$logDir = Split-Path -Parent $exePath
$stdoutPath = Join-Path $logDir 'preview.stdout.log'
$stderrPath = Join-Path $logDir 'preview.stderr.log'
$protectedPorts = @(8093, 8094, 8768, 8770, 5432, 11434)

function Get-ListenerPid([int]$TargetPort) {
    $item = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction Stop | Select-Object -First 1
    return [int]$item.OwningProcess
}

function Get-ProtectedMap {
    $map = [ordered]@{}
    foreach ($targetPort in $protectedPorts) {
        $map[[string]$targetPort] = Get-ListenerPid $targetPort
    }
    return $map
}

$before = Get-ProtectedMap
foreach ($name in @($config.envMachine)) {
    $value = [Environment]::GetEnvironmentVariable([string]$name, 'Machine')
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
foreach ($property in $config.env.PSObject.Properties) {
    Set-Item -Path "Env:$($property.Name)" -Value ([string]$property.Value)
}
if ($config.setPgPasswordFromGl02 -and $env:GL02_PGPASSWORD) {
    $env:PGPASSWORD = $env:GL02_PGPASSWORD
}
$env:BF_PROXY_HOST = '127.0.0.1'
$env:BF_PROXY_PORT = [string]$Port
$env:PYTHONHOME = 'C:\Program Files\Python311'
$env:PATH = 'C:\Program Files\Python311;C:\Program Files\Python311\DLLs;' + $env:PATH
Remove-Item Env:BF_SKIP_ASSISTANT_STARTUP -ErrorAction SilentlyContinue

Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
$process = $null
$acceptance = $null
$failure = $null
try {
    $process = Start-Process -FilePath $exePath -WorkingDirectory $root -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    $deadline = (Get-Date).AddSeconds(90)
    do {
        if ($process.HasExited) { throw "Native preview exited early: $($process.ExitCode)" }
        try {
            $status = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/ollama/status" -UseBasicParsing -TimeoutSec 4
        } catch {
            $status = $null
        }
        if ($status -and $status.StatusCode -eq 200) { break }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    if (-not $status -or $status.StatusCode -ne 200) { throw 'Native preview did not become healthy.' }
    $acceptance = (& $acceptPath -Port $Port -SendFollowup | Out-String) | ConvertFrom-Json
} catch {
    $failure = $_
} finally {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue }
    if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
}

$after = Get-ProtectedMap
$changed = @()
foreach ($key in $before.Keys) {
    if ($before[$key] -ne $after[$key]) { $changed += $key }
}
$result = [ordered]@{
    schema = 'ops.8093.native-preview-acceptance.v1'
    ok = ($null -eq $failure -and $changed.Count -eq 0 -and $acceptance.ok)
    executable_sha256 = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
    preview_port = $Port
    acceptance = $acceptance
    protected_before = $before
    protected_after = $after
    changed_protected_ports = $changed
    stdout_tail = if (Test-Path -LiteralPath $stdoutPath) { @(Get-Content -LiteralPath $stdoutPath -Tail 30) } else { @() }
    stderr_tail = if (Test-Path -LiteralPath $stderrPath) { @(Get-Content -LiteralPath $stderrPath -Tail 30) } else { @() }
    error = if ($failure) { $failure.Exception.Message } else { '' }
}
$result | ConvertTo-Json -Depth 12
if (-not $result.ok) { exit 1 }

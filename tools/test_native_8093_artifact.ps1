[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [Parameter(Mandatory = $true)]
    [string]$FrontendRoot,
    [int]$Port = 18093,
    [int]$StartupTimeoutSeconds = 45,
    [string]$LogDirectory = "$env:LOCALAPPDATA\Codex\python-native-build\smoke-logs"
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 or newer is required.'
}
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$exePath = (Resolve-Path -LiteralPath $Executable).Path
$frontendPath = (Resolve-Path -LiteralPath $FrontendRoot).Path
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$stdoutPath = Join-Path $LogDirectory 'native-8093.stdout.log'
$stderrPath = Join-Path $LogDirectory 'native-8093.stderr.log'
Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue

$previous = @{}
foreach ($name in @('BF_PROXY_HOST', 'BF_PROXY_PORT', 'BF_FRONTEND_DIR', 'BF_SKIP_ASSISTANT_STARTUP')) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
[Environment]::SetEnvironmentVariable('BF_PROXY_HOST', '127.0.0.1', 'Process')
[Environment]::SetEnvironmentVariable('BF_PROXY_PORT', [string]$Port, 'Process')
[Environment]::SetEnvironmentVariable('BF_FRONTEND_DIR', $frontendPath, 'Process')
[Environment]::SetEnvironmentVariable('BF_SKIP_ASSISTANT_STARTUP', '1', 'Process')

$process = $null
try {
    $process = Start-Process -FilePath $exePath -WorkingDirectory (Split-Path -Parent $exePath) -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    $response = $null
    while ((Get-Date) -lt $deadline) {
        if ($process.HasExited) { break }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/ollama/status" -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { break }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }

    $process.Refresh()
    $result = [ordered]@{
        ok = ($null -ne $response -and $response.StatusCode -eq 200 -and -not $process.HasExited)
        executable = $exePath
        pid = $process.Id
        exited = $process.HasExited
        exit_code = if ($process.HasExited) { $process.ExitCode } else { $null }
        http_status = if ($response) { $response.StatusCode } else { $null }
        stdout = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw } else { '' }
        stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { '' }
    }
    $result | ConvertTo-Json -Depth 5
    if (-not $result.ok) { exit 1 }
} finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        $process.WaitForExit(5000) | Out-Null
    }
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}

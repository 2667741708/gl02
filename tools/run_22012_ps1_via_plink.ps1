param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptPath,
    [string]$HostName = "10.30.220.12",
    [string]$UserName = "administrator",
    [string]$RemoteWorkdir = "F:\高炉炼铁项目-real-sensor-v2_V3"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent $PSScriptRoot
$resolvedScript = (Resolve-Path -LiteralPath $ScriptPath).Path
$plink = (Get-Command plink.exe -ErrorAction Stop).Source
$password = [Environment]::GetEnvironmentVariable("BF_22012_SSH_PASSWORD", "Process")
if (-not $password) {
    $agentsPath = Join-Path $root "AGENTS.md"
    $agentsText = Get-Content -LiteralPath $agentsPath -Raw -Encoding UTF8
    $match = [regex]::Match(
        $agentsText,
        "SSH[^\r\n]{0,20}(?::|\uFF1A)([^\r\n]+)"
    )
    if (-not $match.Success) {
        throw "Missing BF_22012_SSH_PASSWORD and AGENTS.md SSH password entry"
    }
    $password = $match.Groups[1].Value.Trim()
}

$passwordFile = [IO.Path]::GetTempFileName()
try {
    [IO.File]::WriteAllText(
        $passwordFile,
        $password,
        [Text.UTF8Encoding]::new($false)
    )
    $body = Get-Content -LiteralPath $resolvedScript -Raw -Encoding UTF8
    $escapedWorkdir = $RemoteWorkdir.Replace("'", "''")
    $remoteScript = @"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
`$OutputEncoding = [System.Text.Encoding]::UTF8
`$ProgressPreference = "SilentlyContinue"
`$env:PYTHONIOENCODING = "utf-8"
`$env:PYTHONUTF8 = "1"
Set-Location -LiteralPath '$escapedWorkdir'
$body
"@
    $encoded = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($remoteScript)
    )
    & $plink -batch -ssh -pwfile $passwordFile "$UserName@$HostName" `
        powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Plink remote PowerShell exited with code $exitCode"
    }
}
finally {
    if (Test-Path -LiteralPath $passwordFile) {
        Remove-Item -LiteralPath $passwordFile -Force
    }
    $password = $null
}

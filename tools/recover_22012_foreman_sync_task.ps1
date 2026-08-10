$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$agentsPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'AGENTS.md'
$agentsText = Get-Content -LiteralPath $agentsPath -Raw -Encoding UTF8
$credentialLabel = 'SSH ' + [char]23494 + [char]30721 + [char]65306
$match = [regex]::Match($agentsText, [regex]::Escape($credentialLabel) + '([^\r\n]+)')
if (-not $match.Success) {
    throw 'Controlled 220.12 credential not found in AGENTS.md.'
}

$server = '10.30.220.12'
$user = 'administrator'
$password = $match.Groups[1].Value.Trim()
$task = '\BlastFurnaceV3PgContinuousSync30s'

$runOutput = & schtasks.exe /Run /S $server /U $user /P $password /TN $task 2>&1
$runExit = $LASTEXITCODE
$queryOutput = & schtasks.exe /Query /S $server /U $user /P $password /TN $task /V /FO LIST 2>&1
$queryExit = $LASTEXITCODE

[ordered]@{
    runExit = $runExit
    runOutput = @($runOutput)
    queryExit = $queryExit
    queryOutput = @($queryOutput)
} | ConvertTo-Json -Depth 4

if ($queryExit -ne 0) {
    exit $queryExit
}

[CmdletBinding()]
param([string]$Work = '.tmp\8093-mcp-parallel-guest-20260813')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Work = Join-Path $Root $Work
$Package = Join-Path $Work 'mcp_parallel_guest_8093_20260813.zip'
$HashFile = Join-Path $Work 'mcp_parallel_guest_8093_20260813.sha256'
$Staging = Join-Path $Work 'package'
$PlanPath = Join-Path $Work 'delta-plan.json'

if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force }
New-Item -ItemType Directory -Path $Staging | Out-Null
$Plan = Get-Content -Raw -LiteralPath $PlanPath -Encoding UTF8 | ConvertFrom-Json
Copy-Item -LiteralPath $PlanPath -Destination (Join-Path $Staging 'delta-plan.json')
foreach ($Change in $Plan.changes) {
    $Name = [IO.Path]::GetFileName([string]$Change.stage)
    Copy-Item -LiteralPath ([string]$Change.local_path) -Destination (Join-Path $Staging $Name)
}
$Accept = Join-Path $Root 'tools\remote_accept_abc33_contextual_assistant.ps1'
Copy-Item -LiteralPath $Accept -Destination (Join-Path $Staging 'remote_accept_abc33_contextual_assistant.ps1')
if (Test-Path -LiteralPath $Package) { Remove-Item -LiteralPath $Package -Force }
Compress-Archive -Path (Join-Path $Staging '*') -DestinationPath $Package
$Hash = (Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash
[IO.File]::WriteAllText($HashFile, $Hash, [Text.Encoding]::ASCII)
[ordered]@{ ok=$true; package=$Package; sha256=$Hash; bytes=(Get-Item -LiteralPath $Package).Length } | ConvertTo-Json

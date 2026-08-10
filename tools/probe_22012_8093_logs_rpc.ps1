param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$agentsPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'AGENTS.md'
$agentsText = Get-Content -LiteralPath $agentsPath -Raw -Encoding UTF8
$credentialLabel = 'SSH ' + [char]23494 + [char]30721 + [char]65306
$match = [regex]::Match($agentsText, [regex]::Escape($credentialLabel) + '([^\r\n]+)')
if (-not $match.Success) { throw 'Controlled 220.12 credential not found in AGENTS.md.' }

$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$server = '10.30.220.12'
$share = '\\10.30.220.12\F$'
$password = $match.Groups[1].Value.Trim()
$rootRelative = ([string]$config.root).Substring(3).Replace('/', '\')
$remoteLogDir = Join-Path (Join-Path $share $rootRelative) 'logs'

$connectOutput = & net.exe use $share $password /user:administrator 2>&1
if ($LASTEXITCODE -ne 0) { throw ('Admin share authentication failed: ' + ($connectOutput -join ' ')) }
try {
    $files = Get-ChildItem -LiteralPath $remoteLogDir -File -ErrorAction Stop |
        Where-Object { $_.Name -like 'proxy_8093*' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 4
    $result = foreach ($file in $files) {
        [ordered]@{
            name = $file.Name
            length = $file.Length
            lastWriteTime = $file.LastWriteTime
            tail = @(Get-Content -LiteralPath $file.FullName -Tail 60 -Encoding UTF8 | ForEach-Object { [string]$_ })
        }
    }
    $result | ConvertTo-Json -Depth 5
}
finally {
    & net.exe use $share /delete /y 2>&1 | Out-Null
}

param(
    [Parameter(Mandatory = $true)][string]$V4List,
    [Parameter(Mandatory = $true)][string]$SecondVersionList,
    [Parameter(Mandatory = $true)][string]$RemoteMainList,
    [Parameter(Mandatory = $true)][string]$RemoteMirrorList
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

function Convert-RemoteFPathToUnc {
    param([string]$Path)
    if ($Path -notmatch '^F:[\\/]') { throw "Only F: remote paths are supported: $Path" }
    return '\\10.30.220.12\F$\' + $Path.Substring(3).Replace('/', '\')
}

$agentsPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'AGENTS.md'
$agentsText = Get-Content -LiteralPath $agentsPath -Raw -Encoding UTF8
$credentialLabel = 'SSH ' + [char]23494 + [char]30721 + [char]65306
$match = [regex]::Match($agentsText, [regex]::Escape($credentialLabel) + '([^\r\n]+)')
if (-not $match.Success) { throw 'Controlled 220.12 credential not found in AGENTS.md.' }

$share = '\\10.30.220.12\F$'
$password = $match.Groups[1].Value.Trim()
$connectOutput = & net.exe use $share $password /user:administrator 2>&1
if ($LASTEXITCODE -ne 0) { throw ('Admin share authentication failed: ' + ($connectOutput -join ' ')) }
try {
    $paths = [ordered]@{
        actualV4 = $V4List
        secondVersion = $SecondVersionList
        remoteMain = Convert-RemoteFPathToUnc -Path $RemoteMainList
        remoteMirror = Convert-RemoteFPathToUnc -Path $RemoteMirrorList
    }
    $hashes = [ordered]@{}
    foreach ($entry in $paths.GetEnumerator()) {
        $hashes[$entry.Key] = (Get-FileHash -LiteralPath $entry.Value -Algorithm SHA256).Hash
    }
    $uniqueHashes = @($hashes.Values | Select-Object -Unique)
    [ordered]@{
        matched = ($uniqueHashes.Count -eq 1)
        sha256 = $uniqueHashes[0]
        hashes = $hashes
    } | ConvertTo-Json -Depth 4
    if ($uniqueHashes.Count -ne 1) { exit 2 }
}
finally {
    & net.exe use $share /delete /y 2>&1 | Out-Null
}

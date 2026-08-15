[CmdletBinding()]
param(
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$OutputPath = 'C:\Users\Administrator\AppData\Local\Temp\8093_source_hashes_20260814.json'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$AllowedExtensions = @('.py', '.ps1', '.js', '.css', '.html', '.sql', '.json', '.yaml', '.yml', '.md')
$AllowedRoots = @(
    '高炉前端数据\智能助手',
    '高炉前端数据\assets',
    '自动诊断服务',
    'tools'
)
$ExcludedSegments = @('\logs\', '\backups\', '\__pycache__\', '\.git\', '\data\', '\node_modules\')
$SecretNamePattern = '(?i)(\.env$|password|passwd|credential|cookie|token|secret|private.?key|storage.?state|service_configs)'

$Rows = @(
    foreach ($AllowedRoot in $AllowedRoots) {
        $Path = Join-Path $Root $AllowedRoot
        if (-not (Test-Path -LiteralPath $Path -PathType Container)) { continue }
        Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            $Full = $_.FullName
            $Relative = $Full.Substring($Root.TrimEnd('\').Length + 1)
            $Excluded = $false
            foreach ($Segment in $ExcludedSegments) {
                if ($Full.IndexOf($Segment, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $Excluded = $true
                    break
                }
            }
            $Eligible = -not $Excluded
            $Eligible = $Eligible -and ($AllowedExtensions -contains $_.Extension.ToLowerInvariant())
            $Eligible = $Eligible -and ($Relative -notmatch $SecretNamePattern)
            if ($Eligible) {
                [ordered]@{
                    path = $Relative
                    length = [long]$_.Length
                    last_write_time_utc = $_.LastWriteTimeUtc.ToString('o')
                    sha256 = (Get-FileHash -LiteralPath $Full -Algorithm SHA256).Hash
                }
            }
        }
    }
)
$Rows = @($Rows | Sort-Object { $_['path'] } -Unique)
$Result = [ordered]@{
    schema = 'bf.8093-source-hash-inventory.v1'
    generated_at = (Get-Date).ToString('o')
    root = $Root
    sensitivity = 'internal_non_secret_hashes_only'
    file_count = $Rows.Count
    files = $Rows
    production_write_performed = $false
}
$Directory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
}
[IO.File]::WriteAllText($OutputPath, ($Result | ConvertTo-Json -Depth 5), $Utf8NoBom)
[ordered]@{
    schema = $Result.schema
    generated_at = $Result.generated_at
    root = $Result.root
    file_count = $Result.file_count
    output_path = $OutputPath
    production_write_performed = $false
} | ConvertTo-Json -Depth 3

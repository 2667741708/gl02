[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InventoryPath,
    [string]$LocalRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputPath = ''
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$Inventory = Get-Content -LiteralPath $InventoryPath -Raw -Encoding utf8 | ConvertFrom-Json
$Rows = foreach ($Item in @($Inventory.files)) {
    $Relative = [string]$Item.path
    $LocalPath = Join-Path $LocalRoot $Relative
    if (-not (Test-Path -LiteralPath $LocalPath -PathType Leaf)) {
        [ordered]@{
            path = $Relative
            status = 'remote_only'
            remote_sha256 = [string]$Item.sha256
            local_sha256 = $null
        }
        continue
    }
    $LocalHash = (Get-FileHash -LiteralPath $LocalPath -Algorithm SHA256).Hash
    if ($LocalHash -ne [string]$Item.sha256) {
        [ordered]@{
            path = $Relative
            status = 'different'
            remote_sha256 = [string]$Item.sha256
            local_sha256 = $LocalHash
        }
    }
}

$Rows = @($Rows | Sort-Object { $_['path'] })
$Result = [ordered]@{
    schema = 'bf.remote-local-source-comparison.v1'
    generated_at = (Get-Date).ToString('o')
    inventory_path = (Resolve-Path -LiteralPath $InventoryPath).Path
    local_root = (Resolve-Path -LiteralPath $LocalRoot).Path
    remote_file_count = [int]$Inventory.file_count
    remote_only_count = @($Rows | Where-Object { $_['status'] -eq 'remote_only' }).Count
    different_count = @($Rows | Where-Object { $_['status'] -eq 'different' }).Count
    rows = $Rows
}

$Json = $Result | ConvertTo-Json -Depth 5
if ($OutputPath) {
    $Parent = Split-Path -Parent $OutputPath
    if ($Parent -and -not (Test-Path -LiteralPath $Parent -PathType Container)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    [IO.File]::WriteAllText($OutputPath, $Json, $Utf8NoBom)
}
$Json

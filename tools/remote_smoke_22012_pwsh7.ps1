[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$listeners = @(8093, 8094, 8768, 8770, 5432 | ForEach-Object {
    $port = [int]$_
    $row = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    [ordered]@{
        port = $port
        listening = ($null -ne $row)
        pid = if ($row) { [int]$row.OwningProcess } else { $null }
    }
})

[ordered]@{
    schema = 'bf.remote.pwsh7.smoke.v1'
    ok = (@($listeners | Where-Object { -not $_.listening }).Count -eq 0)
    executable = [Environment]::ProcessPath
    ps_version = $PSVersionTable.PSVersion.ToString()
    ps_edition = $PSVersionTable.PSEdition
    utf8_text = '冀南钢铁：远端中文执行正常'
    location = (Get-Location).Path
    listeners = $listeners
} | ConvertTo-Json -Depth 5

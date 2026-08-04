[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"

$vars = @("IMES_DB_USER", "IMES_DB_PASSWORD", "IMES_DB_HOST", "IMES_DB_PORT", "IMES_DB_NAME")
foreach ($v in $vars) {
    $m = [Environment]::GetEnvironmentVariable($v, "Machine")
    $u = [Environment]::GetEnvironmentVariable($v, "User")
    if ($m) { Write-Output "$v`_MACHINE: SET" } else { Write-Output "$v`_MACHINE: NOT_SET" }
    if ($u) { Write-Output "$v`_USER: SET" } else { Write-Output "$v`_USER: NOT_SET" }
}

Write-Output "===TCP_VASTBASE==="
$ok = Test-NetConnection 10.10.181.195 -Port 5432 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($ok) { Write-Output "TCP_10.10.181.195_5432: OK" } else { Write-Output "TCP_10.10.181.195_5432: FAIL" }

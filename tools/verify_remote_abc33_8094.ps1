$ErrorActionPreference = "Stop"
function Get-Pid([int]$Port) {
    $x = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($x) { return [int]$x.OwningProcess }
    return $null
}
function Get-Http([string]$Uri) {
    for ($i=1; $i -le 6; $i++) {
        try { return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 20 }
        catch { if ($i -eq 6) { throw }; Start-Sleep -Seconds 2 }
    }
}
$p8093 = Get-Pid 8093
$p8768 = Get-Pid 8768
$p8770 = Get-Pid 8770
$p11434 = Get-Pid 11434
$page = Get-Http "http://127.0.0.1:8094/?abc33_verify=20260808"
if ([int]$page.StatusCode -ne 200) { throw "8094 page status is not 200" }
if (-not ([string]$page.Content).Contains("abc-furnace-rules-production.js")) { throw "8094 page ABC asset marker missing" }
$latest = Get-Http "http://127.0.0.1:8094/api/furnace-rules/latest"
if ([int]$latest.StatusCode -ne 200) { throw "furnace-rules latest status is not 200" }
$latestText = [string]$latest.Content
foreach ($secret in @("formula_terms","normalized_value","contributions","feature_key","weight_overrides")) {
    if ($latestText.Contains($secret)) { throw "public API leaked $secret" }
}
$adminStatus = 0
try { $admin = Get-Http "http://127.0.0.1:8094/furnace-rule-admin.html"; $adminStatus = [int]$admin.StatusCode }
catch { if ($_.Exception.Response) { $adminStatus = [int]$_.Exception.Response.StatusCode } }
if ($adminStatus -ne 403) { throw "admin page without session expected 403, got $adminStatus" }
[ordered]@{
    ok = $true
    http8094 = [int]$page.StatusCode
    latestStatus = [int]$latest.StatusCode
    adminUnauthenticatedStatus = $adminStatus
    publicContractRedacted = $true
    pid8093 = $p8093
    pid8768 = $p8768
    pid8770 = $p8770
    pid11434 = $p11434
    pageBytes = $page.RawContentLength
} | ConvertTo-Json -Depth 5

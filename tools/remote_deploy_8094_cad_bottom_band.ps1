$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$targetHtml = Join-Path $root "高炉前端数据\frontend_dashboard_v3.8094_preview.server.html"
$patcher = "C:\Users\Administrator\AppData\Local\Temp\patch_8094_cad_bottom_band.py"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"
$revisionMarker = "BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\8094_cad_bottom_band_$stamp"
$deployed = $false

function Get-ListenerProcessId {
    param([Parameter(Mandatory = $true)][int]$Port)
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
    if (-not $listener) { throw "Port $Port has no listening socket" }
    return [int]$listener.OwningProcess
}

function Invoke-HttpWithRetry {
    param([Parameter(Mandatory = $true)][string]$Uri)
    $lastError = $null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try { return Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 60 }
        catch {
            $lastError = $_
            if ($attempt -lt 3) { Start-Sleep -Seconds 2 }
        }
    }
    throw $lastError
}

if (-not (Test-Path -LiteralPath $targetHtml -PathType Leaf)) {
    throw "8094 target HTML not found: $targetHtml"
}
if (-not (Test-Path -LiteralPath $patcher -PathType Leaf)) {
    throw "Remote patcher not found: $patcher"
}

$taskBefore = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
if ($taskBefore.State -ne "Running") { throw "8094 preview task is not running: $($taskBefore.State)" }
$pid8093Before = Get-ListenerProcessId -Port 8093
$pid8094Before = Get-ListenerProcessId -Port 8094
$pid8768Before = Get-ListenerProcessId -Port 8768
$pid8770Before = $null
try { $pid8770Before = Get-ListenerProcessId -Port 8770 } catch { }
$html8093Before = (Invoke-HttpWithRetry -Uri "http://127.0.0.1:8093/?cad_bottom_band_probe=$stamp").Content
$htmlBefore = Get-Content -LiteralPath $targetHtml -Raw -Encoding UTF8
if ($htmlBefore -notmatch "OPS-8093-CAD-GHOST-BANDS-FIX" -or $htmlBefore -notmatch "ops-cad-ghost-bands-fix") {
    throw "8094 HTML does not match the expected guarded CAD layout baseline"
}

New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $targetHtml -Destination (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") -Force

try {
    & "C:\Program Files\Python311\python.exe" -X utf8 $patcher --path $targetHtml
    $served = Invoke-HttpWithRetry -Uri "http://127.0.0.1:8094/?cad_bottom_band_fix=$stamp"
    $servedHtml = [string]$served.Content
    if (
        $served.StatusCode -ne 200 -or
        $servedHtml -notmatch "BUG-BF3D-CAD-BOTTOM-BAND-20260804" -or
        $servedHtml -notmatch $revisionMarker -or
        $servedHtml -notmatch "padding-bottom: 0 !important" -or
        $servedHtml -notmatch "bottom: 0 !important"
    ) {
        throw "8094 did not serve the CAD bottom-band fix"
    }
    $html8093After = (Invoke-HttpWithRetry -Uri "http://127.0.0.1:8093/?cad_bottom_band_probe=$stamp").Content
    if ($html8093Before -ne $html8093After) { throw "8093 served HTML changed during the 8094-only deployment" }

    $taskAfter = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
    $pid8093After = Get-ListenerProcessId -Port 8093
    $pid8094After = Get-ListenerProcessId -Port 8094
    $pid8768After = Get-ListenerProcessId -Port 8768
    $pid8770After = $null
    try { $pid8770After = Get-ListenerProcessId -Port 8770 } catch { }
    if ($taskAfter.State -ne "Running" -or $pid8093After -ne $pid8093Before -or $pid8094After -ne $pid8094Before -or $pid8768After -ne $pid8768Before) {
        throw "8094-only deployment disturbed 8093/8094/8768 runtime state"
    }
    if ($null -ne $pid8770Before -and $pid8770After -ne $pid8770Before) { throw "8094 billboard runtime 8770 process changed" }

    $deployed = $true
    [ordered]@{
        ok = $true
        scope = "8094 HTML only"
        backup = $backup
        http8094 = $served.StatusCode
        task8094 = $taskAfter.State.ToString()
        pid8093Unchanged = ($pid8093After -eq $pid8093Before)
        pid8094Unchanged = ($pid8094After -eq $pid8094Before)
        pid8768Unchanged = ($pid8768After -eq $pid8768Before)
        pid8770Unchanged = ($null -eq $pid8770Before -or $pid8770After -eq $pid8770Before)
        htmlSha256 = (Get-FileHash -LiteralPath $targetHtml -Algorithm SHA256).Hash
        marker = "BUG-BF3D-CAD-BOTTOM-BAND-20260804"
        revisionMarker = $revisionMarker
    } | ConvertTo-Json -Depth 4
}
catch {
    Copy-Item -LiteralPath (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") -Destination $targetHtml -Force
    throw
}
finally {
    if (-not $deployed) { Write-Warning "8094 HTML deployment rolled back from $backup" }
}

$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"

function Wait-Port {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($found -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$listener8768Before = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
$listener8770Before = Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
$before = [ordered]@{
    TaskState = $task.State.ToString()
    Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Port8094 = [bool](Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Port8768 = [bool]$listener8768Before
    Port8770 = [bool]$listener8770Before
    Process8768 = $listener8768Before.OwningProcess
    Process8770 = $listener8770Before.OwningProcess
}
if (-not $before.Port8093 -or -not $before.Port8768 -or -not $before.Port8770) {
    throw "8093, 8768, or 8770 is not listening; refusing isolated 8094 restart"
}

try {
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    Wait-Port -Port 8094 -Listening $false -TimeoutSeconds 90
    if (-not (Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "8093 stopped unexpectedly during 8094 restart"
    }
    if (-not (Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "8768 stopped unexpectedly during 8094 restart"
    }
    if (-not (Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "8770 stopped unexpectedly during 8094 restart"
    }

    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    Wait-Port -Port 8094 -Listening $true -TimeoutSeconds 120
    Start-Sleep -Seconds 3
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/?t=restart-$(Get-Date -Format yyyyMMddHHmmss)#overview" -TimeoutSec 60
    if ($response.StatusCode -ne 200) { throw "8094 HTTP status is $($response.StatusCode)" }
    if (-not $response.Content.Contains("BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716")) {
        throw "8094 HTTP is missing adaptive layout marker"
    }
    if (-not $response.Content.Contains("20260726-viewport-wheel-r8")) {
        throw "8094 HTTP is missing the current billboard viewport adapter version"
    }
    $listener8768After = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop |
        Select-Object -First 1
    $listener8770After = Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction Stop |
        Select-Object -First 1
    if (
        $listener8768After.OwningProcess -ne $listener8768Before.OwningProcess -or
        $listener8770After.OwningProcess -ne $listener8770Before.OwningProcess
    ) {
        throw "8094 restart unexpectedly changed the 8768 or 8770 process"
    }

    [ordered]@{
        RestartedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        Before = $before
        After = [ordered]@{
            TaskState = (Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName).State.ToString()
            Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
            Port8094 = [bool](Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
            Port8768 = [bool]$listener8768After
            Port8770 = [bool]$listener8770After
            Process8768Unchanged = $true
            Process8770Unchanged = $true
            HttpStatus = [int]$response.StatusCode
            HttpLength = $response.Content.Length
            HasAdaptiveFix = $response.Content.Contains("BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716")
            HasViewportWheelR8 = $response.Content.Contains("20260726-viewport-wheel-r8")
        }
    } | ConvertTo-Json -Depth 6
}
catch {
    if ((Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName).State -ne "Running") {
        Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    }
    throw
}

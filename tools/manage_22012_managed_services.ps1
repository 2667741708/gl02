param(
    [ValidateSet("status", "ensure", "start", "stop", "restart", "health", "install")]
    [string]$Action = "status",
    [string[]]$ConfigPath = @(),
    [string]$ConfigDir = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs",
    [string]$ConfigPattern = "22012_*.json",
    [string]$InstallScript = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\install_22012_managed_nssm_service.ps1",
    [string]$HealthScript = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\check_managed_nssm_service_health.ps1"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"
chcp 65001 > $null

function Read-Config([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Config not found: $Path"
    }
    return ([System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8) | ConvertFrom-Json)
}

function Get-ConfigPaths {
    if ($ConfigPath.Count -gt 0) {
        return @($ConfigPath)
    }
    if (-not (Test-Path -LiteralPath $ConfigDir)) {
        throw "ConfigDir not found: $ConfigDir"
    }
    return @(Get-ChildItem -LiteralPath $ConfigDir -Filter $ConfigPattern | Sort-Object Name | ForEach-Object { $_.FullName })
}

function Invoke-ServiceHealth([string]$Path) {
    if (-not (Test-Path -LiteralPath $HealthScript)) {
        return [pscustomobject]@{ ok = $false; code = $null; output = "health_script_missing=$HealthScript" }
    }
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $HealthScript -ConfigPath $Path 2>&1
    $code = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }
    return [pscustomobject]@{ ok = ($code -eq 0); code = $code; output = ($output -join "`n") }
}

$results = @()
foreach ($path in Get-ConfigPaths) {
    $config = Read-Config $path
    $name = [string]$config.serviceName
    $service = Get-Service -Name $name -ErrorAction SilentlyContinue
    $before = if ($service) { $service.Status.ToString() } else { "Missing" }
    $note = ""
    $health = $null

    switch ($Action) {
        "status" {
            $note = "checked"
        }
        "ensure" {
            if (-not $service) {
                if (-not (Test-Path -LiteralPath $InstallScript)) {
                    throw "Install script missing: $InstallScript"
                }
                $installOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $InstallScript -ConfigPath $path 2>&1
                $note = "installed: $($installOutput -join ' ')"
            } elseif ($service.Status -ne "Running") {
                Start-Service -Name $name
                $note = "started"
            } else {
                $note = "already_running"
            }
            $health = Invoke-ServiceHealth $path
        }
        "start" {
            if (-not $service) {
                throw "Service missing: $name. Use -Action install or ensure."
            }
            if ($service.Status -eq "Running") {
                $note = "already_running"
            } else {
                Start-Service -Name $name
                $note = "started"
            }
        }
        "stop" {
            if (-not $service) {
                $note = "already_missing"
            } elseif ($service.Status -eq "Stopped") {
                $note = "already_stopped"
            } else {
                Stop-Service -Name $name -Force
                $note = "stopped"
            }
        }
        "restart" {
            if (-not $service) {
                throw "Service missing: $name. Use -Action install or ensure."
            }
            Restart-Service -Name $name -Force
            $note = "restarted"
            $health = Invoke-ServiceHealth $path
        }
        "health" {
            $health = Invoke-ServiceHealth $path
            $note = "health_checked"
        }
        "install" {
            if (-not (Test-Path -LiteralPath $InstallScript)) {
                throw "Install script missing: $InstallScript"
            }
            $installOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $InstallScript -ConfigPath $path 2>&1
            $note = "installed: $($installOutput -join ' ')"
        }
    }

    Start-Sleep -Milliseconds 300
    $afterService = Get-Service -Name $name -ErrorAction SilentlyContinue
    $after = if ($afterService) { $afterService.Status.ToString() } else { "Missing" }
    $results += [pscustomobject]@{
        service = $name
        action = $Action
        before = $before
        after = $after
        health_ok = if ($null -eq $health) { $null } else { $health.ok }
        health_code = if ($null -eq $health) { $null } else { $health.code }
        note = $note
        config = $path
    }
}

$results | ConvertTo-Json -Depth 5

param(
    [string]$ProjectRoot = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW",
    [string]$PayloadRoot = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_27b_only_20260726\payload",
    [string]$ResultPath = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_27b_only_20260726\result.json"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ollamaBaseUrl = "http://127.0.0.1:11434"
$chatModel = "chiqiong-blast-furnace:latest"
$frontendRoot = Join-Path $ProjectRoot "高炉前端数据"
$backendPath = Join-Path $frontendRoot "智能助手\backend\ollama_proxy_server.py"
$previewPath = Join-Path $frontendRoot "frontend_dashboard_v3.8094_preview.server.html"
$runnerPath = Join-Path $ProjectRoot "tools\run_22012_8094_preview.ps1"
$configPath = Join-Path $ProjectRoot "tools\service_configs\22012_BFOllama11434.json"
$manageScript = Join-Path $ProjectRoot "tools\manage_22012_managed_services.ps1"
$payloadBackend = Join-Path $PayloadRoot "ollama_proxy_server.py"
$payloadPreview = Join-Path $PayloadRoot "frontend_dashboard_v3.8094_preview.server.html"
$payloadRunner = Join-Path $PayloadRoot "run_22012_8094_preview.ps1"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $ProjectRoot "logs\deploy_27b_only_$stamp"
$quarantineRoot = Join-Path "F:\Ollama\models\disabled-manifests" "single_27b_$stamp"
$result = [ordered]@{
    ok = $false
    started_at = (Get-Date).ToString("o")
    phase = "initializing"
    backup_root = $backupRoot
    quarantine_root = $quarantineRoot
    config_path = $configPath
    ollama_max_loaded_models = $null
    quarantined_manifests = @()
    tags = @()
    loaded_models = @()
    listener_8093_before = @()
    listener_8093_after = @()
    listener_8094_after = @()
    status_8094 = $null
    direct_30b_status = $null
    error = ""
}

function Save-Result {
    $result.finished_at = (Get-Date).ToString("o")
    $parent = Split-Path -Parent $ResultPath
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $result | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
}

function Get-Listener {
    param([int]$Port)
    return @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object LocalAddress, LocalPort, OwningProcess
    )
}

function Wait-HttpReady {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            Invoke-RestMethod -Method Get -Uri $Uri -TimeoutSec 3 | Out-Null
            return
        } catch {
            Start-Sleep -Seconds 1
        }
    } while ((Get-Date) -lt $deadline)
    throw "HTTP endpoint did not become ready: $Uri"
}

Save-Result

try {
    $required = @(
        $backendPath,
        $previewPath,
        $runnerPath,
        $configPath,
        $manageScript,
        $payloadBackend,
        $payloadPreview,
        $payloadRunner
    )
    foreach ($path in $required) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required file is missing: $path"
        }
    }
    $result.phase = "validating_payload"
    Save-Result

    & "C:\Program Files\Python311\python.exe" -X utf8 -m py_compile $payloadBackend
    if ($LASTEXITCODE -ne 0) {
        throw "Payload backend failed Python syntax validation."
    }
    $backendText = Get-Content -LiteralPath $payloadBackend -Raw -Encoding UTF8
    if ($backendText -notmatch "resolve_upstream_model" -or $backendText -notmatch "/api/ps") {
        throw "Payload backend is missing the loaded-model policy."
    }
    $runnerText = Get-Content -LiteralPath $payloadRunner -Raw -Encoding UTF8
    if ($runnerText -notmatch "BF_ALLOWED_LOADED_MODELS" -or $runnerText -match "BF_LLM_MODEL\s*=") {
        throw "Payload runner does not implement the expected dynamic loaded-model policy."
    }
    if ($runnerText -notmatch 'BF_QA_KNOWLEDGE_SEARCH_MODE\s*=\s*"keyword"') {
        throw "Payload runner must keep 8094 RAG in keyword mode on single-model Ollama."
    }

    $result.listener_8093_before = @(Get-Listener -Port 8093)
    $result.phase = "backing_up"
    Save-Result
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    Copy-Item -LiteralPath $backendPath -Destination (Join-Path $backupRoot "ollama_proxy_server.py") -Force
    Copy-Item -LiteralPath $previewPath -Destination (Join-Path $backupRoot "frontend_dashboard_v3.8094_preview.server.html") -Force
    Copy-Item -LiteralPath $runnerPath -Destination (Join-Path $backupRoot "run_22012_8094_preview.ps1") -Force
    Copy-Item -LiteralPath $configPath -Destination (Join-Path $backupRoot "22012_BFOllama11434.json") -Force

    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    }
    foreach ($listener in @(Get-Listener -Port 8094)) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine -match "ollama_proxy_server.py") {
            Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }

    Copy-Item -LiteralPath $payloadBackend -Destination $backendPath -Force
    Copy-Item -LiteralPath $payloadPreview -Destination $previewPath -Force
    Copy-Item -LiteralPath $payloadRunner -Destination $runnerPath -Force

    $result.phase = "updating_ollama_policy"
    Save-Result
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $config.env) {
        $config | Add-Member -MemberType NoteProperty -Name env -Value ([pscustomobject]@{})
    }
    if ($config.env.PSObject.Properties.Name -contains "OLLAMA_MAX_LOADED_MODELS") {
        $config.env.OLLAMA_MAX_LOADED_MODELS = "1"
    } else {
        $config.env | Add-Member -MemberType NoteProperty -Name OLLAMA_MAX_LOADED_MODELS -Value "1"
    }
    if ($config.env.PSObject.Properties.Name -contains "OLLAMA_KEEP_ALIVE") {
        $config.env.OLLAMA_KEEP_ALIVE = "24h"
    } else {
        $config.env | Add-Member -MemberType NoteProperty -Name OLLAMA_KEEP_ALIVE -Value "24h"
    }
    foreach ($post in @($config.health.httpPost)) {
        if ($post.json) {
            $post.json.model = $chatModel
            $post.json.keep_alive = "24h"
        }
    }
    $config | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $configPath -Encoding UTF8
    $result.ollama_max_loaded_models = "1"

    $manifestPaths = @(
        "F:\Ollama\models\manifests\registry.ollama.ai\library\bf-diagnosis-runtime\v1",
        "F:\Ollama\models\manifests\registry.ollama.ai\library\chiqiong-blast-furnace\latest_M"
    )
    foreach ($manifestPath in $manifestPaths) {
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            continue
        }
        $relative = $manifestPath.Substring("F:\Ollama\models\manifests\".Length)
        $destination = Join-Path $quarantineRoot $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Move-Item -LiteralPath $manifestPath -Destination $destination -Force
        $result.quarantined_manifests += [ordered]@{
            original = $manifestPath
            quarantined = $destination
        }
    }
    $result.phase = "restarting_ollama"
    Save-Result

    & powershell -NoProfile -ExecutionPolicy Bypass -File $manageScript -Action restart -ConfigPath $configPath
    if ($LASTEXITCODE -ne 0) {
        throw "BFOllama11434 managed service restart failed with exit code $LASTEXITCODE."
    }
    Wait-HttpReady -Uri "$ollamaBaseUrl/api/version" -TimeoutSeconds 120

    $result.phase = "warming_27b"
    Save-Result
    $warmPayload = @{
        model = $chatModel
        messages = @(@{ role = "user"; content = "ping" })
        stream = $false
        keep_alive = "24h"
        think = $false
        options = @{
            num_predict = 1
            temperature = 0
            think = $false
        }
    } | ConvertTo-Json -Depth 12 -Compress
    Invoke-RestMethod -Method Post -Uri "$ollamaBaseUrl/api/chat" `
        -ContentType "application/json; charset=utf-8" -Body $warmPayload -TimeoutSec 240 | Out-Null

    $result.phase = "starting_8094"
    Save-Result
    if ($task) {
        Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    } else {
        throw "Scheduled task not found: $taskPath$taskName"
    }
    Wait-HttpReady -Uri "http://127.0.0.1:8094/api/ollama/status" -TimeoutSeconds 60

    $tags = Invoke-RestMethod -Method Get -Uri "$ollamaBaseUrl/api/tags" -TimeoutSec 5
    $running = Invoke-RestMethod -Method Get -Uri "$ollamaBaseUrl/api/ps" -TimeoutSec 5
    $result.tags = @($tags.models | ForEach-Object { $_.name })
    $result.loaded_models = @($running.models | ForEach-Object { $_.name })
    if (@($result.tags | Where-Object { $_ -in @("bf-diagnosis-runtime:v1", "chiqiong-blast-furnace:latest_M") }).Count -gt 0) {
        throw "30.5B tags are still exposed after quarantine."
    }
    if ($result.loaded_models.Count -ne 1 -or $result.loaded_models[0] -ne $chatModel) {
        throw "Expected only $chatModel to be loaded; got: $($result.loaded_models -join ', ')"
    }

    try {
        $badPayload = @{
            model = "bf-diagnosis-runtime:v1"
            messages = @(@{ role = "user"; content = "ping" })
            stream = $false
            options = @{ num_predict = 1 }
        } | ConvertTo-Json -Depth 8 -Compress
        Invoke-WebRequest -Method Post -Uri "$ollamaBaseUrl/api/chat" `
            -ContentType "application/json; charset=utf-8" -Body $badPayload -TimeoutSec 5 | Out-Null
        $result.direct_30b_status = 200
        throw "Direct 30.5B request unexpectedly succeeded."
    } catch [System.Net.WebException] {
        $response = $_.Exception.Response
        $result.direct_30b_status = if ($response) { [int]$response.StatusCode } else { -1 }
    }
    if ($result.direct_30b_status -notin @(400, 404)) {
        throw "Direct 30.5B request did not fail as model-not-found; status=$($result.direct_30b_status)"
    }

    $result.status_8094 = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8094/api/ollama/status" -TimeoutSec 5
    $result.listener_8093_after = @(Get-Listener -Port 8093)
    $result.listener_8094_after = @(Get-Listener -Port 8094)
    $result.ok = [bool]($result.status_8094.ok -and $result.status_8094.model_ok)
    if (-not $result.ok) {
        throw "8094 model status is not healthy."
    }
    $result.phase = "completed"
    Save-Result
} catch {
    $result.phase = "failed"
    $result.error = $_.Exception.Message
    Save-Result
    throw
}

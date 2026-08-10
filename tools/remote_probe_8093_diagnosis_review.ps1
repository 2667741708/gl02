$ErrorActionPreference = 'Stop'

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$configPath = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$serviceNames = @('BFV4PreviewProxy8093', 'BFV4PreviewWs8768')
$filePaths = @(
    (Join-Path $root '高炉前端数据\智能助手\backend\diagnosis_review.py'),
    (Join-Path $root '高炉前端数据\智能助手\backend\diagnosis_model_review.py'),
    (Join-Path $root '高炉前端数据\智能助手\backend\diagnosis_ai_analysis_api.py'),
    (Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'),
    (Join-Path $root '高炉前端数据\assets\bf-diagnosis-review-local.js'),
    (Join-Path $root '高炉前端数据\assets\bf-diagnosis-review-local.css'),
    (Join-Path $root '高炉前端数据\assets\bf-diagnosis-manual-score-local.js'),
    (Join-Path $root '高炉前端数据\assets\bf-diagnosis-manual-score-local.css')
)

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "8093 service config is missing: $configPath"
}

$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$environmentNames = @()
$environmentPresence = [ordered]@{}
if ($config.env) {
    foreach ($property in $config.env.PSObject.Properties) {
        $environmentNames += $property.Name
        $value = [string]$property.Value
        $environmentPresence[$property.Name] = [ordered]@{
            configured = -not [string]::IsNullOrWhiteSpace($value)
            value_length = $value.Length
            sensitive = $property.Name -match '(?i)password|secret|token|key'
        }
    }
}

$services = foreach ($name in $serviceNames) {
    $service = Get-Service -Name $name -ErrorAction Stop
    [ordered]@{
        name = $name
        status = $service.Status.ToString()
    }
}

$listeners = foreach ($port in @(8093, 8768, 5432)) {
    $items = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    [ordered]@{
        port = $port
        listening = $items.Count -gt 0
        owning_processes = @($items | Select-Object -ExpandProperty OwningProcess -Unique)
    }
}

$files = foreach ($path in $filePaths) {
    $exists = Test-Path -LiteralPath $path
    [ordered]@{
        relative_path = if ($path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { $path.Substring($root.Length).TrimStart('\') } else { $path }
        exists = $exists
        sha256 = if ($exists) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash } else { $null }
    }
}

$http = [ordered]@{}
foreach ($uri in @(
    'http://127.0.0.1:8093/',
    'http://127.0.0.1:8093/api/diagnosis-review-context',
    'http://127.0.0.1:8093/api/diagnosis-ai-analysis?label=normal'
)) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $uri -TimeoutSec 5
        $http[$uri] = [ordered]@{ status = [int]$response.StatusCode; body_length = $response.Content.Length }
    }
    catch {
        $status = $null
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        $http[$uri] = [ordered]@{ status = $status; error_type = $_.Exception.GetType().Name }
    }
}

[ordered]@{
    schema = 'ops.8093.diagnosis-ai-analysis.probe.v1'
    service_config = [ordered]@{
        path = $configPath
        executable = $config.executable
        arguments = $config.arguments
        working_directory = $config.working_directory
        environment_names = @($environmentNames | Sort-Object)
        environment_presence = $environmentPresence
    }
    machine_environment_presence = [ordered]@{
        GL02_PGUSER = -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable('GL02_PGUSER', 'Machine'))
        GL02_PGPASSWORD = -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable('GL02_PGPASSWORD', 'Machine'))
    }
    services = $services
    listeners = $listeners
    files = $files
    http = $http
} | ConvertTo-Json -Depth 8

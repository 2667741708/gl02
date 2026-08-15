[CmdletBinding()]
param(
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$OutputPath = 'C:\Users\Administrator\AppData\Local\Temp\8093_authoritative_snapshot.json'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

function Get-ListenerPid([int]$Port) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function ConvertTo-RedactedMap([object]$Value) {
    $Result = [ordered]@{}
    foreach ($Property in $Value.PSObject.Properties) {
        $Name = [string]$Property.Name
        if ($Name -match '(?i)(password|passwd|pwd|token|secret|cookie|credential|private|connection|string|auth|api.?key)') {
            $Result[$Name] = '<redacted>'
        }
        else {
            $Result[$Name] = $Property.Value
        }
    }
    return $Result
}

$RelativeFiles = @(
    '高炉前端数据\frontend_dashboard_v3.server.html',
    '高炉前端数据\assets\abc-furnace-rules-production.js',
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\abc_score_explanation.py',
    '高炉前端数据\智能助手\backend\assistant_pg.py',
    '高炉前端数据\智能助手\backend\abc_rule_assistant_analysis.py',
    '高炉前端数据\智能助手\backend\schema\postgresql_assistant.sql',
    '高炉前端数据\智能助手\backend\schema\20260811_abc_contextual_assistant.sql',
    'tools\manage_22012_managed_services.ps1',
    'tools\service_configs\22012_BFV4PreviewProxy8093.json'
)
$Hashes = [ordered]@{}
foreach ($Relative in $RelativeFiles) {
    $Path = Join-Path $Root $Relative
    $Hashes[$Relative] = [ordered]@{
        exists = Test-Path -LiteralPath $Path -PathType Leaf
        sha256 = if (Test-Path -LiteralPath $Path -PathType Leaf) {
            (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
        } else { $null }
    }
}

$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$PythonVersion = & 'C:\Program Files\Python311\python.exe' --version 2>&1 | Out-String
$Snapshot = [ordered]@{
    schema = 'bf.8093.authoritative-redacted-snapshot.v1'
    generated_at = (Get-Date).ToString('o')
    requirement_id = 'OPS-8093-AUTHORITATIVE-LOCAL-SYNC-20260813'
    target = '10.30.220.12:8093'
    sensitivity = 'internal_non_secret'
    secret_values_included = $false
    runtime = [ordered]@{
        os = [Environment]::OSVersion.VersionString
        powershell = $PSVersionTable.PSVersion.ToString()
        python = $PythonVersion.Trim()
        service = (Get-Service 'BFV4PreviewProxy8093').Status.ToString()
        listeners = [ordered]@{
            '8093' = Get-ListenerPid 8093
            '8094' = Get-ListenerPid 8094
            '8768' = Get-ListenerPid 8768
            '8770' = Get-ListenerPid 8770
            '5432' = Get-ListenerPid 5432
            '11434' = Get-ListenerPid 11434
        }
    }
    service_config = [ordered]@{
        schema = $Config.schema
        serviceName = $Config.serviceName
        root = $Config.root
        workDir = $Config.workDir
        executable = $Config.executable
        python = $Config.python
        arguments = @($Config.arguments)
        envMachine_names = @($Config.envMachine)
        env_redacted = ConvertTo-RedactedMap $Config.env
        health = $Config.health
    }
    file_hashes = $Hashes
    invalidation = 'Refresh before every production mutation and after every successful deployment.'
}
$Directory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
}
[IO.File]::WriteAllText($OutputPath, ($Snapshot | ConvertTo-Json -Depth 10), $Utf8NoBom)
$Snapshot | ConvertTo-Json -Depth 10

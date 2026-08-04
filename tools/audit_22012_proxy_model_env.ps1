$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Get-ProcessEnvironmentValue {
    param(
        [Parameter(Mandatory = $true)][int]$TargetProcessId,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $python = "C:\Program Files\Python311\python.exe"
    $code = @"
import sys
import psutil

try:
    process = psutil.Process(int(sys.argv[1]))
    print(process.environ().get(sys.argv[2], ""))
except Exception as exc:
    print("ENV_ERROR:" + str(exc))
"@
    $temporaryScript = Join-Path $env:TEMP ("bf_proxy_env_" + [guid]::NewGuid().ToString("N") + ".py")
    [IO.File]::WriteAllText($temporaryScript, $code, [Text.UTF8Encoding]::new($false))
    try {
        return (& $python $temporaryScript $TargetProcessId $Name 2>$null) -join "`n"
    } finally {
        Remove-Item -LiteralPath $temporaryScript -Force -ErrorAction SilentlyContinue
    }
}

$rows = @()
foreach ($port in @(8092, 8093, 8094)) {
    foreach ($listener in @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
        $processId = [int]$listener.OwningProcess
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
        $rows += [pscustomobject]@{
            port = $port
            pid = $processId
            parent_pid = $process.ParentProcessId
            creation_date = $process.CreationDate
            command_line = $process.CommandLine
            BF_LLM_MODEL = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_LLM_MODEL"
            OLLAMA_BASE_URL = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "OLLAMA_BASE_URL"
            BF_PUBLIC_MODEL_NAME = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_PUBLIC_MODEL_NAME"
            BF_PUBLIC_MODEL_ID = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_PUBLIC_MODEL_ID"
            BF_ALLOWED_LOADED_MODELS = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_ALLOWED_LOADED_MODELS"
            BF_QA_KNOWLEDGE_SEARCH_MODE = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_QA_KNOWLEDGE_SEARCH_MODE"
        }
    }
}

$ollama = @()
foreach ($listener in @(Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)) {
    $processId = [int]$listener.OwningProcess
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    $ollama += [pscustomobject]@{
        port = 11434
        pid = $processId
        parent_pid = $process.ParentProcessId
        command_line = $process.CommandLine
        OLLAMA_MAX_LOADED_MODELS = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "OLLAMA_MAX_LOADED_MODELS"
        OLLAMA_KEEP_ALIVE = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "OLLAMA_KEEP_ALIVE"
        OLLAMA_MODELS = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "OLLAMA_MODELS"
    }
}

$connections = @(
    Get-NetTCPConnection -ErrorAction SilentlyContinue |
        Where-Object {
            $_.RemotePort -eq 11434 -or
            $_.LocalPort -in @(8092, 8093, 8094, 11434)
        } |
        Select-Object State, LocalAddress, LocalPort, RemoteAddress, RemotePort, OwningProcess,
            CreationTime
)

[pscustomobject]@{
    collected_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
    proxies = $rows
    ollama = $ollama
    connections = $connections
} | ConvertTo-Json -Depth 8

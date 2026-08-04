$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Get-EnvValueFromProcess([int]$TargetProcessId, [string]$Name) {
    $python = "C:\Program Files\Python311\python.exe"
    $code = @"
import os, sys
try:
    import psutil
    p = psutil.Process(int(sys.argv[1]))
    print(p.environ().get(sys.argv[2], ""))
except Exception as e:
    print("ENV_ERROR:" + str(e))
"@
    $tmp = Join-Path $env:TEMP ("read_env_" + [guid]::NewGuid().ToString("N") + ".py")
    [System.IO.File]::WriteAllText($tmp, $code, [System.Text.Encoding]::UTF8)
    try {
        return (& $python $tmp $TargetProcessId $Name 2>$null) -join "`n"
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

foreach ($port in @(8092, 8093)) {
    Write-Host "=== PORT $port ==="
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if (-not $listeners.Count) {
        Write-Host "listen=false"
        continue
    }
    foreach ($listener in $listeners) {
        $pidValue = [int]$listener.OwningProcess
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
        [pscustomobject]@{
            port = $port
            pid = $pidValue
            parent = $proc.ParentProcessId
            creation = $proc.CreationDate
            command = $proc.CommandLine
            BF_LLM_MODEL = Get-EnvValueFromProcess $pidValue "BF_LLM_MODEL"
            OLLAMA_BASE_URL = Get-EnvValueFromProcess $pidValue "OLLAMA_BASE_URL"
            BF_PUBLIC_MODEL_NAME = Get-EnvValueFromProcess $pidValue "BF_PUBLIC_MODEL_NAME"
            BF_PUBLIC_MODEL_ID = Get-EnvValueFromProcess $pidValue "BF_PUBLIC_MODEL_ID"
        } | ConvertTo-Json -Depth 4
    }
    try {
        Write-Host "--- status http://127.0.0.1:$port/api/ollama/status ---"
        (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/api/ollama/status" -TimeoutSec 30).Content
    } catch {
        Write-Host ("status_error=" + $_.Exception.Message)
    }
}

Write-Host "=== OLLAMA PS ==="
& "F:\Ollama\ollama.exe" ps

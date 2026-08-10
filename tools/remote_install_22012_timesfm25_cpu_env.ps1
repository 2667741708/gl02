$ErrorActionPreference = 'Stop'

$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$Python = 'C:\Program Files\Python311\python.exe'
$Venv = Join-Path $ProjectRoot '.venv_timesfm25_cpu'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'

$protectedBefore = @{}
foreach ($port in 8777, 8778) {
  $listener = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
  if ($listener.Count -ne 1) {
    throw "Protected port $port is not listening exactly once."
  }
  $protectedBefore[$port] = $listener[0].OwningProcess
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
  & $Python -m venv --system-site-packages $Venv
  if ($LASTEXITCODE -ne 0) {
    throw 'Failed to create CPU TimesFM environment.'
  }
}

& $VenvPython -m pip install --upgrade 'transformers==5.14.1' 'accelerate>=1.0,<2' 'huggingface_hub>=0.30' 'safetensors>=0.4'
if ($LASTEXITCODE -ne 0) {
  throw 'Failed to install TimesFM CPU runtime dependencies.'
}

& $VenvPython -c 'import torch, transformers; from transformers import TimesFm2_5ModelForPrediction; print(torch.__version__); print(transformers.__version__); print(torch.cuda.is_available())'
if ($LASTEXITCODE -ne 0) {
  throw 'TimesFM CPU runtime import check failed.'
}

foreach ($port in 8777, 8778) {
  $listener = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
  if ($listener.Count -ne 1 -or $listener[0].OwningProcess -ne $protectedBefore[$port]) {
    throw "Protected port $port changed during TimesFM CPU environment installation."
  }
}

[pscustomobject]@{
  environment = $Venv
  python = $VenvPython
  mode = 'cpu-zero-shot-first'
  protected_8777_pid = $protectedBefore[8777]
  protected_8778_pid = $protectedBefore[8778]
} | ConvertTo-Json -Depth 4

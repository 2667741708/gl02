$ErrorActionPreference = 'Stop'

$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$Python = 'C:\Program Files\Python311\python.exe'
$Venv = Join-Path $ProjectRoot '.venv_timesfm25'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python)) {
  throw "Python 3.11 is missing: $Python"
}

$protectedBefore = @{}
foreach ($port in 8777, 8778) {
  $listener = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
  if ($listener.Count -ne 1) {
    throw "Protected port $port is not listening exactly once."
  }
  $protectedBefore[$port] = $listener[0].OwningProcess
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
  & $Python -m venv $Venv
  if ($LASTEXITCODE -ne 0) {
    throw 'Failed to create TimesFM virtual environment.'
  }
}

& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
  throw 'Failed to update pip tooling.'
}

& $VenvPython -m pip install 'torch==2.5.1' --index-url 'https://download.pytorch.org/whl/cu121'
if ($LASTEXITCODE -ne 0) {
  throw 'Failed to install isolated CUDA PyTorch.'
}

& $VenvPython -m pip install 'transformers==5.14.1' 'accelerate>=1.0,<2' 'huggingface_hub>=0.30' 'safetensors>=0.4' 'numpy>=1.26,<3'
if ($LASTEXITCODE -ne 0) {
  throw 'Failed to install TimesFM runtime dependencies.'
}

& $VenvPython -c 'import torch; from transformers import TimesFm2_5ModelForPrediction; print(torch.__version__); print(torch.cuda.is_available())'
if ($LASTEXITCODE -ne 0) {
  throw 'TimesFM runtime import check failed.'
}

foreach ($port in 8777, 8778) {
  $listener = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
  if ($listener.Count -ne 1 -or $listener[0].OwningProcess -ne $protectedBefore[$port]) {
    throw "Protected port $port changed during TimesFM environment installation."
  }
}

[pscustomobject]@{
  environment = $Venv
  python = $VenvPython
  transformers = '5.14.1'
  torch = '2.5.1+cu121'
  protected_8777_pid = $protectedBefore[8777]
  protected_8778_pid = $protectedBefore[8778]
} | ConvertTo-Json -Depth 4


$ErrorActionPreference = 'Stop'

$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$Python = 'C:\Program Files\Python311\python.exe'
$Venv = Join-Path $ProjectRoot '.venv_ttm_cpu'
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
    throw 'Failed to create TTM environment.'
  }
}

& $VenvPython -m pip install --upgrade 'granite-tsfm'
if ($LASTEXITCODE -ne 0) {
  throw 'Failed to install granite-tsfm.'
}

& $VenvPython -c 'import torch; from tsfm_public.models.tinytimemixer import TinyTimeMixerForPrediction; print(torch.__version__)'
if ($LASTEXITCODE -ne 0) {
  throw 'TTM runtime import check failed.'
}

foreach ($port in 8777, 8778) {
  $listener = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
  if ($listener.Count -ne 1 -or $listener[0].OwningProcess -ne $protectedBefore[$port]) {
    throw "Protected port $port changed during TTM environment installation."
  }
}

[pscustomobject]@{
  environment = $Venv
  python = $VenvPython
  model_family = 'ibm-granite-ttm-r2'
  protected_8777_pid = $protectedBefore[8777]
  protected_8778_pid = $protectedBefore[8778]
} | ConvertTo-Json -Depth 4

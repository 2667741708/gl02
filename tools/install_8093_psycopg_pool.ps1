$ErrorActionPreference = "Stop"

$python = "C:\Program Files\Python311\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
  throw "Python not found: $python"
}

& $python -m pip install "psycopg-pool==3.3.1"
if ($LASTEXITCODE -ne 0) {
  throw "psycopg-pool installation failed with exit code $LASTEXITCODE"
}

& $python -m pip show psycopg-pool
if ($LASTEXITCODE -ne 0) {
  throw "psycopg-pool verification failed with exit code $LASTEXITCODE"
}

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$python = 'C:\Program Files\Python311\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python runtime not found: $python"
}

$listener = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction Stop | Select-Object -First 1
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
$version = (& $python --version 2>&1 | Out-String).Trim()
$abi = (& $python -c "import json,platform,struct,sys; print(json.dumps({'version':platform.python_version(),'bits':struct.calcsize('P')*8,'machine':platform.machine(),'cache_tag':sys.implementation.cache_tag}))" | ConvertFrom-Json)
$packages = [ordered]@{}
foreach ($name in @('brotli', 'jsonschema', 'mcp', 'numpy', 'pandas', 'psycopg', 'PyYAML', 'scikit-learn')) {
    $line = & $python -m pip show $name 2>$null | Where-Object { $_ -like 'Version:*' } | Select-Object -First 1
    $packages[$name] = if ($line) { ($line -split ':', 2)[1].Trim() } else { $null }
}

[ordered]@{
    schema = 'ops.8093.native-runtime-probe.v1'
    python = $python
    python_version = $version
    abi = $abi
    packages = $packages
    listener_pid = $listener.OwningProcess
    listener_name = $process.Name
    listener_command = $process.CommandLine
} | ConvertTo-Json -Depth 6

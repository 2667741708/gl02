<#
.SYNOPSIS
  Launch the IMES Vastbase read-only MCP server (imes-22012-readonly-mcp).
  Loads credentials from the git-ignored imes_vastbase.local.env,
  sets relay-mode connection through 127.0.0.1, and runs the MCP server
  on stdio.

.DESCRIPTION
  Prerequisite: the 220.12 SSH relay MUST already be running.
    python .\tools\imes_22012_relay.py --allow-agents-password --profile imes
  or double-click:
    .\tools\start_imes_vastbase_relay_local.cmd

  This script is designed to be invoked by Claude Code / Claude Desktop
  as an MCP server process.  It writes nothing to stdout except the
  MCP JSON-RPC protocol stream; all diagnostics go to stderr.

  Credentials are never written to this script -- they stay in the
  existing PT/imes_vastbase.local.env file.
#>

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ------------------------------------------------------------------
# 1. Load Vastbase credentials from the git-ignored env file
# ------------------------------------------------------------------
$envFile = Join-Path $scriptDir 'imes_vastbase.local.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    [Console]::Error.WriteLine("IMES MCP launcher: credential file not found: $envFile")
    exit 1
}

foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
    $parts = $trimmed.Split('=', 2)
    if ($parts.Count -ne 2) { continue }
    $key = $parts[0].Trim()
    $value = $parts[1]
    [Environment]::SetEnvironmentVariable($key, $value, 'Process')
}

# ------------------------------------------------------------------
# 2. Set relay-mode connection (through 220.12 SSH tunnel)
#    127.0.0.1:15433 -> 10.30.220.12 -> 10.10.181.195:5432
# ------------------------------------------------------------------
$env:IMES_MCP_CONNECTION_MODE = 'relay'
$env:IMES_RELAY_DB_HOST       = '127.0.0.1'
$env:IMES_RELAY_DB_PORT       = '15433'

# Both profiles (operations + laboratory) use the same relay + credentials
foreach ($prefix in @('IMES_OPS_DB_', 'IMES_LAB_DB_')) {
    [Environment]::SetEnvironmentVariable($prefix + 'HOST', '127.0.0.1', 'Process')
    [Environment]::SetEnvironmentVariable($prefix + 'PORT', '15433', 'Process')
    [Environment]::SetEnvironmentVariable($prefix + 'NAME', $env:IMES_DB_NAME, 'Process')
    [Environment]::SetEnvironmentVariable($prefix + 'USER', $env:IMES_DB_USER, 'Process')
    [Environment]::SetEnvironmentVariable($prefix + 'PASSWORD', $env:IMES_DB_PASSWORD, 'Process')
}

# Override the base env vars so any fallback path also hits the relay
$env:IMES_DB_HOST = '127.0.0.1'
$env:IMES_DB_PORT = '15433'

# ------------------------------------------------------------------
# 3. Locate the MCP server script
# ------------------------------------------------------------------
$mcpServer = Join-Path $scriptDir '..\高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py'
$mcpServer = [System.IO.Path]::GetFullPath($mcpServer)
if (-not (Test-Path -LiteralPath $mcpServer)) {
    [Console]::Error.WriteLine("IMES MCP launcher: server script not found: $mcpServer")
    exit 1
}

# ------------------------------------------------------------------
# 4. Find Python and launch the MCP server
# ------------------------------------------------------------------
$pythonExe = $null
foreach ($candidate in @(
    'C:\Program Files\Python311\python.exe',
    'C:\Program Files\Python312\python.exe',
    'C:\Program Files\Python313\python.exe'
)) {
    if (Test-Path -LiteralPath $candidate) {
        $pythonExe = $candidate
        break
    }
}
if (-not $pythonExe) {
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) { $pythonExe = $found.Source }
}
if (-not $pythonExe) {
    $found = Get-Command python3 -ErrorAction SilentlyContinue
    if ($found) { $pythonExe = $found.Source }
}
if (-not $pythonExe) {
    [Console]::Error.WriteLine("IMES MCP launcher: Python not found in PATH or standard locations")
    exit 1
}

# Stdout = MCP JSON-RPC protocol, stderr = diagnostics
& $pythonExe -X utf8 $mcpServer

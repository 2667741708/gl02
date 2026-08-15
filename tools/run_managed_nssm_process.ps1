[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This managed service runner requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

function Read-Config([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Config not found: $Path"
    }
    $json = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
    return $json | ConvertFrom-Json
}

function Write-ManagedLog([string]$Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $script:RunnerLog -Encoding utf8 -Value $line
}

$Config = Read-Config $ConfigPath
if ([string]::IsNullOrWhiteSpace([string]$Config.serviceName)) {
    throw 'Config serviceName is required.'
}
$Executable = [string]$Config.executable
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "Executable not found: $Executable"
}
$WorkDir = if ($Config.workDir) {
    [string]$Config.workDir
} elseif ($Config.root) {
    [string]$Config.root
} else {
    Split-Path -Parent $Executable
}
if (-not (Test-Path -LiteralPath $WorkDir -PathType Container)) {
    throw "WorkDir not found: $WorkDir"
}

$Arguments = @()
if ($Config.arguments) {
    foreach ($arg in @($Config.arguments)) {
        $Arguments += [string]$arg
    }
}

if ($ValidateOnly) {
    [ordered]@{
        schema = 'ops.managed-nssm-runner.validate-only.v1'
        ok = $true
        service = [string]$Config.serviceName
        ps_edition = $PSVersionTable.PSEdition
        ps_version = $PSVersionTable.PSVersion.ToString()
        executable = $Executable
        work_dir = $WorkDir
        argument_count = $Arguments.Count
    } | ConvertTo-Json -Depth 4
    exit 0
}

$LogDir = if ($Config.logDir) { [string]$Config.logDir } else { Join-Path ([string]$Config.root) 'logs' }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPrefix = if ($Config.logPrefix) { [string]$Config.logPrefix } else { [string]$Config.serviceName }
$script:RunnerLog = Join-Path $LogDir "$LogPrefix.service.runner.log"

if ($Config.envMachine) {
    foreach ($name in @($Config.envMachine)) {
        $value = [Environment]::GetEnvironmentVariable([string]$name, 'Machine')
        if ($value) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}
if ($Config.env) {
    foreach ($property in $Config.env.PSObject.Properties) {
        Set-Item -Path "Env:$($property.Name)" -Value ([string]$property.Value)
    }
}
if ($Config.setPgPasswordFromGl02 -and $env:GL02_PGPASSWORD) {
    $env:PGPASSWORD = $env:GL02_PGPASSWORD
}

Set-Location -LiteralPath $WorkDir
Write-ManagedLog "starting service=$($Config.serviceName) executable=$Executable args=$($Arguments -join ' ') workdir=$WorkDir"
& $Executable @Arguments
$exitCode = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }
Write-ManagedLog "process_exited service=$($Config.serviceName) code=$exitCode"
exit $exitCode

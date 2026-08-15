[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Spec,

    [switch]$PlanOnly,
    [switch]$Build,
    [switch]$InstallBuildDeps,
    [switch]$BootstrapPython311,
    [string]$PlanOutput,
    [string]$Manifest,
    [string]$PythonExecutable = ''
)

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'build_python_native_artifact.ps1 requires PowerShell 7 Core or newer.'
}

$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

if ($PlanOnly -and $Build) {
    throw 'Choose either -PlanOnly or -Build, not both.'
}
if ($InstallBuildDeps -and -not $Build) {
    throw '-InstallBuildDeps requires -Build.'
}

$PythonScript = Join-Path -Path $PSScriptRoot -ChildPath 'build_python_native_artifact.py'
if (-not (Test-Path -LiteralPath $PythonScript -PathType Leaf)) {
    throw "Python build entrypoint not found: $PythonScript"
}

if (-not $PythonExecutable) {
    $BuildEnvRoot = Join-Path $env:LOCALAPPDATA 'Codex\python-native-build\py311'
    $PythonExecutable = Join-Path $BuildEnvRoot 'python.exe'
}
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    if (-not $BootstrapPython311) {
        throw "Python 3.11 x64 build environment not found: $PythonExecutable. Re-run with -BootstrapPython311 to create the controlled conda environment."
    }
    $Conda = (Get-Command -Name conda -ErrorAction Stop).Source
    $BuildEnvRoot = Split-Path -Parent $PythonExecutable
    & $Conda create --prefix $BuildEnvRoot python=3.11 pip -y
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
        throw 'Could not create the controlled Python 3.11 x64 native-build environment.'
    }
}

$PythonArguments = @($PythonScript, '--spec', $Spec)
if ($Build) {
    $PythonArguments += '--build'
} else {
    $PythonArguments += '--plan-only'
}
if ($InstallBuildDeps) {
    $PythonArguments += '--install-build-deps'
}
if ($PlanOutput) {
    $PythonArguments += @('--plan-output', $PlanOutput)
}
if ($Manifest) {
    $PythonArguments += @('--manifest', $Manifest)
}

& $PythonExecutable @PythonArguments
if ($LASTEXITCODE -ne 0) {
    throw "Native artifact builder exited with code $LASTEXITCODE."
}

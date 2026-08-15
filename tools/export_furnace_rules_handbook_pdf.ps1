[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MarkdownPath,
    [Parameter(Mandatory = $true)]
    [string]$PdfPath,
    [string]$CssPath = ""
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$utf8 = [Text.UTF8Encoding]::new($false)
$OutputEncoding = $utf8
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8NoBOM'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8NoBOM'

$source = (Resolve-Path -LiteralPath $MarkdownPath).Path
if (-not $CssPath) {
    $CssPath = Join-Path $PSScriptRoot 'furnace_rules_handbook.css'
}
$css = (Resolve-Path -LiteralPath $CssPath).Path
$targetParent = Split-Path -Parent $PdfPath
if (-not (Test-Path -LiteralPath $targetParent)) {
    New-Item -ItemType Directory -Path $targetParent | Out-Null
}
$target = [IO.Path]::GetFullPath($PdfPath)

$pandocCommand = Get-Command pandoc.exe -ErrorAction SilentlyContinue
if (-not $pandocCommand) {
    $knownPandoc = 'D:\ProgramData\anaconda3\Library\bin\pandoc.exe'
    if (-not (Test-Path -LiteralPath $knownPandoc)) { throw 'pandoc.exe not found.' }
    $pandoc = $knownPandoc
} else {
    $pandoc = $pandocCommand.Source
}

$edgeCandidates = @(
    'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
)
$edge = $edgeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $edge) { throw 'Microsoft Edge not found.' }

$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$workDir = Join-Path $tempRoot ("bf-rules-pdf-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $workDir | Out-Null
$html = Join-Path $workDir 'handbook.html'
$profile = Join-Path $workDir 'edge-profile'
New-Item -ItemType Directory -Path $profile | Out-Null

try {
    $pandocArgs = @(
        '--from=gfm',
        '--to=html5',
        '--standalone',
        '--embed-resources',
        "--css=$css",
        '--metadata=lang:zh-CN',
        '--metadata=pagetitle:炉况诊断8类与ABC33规则数学公式手册',
        "--output=$html",
        $source
    )
    $pandocProcess = Start-Process -FilePath $pandoc -ArgumentList $pandocArgs -Wait -PassThru -NoNewWindow
    if ($pandocProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $html)) {
        throw "Pandoc HTML export failed with exit code $($pandocProcess.ExitCode)."
    }

    $htmlUri = [Uri]::new($html).AbsoluteUri
    $edgeArgs = @(
        '--headless=new',
        '--disable-gpu',
        '--no-pdf-header-footer',
        '--print-to-pdf-no-header',
        "--user-data-dir=$profile",
        "--print-to-pdf=$target",
        $htmlUri
    )
    $edgeProcess = Start-Process -FilePath $edge -ArgumentList $edgeArgs -Wait -PassThru -WindowStyle Hidden
    if ($edgeProcess.ExitCode -ne 0) {
        throw "Edge PDF export failed with exit code $($edgeProcess.ExitCode)."
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while (-not (Test-Path -LiteralPath $target) -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 200
    }
    if (-not (Test-Path -LiteralPath $target)) { throw 'PDF was not created.' }
    $pdf = Get-Item -LiteralPath $target
    if ($pdf.Length -lt 10000) { throw "PDF is unexpectedly small: $($pdf.Length) bytes." }
    [ordered]@{
        ok = $true
        markdown = $source
        pdf = $target
        bytes = $pdf.Length
        runtime = $PSVersionTable.PSVersion.ToString()
    } | ConvertTo-Json -Compress
} finally {
    $resolvedWork = [IO.Path]::GetFullPath($workDir)
    if ($resolvedWork.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedWork)) {
        Remove-Item -LiteralPath $resolvedWork -Recurse -Force
    }
}

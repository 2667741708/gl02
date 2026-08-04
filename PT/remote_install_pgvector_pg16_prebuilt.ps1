$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$pgRoot = "F:\PostgreSQL\16"
$work = "F:\pgvector_install"
New-Item -ItemType Directory -Force -Path $work | Out-Null

$api = "https://api.github.com/repos/andreiramani/pgvector_pgsql_windows/releases/tags/0.8.3_16.14"
$releaseJson = Invoke-WebRequest -UseBasicParsing -Uri $api -Headers @{ "User-Agent" = "Codex-22012-maintenance" } -TimeoutSec 60
$release = $releaseJson.Content | ConvertFrom-Json
$asset = @($release.assets | Where-Object { $_.name -match "\.zip$" } | Select-Object -First 1)
if (-not $asset) {
    throw "No zip asset found in release 0.8.3_16.14"
}

$zip = Join-Path $work $asset.name
Write-Host "download=$($asset.browser_download_url)"
Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -Headers @{ "User-Agent" = "Codex-22012-maintenance" } -OutFile $zip -TimeoutSec 300

$extract = Join-Path $work "extract"
if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
New-Item -ItemType Directory -Force -Path $extract | Out-Null
Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force

Write-Host "extracted_files"
Get-ChildItem -LiteralPath $extract -Recurse -File | Select-Object FullName,Length | ConvertTo-Json -Depth 4

$control = Get-ChildItem -LiteralPath $extract -Recurse -File -Filter "vector.control" | Select-Object -First 1
$sqlFiles = @(Get-ChildItem -LiteralPath $extract -Recurse -File -Filter "vector--*.sql")
$dll = Get-ChildItem -LiteralPath $extract -Recurse -File -Filter "vector.dll" | Select-Object -First 1
if (-not $control -or -not $dll -or $sqlFiles.Count -eq 0) {
    throw "Extracted archive does not contain vector.control/vector.dll/vector--*.sql"
}

$backup = Join-Path $work ("backup_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $backup | Out-Null
foreach ($relative in @("share\extension\vector.control", "lib\vector.dll")) {
    $target = Join-Path $pgRoot $relative
    if (Test-Path -LiteralPath $target) {
        $dest = Join-Path $backup ($relative -replace "[\\/:]", "_")
        Copy-Item -LiteralPath $target -Destination $dest -Force
    }
}

Copy-Item -LiteralPath $control.FullName -Destination (Join-Path $pgRoot "share\extension\vector.control") -Force
foreach ($sql in $sqlFiles) {
    Copy-Item -LiteralPath $sql.FullName -Destination (Join-Path $pgRoot ("share\extension\" + $sql.Name)) -Force
}
Copy-Item -LiteralPath $dll.FullName -Destination (Join-Path $pgRoot "lib\vector.dll") -Force

Write-Host "installed_files"
Get-Item -LiteralPath (Join-Path $pgRoot "share\extension\vector.control"),(Join-Path $pgRoot "lib\vector.dll") | Select-Object FullName,Length,LastWriteTime | ConvertTo-Json -Depth 4

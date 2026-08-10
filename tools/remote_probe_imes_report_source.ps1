$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Uri = "http://10.10.181.205:8080/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht"
$OutFile = "C:\Users\Administrator\AppData\Local\Temp\imes_report_source_probe.html"

$response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 20
$content = [string]$response.Content
$parent = Split-Path -Parent $OutFile
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}
Set-Content -LiteralPath $OutFile -Value $content -Encoding UTF8

$title = [regex]::Match($content, "<title>(.*?)</title>", "IgnoreCase").Groups[1].Value
$forms = [regex]::Matches($content, "<form\b", "IgnoreCase").Count
$scripts = [regex]::Matches($content, "<script\b", "IgnoreCase").Count
$inputs = [regex]::Matches($content, "<input\b", "IgnoreCase").Count
$links = [regex]::Matches($content, "(?:src|href)=['""]([^'""]+)['""]", "IgnoreCase") |
    Select-Object -First 30 |
    ForEach-Object { $_.Groups[1].Value }

[pscustomobject]@{
    ok = $true
    uri = $Uri
    status = [int]$response.StatusCode
    length = $content.Length
    title = $title
    forms = $forms
    scripts = $scripts
    inputs = $inputs
    has_fuel_ratio = $content.Contains("燃料比")
    has_material_speed = $content.Contains("料速")
    has_issued = $content.Contains("下达")
    has_coal = $content.Contains("煤")
    has_silicon = $content.Contains("硅")
    out_file = $OutFile
    links = @($links)
} | ConvertTo-Json -Depth 4 -Compress

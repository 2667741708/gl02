param(
  [string]$SourceImage = 'C:\Users\hmw20\AppData\Local\Temp\codex-clipboard-d51461d1-911a-4a75-9650-4523b3627c74.png',
  [string]$ImplementationImage = '',
  [string]$OutputImage = ''
)

Add-Type -AssemblyName System.Drawing
$repo = Split-Path -Parent $PSScriptRoot
if (-not $ImplementationImage) { $ImplementationImage = Join-Path $repo 'logs\front2_optimization_cockpit_qa\optimization_chromium_1366x768.png' }
if (-not $OutputImage) { $OutputImage = Join-Path $repo 'logs\front2_design\optimization_cockpit_comparison.png' }
$source = [System.Drawing.Image]::FromFile($SourceImage)
$implementation = $null
try {
  $implementation = [System.Drawing.Image]::FromFile($ImplementationImage)
  $panelWidth = 1366
  $headerHeight = 36
  $panelHeight = 768
  $canvas = [System.Drawing.Bitmap]::new($panelWidth * 2, $panelHeight + $headerHeight)
  $graphics = [System.Drawing.Graphics]::FromImage($canvas)
  try {
    $graphics.Clear([System.Drawing.Color]::FromArgb(14, 22, 31))
    $font = [System.Drawing.Font]::new('SimSun', 16, [System.Drawing.FontStyle]::Bold)
    $brush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(230, 242, 252))
    try {
      $graphics.DrawString('REFERENCE', $font, $brush, 12, 8)
      $graphics.DrawString('FRONT2 IMPLEMENTATION', $font, $brush, $panelWidth + 12, 8)
      $graphics.DrawImage($source, [System.Drawing.Rectangle]::new(0, $headerHeight, $panelWidth, $panelHeight))
      $graphics.DrawImage($implementation, [System.Drawing.Rectangle]::new($panelWidth, $headerHeight, $panelWidth, $panelHeight))
      $canvas.Save($OutputImage, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
      $brush.Dispose(); $font.Dispose()
    }
  } finally {
    $graphics.Dispose(); $canvas.Dispose()
  }
} finally {
  $source.Dispose(); if ($implementation) { $implementation.Dispose() }
}

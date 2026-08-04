param(
    [Parameter(Mandatory = $true)][string]$BasePath,
    [Parameter(Mandatory = $true)][string]$OutDir
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Drawing

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$generatedRoot = 'C:\Users\hmw20\.codex\generated_images\019f571c-c906-70d1-bc13-b8c9ac9b0a77'
$sources = [ordered]@{
    lowline = 'exec-f8ef2cb7-6b82-4f34-ab87-359b087d5899.png'
    edge    = 'exec-0a243011-6332-4f34-b054-f763448bba95.png'
    center  = 'exec-45975ada-5bed-4c0b-aa42-3b1e5e9e3b90.png'
    channel = 'exec-7e60d51d-9c05-470b-8643-f0d6accc1db6.png'
    cold    = 'exec-71b0e4f1-85e3-4cf4-bb9a-1ad2a6c35091.png'
    hot     = 'exec-357659ee-fc83-4012-8258-d3fe3910ffff.png'
    column  = 'exec-1ae0a61d-a6e3-4efb-9451-b569ba404fbd.png'
}

$base = [System.Drawing.Bitmap]::new($BasePath)
try {
    $normalPath = Join-Path $outDir 'normal.png'
    $base.Save($normalPath, [System.Drawing.Imaging.ImageFormat]::Png)

    # Conservative polygon wholly inside the refractory lining. All pixels outside
    # this polygon are copied verbatim from the original image.
    $points = [System.Drawing.Point[]]@(
        [System.Drawing.Point]::new(474, 355), [System.Drawing.Point]::new(612, 355),
        [System.Drawing.Point]::new(633, 485), [System.Drawing.Point]::new(650, 680),
        [System.Drawing.Point]::new(670, 900), [System.Drawing.Point]::new(642, 1040),
        [System.Drawing.Point]::new(603, 1190), [System.Drawing.Point]::new(574, 1250),
        [System.Drawing.Point]::new(512, 1250), [System.Drawing.Point]::new(482, 1190),
        [System.Drawing.Point]::new(444, 1040), [System.Drawing.Point]::new(416, 900),
        [System.Drawing.Point]::new(436, 680), [System.Drawing.Point]::new(453, 485)
    )
    $maskPath = Join-Path $outDir '_interior-mask.png'
    $clipPath = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $clipPath.AddPolygon($points)
    $mask = [System.Drawing.Bitmap]::new($base.Width, $base.Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $mg = [System.Drawing.Graphics]::FromImage($mask)
    try {
        $mg.Clear([System.Drawing.Color]::Black)
        $mg.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::None
        $mg.FillPath([System.Drawing.Brushes]::White, $clipPath)
    } finally { $mg.Dispose() }
    $mask.Save($maskPath, [System.Drawing.Imaging.ImageFormat]::Png)

    foreach ($entry in $sources.GetEnumerator()) {
        $sourcePath = Join-Path $generatedRoot $entry.Value
        if (-not (Test-Path -LiteralPath $sourcePath)) { throw "Missing generated source: $sourcePath" }
        $source = [System.Drawing.Bitmap]::new($sourcePath)
        try {
            $sourceForDraw = $source
            $resized = $null
            if ($source.Width -ne $base.Width -or $source.Height -ne $base.Height) {
                $resized = [System.Drawing.Bitmap]::new($base.Width, $base.Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
                $rg = [System.Drawing.Graphics]::FromImage($resized)
                try {
                    $rg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                    $rg.DrawImage($source, 0, 0, $base.Width, $base.Height)
                } finally { $rg.Dispose() }
                $sourceForDraw = $resized
            }
            $final = [System.Drawing.Bitmap]::new($base.Width, $base.Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
            $g = [System.Drawing.Graphics]::FromImage($final)
            try {
                $g.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
                $g.DrawImageUnscaled($base, 0, 0)
                $g.SetClip($clipPath)
                $g.DrawImageUnscaled($sourceForDraw, 0, 0)
                $g.ResetClip()
            } finally { $g.Dispose() }
            $outputPath = Join-Path $outDir ($entry.Key + '.png')
            $final.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)

            $outsideDiff = 0
            for ($y = 0; $y -lt $base.Height; $y++) {
                for ($x = 0; $x -lt $base.Width; $x++) {
                    if ($mask.GetPixel($x, $y).R -eq 0 -and $final.GetPixel($x, $y).ToArgb() -ne $base.GetPixel($x, $y).ToArgb()) {
                        $outsideDiff++
                    }
                }
            }
            $final.Dispose()
            if ($null -ne $resized) { $resized.Dispose() }
            Write-Output "$($entry.Key): outside_diff_pixels=$outsideDiff"
        } finally { $source.Dispose() }
    }
    $mask.Dispose()
    $clipPath.Dispose()
} finally { $base.Dispose() }

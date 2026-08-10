param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ATrustWindowCaptureNative {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
}
'@

$process = Get-Process -Name 'aTrustTray' |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
if (-not $process) {
    throw 'aTrust main window was not found.'
}

$handle = [IntPtr]$process.MainWindowHandle
[void][ATrustWindowCaptureNative]::SetForegroundWindow($handle)
Start-Sleep -Milliseconds 300
$rect = New-Object ATrustWindowCaptureNative+RECT
if (-not [ATrustWindowCaptureNative]::GetWindowRect($handle, [ref]$rect)) {
    throw 'GetWindowRect failed.'
}
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
if ($width -le 0 -or $height -le 0) {
    throw 'aTrust window rectangle is empty.'
}
$bitmap = New-Object Drawing.Bitmap $width, $height
$graphics = [Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
    $fullPath = [IO.Path]::GetFullPath($OutputPath)
    $directory = [IO.Path]::GetDirectoryName($fullPath)
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $bitmap.Save($fullPath, [Drawing.Imaging.ImageFormat]::Png)
    Write-Output $fullPath
}
finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}

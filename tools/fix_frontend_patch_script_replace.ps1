$path = Join-Path (Get-Location).Path "tools\apply_foreman_guidance_card_simple.ps1"
$text = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
$text = $text.Replace('$newBlock = $newBlock.Replace("@@BT@@", [char]96)', '$newBlock = $newBlock.Replace("@@BT@@", ([char]96).ToString())')
$text = $text.Replace('$styleBlock = $styleBlock.Replace("@@BT@@", [char]96)', '$styleBlock = $styleBlock.Replace("@@BT@@", ([char]96).ToString())')
[IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))

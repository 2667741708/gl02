$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$frontend = Join-Path $root '高炉前端数据'
$page = Join-Path $frontend 'si_v20_workbench.html'
$asset = Join-Path $frontend 'assets\bf-si-v20-workbench.js'
$tempRoot = 'C:\Users\Administrator\AppData\Local\Temp'
$tempPage = Join-Path $tempRoot 'si_v20_workbench.html'
$tempAsset = Join-Path $tempRoot 'bf-si-v20-workbench.js'
foreach($file in @($tempPage,$tempAsset,$page,$asset)){if(-not(Test-Path -LiteralPath $file -PathType Leaf)){throw "missing file: $file"}}
$backup = Join-Path $root ("backups\si_v20_workbench_static_20260808\" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $page -Destination (Join-Path $backup 'si_v20_workbench.html') -Force
Copy-Item -LiteralPath $asset -Destination (Join-Path $backup 'bf-si-v20-workbench.js') -Force
$pageTmp = "$page.si_v20_installing"
$assetTmp = "$asset.si_v20_installing"
Copy-Item -LiteralPath $tempPage -Destination $pageTmp -Force
Move-Item -LiteralPath $pageTmp -Destination $page -Force
Copy-Item -LiteralPath $tempAsset -Destination $assetTmp -Force
Move-Item -LiteralPath $assetTmp -Destination $asset -Force
$response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/si_v20_workbench.html?cb=20260808' -TimeoutSec 30
if($response.StatusCode -ne 200 -or -not $response.Content.Contains('每60秒自动刷新')){throw '8093 static workbench verification failed'}
[ordered]@{schema='ops.si-v20-workbench-static-hot-deploy.v1';backup=$backup;page_http=$response.StatusCode;auto_refresh_marker=$true;guard_untouched=$true} | ConvertTo-Json -Depth 4

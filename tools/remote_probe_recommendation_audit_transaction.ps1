$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("Rjpc6auY54KJ54K86ZOB6aG555uuLXJlYWwtc2Vuc29yLXYyX1Y0XzgwOTNfUFJFVklFVw=="))
$serviceName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6Ieq5Yqo6K+K5pat5pyN5Yqh"))
$bridge = Join-Path (Join-Path $root $serviceName) "local_pg_ws_bridge.py"
$auditStore = Join-Path (Join-Path $root $serviceName) "recommendation_audit_store.py"
[ordered]@{
    services = [ordered]@{
        proxy8093 = [string](Get-Service -Name "BFV4PreviewProxy8093" -ErrorAction SilentlyContinue).Status
        ws8768 = [string](Get-Service -Name "BFV4PreviewWs8768" -ErrorAction SilentlyContinue).Status
    }
    files = [ordered]@{
        bridgeSha256 = (Get-FileHash -LiteralPath $bridge -Algorithm SHA256).Hash
        bridgeHasAuditImport = (Get-Content -LiteralPath $bridge -Raw -Encoding UTF8).Contains("recommendation_audit_store")
        auditStoreExists = Test-Path -LiteralPath $auditStore -PathType Leaf
        auditStoreSha256 = if (Test-Path -LiteralPath $auditStore -PathType Leaf) { (Get-FileHash -LiteralPath $auditStore -Algorithm SHA256).Hash } else { $null }
    }
    transaction = [ordered]@{
        archiveExists = Test-Path -LiteralPath "C:\Users\Administrator\AppData\Local\Temp\recommendation_audit_deploy.zip"
        payloadExists = Test-Path -LiteralPath "C:\Users\Administrator\AppData\Local\Temp\recommendation_audit_deploy_payload"
    }
} | ConvertTo-Json -Depth 8

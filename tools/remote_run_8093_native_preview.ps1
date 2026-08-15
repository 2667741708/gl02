$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$stage = 'F:\high-furnace-deploy-staging\assistant-native-preview'
$testScript = Join-Path $stage 'remote_test_8093_native_preview.ps1'
$executable = Join-Path $stage 'bf_8093_assistant_native.exe'
$acceptance = Join-Path $stage 'remote_accept_abc33_contextual_assistant.ps1'
& $testScript -Executable $executable -Port 18095 -AcceptanceScript $acceptance
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

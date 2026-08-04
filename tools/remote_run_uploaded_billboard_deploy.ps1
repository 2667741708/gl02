$ErrorActionPreference = "Stop"
$deployPath = "C:\Users\Administrator\AppData\Local\Temp\bf3d_billboard_pspace_live\remote_deploy_8094_billboard_pspace_live.ps1"
$deployText = [IO.File]::ReadAllText($deployPath, [Text.Encoding]::UTF8)
& ([ScriptBlock]::Create($deployText))

$svc = Get-CimInstance Win32_Service -Filter "Name='BFV4PreviewProxy8093'"
$svc | Select-Object Name, State, StartMode, StartName, PathName | Format-List

Write-Host "--- sc qc ---"
sc.exe qc BFV4PreviewProxy8093

Write-Host "--- nssm lookup ---"
$nssm = Get-Command nssm.exe -ErrorAction SilentlyContinue
if (-not $nssm -and $svc.PathName -and (Test-Path -LiteralPath $svc.PathName)) {
  $nssm = Get-Item -LiteralPath $svc.PathName
}
$nssm | Format-List Source
if ($nssm) {
  $nssmPath = if ($nssm.Source) { $nssm.Source } else { $nssm.FullName }
  Write-Host "--- AppEnvironmentExtra ---"
  & $nssmPath get BFV4PreviewProxy8093 AppEnvironmentExtra
  Write-Host "--- AppParameters ---"
  & $nssmPath get BFV4PreviewProxy8093 AppParameters
  Write-Host "--- AppDirectory ---"
  & $nssmPath get BFV4PreviewProxy8093 AppDirectory
  Write-Host "--- AppPath ---"
  & $nssmPath get BFV4PreviewProxy8093 AppPath
}

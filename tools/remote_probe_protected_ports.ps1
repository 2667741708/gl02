$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
foreach($port in 8093,8094,8768,8770,11434){
  $item=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if($item){Write-Output ("$port="+$item.OwningProcess)}else{Write-Output ("$port=NONE")}
}

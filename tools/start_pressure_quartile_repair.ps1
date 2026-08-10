$ErrorActionPreference = 'Stop'
$python = 'C:\Program Files\Python311\python.exe'
$script = 'C:\Users\Administrator\AppData\Local\Temp\repair_pressure_quartiles_22012.py'
$out = 'C:\Users\Administrator\AppData\Local\Temp\pressure_quartile_repair_20260808.out.json'
$err = 'C:\Users\Administrator\AppData\Local\Temp\pressure_quartile_repair_20260808.err.log'
Remove-Item -LiteralPath $out,$err -Force -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath $python -ArgumentList @('-X','utf8',$script,'--apply') -WorkingDirectory 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW' -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
[pscustomobject]@{ pid = $proc.Id; output = $out; error = $err } | ConvertTo-Json -Compress

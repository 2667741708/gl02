$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
function Read-Env([string]$name){
  $value=[Environment]::GetEnvironmentVariable($name,'Machine')
  if(-not$value){$value=[Environment]::GetEnvironmentVariable($name,'User')}
  return $value
}
$env:GL02_PGHOST=Read-Env 'GL02_PGHOST'
$env:GL02_PGPORT=Read-Env 'GL02_PGPORT'
$env:GL02_PGDATABASE=Read-Env 'GL02_PGDATABASE'
$env:GL02_PGUSER=Read-Env 'GL02_PGUSER'
$env:GL02_PGPASSWORD=Read-Env 'GL02_PGPASSWORD'
$script='C:\Users\Administrator\AppData\Local\Temp\export_22012_abc33_snapshot.py'
$output='C:\Users\Administrator\AppData\Local\Temp\abc33_input_snapshot'
if(Test-Path -LiteralPath $output){Remove-Item -LiteralPath $output -Recurse -Force}
& 'C:\Program Files\Python311\python.exe' -X utf8 $script --output-dir $output
if($LASTEXITCODE-ne0){throw 'ABC33 snapshot export failed'}

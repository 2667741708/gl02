$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$roots = @(
    "F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW",
    "F:\\高炉炼铁项目-real-sensor-v2_V3",
    "C:\\Users\\Administrator\\AppData\\Roaming\\Python"
)
$candidateFiles = foreach ($root in $roots) {
    if (Test-Path -LiteralPath $root) {
        Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -in @('.env','*.env') -or
                $_.Name -match '(?i)(postgres|database|pg|runtime|config).*\.(json|yaml|yml|ini|env|ps1|cmd|bat)$'
            } |
            Select-Object -First 120 -ExpandProperty FullName
    }
}
$envNames = Get-ChildItem Env: | Where-Object { $_.Name -match '(?i)(PG|POSTGRES|DATABASE|DB_|BF_)' } | Select-Object -ExpandProperty Name
$tasks = Get-ScheduledTask -TaskPath "\\BlastFurnaceServices\\" -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -match '(?i)(8094|V4|Postgres|Database|Sensor)' } |
    Select-Object TaskName,State,TaskPath
$envLengths = @{}
foreach ($name in @('GL02_PGHOST','GL02_PGPORT','GL02_PGDATABASE','GL02_PGUSER','GL02_PGPASSWORD','GL02_PGADMIN_PASSWORD')) {
    $item = Get-Item "Env:$name" -ErrorAction SilentlyContinue
    $envLengths[$name] = if ($null -eq $item) { $null } else { [string]$item.Value | ForEach-Object Length }
}
$services = Get-Service -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '(?i)(postgres|nssm|bfo|blast|sensor|database)' } |
    Select-Object Name,Status,DisplayName
[ordered]@{
    candidate_files = @($candidateFiles | Select-Object -Unique)
    env_names = @($envNames)
    scheduled_tasks = @($tasks)
    env_lengths = $envLengths
    services = @($services)
} | ConvertTo-Json -Depth 6

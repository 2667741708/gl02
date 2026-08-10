$ErrorActionPreference = 'Stop'
$uri = 'http://10.30.220.12:8093/api/diagnosis-ai-analysis?label=cold&t=local-error-check-20260808'
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $uri -TimeoutSec 40
    $body = $response.Content | ConvertFrom-Json
    $record = $body.analysis
    $item = $record.analysis
    [ordered]@{
        status = [int]$response.StatusCode
        ok = [bool]$body.ok
        enabled = [bool]$body.enabled
        state = [string]$record.state
        target_label = [string]$record.target_label
        target_display_name = [string]$record.target_display_name
        diagnosis_ts = [string]$record.diagnosis_ts
        data_limits = @($item.data_limits | ForEach-Object { [string]$_ })
        variable_ids = @($item.variable_evidence | ForEach-Object { $_.variables } | ForEach-Object { $_.id } | Sort-Object -Unique)
        core_variable_count = [int]$record.core_variable_count
    } | ConvertTo-Json -Depth 8
}
catch {
    $message = ''
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $message = $_.ErrorDetails.Message }
    elseif ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $message = $reader.ReadToEnd()
        $reader.Dispose()
        $stream.Dispose()
    }
    [ordered]@{ error = $_.Exception.Message; body = $message } | ConvertTo-Json -Depth 8
}

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$bridgePath = Get-ChildItem -LiteralPath (Get-Location).Path -Recurse -Filter "local_pg_ws_bridge.py" | Select-Object -First 1 -ExpandProperty FullName
$bridge = [IO.File]::ReadAllText($bridgePath, [Text.Encoding]::UTF8)
if ($bridge.IndexOf('payload["foreman_guidance"]', [StringComparison]::Ordinal) -lt 0) {
    $fn = $bridge.IndexOf("def diagnosis_snapshot_payload", [StringComparison]::Ordinal)
    $ret = $bridge.IndexOf("    return payload", $fn, [StringComparison]::Ordinal)
    if ($fn -lt 0 -or $ret -lt 0) { throw "diagnosis payload return anchor missing" }
    $insert = @'
    if audit_conn is not None:
        try:
            payload["foreman_guidance"] = latest_foreman_guidance(audit_conn)
        except Exception as exc:
            payload["foreman_guidance"] = {"state": "unavailable", "read_only": True, "reason": type(exc).__name__, "fallback_policy": "computed_cold_pressure_when_no_foreman_guidance"}
'@
    $bridge = $bridge.Substring(0, $ret) + $insert + [Environment]::NewLine + $bridge.Substring($ret)
}
[IO.File]::WriteAllText($bridgePath, $bridge, $utf8)
Write-Output "bridge guidance payload inserted"

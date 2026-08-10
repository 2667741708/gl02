from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "set_22012_imes_realtime_1min.ps1"


def test_imes_realtime_one_minute_deployer_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "OPS-IMES-REALTIME-1MIN-20260809" in source
    assert "-RepetitionInterval (New-TimeSpan -Minutes 1)" in source
    assert "$policy.InnerText = 'IgnoreNew'" in source
    assert "[Xml.XmlConvert]::ToTimeSpan([string]$newInterval)" in source
    assert "Export-ScheduledTask" in source
    assert "Register-ScheduledTask" in source
    assert "verification_run_started" in source
    assert "did not start in 10 seconds" in source
    assert "default_transaction_read_only=on" in source
    assert "bf_imes.raw_rows" in source
    assert "foreach ($port in @(8093, 8768, 8094, 8770))" in source
    assert "Stop-Service" not in source
    assert "Restart-Service" not in source

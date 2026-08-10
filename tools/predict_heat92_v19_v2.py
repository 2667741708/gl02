"""Compatibility launcher for the heat-92 V19 runner."""
from pathlib import Path

source = Path(__file__).with_name("predict_heat92_v19.py").read_text(encoding="utf-8")
source = source.replace('cutoff.to_period("M").astype(str)', 'str(cutoff.to_period("M"))')
exec(compile(source, "predict_heat92_v19.py", "exec"), {"__name__": "__main__", "__file__": str(Path(__file__).with_name("predict_heat92_v19.py"))})

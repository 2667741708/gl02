"""Compatibility launcher for the heat-92 V19 runner with full label aliases."""
from pathlib import Path

source = Path(__file__).with_name("predict_heat92_v19.py").read_text(encoding="utf-8")
source = source.replace('cutoff.to_period("M").astype(str)', 'str(cutoff.to_period("M"))')
source = source.replace('si_avg AS target__Si_mean, si_median AS target__Si_median,', 'si_avg AS target__Si_mean, si_avg AS target__Si_representative, si_median AS target__Si_median,')
exec(compile(source, "predict_heat92_v19.py", "exec"), {"__name__": "__main__", "__file__": str(Path(__file__).with_name("predict_heat92_v19.py"))})

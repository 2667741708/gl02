"""Compatibility launcher for heat-92 V19 target aliases."""
from pathlib import Path

source = Path(__file__).with_name("predict_heat92_v19.py").read_text(encoding="utf-8")
source = source.replace('cutoff.to_period("M").astype(str)', 'str(cutoff.to_period("M"))')
source = source.replace('frame = pd.DataFrame(rows)', 'frame = pd.DataFrame(rows)\n    frame["target__Si_mean"] = frame["target__Si_mean"] if "target__Si_mean" in frame else frame["si_avg"]\n    frame["target__Si_representative"] = frame["target__Si_mean"]')
exec(compile(source, "predict_heat92_v19.py", "exec"), {"__name__": "__main__", "__file__": str(Path(__file__).with_name("predict_heat92_v19.py"))})

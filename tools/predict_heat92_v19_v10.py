from pathlib import Path
source=Path(__file__).with_name('predict_heat92_v19.py').read_text(encoding='utf-8')
source=source.replace('cutoff.to_period("M").astype(str)','str(cutoff.to_period("M"))')
source=source.replace("open_ts <= timestamp '2026-08-07 02:25:00'", "meltno IN ('2#20260807-092','2#20260807-091','2#20260806-088','2#20260806-087','2#20260806-086','2#20260806-085','2#20260806-084','2#20260806-083')")
source=source.replace('frame = pd.DataFrame(rows)', 'frame = pd.DataFrame(rows)\n    frame.rename(columns={c: c.replace("target__si_", "target__Si_") for c in frame.columns}, inplace=True)\n    frame["target__Si_representative"] = frame["target__Si_mean"]')
source=source.replace('pd.concat([targets, target_row], ignore_index=True)', 'targets')
exec(compile(source,'predict_heat92_v19.py','exec'),{'__name__':'__main__','__file__':str(Path(__file__).with_name('predict_heat92_v19.py'))})

# Chronos与Ridge分时段融合实验报告

## 实验口径

- 需求：`REQ-TS-FORECAST-SEGMENTED-ENSEMBLE-20260811`
- 数据：本机 `timeseries_benchmark_frame_19.csv`
- 样本：与首轮实验相同的8个切点、19个变量，每个切点预测120分钟
- 基础模型：Chronos-2、Ridge expert-sparse、Ridge target-only
- 硬路由：1-30分钟 Chronos；31-60分钟 expert-sparse；61-120分钟 target-only
- 平滑路由：26-35分钟完成第一次线性过渡，56-65分钟完成第二次线性过渡
- Chronos计算：本机数据经220.12:8777只读推理；未修改生产服务或数据库

## 综合结果

|模型|IQR-NMAE|MAE|STD比|差分STD比|方向准确率|80%覆盖率|WIS|
|---|---:|---:|---:|---:|---:|---:|---:|
|Chronos-2|0.4724|5.7788|0.3640|0.2234|53.88%|75.37%|9.3669|
|Ridge expert-sparse|0.4704|5.9786|0.4693|0.3318|53.77%|82.36%|9.5168|
|Ridge target-only|0.4638|6.1827|0.3557|0.2225|52.89%|79.62%|9.8071|
|分段硬路由|0.4614|5.9609|0.4668|0.4019|53.62%|79.95%|9.4999|
|**分段平滑路由**|**0.4601**|5.9253|0.4578|0.2977|53.18%|80.26%|9.4544|

## 结论

1. 平滑分段的IQR-NMAE为0.4601，比最佳单模型Ridge target-only改善约0.79%，属于小幅改善，尚不足以证明稳定生产收益。
2. Chronos仍拥有最佳MAE、方向准确率和WIS；因此不能把分段融合描述为全面优于Chronos。
3. 平滑分段将STD比从Chronos的0.3640提高到0.4578，曲线动态性更强，同时80%覆盖率提高到80.26%。
4. 硬路由在30/60分钟边界的平均绝对跳变分别为3.6328和1.5645；平滑后降为0.6439和0.6234。生产展示不得使用硬切换。
5. 按IQR-NMAE逐变量统计，Chronos赢7项、expert-sparse赢5项、target-only赢4项、平滑融合赢3项。统一全变量分段规则不是最优终态，下一步应测试“变量级路由 + 分段平滑”。
6. 当前仅8个切点。平滑融合保留为实验候选，不替换8778默认LastValue，也不切换生产趋势页。

## 证据文件

- 汇总：`results/segmented_ensemble_summary_20260811_121921.json`
- 窗口明细：`results/segmented_ensemble_detail_20260811_121921.csv`
- 逐分钟预测：`results/segmented_ensemble_raw_20260811_121921.csv.gz`
- 最新切点曲线：`results/segmented_ensemble_latest_curves_20260811_121921.png`
- Chronos响应缓存：`results/chronos_segmented_cache/`
- 实验程序：`tools/experiment_segmented_ensemble_19.py`
- 权重测试：`tests/test_segmented_timeseries_ensemble.py`

## 复现命令

```powershell
& 'D:\ProgramData\anaconda3\python.exe' 'tools\experiment_segmented_ensemble_19.py' --input-csv 'PT\时间序列预测评测\timeseries_benchmark_frame_19.csv' --cutoff-summary 'PT\时间序列预测评测\results\ttm_chronos2_zero_shot_summary_20260808_124916.json'
```

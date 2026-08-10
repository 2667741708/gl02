# 19项时间序列多模型评测与8778旁路

需求：`REQ-TS-FORECAST-MULTI-MODEL-BENCHMARK-20260808`

## 实现位置

- 固定评测合同：[PT/时间序列预测统一评测标准.md](../../PT/时间序列预测统一评测标准.md)
- 特征合同：[tools/timeseries_model_contract.py](../../tools/timeseries_model_contract.py)
- Ridge-Delta训练回测：[tools/train_benchmark_timeseries_models_19.py](../../tools/train_benchmark_timeseries_models_19.py)
- 8778服务：[tools/timeseries_sidecar_service.py](../../tools/timeseries_sidecar_service.py)
- 本机启动：[tools/start_timeseries_sidecar_python.py](../../tools/start_timeseries_sidecar_python.py)
- 健康检查：[tools/check_timeseries_sidecar_python.py](../../tools/check_timeseries_sidecar_python.py)
- 220.12计划任务安装：[tools/remote_start_22012_timeseries_sidecar_8778.ps1](../../tools/remote_start_22012_timeseries_sidecar_8778.ps1)

## 服务合同

- 生产Chronos仍为`8777`，旁路为`8778`。
- `GET /api/timeseries/status`返回服务、模型目录、训练模型数量和8777上游状态。
- `GET /api/timeseries/models`返回已就绪、待训练和计划接入的模型。
- `POST /api/timeseries/predict`通过顶层`model`选择`last_value`、`linear_drift`、`ridge_delta`或`chronos2`。
- `/api/chronos/status`和`/api/chronos/predict`为现有回测程序提供兼容入口。

## 训练与回测

```powershell
python .\tools\train_benchmark_timeseries_models_19.py --training-days 14 --test-hours 48
```

训练上下文固定480分钟，预测固定120分钟。训练历史由多个滚动窗口组成，不等于向单次预测暴露14天数据。输出进入`PT/时间序列预测评测/models`和`PT/时间序列预测评测/results`。

## 安全边界

- 8778默认模型为LastValue，未训练的Ridge-Delta会明确返回模型不存在，不静默回退。
- 旁路不修改8768、8093、8094或8777调用配置。
- 远端启动脚本只有在确认8777单一监听后才安装旁路任务；若8778被无关进程占用则立即停止。
- 当前模型结果只用于离线比较，未授权写回趋势页。

## 2026-08-08运行结果

- 220.12已启动`\BlastFurnaceServices\TimeSeriesBenchmark8778`，外部8778可达，8777上游正常，38个Ridge-Delta模型已热加载；默认模型仍为LastValue，生产趋势链路未切换。
- Ridge-Delta完成38套训练，每套3364个训练样本；少量协变量把平均STD比从0.3357提高到0.4690，但IQR-NMAE从0.4473轻微变差到0.4545。
- IBM TTM R2完成8个共同有效切点的19项零样本回测。Chronos-2总体IQR-NMAE为0.4724，TTM为0.5082，LastValue为0.6125；Chronos按变量赢14项，TTM赢5项。
- Chronos平均STD比0.3640、差分STD比0.2234、方向准确率0.5388、p10-p90覆盖率0.7537，确认主要问题是过度平滑和区间覆盖不足。
- TimesFM 2.5 CPU运行环境已创建，但本机与220.12下载官方大权重均超时，未生成预测。不得把环境就绪写成TimesFM实验完成。
- 完整结论见[PT首轮实验报告](../../PT/时间序列预测评测/2026-08-08首轮多模型实验报告.md)。

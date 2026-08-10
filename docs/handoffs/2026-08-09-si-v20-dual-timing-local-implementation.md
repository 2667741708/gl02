# V20 双预测时序与一分钟数据链路本机实现

日期：2026-08-09  
状态：`local_implementation_ready_not_deployed`

## 目标

1. 保留220.12本地IMES镜像的一分钟尝试调度。
2. 将 `bf_imes.raw_rows` 到 `heat_performance_quality_summary` 的炉次质量汇总也准备为一分钟尝试调度。
3. 历史回看严格使用目标炉真实开口前60分钟的数据。
4. 生产值守由服务器每个整点运行一次，不依赖浏览器；最终与预测发起后最先真实开口的炉次比较。

## 本机实现

- `si_v20_shadow.py`：整点截止、同高炉同整点幂等、过期候选推进、下一真实开口匹配和汇总指标。
- `ollama_proxy_server.py`：新增 `/api/si-v20/hourly-history`。
- `run_si_v20_hourly_prediction.py` 与 `run_22012_si_v20_hourly_prediction.ps1`：整点原子调用入口。
- `register_22012_si_v20_hourly_task.ps1`：准备注册 `\BlastFurnaceServices\SiV20HourlyShadowPrediction`，每小时 `HH:00:05`。
- `set_22012_heat_quality_sync_1min.ps1`：准备将 `HeatPerformanceQualitySync` 改为一分钟、35秒触发；原Action/Principal保留，失败回滚。
- 工作台删除页面常开定时器；人工按钮只补跑当前整点，新增生产整点汇总视图。

## 严格口径

历史回看：

```text
预测截止 = actual open_ts - 60min
实际匹配 = 同一 target_meltno
```

生产整点：

```text
预测截止 = HH:00:00
预测发起 = requested_at（任务通常在 HH:00:05）
最终实际匹配 = 同高炉中 open_ts >= requested_at 的第一炉
```

候选炉号和预计开口时间保留在审计中，用于说明预测当时认为什么是下一炉；最终评价不强制候选炉号必须正确。

## 数据链路与延迟

```text
外部IMES
  -> \GL02SensorSync\IMESRealtime（一分钟尝试，已部署）
  -> bf_imes.raw_rows
  -> HeatPerformanceQualitySync（一分钟脚本已写，未部署）
  -> bf_assistant.heat_performance_quality_summary.si_avg
  -> V20 API
  -> 页面每60秒刷新
```

`IgnoreNew` 会跳过运行重叠，因此一分钟是触发频率，不是慢任务每60秒必定完成的承诺。需要在部署后观察连续24小时任务时长和数据水位，再判断能否达到稳定分钟级新鲜度。

## 安全边界

- V20 API不直连外部IMES，只读220.12本地数据库。
- 当前炉和截止之后发布的Si不可进入特征。
- 只写预测审计，不写生产控制值。
- 本轮未执行远端任务注册、服务重启或页面部署。

## 本机验证

- 定向 pytest：22项通过。
- `bf-si-v20-workbench.js`：`node --check` 通过。
- 整点运行器：指定严格整点的 dry-run 通过。
- 三个新增PowerShell任务/运行脚本：Windows PowerShell AST 语法解析通过。
- 浏览器连接阻止访问本机私网测试URL，本轮未完成视口矩阵；部署前必须在可访问的8093/8094测试面补验，不能据此宣称UI已通过跨浏览器验收。

## 部署后验收

- 三项计划任务状态、触发周期、动作、Principal和LastTaskResult。
- `bf_imes.raw_rows` 与炉次质量汇总最大更新时间连续推进。
- 每个整点最多一条、连续整点无缺口。
- 预测发起之后第一条真实开口炉次匹配正确。
- 化验迟到后页面自动补齐实际Si、误差和±0.05命中。

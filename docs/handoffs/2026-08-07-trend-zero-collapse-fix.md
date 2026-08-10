# 趋势预测全零塌缩修复记录

## 追踪标识

- 缺陷：`BUG-TREND-19-ZERO-COLLAPSE-20260807`
- 关联需求：`REQ-TREND-19-LANE-MERGE-20260807`
- 页面防护：`REQ-TREND-19-ZERO-COLLAPSE-GUARD-20260807`

## 现象与结论

19 变量合并趋势图中，综合顶压、上升管压 A-D、冷风流量、冷风压力、热风压力和热风温度的预测值大量显示为 0。前端没有把这些变量转换为 0；WebSocket 返回的预测中位数本身为全零序列。

当前预测链路为：趋势页通过 8768 WebSocket 发送 `chronos_predict_recommended_batch`，请求 120 分钟预测和 480 分钟历史上下文；`local_pg_ws_bridge.py` 从 PostgreSQL 读取一分钟历史值，构造目标历史与推荐协变量，然后逐目标调用 8777 的 `/api/chronos/predict`；8777 使用 Chronos2 输出 `p10/p50/p90`，前端以 `p50` 作为虚线预测。数据库读取、特征构造和前端显示均未对上述目标补零。

根因归类为 Chronos2 在部分新增目标及其协变量组合上发生全零预测塌缩。原推理程序无异常值检查，因而把全零量化结果作为成功响应返回。

## 程序修复

- `chronos外推预测/src/inference/live_chronos_predict.py`
  - 检测“近期目标历史存在有效非零值、但预测序列全部接近零”的塌缩结果。
  - 第一次仍按现有推荐协变量推理。
  - 发生塌缩时使用同一 Chronos2 模型，仅以目标自身历史重新推理一次。
  - 重试仍塌缩时返回目标级 `collapsed_zero_forecast` 错误和空量化数组，不伪造常数预测。
  - 批量请求存在部分失败时返回 `partial`，保留其他目标的真实结果。
- `高炉前端数据/front2/frontend_dashboard_front2.server.html`
  - 历史窗口明显非零而预测全零时拒绝接纳该预测序列。
  - 不再绘制误导性的 0 值虚线；历史曲线继续保留，预测状态显示异常。
- `tools/build_8094_trend_19_lane_payload.py`
  - 8093/8094 部署包同步注入相同的全零预测防护。
- `tests/test_chronos_zero_collapse_guard.py`
  - 覆盖非零历史识别、带协变量塌缩后的目标历史重试、持续塌缩返回错误。

## 接口契约

- WebSocket 请求类型仍为 `chronos_predict_recommended_batch`。
- `target_ids` 仍为 19 个目标，不修改端口、数据库和模型名称。
- 8777 HTTP 路径仍为 `/api/chronos/predict`。
- 成功目标继续返回 `p10/p50/p90`。
- 持续塌缩目标返回 `status=error`、`error=collapsed_zero_forecast`、空量化数组；批量状态允许为 `partial`。

## 验证与部署状态

- 本地 front2 页面已应用防护补丁。
- 8093 与 8094 页面部署包已重新生成。
- 当前运行环境阻止启动 `pytest` 和 `py_compile`，原因是进程执行被判定为需要交互审批，而会话策略为禁止审批；不是测试断言或代码语法报错。
- 生产 VPN 虚拟网卡 `Sangfor aTrust VNIC` 当前为 `Disconnected`，无法安全读取 220.12 当前文件、服务注册信息或执行部署。
- 尚未替换生产 8777 推理文件，尚未重启生产 Chronos 服务，也尚未对生产 19 目标执行修复后实测。

## 生产恢复后的固定步骤

1. 人工完成 Sangfor aTrust 登录，确认虚拟网卡为 `Up`。
2. 只读获取 220.12 上 8777 服务注册路径、当前推理文件哈希和 8093/8094 当前页面哈希。
3. 备份当前推理文件与两份页面文件，校验基线后原子替换。
4. 仅重启 Chronos 8777 对应服务，不重启数据库、8768、8093、8094、8770 或 11434。
5. 验证 8777 状态接口、端口监听和受保护服务 PID。
6. 通过 8768 发起 19 目标预测，确认非零历史目标不再返回全零成功结果，失败目标明确返回 `collapsed_zero_forecast`。
7. 使用 cache-bust 打开 8093 趋势页，检查 19 条历史曲线、预测虚线、悬停原始值和错误状态。

## 2026-08-08 最终根因纠正与生产闭环

生产数据库、模型直连和 8768 WebSocket 三层实测后，最终根因纠正如下：

- 28 个核心变量均在 `bf_sensor.sensor_registry` 注册并启用；最近 8 小时均有持续非零分钟值。
- 直接使用生产 PostgreSQL 构造 19 个任务并调用 8777 时，`jobs=19`、`skipped=0`，19 个目标的 120 点 `p50` 全部非零。
- 修复前通过页面同款 `ws://10.30.220.12:8768` 请求 19 项时，8768 只返回旧的 10 项；缺失的正好是综合顶压、上升管压 A-D、冷风流量、冷风压力、热风压力和热风温度。
- 生产 8768 实际运行 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\自动诊断服务\local_pg_ws_bridge.py`，其 `CHRONOS_TARGET_IDS` 仍是旧 10 目标白名单；8777 则运行 V3 目录的推理服务。由此形成“8777 支持 19 项、8768 只放行 10 项”的版本错位。
- 因此截图中的 9 项零值并非数据库补零，也不是 Chronos2 模型坍塌，而是生产 8768 未生成这些目标的预测结果，前端旧表现又把缺失结果呈现为零。

### 稀疏协变量预预测

对新增 9 项分别执行了两组生产 Chronos2 预预测：

- `target_only`：仅目标自身历史，9 项均返回 120/120 非零点。
- `sparse`：按第一版工艺关系加入 4–7 个协变量，9 项均返回 120/120 非零点。
- 输入及结果保存在 `logs/chronos_sparse_prepredict/comparison/chronos_sparse_prepredict_20260808_005213.json`。
- 该实验只证明两种输入均可稳定推理；未来真实值尚未到齐，不能据此判断稀疏方案精度优于目标自身或现有通用协变量。生产本次不切换协变量策略。

### 生产部署

- 仅扩展生产 8768 的 `CHRONOS_TARGET_IDS` 到 19 项，不修改 8777 模型、数据库或稀疏协变量配置。
- 部署脚本：`tools/remote_guarded_deploy_8768_chronos_19_targets.ps1`。
- 守卫结果：`guard_paused=true`、`guard_restored=true`。
- 原文件 SHA-256：`5C17AEE8CFF9FE9C11828C5F854E5896FF061600416605838867BBB72122703D`。
- 新文件 SHA-256：`798C55F262301D72168E775EB1B7AF128A6A08C6EAABCB4C0A99B8D76C8D6652`。
- 远端备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8768_chronos_19_targets_20260808\20260808_012258\local_pg_ws_bridge.py`。
- 数据库、8093、8094、8770、8777 和 11434 的监听 PID 部署前后完全一致。
- 部署后页面同款 WebSocket 验收：`response_status=success`、`prediction_count=19`、`zero_targets=[]`。
- 验收报告：`logs/acceptance/chronos19_zero_diagnosis_20260807.json`。

## 2026-08-08 完整 19 项专属稀疏协变量预预测

按代码实际口径，原生产特制配置覆盖旧 10 项，新增 9 项此前使用通用 23 协变量回退。本次为完整 19 项建立 4–7 个专属稀疏协变量的实验映射：

- 顶压与上升管压力使用同组压力、热风压力、总压差、风量和对应顶温。
- 风量、冷风压力、热风压力与热风温度使用送风压力、总压差、透气性、喷煤和富氧变量。
- 综合顶温与顶温 A-D 使用同组顶温、综合顶压和煤气利用率。
- 透气性与总/上/下部压差使用风量、风压、顶压和压差分量。
- 煤气利用率使用综合/四点顶温、综合顶压和风量。

生产 PostgreSQL 最近数据构造 `jobs=19`，调用生产 8777 后全部成功：

- 每个目标返回 120 个 `p50` 点。
- 19 项均为 `nonzero=120`，没有缺失目标和零预测序列。
- 每个目标实际协变量数为 4–7，不使用约 150 个全量字段。
- 实验脚本：`tools/run_chronos_sparse_prepredict.py`。
- 原始输入清单、响应和统计：`logs/chronos_sparse_prepredict/all19_specific/chronos_sparse_prepredict_20260808_012926.json`。

该结果证明完整 19 项专属稀疏输入可以稳定完成推理，但只是一时点预预测，不能证明精度优于目标自身、旧 10 项特制配置或新增 9 项通用回退。生产 8768 当前继续使用已验收的 19 目标合同；专属稀疏映射须在未来真实值到齐后做滚动回测，再按目标逐项决定是否替换。

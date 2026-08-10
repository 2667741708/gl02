# 系统架构

本文件记录当前仓库中与高炉生产页面、实时诊断、建议引擎和模型解释相关的稳定边界。详细运行、数据库和服务配置分别见 `docs/V3本地运行依赖与启动手册.md`、`docs/数据库账号配置说明.md` 与 `docs/自动值守程序配置索引.yaml`。

## 参数优化建议链路

```text
PostgreSQL分钟数据 / pSpace当前值
  -> 8768 WebSocket诊断与 multi_condition_recommendation.v1
  -> 8093、8094同一前端建议工作台
       -> 8炉况切换
       -> 4项规则主证据
       -> 19项核心证据中心
       -> 动作审计抽屉
       -> /api/diagnosis/model-review 只读解释抽屉
```

- 8768 是8093与8094共同的规则建议数据源；页面修复不得创建第二套规则事实或改写动作。
- [OptimizationVisualWorkbenchLayout](../高炉前端数据/frontend_dashboard_v3.server.html#L10591)只负责选择炉况、组织可视区和打开只读详情。
- [BFCoreEvidenceCenterV2](../高炉前端数据/frontend_dashboard_v3.server.html#L10587)复用现有分钟缓冲、基线和pSpace当前值适配器，不新增数据库表或生产写接口。
- [useDiagnosisModelReviewV2](../高炉前端数据/frontend_dashboard_v3.server.html#L10564)只对当前有效主炉况自动复核；假设炉况由用户明确点击后才调用，模型结果不能修改规则分数、动作幅度或安全门禁。
- 纯HTML/CSS/浏览器组件发布采用页面原子热更新；服务代码、端口和运行进程保持不变。设计取舍见 [ADR-20260806](decision_records/ADR-20260806-recommendation-visual-workbench.md)。

## A9/B13/C11规则边界（REQ-ABC33-FURNACE-RULES-20260807）

33项规则与现有8类诊断并行计算，不覆盖旧 `raw_scores`。`diagnosis_scheduler.py` 保存完整 `abc_rule_bundle_internal` 并写入ABC审计表；`local_pg_ws_bridge.py` 只重建 `abc_rule_bundle.v1` 生产白名单。生产详情通过 `/api/furnace-rules/*` 查看传感器、复核、处置、观察窗口和手册依据；管理员才可访问 `/api/admin/furnace-rules/*` 的公式、权重、精确阈值和贡献。`Q_blast` 只能作为证据，定量调节对象仍由既有建议合同限制为 `P_blast_cold` 与 `PCI_set`。

## 炉体温度历史回放边界（2026-08-08）

`浏览器8892 -> soft_zone_replay_server.py -> PostgreSQL只读分钟表`是一条独立展示链，不经过8093/8094代理、8768诊断或生产控制接口。服务按请求时间窗聚合80个炉体温度点，在浏览器Canvas执行周向/纵向插值与红外色谱渲染；视频由现场Edge使用`canvas.captureStream + MediaRecorder`在客户端生成，服务器不保存视频。固定时间窗色阶保证拖动过程中颜色含义不漂移。

## V20可配置预测调度架构（2026-08-09）

```text
页面选择 1/10/30/60/1440 分钟
        -> POST /api/si-v20/schedule/configure
        -> bf_assistant.si_v20_prediction_schedule

Windows任务（固定每分钟，IgnoreNew）
        -> POST /api/si-v20/schedule/dispatch
        -> 读取到期配置 -> V20预测
        -> bf_assistant.si_v20_prediction_audit

历史批量/指定时刻
        -> POST /api/si-v20/scheduled-replay
        -> bf_assistant.si_v20_prediction_run
        -> 每个 schedule_slot_ts 一条预测审计
        -> GET /api/si-v20/scheduled-history
        -> 时间槽预测曲线 + 下一真实炉次Si
```

页面调整周期只更新数据库配置，不直接操作Windows计划任务。分发器固定一分钟轮询，因此最小支持周期为一分钟；`IgnoreNew`防止模型运行重叠。若分发器长期中断，恢复时不会自动制造大批伪实时点，过期时间槽从当前对齐槽恢复；真正历史补算必须显式使用历史批量入口。

# V20可配置定时预测、曲线导出与220.12生产部署

日期：2026-08-09  
状态：`production_deployed_verified`

## 已实现

- 页面可把生产自动预测改为1、10、30、60或1440分钟，默认60分钟，并可启用/暂停。
- 页面改的是数据库配置，不直接操作Windows计划任务；服务器分发任务固定一分钟检查一次。
- 历史支持任意开始/结束时刻和上述粒度批量预测，也支持单个指定时刻。
- 定时曲线按`schedule_slot_ts`绘制；一分钟模式每分钟一个预测点。
- 每个预测点保留候选炉号、预测发起时间、特征截止、周期、批次、预测区间和最终实际匹配炉次。
- 曲线可按日期和炉次范围筛选；预测曲线、实际平均Si曲线可分别下载CSV，实际值按炉次去重。

## 数据表

- `bf_assistant.si_v20_prediction_schedule`：生产配置。
- `bf_assistant.si_v20_prediction_run`：历史批量/指定时刻运行批次。
- `bf_assistant.si_v20_prediction_audit`：新增`schedule_id/schedule_run_id/schedule_slot_ts/cadence_minutes`逐点审计。

表由V20服务首次读取调度配置时幂等迁移。2026-08-09生产只读核验三表均存在；不会为1分钟、10分钟等分别创建独立表，避免表数量随配置膨胀。

## 匹配口径

- 实时自动点：匹配`requested_at`之后最先真实开口的同高炉炉次。
- 历史时间槽：匹配`schedule_slot_ts`当时或之后最先真实开口的同高炉炉次。
- 实际Si：始终读取`heat_performance_quality_summary.si_avg`。

## 后台任务

- Python：`tools/run_si_v20_schedule_dispatcher.py`。
- 220.12包装：`tools/run_22012_si_v20_schedule_dispatcher.ps1`。
- 注册器：`tools/register_22012_si_v20_schedule_task.ps1`。
- 目标任务：`\BlastFurnaceServices\SiV20ScheduledShadowPrediction`，一分钟、SYSTEM、IgnoreNew。

## 验证

- 定向pytest：28项通过。
- 前端JavaScript语法通过。
- 分发器dry-run通过。
- PowerShell脚本AST语法通过。
- 8093守卫闭环部署时间：`2026-08-09 22:56:08`；备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\si_v20_workbench_8093_20260808\20260809_225546`。
- 三表核验：schedule/run/audit均存在；默认`schedule_id=1`、60分钟、启用。
- 任务核验：`SiV20ScheduledShadowPrediction`注册成功，SYSTEM、IgnoreNew、最近任务结果0。
- 首个生产时间槽：`2026-08-09 23:00:00`，`last_run_status=success`，审计点数1。
- 23:17与23:18连续分钟分发日志均`ok=true/due_count=0/writes_prediction_audit_only=true`，证明任务持续触发且不会在未到期时重复写点。
- 8093/8094的schedule和scheduled-history API均HTTP 200；8094受控重启`13748 -> 728`并加载共享新后端，8093/8768/8770/11434 PID保持`9884/12816/3732/5968`不变。
- 8093真实浏览器验收：页面显示最新实际炉次127和候选128；炉次124~127筛选为4行；实际Si CSV按钮成功导出4炉；页面无横向溢出。
- 8094静态页HTTP 200，资源包含`20260809-curve-export-r6`和下载控件；完整Firefox/WebKit代表视口尚未补跑，不宣称跨浏览器矩阵完成。

## 运行边界

- V20仍是`experimental_shadow`，只写预测审计，不写高炉控制值。
- 1/10/30分钟和日频使用的仍是开口前60分钟训练模型，必须分提前量评价。
- 页面保存周期只改数据库配置；Windows分发任务始终一分钟检查一次。

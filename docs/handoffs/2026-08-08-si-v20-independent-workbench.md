# V20 平均 Si 独立预测工作台（2026-08-08）

追踪编号：`REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808`

## 已实现

- `高炉前端数据/si_v20_workbench.html` 与 `assets/bf-si-v20-workbench.js`：候选炉次、当前预测、数据就绪度、历史实际/预测曲线、筛选、逐炉表格和审计详情。
- `GET /api/si-v20/status` 返回 `candidate_targets`；完成实绩不再推荐为候选，MES 无开口的候选使用估计时间并单独标记。
- `GET /api/si-v20/history` 返回实际实绩与预测审计并集；没有预测的历史炉次也会显示。`requested_at` 保留实际发起预测的时间，`prediction_cutoff_ts` 保留模型数据截止时间。
- `GET /api/si-v20/data-readiness` 与 `GET /api/si-v20/prediction-detail` 已加入 8093 路由。
- 220.12 本地 `bf_imes.raw_rows` 镜像回补已加入同步脚本；预测实际值固定读取 `bf_assistant.heat_performance_quality_summary.si_avg`。

## 本机验收

- `python -B tests\\test_si_v20_shadow_workbench.py`：9/9 通过，包含“开口前60分钟回放”截止时刻断言。
- 本地镜像回补单测：`mirror_test_ok`。
- Chromium、Firefox、WebKit 独立页验收：均通过；候选、曲线、历史行存在，控制台错误为 0。

## 运行边界

- V20 仍为 `experimental_shadow`，不改生产设定值，不写生产控制表。
- 预测提交后，后续化验由同步链路写入汇总表；历史接口按炉号自动补齐实际值和误差，不需要重新预测。
- `requested_at` 与 `prediction_cutoff_ts` 不同：前者是用户点击/请求时间，后者是严格防泄漏的数据截止时间。

## 112 炉化验迟到回填（2026-08-08 17:40）

- 220.12 `bf_imes.raw_rows` 已收到 `2#20260808-112` 的 Si=0.53，镜像时间约 17:18。
- 原同步条件只选择 `h.meltno IS NULL`，已有占位汇总行但 `si_avg IS NULL` 时不会回填；已改为同时处理 `h.si_avg IS NULL`。
- 回填后历史接口返回：`actual_si_mean=0.53`、`actual_sample_count=1`、`history_status=compared`、绝对误差约 `0.198629`、±0.05 未命中。
- 8093 独立页已增加每60秒自动刷新；热更新未重启8093守卫，页面 HTTP 200，自动刷新标记已验收。

## 按小时影子预测（2026-08-08 17:52）

- 新增 `POST /api/si-v20/hourly-predict`，将截止时间对齐到整点并保存 `request_mode=hourly_schedule`。
- 页面新增“按小时预测 Si”按钮和“页面打开期间每小时自动预测”选项；自动模式只在浏览器页面保持打开时运行，不会偷偷改变生产设定值。
- 8093 已部署并验证：目标 `2#20260808-113`、截止 `17:00`、提前量 `74.0min`，返回 `experimental_shadow`。
- 2026-08-09运行复核：220.12没有对应服务器计划任务；上述113炉记录在17:52发起，而真实开口为17:15，故只能证明整点截止API可调用，不能证明严格每小时在线运行。审计表严格开口前小时样本为0。

## 8093 快速部署

从本机项目根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\\tools\\deploy_si_v20_workbench_8093.ps1'
```

该脚本分为上传和远端原子替换两个短阶段，只重启 8093 守卫并保护 8768；远端失败会恢复部署前文件并尝试恢复服务。不要用长时间等待的 8093+8094 联合部署脚本替代它。

## 自动刷新故障修复（2026-08-09 19:28）

- 运行态核查证明 `HeatPerformanceQualitySync` 在 19:21 成功运行，页面 API 已返回 `2#20260809-125`、`si_avg=0.23`、来源更新时间 `19:20:22`；数据库与汇总同步没有停。
- 根因一：8093 对 JS 返回一年 `immutable` 缓存，但 HTML 长期引用 `bf-si-v20-workbench.js?v=20260808-v1`。热更新后的 60 秒刷新逻辑无法到达已缓存旧资源的浏览器。
- 根因二：页面只在首次加载设置历史结束日期，跨午夜保持打开时会继续查询前一天。
- 根因三：没有正式开口时间的旧 `114` 占位炉次未按最新完成炉次序号淘汰，导致候选区错误推荐旧炉次。
- 修复：资源版本更新为 `20260809-auto-refresh-r2`；默认近七日范围随日期推进，手动历史范围保持不变；无正式时间且序号不大于最新完成炉次的旧占位不再作为候选。
- 生产验收：受控部署备份 `backups\si_v20_workbench_8093_20260808\20260809_192733`；8093 守卫恢复、8768 PID `12816` 保持；推荐候选为 `2#20260809-126`。真实 Chrome 显示 125/124/123 最新实绩、结束日期 `2026-08-09`、最新质量时间 `19:20:22`，横向溢出 0。

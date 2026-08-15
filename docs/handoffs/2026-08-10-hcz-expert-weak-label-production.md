# HCZ专家弱标签工作台生产交接

## 结论

`REQ-HCZ-EXPERT-WEAK-LABEL-20260810` 已于2026-08-10部署到220.12的独立8892服务：

- 现场入口：`http://10.30.220.12:8892/hcz-labeling.html`
- 页面只显示GL02炉体温度、18点静压力等实测回放；`labeling_blind=1`强制关闭并隐藏C2/HCZ估计开关和估计结果卡。
- 标注记录是`expert_weak_label`，不是HCZ真实测量，不得直接改名为真值。
- 首次部署后标签数为0；验收没有写入虚假生产标签。

## 高炉长操作

1. 打开现场入口，调整左侧证据窗口并加载历史。
2. 拖动回放时间轴到需要判断的时刻；右侧显示服务器固定的标注时刻、证据窗口、覆盖率和SHA-256前缀。
3. 填写位置高低、移动方向和可信等级；中心高度、厚度、偏心方位允许留空。
4. 填写实际标注人姓名或工号；无法判断时使用“无法判断”，位置和方向均无法判断时必须写明原因。
5. 点击“保存专家弱标签”。记录只追加不覆盖；需要更正时使用“创建修订”，形成`supersedes_label_id`审计链。

历史窗口早于窗口结束时，标签会保存为`retrospective_with_post_observation_evidence`；窗口结束等于标注时刻时保存为`contemporaneous_blind`。两类样本训练时必须分开，不得把事后证据样本冒充实时可用样本。

## 数据与安全合同

- 表：[bf_assistant.hcz_expert_label_events](../../高炉前端数据/智能助手/backend/schema/postgresql_hcz_expert_label.sql)
- 标注版本：`hcz-expert-weak-label.v1`
- 证据版本：`gl02.hcz-label-source.v1`
- 知识时间：`observed_at`、`available_at`、`source_window_start`、`source_window_end`
- 盲标字段：`blind_to_model=true`；证据JSON固定`model_outputs_included=false`
- 浏览器不能提交模型字段；后端会拒绝`model_prediction`、`hcz_estimate`等字段。
- 浏览器传入的哈希只用于乐观一致性检查；服务器提交时重新读取实测窗口、规范化记录并计算SHA-256。
- 存储只追加；不提供UPDATE/DELETE API。导出CSV不包含数据库连接参数或密码。
- 无登录现场模式使用服务器固定审计身份`onsite_8093/现场高炉长`，同时强制操作人手填姓名或工号。

## 程序、API与部署

- 后端合同与存储：[hcz_expert_label.py](../../高炉前端数据/智能助手/backend/hcz_expert_label.py)
- 8892服务/API：[soft_zone_replay_server.py](../../tools/soft_zone_replay_server.py)
- 页面：[hcz-labeling.html](../../高炉前端数据/soft_zone_replay/hcz-labeling.html)、[hcz-labeling.js](../../高炉前端数据/soft_zone_replay/hcz-labeling.js)、[hcz-labeling.css](../../高炉前端数据/soft_zone_replay/hcz-labeling.css)
- 强制盲回放：[soft-zone-replay.js](../../高炉前端数据/soft_zone_replay/soft-zone-replay.js)
- 本机部署入口：[deploy_hcz_expert_label_22012.ps1](../../tools/deploy_hcz_expert_label_22012.ps1)
- 远端受控部署：[remote_guarded_deploy_hcz_expert_label_8892.ps1](../../tools/remote_guarded_deploy_hcz_expert_label_8892.ps1)
- 远端运行入口：[run_22012_soft_zone_replay_8892.ps1](../../tools/run_22012_soft_zone_replay_8892.ps1)
- 计划任务：`\BlastFurnaceServices\SoftZoneTemperatureReplay8892`，SYSTEM、AtStartup、IgnoreNew；Action为`C:\Program Files\PowerShell\7\pwsh.exe -NoLogo -NoProfile -File ...`。

API包括：

- `GET /api/hcz-label-config`
- `GET /api/hcz-label-context?observed_at=&start=&end=`
- `GET /api/hcz-labels?start=&end=&limit=`
- `POST /api/hcz-labels`
- `GET /api/hcz-label-export?start=&end=&limit=`

## 验收证据

- Python专项与原8892回归：`12 passed`
- Ruff：通过
- PowerShell 7.6.4 Core/UTF-8：通过
- 本地UI矩阵：Chromium 9个视口、Firefox 4个、WebKit 4个，共17/17通过；无横向溢出、页面/控制台错误为0、盲标控件不可见、提交流程成功。
- 本地报告：[report.json](../../logs/hcz_expert_label_20260810/viewport_matrix/report.json)
- 生产Edge只读冒烟：服务就绪、实测证据SHA-256已固定、标签0条、HCZ估计开关和结果卡均`display:none`、未勾选、无错误、无坏响应。
- 生产报告：[report.json](../../logs/hcz_expert_label_20260810/remote_22012/report.json)
- 生产截图：[edge_1366x768.png](../../logs/hcz_expert_label_20260810/remote_22012/edge_1366x768.png)

部署结果：8892 PID从`12440`切换为`5496`；非法空POST返回400且标签数仍为0；上下文哈希前缀`14cf6575f7af`。8093=`10008`、8094=`2988`、8768=`18436`、8770=`3732`、5432=`12372`在部署前后均未改变，8093/8094 HTTP均为200。远端文件/任务备份位于`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\hcz_expert_label_8892_20260810_124845`。

## 后续建模门禁

收集到足够样本后，必须先按`available_at`做时间切分，并按标注人、可信度、同期/事后证据模式统计一致性；未经盲测、时间外回测、多人一致性和现场批准，不得把现有低置信度特征融合诊断升级为“已训练HCZ真值模型”，也不得用于自动控制。

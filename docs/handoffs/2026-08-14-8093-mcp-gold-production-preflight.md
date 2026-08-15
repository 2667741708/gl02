# 8093 MCP 金标修复生产部署交接

状态：`completed`  
最后核对：2026-08-14 10:44（Asia/Shanghai）  
需求：`REQ-MCP-AGENT-GOLDEN-SUITE-20260814`、`OPS-22012-GIT-BASELINE-20260814`  
错误：`ERR-MCP-STATIC-PRESSURE-TASKGROUP-20260814`、
`BUG-MCP-EVIDENCE-FORMATTER-20260814`、`BUG-MCP-CROSS-SOURCE-FACT-PROJECTION-20260814`

## 最终结论

220.12 已安装受控 Portable Git，生产根已建立经过敏感扫描的独立 Git 基线；8093 上比本机更新的
炉温趋势、工长基准偏差卡片和已发布阈值配置已经审查并同步回本机。MCP 生命周期异常、确定性
证据格式化和跨 MCP 相关性事实投影三项修复已受控部署到 8093，并通过唯一一次真实 SSE 工具问答。

最终生产状态：

| 项目 | 结果 |
|---|---|
| 服务 | `BFV4PreviewProxy8093 = Running` |
| 最终 PID（8093 / 8094 / 8768 / 8770 / 5432 / 11434） | `1968 / 5912 / 4036 / 3732 / 12372 / 16232` |
| 最终 Git HEAD | `6a5ca5afb5225ba67364857af194438af6d297dd` |
| 最终 Git 状态 | clean |
| keyword 知识检索 | `ok=true`，证据 2 条 |
| 模型驻留 | 仅 `chiqiong-blast-furnace:latest` |
| 共享访客 | `access_mode=guest_shared` |
| MCP health | `ok=true` |

## Git 安装和敏感扫描基线

- 安装包：Portable Git `2.53.0.windows.3`，SHA-256
  `A3E52782970C8FD089A828DB49B24C5A042F7D8A8EFF6F474593AAA9AAB8016F`。
- 安装位置：`F:\Tools\PortableGit\cmd\git.exe`；未修改系统 PATH、服务或计划任务。
- 生产 worktree：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW`。
- 独立 Git 目录：`F:\BF_Git\V4_8093_PREVIEW.git`。
- 初始根提交：`dad65e448958da299dd8359ac50531b161b77da6`，338 个经过文件名和内容敏感扫描的
  明确路径；使用 NUL 路径清单精确暂存，没有执行 `git add .`。
- 初始标签：`prod-8093/20260814-initial-dad65e448958`。
- 基线清单：`F:\BF_Git\V4_8093_PREVIEW.baseline.baseline-finalize-20260814-1008.json`。
- 首次提交耗时超过控制端超时，状态被视为不确定；只读探测确认 HEAD 后才继续，没有重放提交。

## 远端新功能先同步到本机

远端 396 文件 SHA-256 清单用于差异审查。合并内容包括：

1. `thermal_trend_rule.py` 及其公共/管理员 API 集成；
2. 8 项炉温趋势指标、工长基准日期和报警阈值配置；
3. 工长“基准偏差预警 / 炉温趋势研判”子页签、全宽自适应卡片和报警优先排序。

最终本机与远端以下五项内容哈希一致：三个 MCP 生产文件、
`abc-furnace-rules-production.js` 和 `thermal_trend_rule.v1.json`。运行态条件确认文件、凭据、Cookie、
Token、私钥和服务配置快照没有同步进仓库。

## MCP 最小部署与真实验收

密封 delta SHA-256：
`107AE6850F4099E4B77ABBCC47B6968D8EDA5744D0E357878F164413DC247038`。
成功执行 ID：`mcp-gold-20260814-1035-r3`。

只替换以下三项：

| 文件 | 安装 SHA-256 |
|---|---|
| `ollama_proxy_server.py` | `E0BF2DE8C6B6136F167901AEE2F90784804EB3ED8C91C60F3A20EF112DB443C1` |
| `mcp_host/client_manager.py` | `572F89AC88183739089BE4085E538391FF60A0AE2B0F9B15E7E766ADD2F9F7BB` |
| `mcp_host/cross_source_executor.py` | `E64CCDA2FAF7DA1BDAD21FD56CDCFD00F7BC0B0E9DBD02494A7C4D8622B0C9C6` |

成功切换时 8093 PID `2984 → 16464`，一次启动成功；8094、8768、8770、5432、11434 PID
前后分别保持 `5912/4036/3732/12372/16232`。备份位于
`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\mcp_gold_8093_20260814_103534`。

唯一一次真实 SSE：

- 问题：查询当前综合顶压 `P_top`，要求值、单位、数据时间、质量和来源；
- 轨迹：`start(preparing) → start(prepared) → tool_start → tool_result → delta → final → done`；
- 工具：`gl02-data/query_gl02_sensors`，`query_type=latest`；
- 结果：`260.453 kPa`，数据时间 `2026-08-14T10:34:00`，质量 `Good`，只读来源已列出；
- `request_count=1`、`tool_start_count=1`、`tool_result_count=1`；
- 没有自动重试。

说明：该问题命中了 `deterministic_sensor_query`，服务端没有提供底层模型调用计数。最初控制器把
“SSE 已被 HTTP 200 接受”记为 `model_request_count=1`，该口径不严谨，已在本机验收器中废止；
本记录只声明一次真实问答 POST、一次只读 MCP 工具调用和一次确定性答案，不声明底层模型被调用。

两次预期回滚也验证了回滚边界：

1. `mcp-gold-20260814-1025`：计划任务 `267009/0x41301`（仍在运行）被误判失败；三文件回滚，
   模型请求 0。部署器已改为等待该次守卫运行真正完成。
2. `mcp-gold-20260814-1029-r2`：验收器遗漏 bootstrap 的 `conversation.id`，POST 被 400
   `conversation_id_required` 拒绝；三文件回滚，实际模型请求 0。验收器已绑定共享访客会话 ID，
   并分别记录 HTTP 问答与实际模型次数。

## 验收后 Git 版本

- MCP 与当时已审查的前端提交：`aa87f3b76582064b53fd9ce0601bf3a36db94717`；标签
  `prod-8093/20260814-mcp-gold-aa87f3b76582`。
- 随后生产侧发布的卡片布局增量经再次审查、敏感扫描和本机同步后提交：
  `6a5ca5afb5225ba67364857af194438af6d297dd`；标签
  `prod-8093/20260814-frontend-sync-6a5ca5afb522`。
- 最终 Git 保存期间所有六个 PID 前后不变，保存后工作树 clean；没有重启服务。

## 本机验证

- 87 项 MCP/部署/热趋势聚焦回归通过；
- 同步最终生产配置后，热趋势、部署合同和 SSE 验收器 12 项回归通过；
- `node --check 高炉前端数据/assets/abc-furnace-rules-production.js` 通过；
- 三份生产 Python 文件远端/本机 SHA-256 一致。

## 可复现入口

- 生成密封发布：`pwsh.exe -NoLogo -NoProfile -File .\tools\prepare_8093_mcp_gold_release.ps1`
- 受控部署：`tools/remote_guarded_deploy_8093_mcp_gold.ps1`
- 唯一 SSE：`tools/verify_8093_mcp_gold_sse_once.py`
- Git 版本保存：`tools/remote_record_8093_mcp_gold_git_version.ps1`
- 远端前端增量保存：`tools/remote_record_8093_reviewed_frontend_git_version.ps1`
- 金标校验：`python tools/evaluate_mcp_gold_tasks.py --validate`

适用边界：本记录证明 2026-08-14 的生产部署、一次真实 `P_top` 工具问答和版本保存。多工具、
相关性、超时与部分失败的生产实测仍应按金标清单逐项、每题一次执行，不得把本次单工具验收外推为
全部 14 项生产金标已通过。

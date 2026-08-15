# 8093 MCP 并行五轮、共享访客与权威环境同步

- 状态：`deployed / accepted / local-remote-synced`
- 最后核对：2026-08-13
- 需求：`REQ-8093-MCP-PARALLEL-5-AND-GUEST-DEPLOY-20260813`、`OPS-8093-AUTHORITATIVE-LOCAL-SYNC-20260813`
- 适用边界：仅 `220.12:8093`；不修改 8094、8768、8770、PostgreSQL 或 Ollama 服务。

## 已完成

- 模型规划默认上限为 5 轮，整次问答累计最多 5 次工具请求。
- 同轮不同 MCP 服务可并行；同一 stdio 服务使用服务级锁串行，结果按规划顺序进入模型上下文。
- 模型被要求只挑取与问题相关的数值、单位、时间戳/时间窗和来源；工具失败或达限后仍只执行一次禁用工具的模型回答。
- 共享匿名访客使用稳定房间标识和 PostgreSQL 持久会话；不同局域网浏览器访问同一地址时共享同一会话窗口。
- 本地聚焦回归 44 项通过；部署器与新增验收聚焦回归 18 项通过；Python 与 PowerShell AST 校验通过。

## 远端有效更新合并

- 部署前重新读取生产基线，发现远端已经包含有效的 A 类规则失分解释实现。本地没有覆盖该更新，
  而是同步并合并 `abc_score_explanation.py`、规则详情后端集成和
  `abc-furnace-rules-production.js` 展示逻辑。
- 合并后的本地版本同时保留共享匿名访客、五轮规划、最多五次工具调用、跨 MCP 服务并行和
  工具失败后单次无工具模型降级回答。
- 当前远端 A 类失分解释模块与前端资产和本地文件 SHA-256 一致。

## 生产尝试、回滚与最终切换

- 第一次执行 ID：`mcp5-guest-20260813-1015`。
- 生产文件在备份后安装并启动成功，但验收器错误读取了不存在的顶层 `current_conversation_id`，实际合同为 `conversation.id`。
- 部署器因此按合同自动回滚应用文件；`guard_restored=true`、`rollback_applied=true`，8093 最后确认 `Running`、PID `92`。
- 幂等增量数据库迁移保留；没有执行破坏性 DROP。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_contextual_assistant_8093_20260813_101610`。
- 验收器已修正并重新密封，但随后 Sangfor aTrust VNIC 断开。固定前置门禁阻止了第二次上传和部署；不存在不确定远端执行。

- VPN 恢复后，执行 `mcp5-guest-20260813-1133`。该次因部署器仍断言旧前端资产版本而按合同回滚；
  守卫恢复成功，没有发送真实 SSE，备份为
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_contextual_assistant_8093_20260813_113418`。
- 修正确定性资产标记并通过聚焦回归后，执行 `mcp5-guest-20260813-1137` 成功：8093 PID
  `2096 → 6720`，HTTP 200，`guard_paused=true`、`guard_restored=true`、
  `rollback_applied=false`。备份为
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_contextual_assistant_8093_20260813_113749`。
- 真实验收只发送一次 SSE：`access_mode=guest_shared`，两个独立浏览器会话得到同一
  `conversation_id=qa_guest_4f942a3e6bdfc48b4d26b5ea`；消息持久化计数为 2；事件包含
  `preparing → prepared → 5×(tool_start/tool_result) → delta → final → done`；答案非空且
  问答前后 8093 PID 不变。
- 随后以受控配置补丁将生产服务配置显式固定为
  `guest=1 / keyword / tool_rounds=5 / tool_calls=5 / parallel=1 / max_parallel=5`。
  配置备份为
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_guest_mcp_runtime_config_20260813_114302.json`，
  最终 8093 PID 为 `15368`，配置补丁本身没有调用模型。
- 整个切换期间 8094、8768、8770、5432、11434 的 PID 分别保持
  `5912 / 4036 / 3732 / 12372 / 16232` 不变。

## 当前恢复与复用入口

1. 修改前先重跑 VPN、SSH 22、PostgreSQL 5432、8093、Ollama 11434 前置检查。
2. 刷新生产文件哈希；若远端漂移，先下载、审查并合并，不得用本地旧文件覆盖。
3. 复用 `tools/prepare_8093_mcp_parallel_guest_release.ps1`、`tools/build_8093_mcp_parallel_guest_package.ps1`、`tools/stage_abc33_contextual_assistant_8093_package.ps1` 和 `tools/remote_deploy_abc33_contextual_assistant_8093.ps1`。
4. 运行 `tools/remote_export_8093_authoritative_snapshot.ps1` 并下载脱敏快照到
   `docs/handoffs/8093_authoritative_snapshot.latest.json`；各电脑再运行
   `tools/compare_8093_authoritative_snapshot.ps1`。当前比较结果为 `ok=true`。

## 最终验证

- Python 编译：后端代理与 A 类失分解释模块通过。
- Node 语法：ABC33 生产资产通过。
- 聚焦回归：共享访客、并行规划、工具失败降级、上下文会话与部署合同共 42 项通过；
  ABC33 失分解释 1 项通过；上下文 UI 与部署脚本 11 项通过。
- PowerShell 7 UTF-8 项目基线验证通过。
- 生产 QA 页面 Chromium `1366×768` 只读冒烟 1/1 通过，浏览器模型请求
  `real_sent=0`；报告位于 `logs/mcp5_guest_remote_merge_qa_smoke/report.json`。
- 脱敏权威快照已经同步到本地；应用代码、静态资源、schema 和服务管理脚本按 SHA-256
  比较一致，服务配置按脱敏语义字段比较一致。

## 权威同步安全边界

- 同步应用源码/静态资源以 SHA-256 证明字节一致。
- 同步 PowerShell、Python、服务状态、端口、非敏感环境值和配置字段名。
- 密码、Cookie、Token、私钥、连接串和认证环境值只显示 `<redacted>`，不得下载到仓库或普通复用目录。
- 原始远端服务配置仍以受控服务器路径为权威；每次生产修改前重新刷新脱敏快照。

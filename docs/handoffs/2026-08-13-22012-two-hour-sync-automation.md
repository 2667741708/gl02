# 220.12 每两小时更新同步与版本保存自动任务

状态：已启用  
最后核对日期：2026-08-13  
事项编号：`OPS-22012-BIDIRECTIONAL-SYNC-20260813`

## 目标

每两小时检查 220.12 的 V4 项目是否出现新的代码或功能。确认变化可安全合并时同步到本地，完成受影响测试后保存本地 Git commit 和唯一版本 tag。

## 当前任务

- Codex 自动任务 ID：`220-12`
- 名称：`220.12每两小时更新同步与版本保存`
- 状态：`ACTIVE`
- 执行环境：本地项目 `D:\文件\冀南钢铁运行中第二版本`
- 远端根：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW`

## 固定流程

1. 保存本地 `git status --short`，保护运行前已有改动。
2. 只读探测远端环境、Git 身份和源码哈希；远端 Git 不可用时以 SHA-256 清单作为 server version。
3. 生成并下载脱敏权威快照，与 `reports/server_sync/state/last_success.json` 比较。
4. 无变化时记录 `no_update`，不创建空 commit。
5. 有变化时只下载变化的非敏感白名单文件到隔离候选目录。
6. 本地未变化的路径才允许自动同步；双边变化记为 `conflict_needs_review`，禁止覆盖。
7. 运行受影响测试；失败时只回退本轮自动替换。
8. 成功后只暂存本轮同步路径，创建普通 commit 和唯一的本地 annotated tag；不 push 外部 remote。

## 安全边界

该任务没有生产写权限，不上传文件，不停止或启动服务，不修改数据库、端口、计划任务、生产配置或远端 Git。凭据、Cookie、Token、私钥、完整连接串、服务配置原文、日志、备份、数据库、模型和缓存均不得下载到普通证据目录。

当前本地工作树包含大量未提交改动，因此首次运行只建立服务器版本基线。后续发现与这些本地改动重叠的服务器更新时，任务必须保留候选副本并请求人工合并。

## 验收

- 自动任务已通过 Codex 自动任务接口创建，并重新读取任务配置确认状态为 `ACTIVE`。
- 任务频率为每两小时，项目目标指向当前仓库。
- 自动任务提示词已固定冲突保护、精确暂存、测试门禁、版本 tag 和远端只读边界。
- 已立即完成首次只读基线：远端临时执行脱敏快照导出成功，记录 10 个关键应用文件 SHA-256；本地快照为 `reports/server_sync/snapshots/baseline_20260813.json`，SHA-256 为 `3A6EAE4E9C4F22B5A54224F7E98DCF535359AC80D7DC91565E77952E4A2E01D4`。
- 基线状态已写入 `reports/server_sync/state/last_success.json`，状态为 `baseline_initialized`；没有下载或覆盖应用源码，没有创建空 commit/tag，工作树原有改动未被触碰。
- 远端生产目录当前不能通过 PATH 调用 Git；后续周期以白名单 SHA-256 作为 server version。脱敏导出脚本使用远程临时执行，不要求把工具长期写入生产目录。

## 权威来源

- [需求追踪](../requirements_traceability.md#ops-22012-bidirectional-sync-20260813)
- [自动化追踪](../automation_traceability.md#ops-22012-bidirectional-sync-20260813)
- [配置参考](../config_reference.md#22012-每两小时更新同步配置)
- [远端 Git 双向同步规则](../../.codex/skills/deploy-8093-guarded-update/references/remote-git-bidirectional-sync.md)

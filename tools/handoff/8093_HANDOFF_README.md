# 冀南钢铁 220.12:8093 维护交接包

本包是当前工作区的受控快照，用于让获得正式授权的维护人员快速理解并处理 220.12 上的 8093 项目。它不是自动部署包，也不代表接手者已经获得生产写权限。

## 先读内容

1. `.codex/skills/deploy-8093-guarded-update/SKILL.md`
2. `.codex/skills/deploy-8093-guarded-update/references/project-contract.md`
3. `docs/architecture.md`、`docs/program_index.md`、`docs/cli_usage.md`
4. `docs/handoffs/2026-08-10-8093-risk-tiered-validation.md`
5. 与本次具体变更最接近的 `docs/handoffs/` 记录

## 固定生产边界

- 8093 受管服务：`BFV4PreviewProxy8093`
- 部署互斥：`Global\BFV4PreviewProxy8093Deployment`
- 受保护端口：8094、8768、8770、5432、11434、8892
- 本机与远端 PowerShell 入口：PowerShell 7 Core；禁止把日常入口回退到 Windows PowerShell 5.1
- 传输中断后的远端命令状态视为不确定，必须先探测，禁止自动重放
- 生产配置以远端现场为准；任何替换前必须做哈希、服务和端口预检

## 推荐接手顺序

1. 解压到短路径，确认 `PACKAGE_MANIFEST.json` 中的文件哈希。
2. 通过独立安全渠道取得 220.12 的账号、认证材料和变更授权；不要把凭据写入本包。
3. 在项目根目录运行：

   ```powershell
   pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1
   ```

4. 阅读受控 Skill 后，再按任务授权范围启动持久会话：

   ```powershell
   pwsh.exe -NoLogo -NoProfile -File .\tools\start_remote_22012_session.ps1
   ```

5. 需要证明会话复用时运行：

   ```powershell
   pwsh.exe -NoLogo -NoProfile -File .\tools\verify_22012_persistent_ssh_reuse.ps1
   ```

6. 先做只读现场探测，确认远端根目录、PowerShell 7、服务、监听 PID、HTTP、目标文件哈希和部署互斥状态；取得明确生产写授权后，才进入 Skill 规定的“预暂存 → 锁 → 备份 → 仅暂停 8093 → 原子替换 → 恢复 → 验收/回滚”流程。
7. 工作完成后可停止本机持久会话：

   ```powershell
   pwsh.exe -NoLogo -NoProfile -File .\tools\stop_remote_22012_session.ps1
   ```

## 凭据和数据边界

本包刻意不包含：数据库账号说明、`.env`、密码、Cookie、Token、SSH 私钥、运行日志、数据库、生产数据、备份目录、模型和浏览器会话。服务配置只列出所需环境变量名称，不包含其值。

若接手者没有独立提供的认证材料或生产授权，应停留在本地阅读和只读检查阶段。

## 快照说明

本包按构建时的工作区内容生成，可能包含尚未提交的当前版本。`PACKAGE_MANIFEST.json` 记录 Git 分支、提交、脏工作区状态、每个文件的 SHA-256 和大小；应以该文件为快照证据。

项目规范中曾引用 `docs/V3本地运行依赖与启动手册.md`，但构建本包时仓库中未找到该文件，因此没有把它作为隐式依赖。现有入口以本说明和 `docs/cli_usage.md` 为准。

# 8093/8094 诊断功能 reliable_ssh 一键部署器

## 交付结果

统一入口为：

```powershell
python .\tools\deploy_diag_rules.py
```

默认命令只运行本地检查、47项合同测试和dry-run，不访问生产。确认输出正确后，才使用：

```powershell
python .\tools\deploy_diag_rules.py --apply
```

需要完整API复验时追加 `--verify full`。

## 发布内容

压缩包只包含9个白名单业务文件：共享代理中的诊断接口、4个诊断后端模块、2个评分/分析JavaScript和2个对应CSS。代理不直接以本机整文件覆盖生产；远端安装器以220.12当前 `ollama_proxy_server.py` 为基线，只合并诊断函数块、诊断路由和四个资产版本，因此保留已经升级的跨库MCP代码。

快速包不更新 `自动诊断服务/diagnosis_scheduler.py`、8768 WebSocket桥接或实际炉况计算规则。需要发布诊断计算公式时，必须走独立的8768受控发布流程。

## 可靠SSH与保护边界

- 传输复用本机 `reliable-ssh-mcp` 配置：固定 `administrator@10.30.220.12`、固定ed25519主机指纹、受控密码文件和审计日志。
- 一次发布只做一次身份校验、一次ZIP原子上传和一次远程PowerShell执行。
- 只允许重启 `BFV4PreviewProxy8093` 与计划任务 `V3AutoPreviewProxy8094`。
- 8768、8770、11434监听PID在发布前后必须不变。
- 所有目标修改前写入 `logs/deploy_backups/<deploymentId>`；安装或验证失败时恢复备份并恢复服务。
- 8093按既有守卫“停—改—启”执行；8094只操作自己的计划任务和经命令行、父子关系校验的监听进程。

## 本轮验证

- `node --check tools/reliable_ssh_22012_cli.mjs`：通过。
- 三个Python入口 `py_compile`：通过。
- `remote_deploy_diag_rules.ps1` PowerShell语法：通过。
- 诊断、复核和部署器合同：`47 passed`。
- `python tools\deploy_diag_rules.py`：dry-run通过，输出9个业务文件、目标8093/8094和保护端口8768/8770/11434。
- 本机 `reliable_ssh` 身份探测：成功；主机 `WIN-54B94HVHKBA`，地址包含 `10.30.220.12`，用户 `administrator`。
- 额外的MCP `exec_argv` 在固定30秒客户端等待窗口内超时；没有远端写入。部署CLI使用240秒远程命令窗口。

## 当前生产状态

本轮没有运行 `--apply`。220.12没有收到本部署包，8093/8094没有因本轮工作被重启或改写。真正发布后应保存CLI生成的 `logs/deploy_diag_rules/*.json` 报告，并以其中的备份目录、服务PID、HTTP标记和远端回执作为验收依据。

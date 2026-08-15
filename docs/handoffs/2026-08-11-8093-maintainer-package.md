# 2026-08-11 220.12:8093 维护交接包

## 需求

需求编号：`OPS-8093-MAINTAINER-HANDOFF-PACKAGE-20260811`

目标是把本机常见备份产物纳入 Git 忽略范围，并生成一个可重复构建、可校验、无凭据的 8093 维护交接包，使获得授权的维护人员能快速掌握 220.12 对应项目的连接、守卫、服务、部署和验收边界。

## 实现

- `.gitignore` 增加常见备份后缀、备份目录和 `/handoff_packages/`。
- `tools/handoff/8093_handoff_manifest.json` 使用明确白名单选择交接内容。
- `tools/build_8093_handoff_package.ps1` 在 PowerShell 7 UTF-8 环境中复制当前工作区文件，执行高置信敏感信息扫描，写入 Git 快照与逐文件 SHA-256，并验证 ZIP 中每个源文件的哈希。
- `tools/handoff/8093_HANDOFF_README.md` 给出接手顺序、受保护资源、凭据边界和远端操作前置条件。
- `tests/test_8093_handoff_package.py` 固化清单完整性和排除策略。

## 安全边界

交接包不包含 `docs/数据库账号配置说明.md`、`.env`、密码、Cookie、Token、私钥、日志、备份、数据库、生产数据、模型或已认证会话状态。服务器凭据和生产变更授权必须通过独立安全渠道提供。

构建交接包只操作本机文件；不会连接 220.12，不会获取部署互斥，不会暂停服务，也不会产生生产写入。

## 构建与验证

```powershell
pwsh.exe -NoLogo -NoProfile -File .\tools\build_8093_handoff_package.ps1
pwsh.exe -NoLogo -NoProfile -File .\tools\verify_pwsh7_utf8.ps1
pytest -q .\tests\test_8093_handoff_package.py
```

构建结果输出到被 Git 忽略的 `handoff_packages/`。ZIP 根目录包含 `HANDOFF_README.md` 与 `PACKAGE_MANIFEST.json`；后者记录源码清单哈希、Git 分支/提交/脏状态、排除说明、敏感扫描结果和每个源文件的 SHA-256。

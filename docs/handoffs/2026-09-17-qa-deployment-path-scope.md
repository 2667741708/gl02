# 8093 助手部署：按实际读写范围处理生产更新

状态：本机工具修复、独立审查和真实 Git 测试通过；本记录不代表已部署。最后核对：2026-09-17。权威来源：Reliable SSH 生产只读结果、V49-r6 密封前候选与本机测试。适用边界：8093 助手代码更新，不授权模型、数据库或计划任务修改。

## OPS-QA-DEPLOYMENT-PATH-SCOPE-20260917

用户明确要求读取生产 Git 更新日志，保留与助手无关的更新并继续提交部署。旧 `Assert-Baselines` 虽然核对目标和依赖摘要，仍要求全局 HEAD 完全一致，因而会错误阻止仅修改 CSS 的生产提交。

2026-09-17 13:20:44 UTC 的只读复核确认：

| 核对项 | 实际结果 |
|---|---|
| 已集成的共享代理基线 | `cdd390cc386ce486d8a4685ebe060b8eeda7c38a` |
| 当前生产 HEAD | `e3cca548033736f31500f703aa877a6b519a1977`，基线是其祖先 |
| 两者实际变更范围 | 仅 `高炉前端数据/assets/abc33-readable.css` |
| 与候选读写范围交集 | 0；60 个实际运行依赖摘要全部匹配 |
| 候选写范围 | 16 个文件，其中 6 个新文件；目标及依赖范围没有 staged、unstaged 或 untracked 改动 |
| 无关生产工作树改动 | 4 个，仅分类元数据，不读取服务配置内容，保留 |
| 本轮生产写入、问题 POST、模型推理 | 均为 0 |

最新提交说明是隐藏 ABC33 展示说明文字，与助手路由无关。此前 ABC33 共享代理更新已经由 V47 集成并由 V49 继承，不能用旧代理文件覆盖当前共享功能。

## 实施与可核对条件

| 条件 | 实现 | 成功信号 |
|---|---|---|
| 无关 HEAD 更新允许继续 | [audit](../../tools/audit_qa_release_baseline_readonly.py#L29) | `head_match=false` 时仍可 `path_scope_ok=true` |
| 当前分支与基线血缘正确 | 同一审计函数 | `production-8093`、基线祖先、没有 merge/rebase/cherry-pick/revert 进行状态 |
| 实际目标、依赖不冲突 | 同一审计函数 | 范围交集空、范围工作树干净、依赖摘要与候选摘要匹配 |
| 文件不能越过根目录 | [路径检查](../../tools/audit_qa_release_baseline_readonly.py#L12) | 拒绝反斜杠、盘符、绝对路径、`.`、`..`；解析后的仓库路径与候选 stage 路径仍位于各自根目录 |
| 检查期间版本不能变化 | 同一审计函数 | 最后复核 HEAD 和分支稳定 |
| 审计器必须是已审查字节 | [scope-gate](../../tools/prepare_qa_routing_v3_release.py#L264) | `baseline_auditor_sha256` 与上传审计器一致，纳入 release sources |
| 停服前和获取锁后再次检查 | [Assert-Baselines](../../tools/remote_guarded_deploy_qa_routing_v3_8093.ps1#L193) | 审计成功，返回 repo 和分支与固定生产目标一致 |
| 分阶段预暂存 | [stage](../../tools/stage_qa_release.py#L24) | preflight 阶段同时上传审计器；不在此阶段切换服务 |

旧 scope-gate 缺少审计器摘要时必须重新准备和审查，不自动接受未绑定的审计器。目标文件当前基线摘要、create 目标不存在、固定 allowlist、临时索引 Git 可记录性、互斥锁、备份、finally 恢复、回滚、HTTP、模型 readiness 和受保护 PID 验收仍然适用。

## 验证与限制

- [36 项真实 Git / PowerShell 测试](../../tests/test_qa_deployment_path_scope.py)：无关提交与无关 dirty 保留；相关提交、staged、unstaged、untracked、分支/血缘/合并状态、错误候选摘要、范围不一致及路径越界拒绝。3 项直接执行实际 `Assert-Baselines`，证明无关提交通过、审计器篡改和依赖漂移拒绝；4 项原有模型 readiness 测试包含立即、延迟、持续失败和异常。
- 生产工具 PowerShell 7 语法与安全标记校验通过；独立 `gpt-5.6-luna` 增量复审 PASS。
- 初次测试因系统默认 pytest 临时目录拒绝访问而没有执行；改用仓库内新的忽略目录。扩展路径测试中一处测试夹具放置错误已修正，最终 36 项全部通过。
- V49-r6 原有 905 项关联测试和 40 项生产 Python 3.11 原生合成合同结果保持原记录，不能折算为原始问题准确率。
- 最新 13:26:41 UTC 的 tags→ps→tags 检查中，生产 `latest` 标签与全部驻留记录均为禁止摘要 `9111…`，冻结摘要 `e4ad…` 虽存在于另一个标签，却不能据此自动更换标签或切换驻留。固定底座要求独立于 Git 范围检查；本修复没有放宽模型就绪要求，没有切换或恢复模型。
- 原始失败问题未重发；822 个失败/部分答复的全量复测仍待实际部署及冻结底座就绪。数据库知识原文发布和模型管理任务修改仍遵守各自授权边界。

可复现入口：新建唯一 pytest basetemp 后执行 `python -B -X utf8 -m pytest -q tests/test_qa_deployment_path_scope.py tests/test_qa_release_readiness.py --basetemp .codex_runtime/<unique-run>`；运行 `pwsh.exe -NoLogo -NoProfile -File tools/verify_qa_routing_release.ps1`。远端只读审计入口：`audit_qa_release_baseline_readonly.py --stage <reviewed-stage>`，只读取已有预暂存文件、生产 Git 与代码，不推理、不 POST、不写生产或真实索引。

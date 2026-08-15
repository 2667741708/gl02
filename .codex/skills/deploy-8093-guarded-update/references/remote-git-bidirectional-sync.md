# 220.12 Git 双向同步与验收后版本保存

对每次 220.12:8093 部署使用以下固定顺序。Git 用于发现和保存版本；生产切换仍必须走受控
部署器，不能用 `git pull`、`git checkout` 或 `git reset` 代替备份、原子安装和回滚。

## 1. 先做只读远端 Git 门禁

通过复用的 `remote_22012_session.py` 会话，在上传前分别执行短步骤并保存脱敏结果：

1. 验证生产根目录确实属于预期 Git worktree，记录 `rev-parse --show-toplevel`、当前分支、
   `HEAD` 和仓库对象格式；路径或身份不符立即停止。
2. 读取最近提交日志、装饰引用和相关文件历史；记录本地已知生产版本与远端 `HEAD` 的祖先关系。
3. 读取 `status --porcelain=v2`、tracked diff、staged diff 和相关 untracked 源文件清单。
   不读取或下载凭据、日志、数据库、备份、Cookie、Token、私钥和含秘密的服务配置。
4. 不运行 `git pull`、`reset`、`checkout --`、`clean`、rebase、commit、tag 或 push。

远端没有 Git 仓库、分支/HEAD 不可证明、存在合并进行中、工作树包含未知敏感文件或历史关系
不清楚时，状态为 `not_started`。不得为了完成流程而在生产目录静默初始化新仓库。

## 2. 审查远端新功能并同步到本地

把远端新增内容分为：有效功能、部署生成差异、敏感/运行时文件、未知差异。只处理经审查的
有效功能：

1. 优先导出提交 bundle 或格式化 patch；未提交功能只下载明确 allowlist 内的 diff 和文件，
   同时记录远端原始 SHA-256。禁止整棵生产目录覆盖本地。
2. 在独立的本地集成分支或 worktree 中导入；本地已有脏改动时不得 checkout/reset 覆盖。
3. 逐项审查行为、安全边界、schema、配置、测试和文档。远端更新时间较新不等于代码正确。
4. 将通过审查的远端功能与本地新增功能做三方合并；冲突必须按合同和测试解决，不能机械选择
   `ours` 或 `theirs`。
5. 运行受影响的编译、单元、合同和浏览器档位验证。失败则不形成 prepared release。

记录远端基线 HEAD、审查过的 commit/path、采用/拒绝原因、合并后本地 commit 或工作树证据、
文件 SHA-256 和验证结果。Git remote URL 只保留不含凭据的主机/仓库标识。

## 3. 将合并后的本地功能部署到 220.12

以合并后的本地树生成 sealed manifest 和 delta plan；只上传差异文件。使用部署 mutex、备份、
仅暂停 8093、原子替换、finally 恢复、失败回滚及受保护 PID 验收。Git 传输不能替代这个步骤。

若远端 Git/worktree 在门禁与临界区之间发生变化，baseline 校验必须失败并返回第 1 步重新审查；
不得继续覆盖。SSH 执行状态不确定时先检查实际状态，不自动重放。

## 4. 运行验收通过后才保存远端 Git version

仅当结构化结果已经证明 `rollback_applied=false`、8093 Running/HTTP/API/功能正常、安装哈希正确、
守卫恢复且受保护 PID 不变时，执行版本保存：

1. 再次记录 `HEAD` 和 status，确认除已接受 manifest 目标外没有并发漂移。
2. 使用 pathspec 逐个暂存 manifest 中实际部署的、允许进入 Git 的源文件。禁止 `git add .` 和
   `git add -A`；运行配置、密码、连接串、日志、备份和状态文件永不暂存。
3. 比较 staged path 集合、staged blob SHA-256 与已验收安装文件；运行 `git diff --cached --check`。
4. 提交信息包含 requirement ID、deployment ID、验收摘要和旧/新 8093 PID。不得 amend 或改写
   既有历史。
5. 创建唯一且不可复用的受控版本引用，例如
   `prod-8093/YYYYMMDD-HHMMSS-<requirement-short>`；已存在同名引用时停止，禁止强制覆盖。
6. 默认只保存在 220.12 本地 Git 仓库。任何 `external remote push`（例如 GitHub/GitLab）
   都需要用户另行明确授权。
7. 提交后重新验证 version reference 指向新 commit、commit blob 与安装哈希一致，并再次执行
   8093 HTTP/API 及受保护 PID 轻量检查。

若第 4 步失败而运行服务仍健康，保留已验收部署，报告 `deployed_version_record_failed`，给出未完成
的 Git 步骤和可安全重试的只读证据；不能谎报完整成功，也不能仅因 Git 元数据失败回滚健康程序。

## 5. 固定结构化证据

最终报告至少包含：

- `remote_git_baseline_head`、`remote_git_branch`、`remote_git_dirty_paths_reviewed`；
- `remote_features_merged`、`local_integration_evidence`；
- `prepared_manifest_sha256`、`installed_hashes`、运行验收及保护 PID；
- `production_git_commit`、`production_version_ref`、`production_git_staged_paths`；
- `post_version_hash_match`、`post_version_runtime_ok`；
- 总状态：`deployed`、`rolled_back`、`not_started` 或 `deployed_version_record_failed`。

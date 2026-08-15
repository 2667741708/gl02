# 文档与知识清理交接（2026-08-11）

追踪编号：`REQ-DOC-KNOWLEDGE-CLEANUP-20260811`

## 目标与范围

整理根 `AGENTS.md` 与用户所称 `PD` 目录文档。工作区未发现 `PD`，因此按内容匹配的
`PT` 目录实施。任务只修改本机文档与链接检查工具；未连接生产、未修改数据库、未上传文件、
未停止或重启服务。

## 主要结果

| 对象 | 整理前 | 整理后 | 变化 |
|---|---:|---:|---|
| 根 `AGENTS.md` | 206,461 字节 / 1,123 行 | 11,730 字节 / 190 行 | 收敛为长期规则与权威文档路由 |
| `PT/预测铁水Si含量/README.md` | 306 行 | 125 行 | 当前状态与 V1～V21 历史索引分离 |
| `PT` Markdown | 285 份 | 285 份 | 不删除冻结实验/资产证据，新增两级导航 |

根 `AGENTS.md` 移除了不适合作为长期规则的内联 CSS/JS、一次性 PID/哈希/备份目录、
账号和服务快照、Open WebUI 内容清单、最近会话、历史故障流水账及重复验收正文；稳定规则改为
链接到 `docs/` 当前合同与 `docs/handoffs/` 日期证据。

## 新增入口

- [根 README](../../README.md)
- [项目上手](../project_onboarding.md)
- [V3 本地运行依赖与启动手册](../V3本地运行依赖与启动手册.md)
- [文档链接规范](../link_policy.md)
- [PT 专项资料导航](../../PT/README.md)
- [时间序列评测导航](../../PT/时间序列预测评测/README.md)
- [Markdown 本地链接检查器](../../tools/check_markdown_links.py)

## 过时与重复知识处理

- 8 份 PT 根文档增加“当前 / 参考 / 历史快照 / 路线图”状态和当前权威入口。
- MCP 九阶段文档明确为路线图，未取得实现、测试和现网验收三方证据时不得宣称完成。
- `PT/高炉3D模型` 中修复 7 个错误相对路径或含空格/括号的 Markdown 链接；另将一个未随
  冻结包保留的截图目录链接改为事实说明。
- 全 PT 哈希扫描发现 6 组完全相同 Markdown，均位于冻结 3D 发布包或独立实验目录；这些是
  自包含复现快照，不作为普通重复知识删除。
- `PT/imes.md` 与 `docs/imes.md` 内容有交叉但职责不同：前者保留当前连接/交接，后者保留
  通用数据访问说明；已在 PT 导航中明确关系，不做有损合并。

## 后续代码债务状态

文档清理时发现的 `start_v3_full.ps1` Docker `15432` 默认分支已在后续独立任务中修复，
当前默认口径为本机原生 `127.0.0.1:18000/bf_trend`。实现与验收见
[start_v3_full 原生 PostgreSQL 同步交接](2026-08-11-start-v3-native-postgresql.md)。

## 验证

```powershell
& 'D:\ProgramData\anaconda3\python.exe' -m py_compile .\tools\check_markdown_links.py
& 'D:\ProgramData\anaconda3\python.exe' .\tools\check_markdown_links.py .\PT
& 'D:\ProgramData\anaconda3\python.exe' .\tools\check_markdown_links.py .\docs
git diff --check -- <本轮修改的已跟踪文档>
```

结果：

- 链接检查器编译通过。
- `PT`：`checked_files=285 missing_links=0`。
- `docs`（自动忽略第三方 `node_modules` README）：`checked_files=163 missing_links=0`。
- 10 份新/重写入口文档均只有一个 H1；本轮新增差异无空白错误。

## 版本控制说明

根和子目录 `AGENTS.md` 被当前 `.gitignore` 的 `AGENTS.md` 规则排除，因此这些协作规则是
本机有效文件，不会出现在普通 `git status` 中。本轮没有修改用户已有的 `.gitignore`；若后续
希望版本化 AGENTS，需要先单独评审其中的敏感信息边界和跟踪策略。

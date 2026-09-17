# 冀南钢铁高炉工艺大模型智能决策项目

本仓库集成高炉实时数据同步、炉况诊断、规则与建议、8093/8094 前端、IMES/Vastbase
只读数据、铁水 Si 预测、时间序列实验和三维炉体展示。生产相关能力默认只读；任何远端写入、
服务停启、数据库修改或计划任务修改都需要明确授权。

## 从这里开始

| 你要做什么 | 先读 |
|---|---|
| 了解系统边界与模块 | [项目上手](docs/project_onboarding.md) → [系统架构](docs/architecture.md) |
| 本机启动或检查依赖 | [V3 本地运行依赖与启动手册](docs/V3本地运行依赖与启动手册.md) |
| 查端口、服务、计划任务 | [自动化追踪](docs/automation_traceability.md) → [自动值守配置索引](docs/自动值守程序配置索引.yaml) |
| 修改需求、代码、接口或配置 | [AGENTS.md](AGENTS.md) → [需求追踪](docs/requirements_traceability.md) → [程序索引](docs/program_index.md) |
| 排查故障 | [排障手册](docs/troubleshooting.md) → [错误追踪](docs/error_traceability.md) |
| 查研究、预测、MCP、IMES、3D 资料 | [PT 文档导航](PT/README.md) |
| 查看近期实施证据 | [阶段交接目录](docs/handoffs/) |

## 主要目录

| 目录 | 职责 |
|---|---|
| `高炉前端数据/` | 8093/8094 页面、共享前端资产、助手后端与 MCP |
| `自动诊断服务/` | 炉况诊断、规则运行、审计与只读解释 |
| `炉况规则引擎/` | 炉况规则、特征和专项诊断 |
| `数据库同步和存取/` | pSpace/PostgreSQL 同步、看门狗与数据质量 |
| `db_dashboard/` | 炉次与数据库仪表盘服务 |
| `PT/` | 专项研究、实验报告、冻结资产和文档索引 |
| `tools/` | 本机验证、远端探测、构建与受控部署工具 |
| `tests/` | 单元、合同、部署脚本与浏览器回归测试 |
| `docs/` | 当前知识库、追踪索引、决策与阶段交接 |

## 安全提示

- 不要把生产密码、Cookie、Token、私钥或个人信息复制到普通文档、脚本、日志或截图。
- 根目录 [AGENTS.md](AGENTS.md) 是协作规则入口；子目录存在 `AGENTS.md` 时，以更近的规则补充根规则。
- `docs/handoffs/` 中带日期的记录是验收证据，不自动代表今天的运行状态；变更前仍需只读探测。

## 智能助手当前本机候选（2026-09-17）

生产仍V26；[V31答复合同修复](docs/handoffs/2026-09-17-qa-v31-renderer-contract.md)继承V27固定底座、V28统计证据、V29完成状态和V30质量窗口证据。126项相关回归及独立审查通过，未部署。唯一底座与权重摘要保持固定，不使用切换或备用模型；原822失败/部分题复测与准确率尚未验证。逐项状态见[执行账本](tests/qa_regression/optimization_execution_ledger_20260916.json)。

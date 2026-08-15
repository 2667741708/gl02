# 项目上手

> - 状态：当前入口文档
> - 最后核对：2026-08-11
> - 适用范围：新同事、自动化代理、跨模块改动前的快速定位

## 项目目标与边界

项目面向冀南钢铁高炉炼铁场景，将现场数据、MES/IMES 业务数据、炉况规则、模型解释、
铁水 Si 预测和三维页面组织为可追踪的只读决策辅助系统。系统可以读取、诊断、预测、解释、
导出和展示，但不得未经授权自动修改生产设定值。

## 核心链路

```text
pSpace / IMES / PostgreSQL
  → 数据同步与质量门禁
  → 炉况规则、ABC33、Si 与专项诊断
  → 8768/相关只读 API
  → 8093 生产预览、8094 隔离预览、专项页面
  → 人工复核、审计和导出
```

详细调用关系见 [系统架构](architecture.md)。端口、任务、运行目录和最近核查结果以
[自动值守程序配置索引](自动值守程序配置索引.yaml) 为准。

## 模块地图

| 模块 | 代码/资料入口 | 当前职责 | 修改前必读 |
|---|---|---|---|
| 前端与助手 | [高炉前端数据](../高炉前端数据/) | 8093/8094 页面、助手后端、MCP、三维交互 | [前端架构](architecture.md)、[8093 守卫](22012_8093_v4_guard_ops.md) |
| 自动诊断 | [自动诊断服务](../自动诊断服务/) | 诊断调度、规则审计、模型解释 | [程序索引](program_index.md)、[测试索引](test_reference.md) |
| 炉况规则 | [炉况规则引擎](../炉况规则引擎/) | 八炉况、ABC33、软熔带等规则与特征 | [需求追踪](requirements_traceability.md) |
| 数据同步 | [数据库同步和存取](../数据库同步和存取/) | pSpace 到 PostgreSQL、质量检查、看门狗 | [自动化追踪](automation_traceability.md)、[配置索引](自动值守程序配置索引.yaml) |
| 数据库仪表盘 | [db_dashboard](../db_dashboard/) | 炉次、质量、历史查询与只读服务 | [API](api_reference.md)、[数据结构](data_schema_reference.md) |
| Si 与时序研究 | [PT](../PT/) | 铁水 Si、19 项时序评测、实验产物 | [PT 导航](../PT/README.md) |
| 运维与验证 | [tools](../tools/) / [tests](../tests/) | 探测、构建、受控发布和回归 | [CLI](cli_usage.md)、[测试索引](test_reference.md) |

## 推荐阅读顺序

1. [README](../README.md) 与 [AGENTS](../AGENTS.md)。
2. 本文与 [系统架构](architecture.md)。
3. 按任务进入 [需求追踪](requirements_traceability.md) 或 [程序索引](program_index.md)。
4. 运行前读 [本地启动手册](V3本地运行依赖与启动手册.md)。
5. 修改配置/API/表结构时分别读 [配置](config_reference.md)、[API](api_reference.md)、
   [数据结构](data_schema_reference.md)。
6. 验证时读 [测试索引](test_reference.md)；故障时先读 [排障手册](troubleshooting.md)。

## 常见任务入口

| 任务 | 权威入口 | 关键约束 |
|---|---|---|
| 本机运行 | [本地启动手册](V3本地运行依赖与启动手册.md) | PowerShell 7、UTF-8、先 dry-run/探测 |
| 查数据库连接 | [数据库账号配置说明](数据库账号配置说明.md) | 仅授权文件可保存指定明文；实际服务必须现场确认 |
| 8093 更新 | [部署 skill](../.codex/skills/deploy-8093-guarded-update/SKILL.md) | 明确授权、守卫闭环、受保护服务不变 |
| IMES/Vastbase 查询 | [IMES 交接](../PT/imes.md) | 只读、白名单、有界查询、凭据不落普通文档 |
| 时间序列实验 | [评测入口](../PT/时间序列预测评测/README.md) | 公共切点、统一 19 项、不得自动切生产模型 |
| 铁水 Si 实验 | [Si 项目入口](../PT/预测铁水Si含量/README.md) | 当前仍为只读/离线或影子边界，以状态门为准 |

## 文档维护

- 稳定规则写入 `AGENTS.md` 或当前参考文档；实施证据写入 `docs/handoffs/`。
- 旧记录不直接冒充当前状态：标记为“历史快照”“参考”或“已取代”，并链接新入口。
- 从代码、配置、数据库、任务或日志核实的新事实，必须回写对应权威文档。
- 文档链接与行号格式见 [链接规范](link_policy.md)。

# 19 项时间序列预测评测导航

> - 状态：当前实验入口
> - 最后核对：2026-08-11
> - 生产边界：只读旁路评测；不得自动切换 8777/8778 或生产趋势页模型

## 先看当前结果

1. [统一评测标准](../时间序列预测统一评测标准.md)
2. [当前排行榜（Markdown）](results/timeseries_model_leaderboard_current.md)
3. [当前排行榜（CSV）](results/timeseries_model_leaderboard_current.csv)
4. [当前排行榜（JSON）](results/timeseries_model_leaderboard_current.json)
5. [2026-08-11 Chronos 与 Ridge 分时段融合实验](2026-08-11_Chronos与Ridge分时段融合实验报告.md)

`*_current.*` 是当前入口；带时间戳的 detail/summary/report 文件是不可改写的实验快照。

## 报告时间线

| 日期 | 报告 | 角色 |
|---|---|---|
| 2026-08-08 | [首轮多模型实验](2026-08-08首轮多模型实验报告.md) | 初始候选与共同切点评测 |
| 2026-08-08 / 08-11 补充 | [Ridge 同切点与 5 分钟聚合](2026-08-08_Ridge同切点与5分钟聚合评测报告.md) | Ridge 细化与实际/预测曲线 |
| 2026-08-11 | [Chronos 与 Ridge 分时段融合](2026-08-11_Chronos与Ridge分时段融合实验报告.md) | 当前分段融合实验 |

## 目录职责

| 路径 | 内容 | 清理规则 |
|---|---|---|
| `models/` | Ridge 等模型参数与配置 | 与报告/摘要成套保留 |
| `pretrained/` | 第三方预训练模型说明与配置 | 不把上游 README 当项目当前结论 |
| `results/` | 当前排行榜、时间戳结果、曲线和缓存 | `current` 为入口；时间戳文件为复现证据 |
| `results/chronos_segmented_cache/` | 固定切点的 Chronos 缓存 | 与分段实验绑定，不机械去重 |

## 统一口径

- 所有模型使用共同完整切点和同一 19 项目标。
- 排名保留点误差、概率、方向、振幅、分钟动态、覆盖率和分段指标，不只看单一 MAE。
- 分段误差按历史 IQR 归一化；WIS 同时输出 `iqr_nwis_80`。
- `std_ratio` 与 `diff_std_ratio` 按距离 1 的对称尺度判断。
- 排行榜是实验决策证据，不构成生产模型切换授权。

实现与生产边界见 [时间序列排行榜交接](../../docs/handoffs/2026-08-11-timeseries-leaderboard.md)。

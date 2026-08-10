# ABC33 C类严重事件交叉确认与逐点复核上线报告

## 结论

需求编号：`REQ-ABC33-C-EVENT-CROSS-CONFIRMATION-20260810`。

本次修复已经部署至 220.12 的 8768、8093 和 8094。C4“冷却系统超负荷”、C5“烧穿风险”、C7“炉壳热点”不再把同一批炉壳点的偏高、层内极差和上升斜率当成三份独立严重事件证据，也不再由单个冷却传感器把整个冷却系统风险直接确认到满分。

生产页面继续处于分数试运行状态，B/C自动告警未开放。原文公式初算分完整保留在受保护后台和数据库审计字段中；工长页面显示经过独立系统交叉确认后的操作研判分。

## 根因与修复

修复前的当前批次中：

- `CoolingRisk=1` 仅由高压水流量一个点偏低触发，其他五个冷却点对应风险均为0。
- `BodyHotRisk=1`、`BodyTempRange=1`、`slopeBodyMax=1`来自同一批炉壳测温点，C4/C5/C7把这些相关信号分别加权，形成75—100的机械饱和分。

修复后新增：

- `CoolingConcurrence`：取独立冷却证据中的第二高风险；只有一个冷却点异常时为0。
- `BodyHotConcurrence`：至少三个炉体点共同偏离的强度。
- `BodyHotEscalation`：同一点必须同时表现为偏高和继续上升。
- C4/C5/C7独立证据门禁：保留原文初算分，但生产操作分乘以跨系统确认门禁；门禁未形成时返回“未确认”或“部分确认”，不触发严重事件。

当前真实数据的门禁预演见 [abc_c_event_gate_preview.json](../../data/abc33_acceptance/abc_c_event_gate_preview.json)：原文初算分 C4=100、C5=89.4737、C7=100，经过交叉确认后均为0。

## 逐点复核详情

生产详情合同升级为 `furnace_rule_detail.v2`。C4/C5/C7详情固定返回：

- 第7—16层、A—H方位共80个炉壳温度点。
- 软水流量/压力、高压水流量/压力、中压水压力和膨胀罐液位共6个冷却点。
- 四点顶温、四点顶压、综合顶压、全炉/下部压差、透气性和两个铁口温度等配套参数。
- 每个点的当前值、时间戳、数据年龄、30日中位数/IQR/Q1/Q3、15/30/60分钟变化、15/30/60分钟波动、相对历史典型波动倍数和60分钟曲线点。
- 完整中文变化语义；缺数点保留并说明原因，不补0。

页面按“最重要复核点 → 全部炉壳温度 → 全部冷却点 → 其他配套参数”分层展示。公式、权重、精确阈值、内部特征名和贡献仍未进入普通生产接口或浏览器源码。

2026-08-10 06:17 的双端验收：

| 项目 | 8093 | 8094 |
|---|---:|---:|
| HTTP | 200 | 200 |
| 规则数 | 33 | 33 |
| 详情合同 | v2 | v2 |
| 详情变量 | 100 | 100 |
| 炉壳点 | 80 | 80 |
| 冷却点 | 6 | 6 |
| 缺数 | 0 | 0 |
| C4 | 0 / 未确认 | 0 / 未确认 |
| C5 | 0 / 未确认 | 0 / 未确认 |
| C7 | 5.0975 / 部分确认 | 5.0975 / 部分确认 |

最显著复核点为炉身第11层E点：当前330.40℃，30日中位数90.32℃，15/30/60分钟分别增加85.66/227.50/244.94℃，60分钟波动为历史典型波动的2.15倍。该异常已在页面明确展示，但因没有形成独立系统的完整交叉确认，没有直接升级为C类严重事件。

## 测试与回放

- ABC规则、公共因子、回放、桥接和生产UI合同：`122 passed`。
- JavaScript语法检查：通过。
- 三天回放：2026-08-07 06:00 至 2026-08-10 06:00，共865个五分钟批次，成功865，错误0。
- 回放未开放生产分数、未开放生产告警、未写数据库。
- 回放仍发现C4有23个、C7有24个跨系统候选批次达到70分；因此本次没有擅自开放红色弹窗，而是保留给人工复核和后续现场阈值批准。
- 回放证据：[abc33_three_day_c_gate_replay.json](../../data/abc33_acceptance/abc33_three_day_c_gate_replay.json)。

## 部署与运行状态

- 8768备份：`backups\abc33_c_event_gate_8768_20260810_060755`。
- 8093/8094页面与代理备份：`backups\abc33_c_event_detail_20260810_060929`。
- 8093守卫：已暂停并恢复，`BFV4PreviewProxy8093=Running`。
- 8768服务：`BFV4PreviewWs8768=Running`。
- 最终监听PID：8093=2044、8094=2988、8768=18168、8770=3732、11434=5968。
- 8094重启时8093、8768、8770、11434均未变化。
- 页面资源版本：`abc33-20260810-c-event-detail-r3`。
- 生产资源SHA-256：
  - `abc_feature_builder.py`: `409108B109911FEB2FD5F07FEB1FB3EEC97D0E3D66BC22D2AE1EBB9368EE79B3`
  - `abc_rule_engine.py`: `62A389C27DA3EA020265822EEB176636D33C8C0E54DEAB674AAA3F3B74DC8AF3`
  - `abc_public_review.py`: `978FC9156A6A2FD55B7D858D0612F36ACA629FC3F20FB60B3E68E11BD6FB2AE1`
  - `abc-furnace-rules-production.js`: `8632C985F6FC9EFEC0EB025808D18DAC9B196057A801501A4F1512512C232EB9`
  - `ollama_proxy_server.py`: `043C500C0A50469BACDA3A7D4FD9CA42291B34CFCFFB61CB055740B2A61A7BD4`

## 代码与运维入口

- 特征与交叉因子：[abc_feature_builder.py](../../自动诊断服务/abc_feature_builder.py)
- C类操作分门禁：[abc_rule_engine.py](../../自动诊断服务/abc_rule_engine.py)
- 逐点安全详情合同：[abc_public_review.py](../../自动诊断服务/abc_public_review.py)
- 8093/8094详情API：[ollama_proxy_server.py](../../高炉前端数据/智能助手/backend/ollama_proxy_server.py)
- 页面渲染：[abc-furnace-rules-production.js](../../高炉前端数据/assets/abc-furnace-rules-production.js)
- 8768部署：[remote_deploy_abc33_c_event_gate_8768.ps1](../../tools/remote_deploy_abc33_c_event_gate_8768.ps1)
- 8093守卫部署：[remote_guarded_deploy_abc33_c_event_detail_8093.ps1](../../tools/remote_guarded_deploy_abc33_c_event_detail_8093.ps1)
- 双端验收：[remote_verify_abc33_c_event_detail.ps1](../../tools/remote_verify_abc33_c_event_detail.ps1)


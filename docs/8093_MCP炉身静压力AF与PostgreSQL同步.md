# 8093 MCP 炉身静压力 A–F 与 PostgreSQL 同步

需求编号：`REQ-8093-MCP-STATIC-PRESSURE-AF-20260716`

## 数据源、唯一映射与计数边界

pSpace 正式根分支为 `\冀南二期\EQ\SI0\GL02\BT`。2026-07-16
元数据与实时值核查确认三个高度各有六个物理点；当前唯一数据身份继续使用
EQ/SI0 的 18 个 Tag，不自动切换到 SIO 分支另行检出的“检测1～6”候选。

项目中同时出现的三种计数表示不同对象，不能混写：

| 计数 | 对象 | 与本次 18 点的关系 |
|---:|---|---|
| 115 | GLB 已有核心传感器节点合同 | 保护既有模型节点；新增 A～F 静压力不通过复制原三个平均点伪造，也不改变 115 节点身份 |
| 133 | PostgreSQL 同步目录中的物理点 | 原 115 个同步物理点加本次 18 个 EQ/SI0 静压力物理点 |
| 134 | 当前数据集构建时读取到的启用注册点 | `bf_sensor.sensor_registry` 的启用记录数；其中可能有本时段无分钟值的注册点，因此不等同于 133 个同步物理点 |

18 点的语义 ID、业务层名、标高与 Tag 映射如下。`business_level_name`
使用现场 HMI/当前业务口径；`source_description_raw` 原样保留 pSpace 历史描述，
两者并存，不用显示名覆盖源取证文本。

| 语义组 | `business_level_name` | 标高 m | A～F 对应短名尾号 | `source_description_raw` 区域词 |
|---|---|---:|---|---|
| `P_static_lower_A`～`F` | 炉身下部 | 20.350 | `T0102,T0103,T0104,T0105,T0107,T0108` | 炉腰部 |
| `P_static_middle_A`～`F` | 炉身中部 | 23.488 | `T0068,T0069,T0070,T0071,T0072,T0110` | 炉身下部 |
| `P_static_upper_A`～`F` | 炉身上部 | 28.976 | `T0075,T0076,T0077,T0078,T0079,T0080` | 炉身中部 |

短名完整形式为 `EQ_SIO_GL02_BT_Txxxx`，长名为根分支加短名。A～F
只代表同一高度的相对顺序，当前固定 `orientation_status=relative_only`；现场
HMI 方位图、模型正面和厂区基准尚未完成受控对表，不能将 A～F 标成东南西北。

扩展目录暂存的 `PE242021/PE242022/PE242023 A-F` 与历史截图记录的
`PE424022A-F` 存在冲突，因此 PE 号状态固定为
`unconfirmed_conflicting_records`，不得作为数据库主键、Blender 节点稳定 ID
或现场绝对位置依据。目录配置单位为 `kPa`，但本次 pSpace 元数据的单位字段
为空，故单位状态固定为
`configured_kpa_source_metadata_blank_unconfirmed`；显示可以使用受控配置的
`kPa`，同时必须保留该确认状态。

原 `P_static_lower/middle/upper_mean` 三个平均代理继续保留，保证旧问题兼容，
但禁止把三个平均代理复制为 18 个实测点。完整逐点合同见
[静压力扩展目录](../高炉前端数据/智能助手/mcp/gl02_static_pressure_points.json)。

## 3D 位置与可见性合同（2026-07-21）

- Blender/Three.js 的三层局部高度为 `标高 - 20 m`，即
  `0.350 / 3.488 / 8.976 m`；点位中心位于受控炉壳半径外 `0.12 m`。
- A～F 在每层按 60° 等分，只固定相对顺序；模型中的零角只服务于一致显示，
  不代表厂区绝对零方位。
- 运行/测量审查使用独立的 18 点 `measured/raw` Overlay；纯材质审查必须隐藏
  传感器、数据引线、黄色轮廓和工艺粒子。正式 115 节点 GLB 不因该 Overlay 改写。
- `good/illustrative` 点统一使用工业黄色 `#F2C94C` 身份色且不按偏差值改色；
  `stale` 冻结最后有效值并使用明显变暗的黄色 `#8F7728`，`missing` 或超过硬过期阈值隐藏。
  界面显示实际 `N/18`，不能在缺点时仍写“18点实测”。
- 原始压力值不等于相对历史基线的压力偏差。没有 `deviation_kpa` 时仍显示黄色
  实测点，但不生成色带或箭头；同层 6 点全部有效且均有偏差值后，才允许输出
  `interpolated/periodic_interpolation` 色带和 `estimated` 偏流箭头。

运行实现与回归入口分别为
[bf3d-internal-simulation.js](../高炉前端数据/assets/bf3d-internal-simulation.js)和
[verify_bf3d_internal_simulation.cjs](../tools/verify_bf3d_internal_simulation.cjs)。
Blender 候选、18 点独立 Overlay GLB、机器报告和前后/分层证据位于
[VIS-30 受控目录](../PT/高炉3D模型/work/VIS_30_20260721_STATIC_PRESSURE_18_PLACEMENT)。

## MCP 与口语合同

- 单点/多点最新值、历史和统计统一调用 `query_gl02_sensors`。
- 趋势绘图统一调用 `plot_gl02_trends`；不同点可任意组合。
- “20.35米A到F六个点”“六个点”“各点/各方位”展开为对应高度 A–F。
- 指定“A、C、F点”只展开被点名的方位。
- 只说高度、不说方位时仍返回旧平均代理，避免改变既有语义。

实现位置：

- [MCP 扩展目录加载与统一查询](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py)
- [8093 A–F 口语路由](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)
- [pSpace 单点/批量 helper](../高炉前端数据/智能助手/mcp/gl02_pspace_direct_query.py)
- [路由与目录测试](../高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py)
- [绘图与扩展目录测试](../高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py)

## PostgreSQL 同步策略

18 点已加入正式 `点位清单.tsv`，与当前133个物理点使用完全相同的链路：

```text
pSpace raw 约5秒数据（同一次读取写raw短期表）
  → source_aggregate=average（每分钟有效Good样本算术平均）
  → target_aggregate=PS_RAW_AVERAGE / semantic_version=valid_raw_mean_v1
  → target_interval_seconds=60
  → bf_sensor.one_minute_values
  → ON CONFLICT(tag_long_name, ts) 幂等更新
```

同时维护：

- `bf_sensor.sensor_registry`
- `bf_sensor.raw_5s_values`
- `bf_sensor.one_minute_values`
- `bf_sensor.sync_state`

正式源目录为 [V4 点位清单](D:/文件/服务器实际运行版V4/数据库同步和存取/config/点位清单.tsv)。部署与验证入口为 [同步目录发布脚本](../tools/remote_deploy_22012_static_pressure_sync_catalog.ps1) 和 [数据库核验脚本](../tools/verify_22012_static_pressure_sync.py)。

## 2026-07-16 验收

- 本地联合回归：`40/40`。
- 同步目录：物理点 `133`，变量名和 tag 均 `133/133` 唯一。
- pSpace raw 同步：`133/133` 成功，错误 `0`。
- 分钟聚合：写入 `1518` 行，失败 chunk `0`。
- PostgreSQL：新增点 `registry_count=18`、`enabled_count=18`、最近数据点 `18/18`，最新时间 `2026-07-16 12:55:00`。
- 8093 最新值口语：成功返回 A–F 六点，其中 C 点为真实 `0.0`，已提示异常核查。
- 8093 绘图口语：成功生成 A/C/F 最近一小时曲线，PNG 为 `/data/mcp_charts/gl02_line_20260716_125944_6420b1bf.png`。
- 验收报告：[8093_static_pressure_af_acceptance_20260716.json](../logs/8093_static_pressure_af_acceptance_20260716.json)。

运行边界：只滚动重启 8093 问答代理；8768 和 PostgreSQL 均未重启。持续同步循环每轮重新读取点位目录，不需要为了新增点重启数据库。

# WEB-60 炉内仿真运行时说明

更新时间：2026-07-19  
需求编号：`REQ-BF3D-INTERNAL-RUNTIME-6X-20260719`  
状态：已进入本机 8092 页面源码；正式 GLB 未替换；8767 已生成并发布
`bf3d_snapshot.v1`，18 点静压力按真实点位透传，C2 根部低置信度估计已接入；
MES 上料/开堵口、经真值标定 C2 和 C3 仍未接入。

## 1. 交付结论

本轮在现有 `gl02_blast_furnace.glb`、115 点、L7～L16、分层筛选和内切面生命周期之上增加独立 Three.js 运行时场景层：

```text
正式 GLB（只读）
  └─ 既有局部剖切、相机、传感器与 L7～L16
       └─ BF3D_INTERNAL_SIMULATION_RUNTIME
            ├─ 料面、近表面实例颗粒与矿焦体层
            ├─ 参数化闭合软熔带和置信壳
            ├─ 26 风口回旋区 InstancedMesh 与喷煤 Points
            ├─ 18 点静压力标记、三条有界插值带和偏流箭头
            └─ 滴落 Points、铁水/炉渣独立液面和统一流束
```

运行时默认是“数据态”。只有当 8767 快照含合规且未硬过期的
`estimated.cohesive_zone` 时才显示 C2 软熔带；没有可靠输入的 18 点静压力、
滴落和炉缸液面仍隐藏。主料线零点、方向和量程门禁未确认，因此 `L`
不驱动几何，`L_south/L_north` 不驱动倾斜。用户可切换“教学演示”，查看
固定随机种子和明确标为 `illustrative` 的完整工艺演示。

## 2. 实现定位

| 能力 | 实现 |
|---|---|
| 页面加载 | [CSS 接入](../../../高炉前端数据/frontend_dashboard_v3.server.html#L8633)、[模块脚本](../../../高炉前端数据/frontend_dashboard_v3.server.html#L11317) |
| 料面、矿焦层与实例颗粒 | [createBurdenSystem](../../../高炉前端数据/assets/bf3d-internal-simulation.js#L324) |
| 软熔带闭合体积壳与置信带 | [createCohesiveSystem](../../../高炉前端数据/assets/bf3d-internal-simulation.js#L636) |
| 18 点静压力、有界插值与固定色标 | [createPressureSystem](../../../高炉前端数据/assets/bf3d-internal-simulation.js#L805) |
| 26 风口统一回旋区与喷煤 Points | [createTuyereSystem](../../../高炉前端数据/assets/bf3d-internal-simulation.js#L974) |
| 滴落、铁水、炉渣和出铁流束 | [createHearthSystem](../../../高炉前端数据/assets/bf3d-internal-simulation.js#L1138) |
| 数据态、教学场景、状态机与公开 API | [createController](../../../高炉前端数据/assets/bf3d-internal-simulation.js#L1445) |
| 门禁、阈值、色标和性能预算 | [运行配置](../../../高炉前端数据/config/bf3d_internal_simulation.v1.json#L1-L41) |
| 响应式状态面板 | [样式](../../../高炉前端数据/assets/bf3d-internal-simulation.css) |

## 3. 6.1～6.6 映射

### 3.1 料面、料柱与下降

- 料面使用 9 个径向环、桌面 64/移动端 36 个环向分段的低阶曲面，不使用固定圆柱顶面。
- 高度用弹簧—阻尼更新，速度限制在 `±0.12m/s`；陈旧状态冻结，硬失联或越界隐藏形变。
- 南北料线倾斜固定禁用，直到配置门禁明确启用。
- 近表面矿焦采用两个 `InstancedMesh`；内部使用 12 个循环复用的低面数体层。
- `BURDEN_CHARGE_COMPLETED` 只有同时满足矿/焦类型和 `mass_balance_valid=true` 才进入层池。
- 无布料矩阵时只使用中性径向分布；教学场景也不生成中心/边缘偏布。

### 3.2 软熔带

- 旧固定橙色环仍保留在正式 GLB 中作为历史资产，但运行时每帧强制隐藏。
- 新对象是带内外半径、厚度、中心高度、偏心和不确定区间的闭合参数化体积壳。
- 形状只接受 `flat/inverted_v/w/eccentric`，由输入明确选择；教学场景固定 `inverted_v`，不随机切换。
- `estimated` 显示半透明置信壳；`simulated` 保存场景版本；无输出时隐藏。
- 参数使用指数阻尼连续过渡，不在状态之间瞬切。

### 3.3 风口、回旋区、鼓风与喷煤

- 26 个风口以固定等角圆周位置创建一个 `InstancedMesh`；现场绝对方位未确认，不宣称东南西北。
- 当前只有总量时，26 个风口使用完全相同的强度、尺度和每风口 Points 数。
- 喷煤使用单个 `THREE.Points`，容量为 `26×12=312`；方向、速度、寿命相位和随机种子由一个控制器管理。
- 不生成随机单风口差异；后续单风口数据需新增独立且可审计的输入合同。

### 3.4 煤气场与压力

- 18 点合同为三高度×A～F；真实快照中的点标为 `measured`。
- 教学快照中的 18 点明确标为 `illustrative`，不能冒充实测。
- 三条色带使用六方位周期有界插值，固定显示相对基线 `−12～+12kPa`，不按每帧极值重拉。
- 偏流箭头明确命名为“压力偏流指示（非煤气真实流线）”；没有生成 C3 流线。

### 3.5 滴落带、铁水与炉渣

- 液滴是单个 `THREE.Points`，只有 `estimated/simulated` 输入时显示。
- 铁水和炉渣为独立液面、材质、透明度、深度写入策略和渲染顺序。
- 铁口由 `TAP_OPENED/TAP_CLOSED` 或快照状态驱动。
- 未接瞬时流量时，流束半径固定，不用粗细伪装流量。
- 当前实现不读取化验成分改变液池颜色。

## 4. 输入合同与公开 API

运行时接受两类浏览器事件：

```javascript
window.dispatchEvent(new CustomEvent("bf3d:snapshot", { detail: snapshot }));
window.dispatchEvent(new CustomEvent("bf3d:event", { detail: event }));
```

也可通过 `window.__BF3D_INTERNAL_SIMULATION__` 调用：

| API | 作用 |
|---|---|
| `setMode("live" \| "illustrative")` | 切换数据态/教学态 |
| `injectSnapshot(snapshot)` | 注入 `bf3d_snapshot.v1` |
| `dispatchEvent(event)` | 注入 `bf3d_event.v1` |
| `play()/pause()/reset()` | 播放控制 |
| `getState()` | 获取对象、证据、资源和真实性边界状态 |
| `makeIllustrativeSnapshot()` | 生成确定性教学 fixture |

现有 8767 会在 `init/tick` 中生成 `bf3d_snapshot.v1`，并由页面统一缓存、
发布 `bf3d:snapshot`。快照会透传实际存在的 18 点静压力、80 个炉体温度点
和鼓风参数；缺点保持 `null`，不得把原有三个高度平均静压力复制成 18 个
实测点。MES 上料、开堵铁口和 C3 仍需后续 `bf3d_event`/统一快照适配。

### 4.1 C2 根部估计运行合同

8767 使用 [C2 估计器](../../../炉况规则引擎/features/cohesive_zone_estimator.py)
输出以下字段：

```text
centerHeight / thickness
eccentricity / eccentricAngle
movement.direction / velocity_m_per_h
movement.forecast_height_m / forecast_horizon_minutes
sector_roots[A..H]
confidence / input_coverage / uncertainty
model_version / sample_time / quality
```

Three.js 状态行显示“上移/下移/稳定、根部标高、厚度和置信度”，并暴露
`data-cohesive-*` 验收属性。数据从新鲜变为陈旧时保留上一估计并标记
`stale`；超过硬失效阈值后隐藏；收到更新快照后自动恢复。运行时优先读取
`window.__BF3D_LATEST_SNAPSHOT__`，因此组件重挂载不会退回固定教学值。

强制真实性标记：

```text
evidence=estimated
calibration_status=uncalibrated
control_use=prohibited
confidence<=0.45
absolute_azimuth_status=unconfirmed
```

页面必须明确显示“未标定估计/禁止控制”。这一版是炉墙侧热活动根部代理，
不是炉内真实 1000℃ 边界或完整软熔带形状真值。

运行时不只信任 8767：浏览器还会独立检查 `status/evidence`、几何范围、
运动与外推字段、采样时间、`confidence<=0.45`、`uncalibrated`、
`control_use=prohibited`、根部定义和相对方位元数据。合同无效时显示
“C2 输出合同无效，几何已隐藏”，并暴露
`data-cohesive-contract-state/issues` 供自动验收。

## 5. 配置边界

新鲜度阈值当前状态为 `candidate_runtime_thresholds_pending_source_freeze`。它们已实现 `good → stale → no-data`，但在生产发布前仍需按数据源冻结：

- `sensor_warn_after_ms=180000`
- `sensor_hard_expire_after_ms=600000`

主料线门禁默认：

```text
enabled=false
zero_datum_m=null
positive_direction=null
valid_range_m=null
south_north_tilt_enabled=false
```

这些空值是主动安全边界，不是待前端猜测的缺省值。

## 6. 验证

```powershell
node --check .\tools\verify_bf3d_internal_simulation.cjs
node --check .\tools\verify_bf3d_c2_cross_engine.cjs
node .\tools\verify_gl02_cutaway_runtime.cjs
node .\tools\verify_bf3d_internal_simulation.cjs
node .\tools\verify_bf3d_c2_cross_engine.cjs
node .\tools\verify_bf3d_internal_simulation_matrix.cjs
```

结果：

- 旧内切面回归通过，115 点、L7～L16 每层八点、相机复位、路由卸载和资源复用保持；
- 专项合同通过：18 压力点、3 插值带、26 风口、312 喷煤点容量、96 滴落点、12 体层池；
- 无效质量平衡事件拒绝，有效事件生成新层；
- C2 后端估计器/桥接 `34 passed`；前端拒绝
  `confidence=0.9/control_use=allowed` 越权快照并隐藏几何；
- C2 专项 Chromium、Firefox、WebKit 各四个代表视口，共 `12/12`；
- 50 次数据态/教学态切换后资源数量不增长；
- Chromium 9 个固定视口、Firefox 4 个、WebKit 4 个，每个覆盖 5 个业务页面，共 85 个页面组合；
- 静态验收未启动 8767/问答 API，报告只忽略明确的离线连接拒绝与 API 404；其余页面、控制台和资源错误为 0。

报告：

- [专项合同报告](../../../logs/bf3d_internal_simulation_20260719/runtime_contract_report.json)
- [C2 三引擎专项报告](../../../logs/bf3d_c2_cross_engine_20260719/report.json)
- [跨引擎/视口报告](../../../logs/bf3d_internal_simulation_20260719/matrix/cross_engine_viewport_report.json)
- [桌面教学剖面](../../../logs/bf3d_internal_simulation_20260719/chromium_1440x900_illustrative_cutaway.png)
- [手机教学剖面](../../../logs/bf3d_internal_simulation_20260719/matrix/chromium_390x844.png)

## 7. 未解除的发布门禁

- 正式 GLB 未替换，P50/P60/P70 批准状态不变。
- 本轮没有在浏览器中求解 CFD/DEM；没有“煤气真实流线”。
- 18 点生产快照与 C2 根部基线已经进入 8767/Three.js 合同，但本轮因现场
  数据连接不可用，只完成确定性数据与缺数降级验收，未声称当前在线值通过。
- MES 上料/开堵铁口、经真值标定的 C2 和 C3 输出尚未接入。
- `L/L_south/L_north` 现场对表尚未完成。
- 新鲜度阈值仍需按源冻结。
- 静态跨浏览器验收不等于现场 Edge、生产数据库、8767 和模型链路验收。

## 8. R2N 炉顶布料、颗粒 FX 与聚焦视图增量

### 8.1 阶段状态

R2N 是 WEB-60 的 `running_candidate`，证据等级为 `E/illustrative`。它把 R2M Blender 候选的视觉语言转译为浏览器实时代理，但不改变正式资产与生产数据门：

- 正式 `gl02_blast_furnace.glb` 未替换，SHA-256 仍为
  `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`；
- `live_motion_gate.enabled=false`；
- P50/P60/P70 状态不变；
- 十阶段当前为 5 完成、2 部分、3 未正式开始，总项目未完成。

### 8.2 新增场景对象

```text
BF3D_ILL_BURDEN_DELIVERY_FX
├─ BF3D_ILL_CHUTE_AZIMUTH_PIVOT
│  └─ BF3D_ILL_CHUTE_TILT_PIVOT
│     ├─ chute floor / left wall / right wall
│     └─ emitter
├─ BF3D_ILL_FALLING_ORE_INSTANCES
├─ BF3D_ILL_FALLING_COKE_INSTANCES
├─ BF3D_ILL_COKE_PORE_DARK_DETAILS
└─ BF3D_ILL_IMPACT_DUST_POINTS

BF3D_ILL_COHESIVE_RESPONSE_WHAT_IF
```

- 矿石和焦炭各有 180 个固定容量槽位，高/中/低档只改变活跃上限，不重建几何或材质。
- 焦炭暗孔使用独立低成本实例，只跟随可见焦炭粒子；它是孔隙读感代理，不是孔隙率测量。
- 扬尘池容量 180；撞击产生短时扩散和衰减，不表示粉尘浓度。
- 12 个料层槽位循环复用；超过容量时回收最旧槽位并重新排布，不让资源随批次增长。
- 所有新对象复用当前控制器和单一 RAF，没有另起动画循环。

实现定位：

| 能力 | 位置 |
|---|---|
| 布料 FX、溜槽层级和固定粒子池 | [createBurdenDeliveryFx（第 403 行起）](../../../高炉前端数据/assets/bf3d-internal-simulation.js) |
| START/COMPLETE、料层池和解析接触 | [createBurdenSystem（第 1152 行起）](../../../高炉前端数据/assets/bf3d-internal-simulation.js) |
| 事件门、幂等、聚焦、控制器和销毁 | [事件门第 2627 行、聚焦第 2706 行、销毁第 3194 行](../../../高炉前端数据/assets/bf3d-internal-simulation.js) |
| 容量、教学周期和 live 门禁 | [burden_fx（第 36 行起）](../../../高炉前端数据/config/bf3d_internal_simulation.v1.json) |
| 聚焦和响应式面板 | [R2N styles（第 146 行起）](../../../高炉前端数据/assets/bf3d-internal-simulation.css) |

以上行号按本阶段冻结版本记录；后续代码变更时由符号扫描同步刷新。

### 8.3 解析运动与事件语义

R2N 的运动是有界解析代理：

1. `BURDEN_CHARGE_STARTED` 通过事件门后设置方位、俯仰、矿/焦类型和运动时间线；
2. 颗粒在溜槽出口按固定种子错时生成，使用重力积分；
3. 与当前料面接触后记录撞击并产生有限扬尘；
4. 颗粒只进行有界径向摩擦滚落，超出寿命或边界后返回池；
5. `BURDEN_CHARGE_COMPLETED` 通过门禁后才把一个矿/焦层沉积到 12 层池。

这套算法不是 DEM，没有粒子—粒子全碰撞、真实粒径分布、真实恢复系数或真实堆密度。事件门至少验证：

- `schema_version === "bf3d_event.v1"`；
- `furnace_id === "GL02"`；
- 事件 ID 和事件时间有效；
- 事件证据与当前 `live/illustrative` 模式一致；
- 类型为 `BURDEN_CHARGE_STARTED` 或 `BURDEN_CHARGE_COMPLETED`；
- 矿/焦类型有效，质量平衡有效；
- 生产态还必须通过真实运动源门禁；
- 256 个事件 ID 的幂等窗口内拒绝重复事件。

### 8.4 软熔 what-if

`BF3D_ILL_COHESIVE_RESPONSE_WHAT_IF` 与运行时已有 C2/C3 软熔带对象分离：

- 默认关闭、生产态不可启用；
- 只有教学态可以通过“软熔响应”按钮或
  `setCohesiveWhatIf(true)` 显式打开；
- 撞击只触发轻微视觉响应，不建立上料到软熔带的因果模型；
- 状态固定返回 `evidence=illustrative`、`causal=false` 和
  `productionDefaultHidden=true`。

### 8.5 布料聚焦

“布料聚焦”调用 `setChargingFocus(true)`，临时保存并调整相机/OrbitControls 目标，同时隐藏与炉顶布料无关的传感器、压力/风口/炉缸覆盖和页面控制遮挡。退出聚焦或销毁控制器时恢复进入前状态。聚焦只改变观看方式，不缩放炉体、不移动 115 个传感器，也不改变 L7～L16 分层合同。

公开 API 增量：

| API | 作用 |
|---|---|
| `setChargingFocus(enabled)` | 进入/退出炉顶布料聚焦 |
| `setCohesiveWhatIf(enabled)` | 仅教学态启用/关闭非因果软熔响应 |
| `triggerIllustrativeCohesiveResponse()` | 仅教学态触发一次视觉响应 |
| `getState().eventGate` | 查看校验、应用、拒绝、重复和幂等窗口计数 |
| `getState().stock.delivery` | 查看溜槽、粒子、撞击、滚落、扬尘和质量档 |

### 8.6 性能、销毁与降级

- 初始质量参考设备内存、核心数和 DPR；五秒采样后若帧率不足，只向下逐级降档。
- 低档以约 30fps 更新模拟；高/中/低只改变活跃上限和步进，不改变固定池容量。
- 后台标签页暂停逐帧更新；`prefers-reduced-motion` 保留静态溜槽和状态，不持续发射颗粒。
- `dispose()` 取消 RAF、移除事件/可见性监听、面板和根组，释放几何/材质，并删除 Viewer/Window API。
- 同一已连接 Viewer 在显式销毁后可以重新挂载；再次挂载仍只有一个面板和一个运行时根组。

### 8.7 验证和证据

```powershell
node --check .\高炉前端数据\assets\bf3d-internal-simulation.js
node --check .\tools\verify_bf3d_internal_simulation.cjs
node .\tools\verify_gl02_cutaway_runtime.cjs
node .\tools\verify_bf3d_internal_simulation.cjs
node .\tools\verify_bf3d_internal_simulation_matrix.cjs
```

专项验证覆盖：默认生产门、START/COMPLETE 分离、有效/无效/重复/错炉号事件、矿焦发射、撞击、滚落积分、暗孔、扬尘、12 层轮换、软熔 what-if、暂停冻结、聚焦、50 次模式切换、dispose/remount 和控制台/页面错误。

阶段证据：

- [阶段成果总结](../work/WEB_60_20260719_R2N_BURDEN_CHARGING_RUNTIME/WEB-60_R2N_阶段成果总结.md)
- [专项合同报告](../work/WEB_60_20260719_R2N_BURDEN_CHARGING_RUNTIME/reports/r2n_runtime_contract_report.json)
- [跨引擎/视口报告](../work/WEB_60_20260719_R2N_BURDEN_CHARGING_RUNTIME/reports/r2n_cross_engine_viewport_report.json)
- [布料聚焦图](../work/WEB_60_20260719_R2N_BURDEN_CHARGING_RUNTIME/renders/R2N_BURDEN_CHARGING_CLOSEUP.png)
- [仪表盘全景图](../work/WEB_60_20260719_R2N_BURDEN_CHARGING_RUNTIME/renders/R2N_BURDEN_CHARGING_DASHBOARD.png)

机器合同和浏览器矩阵通过只证明 R2N 候选范围内可运行；最终 WEB-60 仍需真实 8767/MES 输入、现场 Edge、PMREM/LOD/KTX2 全链、长稳性能、独立视觉/代码/规范复核和 QA-70。

## 9. R2O 受控结构资产与审查模式

R2O 将 R5 Web 表面、R2J 五区实体和 R2K 墙体内部层合并为一个版本化 Web GLB。页面使用新资产，但历史正式 `gl02_blast_furnace.glb` 不覆盖，保留为明确回滚点。

### 9.1 受控资产

- 输出：`高炉前端数据/models/gl02_blast_furnace_structural_review.v1.glb`
- SHA-256：`859819f415feee0533018daf3290c65c69b607352d8e8e34735e952d8f3772fd`
- 大小：11,003,464 bytes
- 合同：257 节点、53 网格、51 材质、115 个传感器、五个 R5 区、五个 R2J 实体；
- R2K：背衬、铜冷却壁、铸铁冷却壁、热面嵌入、残余耐火层和 missing 结瘤层；
- 560 块冷却壁按材料族合并为两个 Web 网格；
- 旧 INT10/INT20 说明卡、引导线、重复静压力标记和调试 primitive 不进入资产。

受控输入和回滚 SHA 记录在 [资产清单](../../../高炉前端数据/models/gl02_blast_furnace_structural_review.v1.manifest.json)。构建入口为 [导出器](../../../tools/export_bf3d_structural_review_glb.py)，输入哈希漂移、五区数量不符或正式回滚文件被改变时失败关闭。

### 9.2 模式

运行视图的审查入口并入原有分层控制区：

- `运行视图`：恢复 115 点和既有业务交互，R2J/R2K 结构对象默认隐藏；
- `纯材质审查`：只显示五个 R5 炉壳，使用烘焙 BaseColor/Normal/ORM 与 R2H RNM 细节法线，隐藏测点、拾取体、数据卡、引线、黄色剖切轮廓和全部工艺运行时；
- `结构剖面`：隐藏外部 R5 和工艺对象，显示 R2J/R2K，使用局部裁剪与炉腰近景读取薄层；missing 结瘤层不显示。

公开状态入口：

```javascript
window.__BF3D_STRUCTURAL_REVIEW__.setMode("material");
window.__BF3D_STRUCTURAL_REVIEW__.setMode("structural");
window.__BF3D_STRUCTURAL_REVIEW__.setMode("operational");
window.__BF3D_STRUCTURAL_REVIEW__.getState();
```

`getState()` 返回资产 ID/URL、五区数量、11 个逻辑结构对象、27 个多材质渲染 primitive、可见数量、测点/拾取体数量、覆盖层隔离状态和 R2H 细节法线状态。

### 9.3 与旧内切面的关系

旧 GLB 中 45 个固定圆环、蓝线和工艺装饰对象保留在基底中供历史取证，但不再由旧内切面显示。内切面只负责炉壳裁剪、相机和附件遮挡；料面、矿焦层、软熔带、风口喷煤、静压力和炉缸动画统一由 `BF3D_INTERNAL_SIMULATION_RUNTIME` 管理，避免两套语义重叠。

### 9.4 验证

```powershell
node .\tools\verify_bf3d_structural_review.cjs
node .\tools\verify_bf3d_structural_review.cjs --matrix
node .\tools\verify_gl02_cutaway_runtime.cjs
node .\tools\verify_bf3d_internal_simulation_matrix.cjs
```

- 专项隔离与 30 次往返：通过；
- 审查模式 Chromium 九视口、Firefox/WebKit 各四代表视口：17/17；
- 总览、诊断、参数优化、趋势、问答五页：85/85；
- 断言包括无横向溢出、入口可点击、面板不互相遮挡、控制台/页面错误为零。

结果见 [R2O 阶段成果总结](../work/WEB_60_20260719_R2O_STRUCTURAL_REVIEW/WEB-60_R2O_阶段成果总结.md)。R2J/R2K 厚度和侵蚀状态继续标为 `E/illustrative`、`not_for_construction=true`，不能据此进行施工、检修或生产测厚判断。

## 10. R2V V5 隔离材质/结构审查入口

R2V 另提供 [V5 隔离审查页](../../../高炉前端数据/bf3d_review_v5.server.html)和
[只读服务器](../../../tools/serve_bf3d_review_v5.py)。它只加载 SHA 锁定的
`gl02_blast_furnace_review.v5.glb`，提供“纯材质审查/外表面”“纯材质审查/内部层
近景”和“结构剖面”。它不接生产 8092、8767、实时数据或工艺控制器。

V5 资产层已经物理排除传感器、数据引线、黄色轮廓、工艺粒子、旧固定圆环与装饰性
竖向流线；因此 Blender 导入和 Three.js 都不依赖运行时隐藏这些对象。全炉横向明暗带
是 R2J 五区交界；内部可见带不是数据线，但 R2V 的“相邻物理层边界/遮挡缝”只是
初步解释，已由第 11 节 R2W 完整相邻链审计修正。

```powershell
python tools\serve_bf3d_review_v5.py --check-only
python tools\serve_bf3d_review_v5.py
```

完整矩阵为 Chromium/Firefox/WebKit 两轮 `34/34` viewport runs、`102` captures，
五类错误 `0`。该入口只批准 `E/illustrative` 静态审查；三资产解码内存、现场 Edge、
P50/P60/P70/QA-70、生产接入和数值光度等价继续待办。详见
[R2V 根审查](../work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/WEB-60_R2V_根审查结论.md)。

## 11. R2W 相机可读性入口与失败关闭边界

R2W 提供 [相机专用隔离页](../../../高炉前端数据/bf3d_review_r2w.server.html)和
[只读服务器](../../../tools/serve_bf3d_review_r2w.py)。该页仍只加载锁定的 V5
统一审查 GLB，不接生产 8092、8767、实时数据或炉内工艺控制器。

四个审查模式为：

1. 外表面全景：核对完整五区炉壳与总体框景；
2. 外表面材质近景：阅读既有细颗粒、粗糙度和法线响应；
3. 内部层近景：区分现有内部材质族；
4. 结构剖面：查看 10 个闭合 Section，但不据此批准真实层厚。

```powershell
python tools\serve_bf3d_review_r2w.py --check-only
python tools\serve_bf3d_review_r2w.py
```

服务器默认监听 `127.0.0.1:8125`。完整矩阵为三引擎双轮 `34/34` runs、
`136` captures，五类错误 `0`；PBR 运行时改写、禁止对象、黄色轮廓和受保护文件变化
均为 `0`。

### 11.1 为什么近景更清楚但表面仍可能偏平

R2W 只改相机，没有“更换成另一套材质”。当前 4K ORM.R 全部为 `255`，V5 glTF
没有 `occlusionTexture`，Blend ORM.R 也没有接入，因此 AO 并不存在或未被消费。
外表面近景可读只说明已有 BaseColor/Normal/roughness 更容易观察，不能写成 AO 或
P50 通过。旧 P50 R3 图集与当前 R2J UV/对象不兼容，禁止直接套用。

### 11.2 内部可见带的正确解释

L03 铜壁为 `z=-20…7.55 m`，L04 热面层为 `z=16…20 m`，共同高度和覆盖率为
`0`；L03→L04→L05 真相邻链在铜壁高度内不可测。运行页和用户说明统一显示：

`内部层边界 REF-PENDING，非数据竖线`

L03→L05 的 `14.816–49.456 mm` 仅为非相邻诊断；`z=-1.2 m` 异常是冷却壁
拼缝/端面与固定剖面的交点。不得用 AO、灯光、材质加深、polygon offset 或装饰条
遮盖该结构证据缺口。

### 11.3 批准边界

R2W 只条件批准隔离页的相机可读性。AO、相邻层连续性、施工厚度、P50/P60/P70/
QA-70、正式 GLB、生产 8092、现场性能/长稳和数值光度等价均未批准。详见
[R2W 阶段总结](../work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_阶段成果总结.md)
和[R2W 根审查](../work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_根审查结论.md)。

## 12. R2X 当前 R2J 独立 AO 1K 代表审查

R2X 对应需求
`REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720`。它没有覆盖 V5，而是从
锁定的 V5 纯材质 GLB 派生一个 1K、`E/illustrative`、`not P50`、`not production`
候选，专门验证“当前 R2J 五壳能否建立独立 UV2、写入 glTF AO，并被 Three.js
实际消费”。需求与边界见
[阶段预注册合同](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_阶段预注册合同.md)。

### 12.1 需求、程序、配置与产物

| 追踪类型 | 受控入口 | 当前结果 |
|---|---|---|
| Blender 1K 构建 | [build_bf3d_r2x_r2j_ao_candidate.py:L2243](../../../tools/build_bf3d_r2x_r2j_ao_candidate.py#L2243) | 五个 R2J 炉壳 UV2、1K AO、重开和事务恢复机器门通过 |
| V5 payload 外科式重打包 | [repack_bf3d_r2x_ao_v5_payload.py:L2202](../../../tools/repack_bf3d_r2x_ao_v5_payload.py#L2202) | 只增加五个 `TEXCOORD_2`、一个 AO image/texture 和两材质 `occlusionTexture`；复用 V5 sampler 0 |
| 独立只读审计 | [audit_bf3d_r2x_ao_candidate.py:L3787](../../../tools/audit_bf3d_r2x_ao_candidate.py#L3787) | 最终 v5payload 独审 `PASS`，Khronos `0 errors / 0 warnings` |
| Three.js 消费 | [候选校验:L265-L383](../../../高炉前端数据/assets/bf3d-review-renderer-r2x.js#L265-L383)、[AO 开关:L723](../../../高炉前端数据/assets/bf3d-review-renderer-r2x.js#L723) | 5/5 `aoMap.channel=2`、uv2 finite；BaseColor/Normal/Roughness/Metalness 仍为 channel 0；off/on 只改 `aoMapIntensity 0→1` |
| 代表验证 | [verify_bf3d_review_r2x_preview.cjs:L990](../../../tools/verify_bf3d_review_r2x_preview.cjs#L990) | Chromium `1440×900`，全景/近景各 off/on，共四图、两 pair；五类错误为 0 |
| 决策封存 | [finalize_bf3d_r2x_stage.py:L2128](../../../tools/finalize_bf3d_r2x_stage.py#L2128) | 根状态 `r2x_machine_passed_three_visual_failed_closed` |

最终候选为
[gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/glb/gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb)，
大小 `1,115,216` bytes，SHA-256
`bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00`。
正式 V5 Blend/三份 V5 GLB、formal GLB 与生产页面均保持原 SHA。

### 12.2 首次 sampler 失败必须保留

[最终独立审计](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_ao_smoke1k_v5payload_audit.json)
保留第一次候选
`c8b748ef03b516a78de658a3b25a5f2265fef9bd34cea334a3490fba1fbab139`
的 `UNAUTHORIZED_EXTRA_AO_CLAMP_SAMPLER`：它越权增加第二个 clamp sampler，故被
`fail_closed`。最终候选改为复用 V5 sampler 0；不得删除或改写该失败历史。

### 12.3 为什么 AO 已接通但用户仍看不到变化

[Three 代表报告](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/bf3d_review_r2x_representative_report.json)
证明运行链机器门通过且 `runtime_failed=false`，但全景与炉腰近景两组 off/on 均为
`changed_pixels=0`，每组 PNG SHA 也完全相同。独立视觉结论因此是
`fail_closed_ao_visual_signal_absent`，而不是视觉通过。

[独立视觉复核](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_independent_visual_review.json)
进一步证明 AO PNG 中 `99.6763%` 像素为纯白，非白仅 `0.3237%`，全图平均衰减仅
`0.0122%`。这说明“glTF/Three 已消费 AO”和“画面出现可见接触层次”是两道不同的门。
R2X 没有修复用户“看不到具体材质”的问题，也不能把现有横向明暗带解释成新增 AO
或数据圆环。

后续应保持 1K 失败关闭，优先回到当前 R2J 的可见几何接触源、UV2 与非白 texel
命中诊断、材质检视照明和确定性近景；若要表达真实内部结构，必须先取得权威炉墙层栈/
断面参考。禁止通过增加黑色圆环、装饰竖线、整体压暗或修改 BaseColor 掩盖无可见 AO
信号。

### 12.4 停止线

R2X 没有运行完整跨引擎/视口矩阵，因为代表视觉门已经失败；继续跑矩阵不会把零差异
变成有效 AO。`ao_2k_approved=false`、`p50_approved=false`、
`p60_approved=false`、`production_integration_allowed=false`、
`next_release_stage_allowed=false`。权威结论见
[阶段总结](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_阶段成果总结.md)
和[根审查](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_根审查结论.md)。

## 13. R2Y 材质信号可见性诊断（非 beauty / production）

阶段 `WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC` 把纹理存在、可见
片元命中、shader 消费和最终 8-bit 可见拆成独立门。R2Y 只加载锁定 V5 纯材质 GLB
做 PBR fixture；V5、R2X、formal 与生产资产均未修改。

### 13.1 运行结论

- CPU UV/AO hit：`PASS_DIAGNOSTIC`，排除当前固定相机下的
  `uv_or_camera_miss`；
- AO WebGL synthetic-black / float / final 8-bit liveness：
  `NOT_EXECUTED`，不得写成 PASS 或 FAIL；
- PBR 代表 fixture：`FAIL_CLOSED`；
- 独立视觉：`FAIL_CLOSED`；
- 完整矩阵：`NOT_EXECUTED`。

PBR 失败项为 macro `0.962958 < 1`、anisotropy `1.021708 < 1.03`、
environment A/B 最终差异 `0`。三个 PBR 通道只证明数据、采样与绑定存在，未独立
证明 shader 消费；运行报告固定 `consumed=null`、`visible=false`。

### 13.2 可见线条解释

R2J 五区交界属于受控结构边界；当前 beauty/掠射/宏距中重复出现的竖向波纹、Normal
网格和 Roughness 竖波是 `runtime_adapter_approximation` 的周期平铺伪影，不能作为
炉壳板缝、焊缝或炉墙层栈。未发现新增黑环、黄色轮廓、传感器、数据引线或工艺粒子。

### 13.3 停止线

状态为 `r2y_cpu_hit_passed_pbr_visual_failed_ao_webgl_pending_fail_closed`。
`beauty_approved=false`、`full_matrix_allowed=false`、
`ao_2k_approved=false`、`p50_approved=false`、`p60_approved=false`、
`production_integration_allowed=false`。见
[阶段总结](../work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/WEB-60_R2Y_阶段成果总结.md)
与[根审查](../work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/WEB-60_R2Y_根审查结论.md)。

## 14. 2026-07-24 原始 GLB × 程序化外观隔离候选

新增 `REQ-BF3D-GLB-IMG2THREEJS-BRIDGE-R1-20260724`，验证“正式 GLB
保留结构/设备/115 点，Three.js 运行时接管程序化钢灰与炉况视觉映射，
18 点静压力独立覆盖，V5 五区 PBR 壳体桌面按需加载”的混合架构。

关键取证：

- 正式 `gl02_blast_furnace.glb` 为 190 节点、115 点、80 个炉体测温点，
  L7～L16 每层八点，无贴图，适合作为语义底座；
- 当前 `structural_review.v1` 含四条本机绝对路径，并有五个绑定法线贴图但
  缺显式切线的 primitive，不再作为继续叠加修补的首选底座；
- V5 五区外观壳体结构审计通过，但 4K 纹理解码含 mip 约 256 MiB，
  本候选只允许显式按需加载；
- 原始坐标中正 Z 对应 `L_north`，因此北出铁口绑定 `T_taphole_2`，
  南出铁口绑定 `T_taphole_1`。

隔离页已通过 Chromium 九个固定视口、Firefox 四个、WebKit 四个，共
`17/17`；V5 五网格延迟加载另在 Chromium 1440×900 通过。正式 GLB、
8092 路由、8767 合同和数据库均未修改。

实现、审计、R2 优化路线与回滚边界见
[追踪文档](../work/WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1/REQ-BF3D-GLB-IMG2THREEJS-BRIDGE-R1-20260724_追踪.md)。

## 15. 2026-07-24 GLB 与程序化原型同源外观 R2

`REQ-BF3D-GLB-APPEARANCE-PARITY-R2-20260724` 将程序化原型与 GLB 页的
材质、PBR 贴图、ACES、曝光、雾、地面和灯组收敛到同一份
[外观合同](../web/img2threejs-appearance-contract.js)。正式 GLB 五区壳体在
运行时生成圆柱 UV，再使用原型同一组 normal/roughness 贴图；同时从正式点位
位置重建十个 L7～L16 身份环和三个静压力身份环。

本阶段的“一致”是 renderer/material/PBR/lighting 参数同源，不是把两套不同
几何伪称为逐像素相同，也不意味着静态 GLB 能保存浏览器 ACES、Fog 或实时炉况。
正确交付单位是“GLB 几何 + 共享 Three.js 外观合同”。

程序化页与 GLB 页分别通过 Chromium 9、Firefox 4、WebKit 4，共两套
`17/17`；正式 GLB、8092、8767 和数据库仍未修改。完整证据和边界见
[R2 追踪章节](../work/WEB_60_GLB_IMG2THREEJS_BRIDGE_20260724_R1/REQ-BF3D-GLB-IMG2THREEJS-BRIDGE-R1-20260724_追踪.md#8-r2-同源外观合同2026-07-24)。

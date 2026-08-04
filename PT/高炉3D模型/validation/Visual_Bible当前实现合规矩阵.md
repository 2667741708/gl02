# Visual Bible 当前实现合规矩阵

> 稳定编号：`VB-QA-001`  
> 矩阵版本：v1.0  
> 审计快照：2026-07-19  
> 审计范围：Blender P40/P50、P60 隔离预检、R2Q V3、R2R 渲染器数值门、正式 GLB、Three.js 页面、数据合同和现有自动验收  
> 目标规范：[工业级高炉数字孪生视觉规范（Visual Bible）](../工业级高炉数字孪生视觉规范（Visual Bible）.md)  
> 机器可读镜像：[visual_bible_conformance_v1.json](visual_bible_conformance_v1.json)

## 1. 结论

本矩阵只描述“当前实现是否符合”，不把目标规范、候选资产、机器检查通过或隔离预览自动升级为生产批准。

| 状态 | 数量 | 含义 |
|---|---:|---|
| `compliant` | 13 | 当前证据和验证足以证明本条范围内符合 |
| `partial` | 17 | 已有一部分实现或证据，但尚未满足完整发布合同 |
| `noncompliant` | 9 | 当前实现缺失或与规范目标不符 |
| `blocked` | 6 | 依赖外部确认、批准、工具或受控替换，当前不能完成 |
| `not_applicable` | 0 | 经记录确认不适用于当前项目范围；本次没有此类条目 |
| **合计** | **45** | 不等于 45 项全部实现 |

当前最重要的停止线：

1. P40 固定 LookDev 已经人工 `approve`，但不代表 P50/P60 获批；
2. P50 的 4K 纹理仍为 `KEEP_P50_PENDING_NOT_APPROVED`；
3. P60 只通过内部隔离预检，状态仍为 `not_granted_preflight_only`；
4. 正式 GLB 尚未替换，仍使用原 SHA-256；
5. 正式页面已有 sRGB 输出和 ACES Tone Mapping，但没有 PMREM/HDR 环境链，也没有 KTX2/Draco/Meshopt Loader 接线；
6. L7～L16 和内切面交互已通过既有浏览器矩阵，但 18 点静压力、MES/化验和七类时间尚未形成统一实时 3D 数据包。

## 2. 状态判定规则

| 状态 | 使用条件 |
|---|---|
| `compliant` | 有资产/程序证据、有对应验证，且批准边界与声明一致 |
| `partial` | 有候选或局部功能，但正式资产、完整参数、数据语义或验收尚缺 |
| `noncompliant` | 规范要求明确，当前代码/资产中没有实现或存在反向实现 |
| `blocked` | 依赖现场对表、责任人批准、Validator、生产替换或其他外部门禁 |
| `not_applicable` | 经记录确认该条款不适用于当前项目范围；必须说明原因，不能用来回避缺失实现 |

禁止把 `candidate_ready_for_visual_review`、`internal_preflight_passed`、机器断言通过、浏览器隔离预览通过写成 `approved`。

## 3. 治理与追踪

| ID | 要求/目标 | 当前证据 | 状态 | 下一步 | 验证 |
|---|---|---|---|---|---|
| `VB-GOV-001` | Visual Bible、附件和实现证据使用受控版本与稳定编号 | Visual Bible v1.1 已建立附件索引；本矩阵和[数据附件](../docs/GL02数据映射附件.md)已建立稳定 ID | `partial` | 给附件指定维护人、审批人和变更记录；接入文档链接检查 | 审查版本、负责人、变更记录和链接完整性 |
| `VB-GOV-002` | 候选、预检和正式批准严格区分 | [P50 决定](../work/P50_MASTER_4K_20260717_R1/p50_master_4k_visual_review.json#L1-L55)与[P60 approval](../work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_report.json#L1-L8)明确未批准；正式 GLB 未覆盖 | `compliant` | 保持停止线；只有签字后更新状态 | 比较报告状态、正式 GLB 哈希和发布记录 |
| `VB-GOV-003` | 所有资产、HDRI、纹理和参考图具有来源、许可和哈希 | P50 纹理和 GLB 有 SHA；候选 HDRI `industrial_sunset_2k.hdr` 已按 Poly Haven CC0、作者和 SHA-256 `2a411097…2b990` 登记于[第三方声明](../THIRD_PARTY_NOTICES.md#L22-L24)，但其视觉批准及其余参考项的来源闭环仍未全部完成 | `partial` | 完成其余 `source/licence/captured_at/sha256` 台账，并对 HDRI 做 Blender/Web 同机位视觉批准 | 对外部资产执行清单审计，并复算 HDRI SHA-256 |
| `VB-GOV-004` | 条款→资产→代码→测试→批准可双向追踪 | 本矩阵已建立第一版映射，但尚无 CI 自动校验和反向程序索引 | `partial` | 增加链接/哈希/状态 schema 检查，变更时自动刷新 | JSON Schema + Markdown 链接检查 + CI |

## 4. 材质、纹理与 Shader

| ID | 要求/目标 | 当前证据 | 状态 | 下一步 | 验证 |
|---|---|---|---|---|---|
| `VB-MAT-001` | 金属度/粗糙度 PBR，BaseColor/Normal/ORM 色彩空间和通道正确 | [P50 纹理清单](../work/P50_MASTER_4K_20260717_R1/p50_texture_manifest.json#L15-L91)包含 4K BaseColor、NormalGL、ORM；但只属于待批准候选 | `partial` | 完成人工材质审查、P60 Validator 和正式交付批准 | 通道统计、glTF Validator、Blender/Web 同机位对照 |
| `VB-MAT-002` | 正式页面炉壳为不透明哑光钢，保留已有贴图 | 页面把无图材质设为 `metalness=.38/roughness=.76`，保持不透明，并保留 GLB 贴图引用：[运行材质合同](../../../高炉前端数据/frontend_dashboard_v3.server.html#L11081-L11103) | `compliant` | 后续正式 PBR 资产替换时维持贴图保留测试 | `verify_gl02_layered_model_ui.py` 材质合同 |
| `VB-MAT-003` | 宏观/中尺度/微尺度表面同时存在且尺度可解释 | 用户已选择 R1 粗糙读感；[SURF-20 R5 总结](../work/SURF_20_20260718_R5/SURF-20_R5_阶段成果总结.md)锁定 `B=0.16 / D=0.10m / N=0.45 / metallic=0.06 / roughness=0.56–0.82`，R2D 四层三视角证明合流候选与源 R5 像素等价；正式 GLB/Web 尚未交付该材质 | `partial` | 保持 `VB-DEC-MAT-001` 不变，将 R5 受控烘焙/导出到隔离 GLB，并验证浏览器近中远距离读感 | 固定 LookDev R5 对照 + 0.5m/3m/8m/20m/40m Web 镜头 + 参数/节点/GLB 哈希 |
| `VB-MAT-004` | AO 只表达局部接触，不压黑大面，并在正式 Web 消费 | P50/P60 候选含局部 AO；正式运行报告显示 `bakedAoMapCount=0`，只有候选 P60 为 1 | `noncompliant` | P50/P60 获批后受控交付 AO，并验证指定 `texCoord`、Three `aoMap.channel` 与 `aoMapIntensity`；当前 R2J 独立 AO 预注册为 `TEXCOORD_2/uv2` | 正式与候选运行报告 + AO on/off 对比 |
| `VB-MAT-005` | Structural Normal 与 Detail Normal 使用 RNM/等价方式合成，按像素覆盖衰减 | 当前 Three.js 页面没有自定义 Detail Normal 合成或距离衰减 Shader；正式材质仅有 bump fallback | `noncompliant` | 实现受质量档控制的 RNM/normal blending 和 mip/specular AA | 旋转 shimmer、远景摩尔纹和近景颗粒矩阵 |
| `VB-MAT-006` | 浏览器交付优先 KTX2/BasisU，并保留失败回退 | 当前页面未接 `KTX2Loader`，P60 仍为 32.7MB 未压缩隔离 GLB | `noncompliant` | 生成 KTX2、接 Loader/Transcoder、验证格式支持和 PNG 回退 | Chromium/Firefox/WebKit 网络与显存报告 |
| `VB-MAT-007` | 钢壳、焊缝、平台、管道、铜/铸铁冷却壁、耐材、炉料和熔体使用独立材质族 | P40/P50 已区分部分设备材质，炉内 45 对象有 9 个材质克隆；完整受控材质卡与正式资产覆盖仍不足 | `partial` | 按材质卡逐族绑定资产 ID、PBR 参数和 LOD | 材质槽审计、对象卡和固定特写 |

## 5. 灯光、色彩和相机

| ID | 要求/目标 | 当前证据 | 状态 | 下一步 | 验证 |
|---|---|---|---|---|---|
| `VB-LIGHT-001` | Blender 有固定中性/展示 LookDev 与七个固定机位 | [P40 视觉审查](../work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/p40_visual_review.json#L1-L35)为 `approve`，18 张渲染和七机位完整 | `compliant` | 保持 P40 哈希和相机 JSON，后续变更重新评审 | 重跑 P40 固定机位，图像与哈希对照 |
| `VB-LIGHT-002` | Blender 与 Web 色彩链被唯一预设锁定并可比较 | Blender 使用 AgX；Web 设置 sRGB 输出、ACESFilm 和 1.05 曝光，但另有未接线配置仍写 1.28，跨端容差未冻结 | `partial` | 用唯一机器预设生成 Blender/Web 参数，删除漂移源 | 灰卡/材质球/同机位 ΔE 和亮度统计 |
| `VB-LIGHT-003` | 粗糙金属使用 HDRI + PMREM 预过滤环境光 | CC0 候选 HDRI 已入库并锁定 SHA-256，但尚未通过 GL02 视觉批准；当前页面也未创建 `PMREMGenerator`、未设置 `scene.environment` | `noncompliant` | 先完成候选 HDRI 的 Blender/Web 同机位批准，再锁定旋转/强度、接 PMREM 并提供低档回退 | 哈希复算、env on/off、粗糙度阶梯球、同机位对比和显存检查 |
| `VB-LIGHT-004` | 主光、轮廓光、剖切补光服务结构和数据阅读 | 页面有半球光、主/轮廓方向光、暖主光及剖切暖/冷点光：[Viewer 基础灯光](../../../高炉前端数据/frontend_dashboard_v3.server.html#L8655)和[剖切补光](../../../高炉前端数据/frontend_dashboard_v3.server.html#L11162-L11165) | `partial` | 统一由 LookDev 预设驱动，补灯光单位、色温和曝光容差 | 中性/展示/剖切三模式 Golden View |
| `VB-LIGHT-005` | 地面接触、阴影和 AO 不漂浮、不双重压黑 | 当前正式 Viewer 使用网格地面，无受控接触阴影/实时阴影链；独立配置文件中的 shadow/floor 尚未在当前 Viewer 消费 | `noncompliant` | 实现低成本接触阴影或已验证阴影方案，并与 AO 联调 | 脚底/支柱/平台接触图和 GPU 时间 |

## 6. 炉内对象和工艺表达

| ID | 要求/目标 | 当前证据 | 状态 | 下一步 | 验证 |
|---|---|---|---|---|---|
| `VB-INT-001` | 内部对象有稳定语义分类，外观模式默认隐藏 | 兼容 GLB 的旧 45 个 burden/softening/flow 装饰对象可识别但在外观和内切面均始终隐藏；权威 `BF3D_INTERNAL_SIMULATION_RUNTIME` 按料面、矿焦层、软熔带、风口/回旋区、压力、炉缸分类：[运行时专项](../../../logs/bf3d_internal_simulation_20260719/runtime_contract_report.json) | `compliant` | 新增对象继续走权威运行时并保持旧对象零可见合同 | `verify_gl02_cutaway_runtime.cjs` + internal simulation suite |
| `VB-INT-002` | 内切面可打开、分阶段显现、暂停、复位且资源复用 | Viewer 的裁剪/复位与权威 simulation 控制器已委托打通；旧 45 对象不再分阶段显现，权威仿真根在内切面显示；Firefox/WebKit [8/8 通过](../../../logs/bf3d_cutaway_cross_engine_20260717/report.md#L1-L17) | `compliant` | 保持交互回归；接真实事件后增加 seek/断线/重连测试 | cutaway runtime、internal simulation 与 cross-engine 脚本 |
| `VB-INT-003` | 剖切面显示真实壳体/耐材/冷却结构厚度并可靠封口 | 隔离 R2Q V3 已有 10 个 `1.0×` 物理半剖对象和独立切面封口，覆盖五段钢壳、背衬、铜/铸铁冷却、热面和耐火层；正式运行 Viewer 仍使用裁剪平面而未消费这些实体：[R2Q 剖面验证](../work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reports/section_scale_cap_validation.json) | `partial` | 完成数值 A/B、现场 Edge 和发布门后再决定是否接入正式 Viewer；实测厚度仍须现场资料 | 多角度剖切、封口、背面/穿帮、深度和资产哈希 |
| `VB-INT-004` | 料面、压力、上料、软熔带、炉缸和化验由统一时钟与证据驱动 | 权威运行时已实现统一时钟、事件/快照门和 6.1～6.6 的降级边界；C2 当前只接低置信未校准的软熔带根部趋势，压力偏流、完整料层下降、炉缸库存和化验滞后仍未完成 | `partial` | 进入 INT-40 真值/回测输入门；缺独立参考时保持 `uncalibrated/control_use=prohibited` | 数据 fixture、知识时间、pause/seek/重连、历史回测 |
| `VB-INT-005` | 内部结构覆盖死料柱、炉衬、冷却壁、保护渣皮及真实剖切层级 | R2Q V3 已独立建模五段钢壳、背衬、铜/铸铁冷却壁、热面和残余耐火层；死料柱和可证保护渣皮/结瘤层仍缺，现有厚度为 `E/illustrative`、非施工尺寸 | `partial` | 取得工程资料后补 deadman/skull 证据对象并复核厚度；不得由视觉猜测补齐 | 对象树、物理剖面、来源标签和独立规格审查 |
| `VB-INT-006` | 示意对象不得伪装实时物理场 | 控制栏固定显示“工艺示意，非实时断面测量”，默认外观隐藏蓝线/圆环 | `compliant` | 接入数据后仍保持逐对象 evidence 标签 | UI 文案与 `userData.evidence` 自动测试 |

## 7. 数据、时间和质量

| ID | 要求/目标 | 当前证据 | 状态 | 下一步 | 验证 |
|---|---|---|---|---|---|
| `VB-DATA-101` | 正式模型保持 115 个稳定 `SENSOR_<id>` 节点 | [正式 Manifest](../../../高炉前端数据/models/gl02_blast_furnace.manifest.json#L12-L36)记录 115；正式/候选运行脚本均检查 115 | `compliant` | 任何资产替换都执行节点名和世界矩阵 diff | `verify_gl02_layered_model_ui.py` + GLB manifest diff |
| `VB-DATA-102` | L7～L16 共 80 点，每层 A～H 八点，层高正确 | 页面十层和层高已实现：[layerHeights](../../../高炉前端数据/frontend_dashboard_v3.server.html#L11030-L11040)；Chromium [9/9](../../../logs/bf3d_layer_matrix_20260717/report.md#L1-L17)、Firefox/WebKit [8/8](../../../logs/bf3d_layer_cross_engine_20260717/report.md#L1-L16) | `compliant` | 接统一质量包后补 stale/bad/missing 每层测试 | 既有 layer UI 和跨引擎脚本 |
| `VB-DATA-103` | 18 个静压力点作为三高度×A～F 实测 Overlay，并与原 3 点区分 | [18 点映射 JSON](../../../高炉前端数据/智能助手/mcp/gl02_static_pressure_points.json#L1-L30)完整，当前 Three.js 尚未创建 18 点 Overlay | `partial` | 接 `P_static_lower/middle/upper_A-F`，完成 A～F 方位门禁和插值标签 | 18/18 fixture、点位截图、M/E schema 检查 |
| `VB-DATA-104` | 每个值保留七类时间、evidence/derivation/quality | [GL02 数据附件](../docs/GL02数据映射附件.md#3-统一语义包)已定义；当前页面缓冲和炉内对象未携带完整包 | `noncompliant` | 后端统一生成 `bf3d_snapshot.v1/bf3d_event.v1` | JSON Schema、回放知识时间和迟到数据测试 |
| `VB-DATA-105` | 料线零点、方向、南北尺语义和绝对方位已确认 | 主料线可访问，但 `L_south/L_north` 描述冲突，零点/方向尚未签字 | `blocked` | 完成 HMI/点表/趋势对表并冻结唯一配置 | 固定样本、正负方向和现场截图签字 |
| `VB-DATA-106` | 上料、炉次、开堵口和生产实绩形成可重放事件流 | 只读数据和字段存在，当前未合并为持续 `bf3d_event`；炉次—料批关联仍缺 | `partial` | 建事件适配器，核实 `workdate/workdate2/remark3` 和关联键 | 真实脱敏 fixture + 单炉次 seek 重建 |
| `VB-DATA-107` | 铁水/炉渣化验按炉次和发布时间挂接 | 来源存在，但铁水炉次关联尚未贯通；禁止最近时间猜测 | `blocked` | 建受控 ETL/关联键，保留 sample/judged/published time | 当时已知/事后分析双模式测试 |
| `VB-DATA-108` | 缺失、陈旧、异常、人工和检修状态不被显示为正常 | 当前层高亮有正常/关注/严重/无数据，但尚未覆盖全部来源和按源失联阈值 | `partial` | 冻结每源 `warn_after/hard_expire_after`，统一状态机 | stale/bad/missing fixture 和恢复测试 |

## 8. GLB、Three.js 和资源生命周期

| ID | 要求/目标 | 当前证据 | 状态 | 下一步 | 验证 |
|---|---|---|---|---|---|
| `VB-RUNTIME-001` | 使用受控 Three.js/GLTFLoader，并记录版本 | 本地 Three.js 为 [r160](../../../高炉前端数据/libs/three/three.module.js#L6)，页面显式加载 `three/OrbitControls/GLTFLoader` | `compliant` | 升级前做 GLB/Shader/浏览器完整回归 | 版本探针与加载冒烟 |
| `VB-RUNTIME-002` | GLTF 导入保留 PBR 通道并有无图回退 | 页面保留 map/roughness/metalness/AO/normal 引用并只给缺图材质 fallback；P60 隔离报告证明完整 PBR 通道可被消费 | `partial` | 正式资产获批替换后再次验证，不以隔离候选代替正式结果 | formal/P60 runtime 报告对照 |
| `VB-RUNTIME-003` | Draco/Meshopt/KTX2 加载、能力探测和回退完整 | 当前 Viewer 只创建 `GLTFLoader`，未配置 `DRACOLoader/KTX2Loader/MeshoptDecoder` | `noncompliant` | 接解码器、Basis transcoder 和超时/回退 | 三引擎加载、压缩比、失败注入 |
| `VB-RUNTIME-004` | 高/中/低性能分级覆盖完整场景预算 | 页面已有 DPR、环带段数、脉冲频率和低 FPS 降级；尚未覆盖纹理、粒子、LOD、体积和全场景 GPU 预算 | `partial` | 统一质量控制器，记录 P95 帧时、显存、TTI 和降级原因 | 三档 10s/30min 性能测试 |
| `VB-RUNTIME-005` | 反复切换和路由卸载不泄漏几何、材质、纹理和 RAF | 环带双槽复用、几何缓存、dispose 和 cutaway 复位已实现并被现有脚本检查 | `compliant` | 扩展到新 Overlay、粒子和 PMREM 资源 | 100 次切换 + 路由往返 + renderer.info |
| `VB-RUNTIME-006` | 只有批准后的 GLB 才能受控替换正式资产 | [P60 Manifest](../work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_manifest.json#L1-L35)证明正式 SHA 未变；P50/P60 尚未批准 | `blocked` | 完成 P50 审批、Validator、P60/P70 门禁和回滚包 | 哈希、签字、生产/回滚双清单 |

## 9. 验收和发布

| ID | 要求/目标 | 当前证据 | 状态 | 下一步 | 验证 |
|---|---|---|---|---|---|
| `VB-QA-101` | 固定 LookDev 的中性/展示机位完成审查 | [P40 人工决定](../work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/p40_visual_review.json#L1-L35)为 `approve` | `compliant` | 将相机和灯光参数纳入机器预设/Golden View | 重渲染 18 张并比对 |
| `VB-QA-102` | P50 材质烘焙通过人工批准 | [P50 决定](../work/P50_MASTER_4K_20260717_R1/p50_master_4k_visual_review.json#L1-L55)仍为 `KEEP_P50_PENDING_NOT_APPROVED` | `blocked` | 补近景、多角度、旋转 shimmer 和人工签字 | P50 材质评审清单 |
| `VB-QA-103` | P60 GLB 交付获得正式批准 | [P60 报告](../work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_report.json#L1-L8)仅 `not_granted_preflight_only` | `blocked` | P50 先获批，再完成压缩、Validator、Web handoff 和签字 | P60/P70 发布门禁 |
| `VB-QA-104` | Khronos glTF Validator 无错误/警告门禁 | [Validator 状态](../work/P60_PREFLIGHT_4K_20260717_R1/gltf_validator_status.json#L1-L38)为 `unavailable` | `blocked` | 安装/固定 Validator 版本并输出完整报告 | Validator CLI/Node 报告和版本 |
| `VB-QA-105` | 十层与响应式浏览器矩阵通过 | Chromium 9/9、Firefox/WebKit 8/8，115 点和十层合同通过 | `compliant` | 数据状态接入后在同矩阵重跑 | layer matrix/cross-engine 报告 |
| `VB-QA-106` | 内切面跨引擎代表视口通过 | [Firefox/WebKit 8/8](../../../logs/bf3d_cutaway_cross_engine_20260717/report.md#L1-L17)，旧 45 对象始终零可见、权威 simulation 根显现、暂停、复位和错误检查通过 | `compliant` | 正式接入 R2Q 实体剖面或新数据源后重跑 | cutaway runtime/internal simulation/cross-engine |
| `VB-QA-107` | Golden View 固定相机、视口、数据快照、随机种子、HDR 和基准图 | R2R 已冻结相机/视口/seed/shot/阈值并形成 Blender diff；R2S 已实现双门控只读 Three.js 正交 shot、P40 四灯与阈值合同，但色彩/光度仍 `pending_preapproval`、`captureEligible=false`，Blender 仍为 `68/80 pass`，尚无批准的 Web Golden 基准图 | `partial` | 先批准色彩和光度合同，再实现独立一次性捕获、按原阈值复跑 Blender/Three 并建立批准/更新流程 | R2R 图像 diff + R2S 双门控数值合同 + 参数/哈希一致性 |
| `VB-QA-108` | 全场景满足 TTI、P95 帧时、显存、Draw Call 和长期运行预算 | 现有验证覆盖交互资源复用，尚无完整高/中/低三档 10s 与 30min 报告 | `noncompliant` | 建标准设备档、采样脚本和失败阈值 | TTI、renderer.info、P95 frame、内存曲线 |
| `VB-QA-109` | 数据语义、单位、七类时间、失联和回放可自动验收 | 数据合同已经定义，当前没有对应 schema/fixture/replay 自动测试 | `noncompliant` | 实现 `TEST-VB-DATA-003`～`009` | [数据附件验收表](../docs/GL02数据映射附件.md#18-验收和发布门禁vb-data-114) |

## 10. 当前证据基线

| 资产/程序 | 当前事实 | 批准含义 |
|---|---|---|
| 正式 `gl02_blast_furnace.glb` | SHA-256 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6` | 当前正式资产，仍为近似炉型 |
| P40 | 人工 `approve` | 只批准固定 LookDev 阶段 |
| P50 4K | `KEEP_P50_PENDING_NOT_APPROVED` | 不得称 P50 已批准 |
| P60 GLB | `not_granted_preflight_only`，32.7MB 未压缩 | 只用于隔离预览和预检 |
| glTF Validator | `unavailable` | P60 正式门禁未完成 |
| Three.js | r160、sRGB、ACES 1.05 | 有基础色彩链，不等于有 PMREM/HDR |
| 正式页面炉壳 | 不透明，fallback `roughness=.76/metalness=.38` | 哑光基线存在，完整 4K PBR 尚未正式交付 |
| L7～L16 | 115 点、十层按钮、每层八点和动画 | 交互合同已验证 |
| 内切面 | 旧 45 对象始终隐藏；权威 `BF3D_INTERNAL_SIMULATION_RUNTIME` 接管；R2Q 隔离审查具有 10 个物理半剖对象 | 运行时仍按 `illustrative/estimated/simulated` 分级；R2Q 为隔离候选，不是施工模型或实时断面 |

## 11. 更新规则

每次材质、灯光、相机、GLB、Three.js、数据适配或测试结果变化时：

1. 更新对应行的“当前证据”和状态；
2. 更新机器镜像 `visual_bible_conformance_v1.json`；
3. 保留旧报告和哈希，不覆盖历史证据；
4. `partial/noncompliant/blocked → compliant` 必须同时有实现、验证和批准；
5. 正式资产替换必须记录旧/新 SHA、回滚路径、浏览器矩阵和签字人；
6. 若 Visual Bible 条款变化，先更新稳定 ID 的目标，再评估所有受影响行，不能静默改变验收口径。

## 12. 2026-07-19 WEB-60 R2N 增量附录

> 本节是 2026-07-19 的候选实现增量，不重算、不覆盖 2026-07-18 的 45 项审计快照，也不修改
> [visual_bible_conformance_v1.json](visual_bible_conformance_v1.json)。
> 页首 `13 compliant / 14 partial / 12 noncompliant / 6 blocked` 仍是原始 45 项快照计数，不是对 R2N 的新汇总。

R2N 在现有单 Three.js 炉内运行时中增加了 E/illustrative 炉顶布料候选，阶段证据见
[WEB_60_20260719_R2N_BURDEN_CHARGING_RUNTIME](../work/WEB_60_20260719_R2N_BURDEN_CHARGING_RUNTIME/)。

| 关联稳定 ID | R2N 候选增量 | 本附录判断 | 原 45 项状态是否改变 |
|---|---|---|---|
| `VB-INT-004` | 增加溜槽、矿焦实例、解析碰撞滚落、扬尘和 START/COMPLETE 事件语义 | `candidate_evidence_added`；仅教学态，不是统一生产时钟和真实数据 | 否；仍需 `bf3d_snapshot/event` 生产适配 |
| `VB-INT-006` | 软熔响应独立为默认隐藏的 `illustrative / non-causal what-if` | `candidate_compliant` | 否；不把候选直接改写旧快照 |
| `VB-DATA-104` | 事件门验证 `bf3d_event.v1`、GL02、模式、事件时间和 256-ID 幂等窗口 | `partial_candidate` | 否；七类时间和生产快照仍未完整接通 |
| `VB-DATA-106` | `BURDEN_CHARGE_STARTED` 启动运动，`BURDEN_CHARGE_COMPLETED` 才沉积料层 | `partial_candidate` | 否；MES 真实事件适配与炉次—料批链仍缺 |
| `VB-RUNTIME-004` | 增加高/中/低实例/扬尘预算、五秒帧率采样、单向降级、低档降频和 reduced-motion | `candidate_evidence_added` | 否；完整场景 TTI/P95/显存预算未完成 |
| `VB-RUNTIME-005` | 固定容量 `InstancedMesh/Points`、12 层循环池、单 RAF、dispose/remount 和多次模式切换资源稳定 | `candidate_compliant_in_R2N_scope` | 否；待最终 WEB-60/QA-70 发布门复核 |
| `VB-QA-105` | R2N 跨引擎矩阵沿用 Chromium 九视口、Firefox/WebKit 各四代表视口并检查五业务路由 | `candidate_evidence_added` | 否；不替代生产现场 Edge |
| `VB-QA-108` | 有自动降级和固定资源证明，但没有 30 分钟长稳、标准设备 P95 和显存报告 | `partial_candidate` | 否；原发布级性能条仍未满足 |

### 12.1 保持不变的发布门

- R2N 的 `live_motion_gate.enabled=false`；没有真实溜槽程序、上料事件语义、粒径/堆密度和料线标定时，生产运动保持关闭。
- 软熔带 what-if 只允许教学态显式开启，不能标为本批次 `estimated/simulated` 因果结果。
- 正式 GLB 没有替换，SHA-256 仍为
  `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`。
- P50 仍为 `KEEP_P50_PENDING_NOT_APPROVED`，P60 仍为 `not_granted_preflight_only`，P70 未批准。
- 十阶段当前为 5 完成、2 部分、3 未正式开始；总项目未完成。

若 R2N 后续通过最终代码、视觉、规范和发布审查，应在新的矩阵版本中同步修改 Markdown、机器 JSON、证据哈希和批准记录，而不是回改本附录的历史快照说明。

## 13. 2026-07-19 C2 根部低置信度估计增量

> 本节记录 `REQ-BF3D-C2-ROOT-MOTION-20260719` 的实现增量，不重算、
> 不覆盖页首历史 45 项审计计数，也不把局部 C2 基线提升为完整物理孪生批准。

| 关联稳定 ID | C2 增量证据 | 本附录判断 | 仍未解除的门禁 |
|---|---|---|---|
| `VB-INT-004` | 8767 生成 `bf3d_snapshot.v1`；Three.js 按快照显示根部标高、厚度、偏心和移动状态 | `partial_candidate`；软熔带根部这一对象已由统一知识时间和证据驱动 | MES 上料/开堵口、炉缸、化验、经校准 C2/C3 仍未统一接入 |
| `VB-INT-006` | live C2 固定 `estimated/uncalibrated`，教学 what-if 仍独立且默认关闭 | `candidate_compliant` | 现场评审仍必须区分估计、仿真和实测 |
| `VB-DATA-103` | 快照透传三高度×A～F 18 点；缺点保留 null；Three.js 只显示真实点 | `partial_candidate` | A～F 绝对厂区方位未确认 |
| `VB-DATA-104` | 快照携带 render/knowledge/sample time、evidence、quality、model version 和输入覆盖率 | `partial_candidate` | 尚未覆盖 MES/lab 七类时间和完整 derivation |
| `VB-DATA-108` | C2 已实现 missing、stale、hard-expire、隐藏和恢复 | `candidate_evidence_added` | 其余数据对象和各源阈值仍需冻结 |
| `VB-RUNTIME-005` | 快照缓存、组件重挂载恢复和固定软熔带资源复用 | `candidate_compliant_in_C2_scope` | 长稳、现场 Edge 和生产数据链仍未批准 |
| `VB-QA-105` | Chromium 九视口、Firefox/WebKit 各四代表视口继续通过；另有 live C2 专项 | `candidate_evidence_added` | 不替代现场 Edge 与当前生产输入验收 |

### 13.1 C2 真实性停止线

- `root_definition=wall_thermal_activity_centroid`，只表示炉墙侧热活动代理；
- `confidence<=0.45`、`calibration_status=uncalibrated`、
  `control_use=prohibited` 是强制合同，不允许前端或桥接器覆盖；
- 偏心方位以传感器 A 点为相对零度，不得显示为东/西/南/北；
- 输入支持不对称、压力陈旧、知识时间回拨或输出合同异常时必须拒绝几何；
- 没有垂直探针、TDR、解剖或受控物理模型真值前，不得称为真实软熔带边界、
  完整倒 V/W 型预测或生产控制信号。

## 14. 2026-07-19 WEB-60 R2Q V3 受控材质/结构剖面增量

> 本节记录稳定增量 `VB-REC-WEB-60-R2Q-V3`。它不重算、不覆盖页首
> `13 compliant / 17 partial / 9 noncompliant / 6 blocked` 的当前 45 项快照，
> 并与 [visual_bible_conformance_v1.json](visual_bible_conformance_v1.json) 保持镜像一致。
> 局部复审 `PASS` 只在隔离 V3 审查候选边界内有效。

### 14.1 关联条款与候选证据

| 关联稳定 ID | R2Q V3 增量证据 | 本附录判断 | 原 45 项状态是否改变 |
|---|---|---|---|
| `VB-MAT-007` | 建立 `steel_inner`、`backfill`、`cast_iron`、`copper`、`hotface`、`refractory` 六材质族，并提供 BaseColor/ORM/NormalGL 受控候选 | `candidate_compliant_in_R2Q_scope` | 否；正式资产的完整材质族覆盖仍未批准 |
| `VB-INT-003` | `10` 个结构逻辑对象均为物理半剖，保持 `1x` 厚度和家族匹配封盖；每对象为“主体 + 物理封盖”两个 primitive，共 `20` 个 | `candidate_compliant_in_R2Q_scope` | 否；正式 GLB/正式运行态仍未受控替换 |
| `VB-INT-005` | 结构候选包含五区钢壳、背衬填料、铸铁/铜冷却壁、热面嵌入层和残余耐火层 | `partial_candidate` | 否；死料柱、保护渣皮和现场结构依据等完整范围仍缺 |
| `VB-INT-006` | 纯材质/结构审查态均无传感器、引线、黄色轮廓、工艺粒子、旧圆环或装饰竖线；三份 V3 GLB 中禁止对象彻底不存在 | `candidate_compliant` | 否；继续保持逐对象证据等级与模式隔离 |
| `VB-RUNTIME-001` | Three.js r160 对当前 WebP GLB 完成 `17/17` 引擎/视口矩阵 | `candidate_compliant_in_R2Q_scope` | 否；版本条原本已合规，本节只追加当前候选证据 |
| `VB-RUNTIME-002` | 三份 GLB 的 PBR 通道、UV、identity transform 和 WebP 引用通过独立前端/规格复审 | `candidate_evidence_added` | 否；不等于正式资产获批替换 |
| `VB-RUNTIME-006` | V3 资产保持隔离候选；正式 GLB SHA 未变 | `release_boundary_preserved` | 否；正式替换门仍为 `blocked` |
| `VB-QA-105` | Chromium 九视口、Firefox/WebKit 各四代表视口，共 `17/17 PASS`；本机真实 Edge 四代表视口 `4/4 PASS` | `candidate_evidence_added` | 否；本机 localhost/headless/静态数据源冒烟不替代现场主机与真实链路 Edge |
| `VB-QA-102`～`VB-QA-104`、`VB-QA-107`～`VB-QA-108` | R2Q 未提供 P50/P60/P70/QA-70 批准；R2R 严格跨渲染器数值门已经执行但为 `FAIL/BLOCKED` | `no_gate_change` | 否 |

厚度/封盖、禁止对象和 GLB 通道的机器证据分别见
[section_scale_cap_validation.json](../work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reports/section_scale_cap_validation.json)、
[role_forbidden_validation.json](../work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reports/role_forbidden_validation.json)
与
[glb_channel_texcoord_validation.json](../work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reports/glb_channel_texcoord_validation.json)。

### 14.2 受控对象、模式与兼容边界

| 项目 | 当前受控事实 |
|---|---|
| 纯材质资产组 | `5` 个完整 R2J 炉壳逻辑对象；保留独立外表面材质资产合同 |
| Web 纯材质审查 | 显示 `10` 个物理半剖逻辑对象；以层材质近景露出六材质族 |
| 结构模式 | `10` 个结构逻辑对象；提供整炉剖面和局部分层近景 |
| 结构 primitive | `20` 个，严格为每对象一个主体 primitive 加一个家族匹配的物理封盖 primitive |
| 物理尺度 | `thickness_scale=1.0`、`layer_thickness_amplified=false` |
| 审查态 | 传感器、数据引线、黄色轮廓、工艺粒子、旧圆环和装饰竖线全部隐藏 |
| 旧运行态兼容 | `45` 个装饰/示意对象保留作兼容，在 V3 受控路径中始终隐藏，并由权威 `simulation` 接管 |
| V3 GLB 边界 | 上述 `45` 个旧对象及其环、线、点图元在三份 V3 GLB 中彻底不存在 |

### 14.3 WebP GLB 身份与运行证据

| 用途 | 受控产物 | Bytes | SHA-256 |
|---|---|---:|---|
| main | [gl02_blast_furnace_review.v3.glb](../../../高炉前端数据/models/gl02_blast_furnace_review.v3.glb) | `4,380,396` | `7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b` |
| material | [gl02_blast_furnace_material_review.v3.glb](../../../高炉前端数据/models/gl02_blast_furnace_material_review.v3.glb) | `993,260` | `87c2bbe632d71113e69c4b5ac95ad35c12e7a03f17f7b74a1cb8b25661df4c09` |
| structural | [gl02_blast_furnace_structural_review.v3.glb](../../../高炉前端数据/models/gl02_blast_furnace_structural_review.v3.glb) | `3,663,988` | `8490f56bddeba24f2819adfc3013d96aca448264e09b43793e0f2d7d2744f41a` |

三份文件均为 `EXT_texture_webp` 浏览器交付 GLB。当前
[Web 主验证](../../../logs/bf3d_structural_review_v3_20260719/report.json)
与
[17 组合矩阵](../../../logs/bf3d_structural_review_v3_20260719/matrix_report.json)
记录 Three.js r160、`17/17 PASS`。以下三个角色分离的复审也均为限定范围 `PASS`：

- [前端资产独立复审](../work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reviews/R2Q_V3_WEBP_FRONTEND_ASSET_REVIEW.md)；
- [规格符合性独立复审](../work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reviews/R2Q_V3_WEBP_SPEC_COMPLIANCE_REVIEW.md)；
- [Web 运行视觉复审](../work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reviews/R2Q_V3_WEB_RUNTIME_VISUAL_REVIEW.md)。

### 14.4 保持不变的真实性与发布停止线

- 全部 R2Q V3 对象保持 `E/illustrative`、`REF-PENDING`、
  `not_for_construction=true`；不得用于实测壁厚、施工尺寸、材质牌号或真实冷却壁配置声明。
- 严格 Cycles/Eevee 数值 A/B 已执行但为 `68/80 pass、12 fail`；Three.js/Eevee
  因相机、四灯和色彩管理合同不匹配在捕获前停止；本机真实 Edge 已 `4/4 PASS`，
  但现场主用 Edge 尚未通过；引擎矩阵、本机 Edge 与视觉复审不得替代这些门禁。
- P50、P60、P70 与 QA-70 均未通过。
- 正式 [gl02_blast_furnace.glb](../../../高炉前端数据/models/gl02_blast_furnace.glb)
  仍为 SHA-256
  `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`，
  没有被 R2Q V3 覆盖。
- 十阶段仍为 `5` 个完成、`2` 个部分完成、`3` 个未正式开始；总项目未完成。

阶段汇总、产物清单和当前状态见
[WEB-60 R2Q 受控目录](../work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/)。

## 15. 2026-07-19 WEB-60 R2R 渲染器数值门增量

> 本节记录 `VB-REC-WEB-60-R2R-AB-GATE`。它为 `VB-QA-107` 增加真实失败证据，
> 不将该条从 `partial` 升级，也不改变任何发布门状态。

### 15.1 数值与视觉证据

| 关联稳定 ID | R2R 增量证据 | 本附录判断 | 原 45 项状态是否改变 |
|---|---|---|---|
| `VB-QA-107` | 捕获前冻结固定正交相机、`1920×1080`、P40 四灯、AgX/0 EV、三 shot、两 repeat、随机种子、输入 SHA 和原阈值；Blender 真实捕获 `12/12`，有 beauty/mask/diff | `partial_with_fail_evidence` | 否；尚无通过的 Blender/Three Web Golden 基准 |
| `VB-RUNTIME-002` | 轮廓 IoU 最低约 `0.999708`、边缘 P95 `0 px`，但结构亮度 SSIM 与四材质族相对亮度失败 | `geometry_contract_pass_material_parity_fail` | 否 |
| `VB-QA-102`～`VB-QA-104` | R2R 不批准 P50/P60、Validator 或正式 GLB | `no_gate_change` | 否 |
| `VB-QA-108` | R2R 只验证固定离线捕获和合同预检，不是 TTI/P95/30min/显存预算 | `no_gate_change` | 否 |

Blender 数值报告为 `80 required / 68 pass / 12 fail / 0 not-evaluated`。Three.js
预检为 `13 pass / 8 fail / 2 blocked`，且
`capture_attempted=false`、beauty/mask `0`、`ab_pass_claimed=false`。

### 15.2 失败根因边界

- 标准剖面和局部分层近景在两个 repeat 中分别约 `0.829` 和 `0.789`，低于结构亮度 SSIM `0.85`；
- 内侧钢、铸铁、铜和热面层在两个 repeat 中超过 `8%` 相对亮度差；
- Three.js 生产运行时为透视动态构图，缺 P40 顶部 Area/RectAreaLight 和锁定光向，且 ACES/exposure `1.05` 与 Blender AgX/0 EV 合同不匹配；
- 独立视觉复审确认差异可见，不是 mask、轮廓、裁切或单次抖动。

### 15.3 下一证据要求

R2S 必须分离生产 UX 相机和固定正交审查捕获路径，补齐 P40 四灯，先批准跨渲染器色彩管理等价合同，再逐变量修正并复跑相同阈值。阈值不得捕获后放宽；若修改资产，必须新版本和新 SHA。

权威证据：

- [R2R 阶段状态](../work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/pipeline_status.json)；
- [Blender 数值报告](../work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/comparison_report.md)；
- [Three.js 合同预检](../work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reports/three_contract_preflight.json)；
- [独立规格复审](../work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reviews/R2R_INDEPENDENT_SPEC_REVIEW.md)；
- [独立视觉复审](../work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reviews/R2R_INDEPENDENT_VISUAL_REVIEW.md)。

## 16. 2026-07-20 WEB-60 R2S 审查数值合同增量

> 本节记录 `VB-REC-WEB-60-R2S-AUDIT-CONTRACT`。它只提升 `VB-QA-107` 的可追踪性，
> 不把原 `partial` 改为 `compliant`，也不批准图像 A/B 或发布。

### 16.1 增量判断

| 关联稳定 ID | R2S 增量证据 | 本附录判断 | 原 45 项状态是否改变 |
|---|---|---|---|
| `VB-QA-107` | 双门控只读 API 固定三正交 shot、P40 四灯坐标/方向/拓扑和原 13 阈值；真实生产 HTML 与 harness 各 9 组负向门、22/22 输入锁、12 捕获记录、递归冻结与突变拒绝通过 | `partial_with_hardened_numeric_contract_only` | 否；没有 Web beauty/mask 或批准基准 |
| `VB-RUNTIME-002` | 应用脚本前 instrumentation；两个独立 full-ready 上下文在 ready/API/4 RAF/450ms 后的 Viewer、camera、controls、renderer、scene、resources、viewport/scissor/render target/RAF 引用和状态不变，审计副作用 0 | `audit_contract_isolated_hardened` | 否；不代表材质光传输等价 |
| `VB-QA-102`～`VB-QA-104` | 正式 GLB、R2Q Blend/三 GLB SHA 未改变 | `no_gate_change` | 否 |
| `VB-QA-108` | 原专项、17 组合矩阵、本机 Edge 4 视口和旧切面回归通过 | `local_regression_passed` | 否；TTI/P95/30min/显存与现场 Edge 仍待办 |

### 16.2 仍然阻断

- Three r160 内建 AgX 默认对比不能自动等同 Blender AgX Medium Low；
- Blender Sun/Area 能量、Sun angle、Disk 与 Three.js intensity/RectAreaLight 的等价未批准；
- `colorState=pending_preapproval`；
- `captureEligible=false`；
- 未创建独立 renderer/scene/camera/light，也未输出 beauty/mask；
- R2R `68/80` 失败事实和原阈值保持不变。

### 16.3 证据

- [R2S 阶段状态](../work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/pipeline_status.json)；
- [输入锁](../work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/input_lock.json)；
- [增量清单](../work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/implementation_delta_manifest.json)；
- [专项验证](../work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/r2s_audit_contract_verification.json)；
- [色彩决定](../work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/color_management_decision.json)；
- [光度决定](../work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/photometric_mapping_decision.json)。

## 17. 2026-07-20 WEB-60 R2T OCIO 与光度候选增量

> 本节记录 `VB-REC-WEB-60-R2T-OCIO-PHOTOMETRY`。它把色彩源资产和 P40 光度候选
> 变成机器可验证合同，但 WebGL、线性标定和炉体图像仍未通过，所以不改变原 45 项状态。

### 17.1 增量判断

| 关联稳定 ID | R2T 增量证据 | 本附录判断 | 原 45 项状态是否改变 |
|---|---|---|---|
| `VB-QA-107` | 固定 Blender 5.2 OCIO/Three r160 输入；生成 14155 bytes GLSL、37³/57³ LUT；235846 texel 与 8 CPU oracle 通过 | `partial_with_exact_color_assets_cpu_only` | 否；GPU oracle、许可和图像 A/B 未完成 |
| `VB-MAT-001`～`VB-MAT-006` | V3 六材质族 PBR 通道存在；R2T 明确 Web 过暗来自环境/灯光/Tone Mapping，不授权改 BaseColor 或按引擎调材质 | `asset_channels_present_transport_pending` | 否；材质仍为 E/illustrative、REF-PENDING |
| `VB-LIGHT-001` | SUN/TOP/world 只预注册 family-level 标量和 fit/held-out；TOP k=1 候选 1.3275510357953；官方 r160 LTC addon 与两份许可证已按 commit/bytes/SHA 锁定 | `photometry_candidate_and_ltc_source_preregistered_only` | 否；LTC 运行初始化、SUN angle、阴影和 held-out 未通过 |
| `VB-RUNTIME-002` | R2T 只新增工具和阶段产物，未改生产页面、控制器、renderer、ACES 或 GLB | `production_unchanged` | 否 |

### 17.2 仍然阻断

- WebGL2 RGBA32F 与默认 8-bit GPU oracle 未评估；
- LUT/AgX 专属许可与归属取证未完成；
- r160 RectAreaLightUniformsLib 来源/SHA/许可已固定，但同一 ESM 的 init-once、四张 64×64 texture 与扩展分支未验证；
- Three DirectionalLight 无 Blender SUN 8°角直径，RectAreaLight 无阴影；
- 线性 fixture、family-level fit 和 held-out 材质板未执行；
- R2R `68/80` 失败与 Three 捕获前 BLOCKED 保持；
- `capture_eligible=false`、`approval_granted=false`、`next_stage_allowed=false`。

### 17.3 证据

- [R2T 阶段状态](../work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/pipeline_status.json)；
- [R2T 输入锁](../work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/input_lock.json)；
- [材质可见性诊断](../work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/material_visibility_diagnosis.md)；
- [色彩候选](../work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/color_management_candidate.json)；
- [光度合同](../work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/photometric_calibration_contract.json)；
- [OCIO 生成清单](../work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/generated/ocio_assets_manifest.json)；
- [R2T 阶段验证器](../../../tools/verify_bf3d_r2t_stage.py)。

## 18. 2026-07-20 WEB-60 R2V V5 可移植静态审查增量

> 稳定记录：`VB-REC-WEB-60-R2V-PORTABLE-V5`。只改变 Web 静态审查资产的
> 可移植性和可解释性证据，不改变原 45 项的生产批准状态。

| 关联稳定 ID | R2V 增量证据 | 本附录判断 | 原状态是否改变 |
|---|---|---|---|
| `VB-MAT-001`～`VB-MAT-006` | 六类内部 PBR 材质、材质合同与内嵌图像 payload 保持；近景可辨钢灰/锈红/浅棕/深棕层 | `pass_for_isolated_static_review_only` | 否；仍是 E/illustrative、REF-PENDING |
| `VB-GEO-SECTION` | 10/10 闭合正体积，boundary/non-manifold/封口重叠为 0；V4→V5 顶点/包围盒/材质槽/UV 边界等价 | `pass_r2v` | 否；不形成施工尺寸 |
| `VB-RUNTIME-002` | 三 GLB 绝对路径/缺失切线/无效切线/Khronos error/warning 均为 0；Three.js 两轮 34/34、102 captures、五类错误 0 | `pass_isolated_portability` | 否；生产 8092 未接入 |
| `VB-QA-107` | Blender/Three 仅完成静态可见性与加载稳定性；未完成数值光度等价 | `still_blocked` | 否 |

附加视觉条件：外表面全景对比偏弱；锈红/浅棕间可见带在 R2V 只属于待复核的物理
边界候选，不构成相邻层连续性证据，后续由 R2W 第 19 节修正。三资产解码约
`720 MiB`、完整 mip 约 `960 MiB`，现场/移动端性能仍未批准。证据见
[R2V pipeline](../work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/pipeline_status.json)、
[独立审查](../work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/independent_review_decisions.json)和
[根审查](../work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/WEB-60_R2V_根审查结论.md)。

## 19. 2026-07-20 WEB-60 R2W 镜头、AO 与相邻层审计增量

> 稳定记录：`VB-REC-WEB-60-R2W-CAMERA-AO-EDGE`。相机可读性条件通过不改变
> 原 45 项生产状态，也不解除 AO、结构连续性或发布门。

| 关联稳定 ID | R2W 增量证据 | 本附录判断 | 原状态是否改变 |
|---|---|---|---|
| `VB-MAT-003` | 锁定 V5 的外表面材质近景可阅读既有细颗粒/粗糙度；相机调整未改 PBR | `pass_camera_readability_only` | 否；宏/中/微尺度正式交付仍为 `partial` |
| `VB-MAT-004` | ORM.R 全 `255`；glTF 无 `occlusionTexture`；Blend ORM.R 未接入；旧 P50 UV/目标不兼容 | `fail_closed_no_ao_consumption` | 否；保持 `noncompliant` |
| `VB-GEO-SECTION` | L03 `z=-20…7.55 m`、L04 `z=16…20 m`，共同高度/覆盖率 `0`；真相邻链不可测 | `fail_closed_design_reference_required` | R2V 闭合拓扑 PASS 保持，但不再推导相邻层连续性 |
| `VB-RUNTIME-002` | 三引擎双轮 `34/34` runs、`136` captures、五类错误 `0`；PBR 改写/禁止对象/黄色轮廓 `0` | `pass_isolated_camera_candidate_only` | 否；生产 8092 未接入 |
| `VB-RUNTIME-006` | 正式 GLB SHA 不变，R2W 仅新增隔离页/渲染器 | `release_boundary_preserved` | 否；正式替换仍为 `blocked` |
| `VB-QA-107` | 相机框景稳定，但没有数值色彩/光度 A/B | `still_blocked` | 否 |

边界解释统一为“内部层边界 REF-PENDING，非数据竖线”。L03→L05 的
`14.816–49.456 mm` 是非相邻直差诊断，不能写成层厚或相邻层间隙；
`z=-1.2 m` 异常是冷却壁拼缝/端面剖切诊断。

R2W 状态为 `r2w_camera_readability_passed_ao_and_structure_blocked`。P50/P60/P70/
QA-70、施工尺寸、正式 GLB、生产 8092、现场性能/长稳和 Blender/Three 数值光度
等价均未批准。证据见
[Web 矩阵](../work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/bf3d_review_r2w_preview_report.json)、
[AO 审计](../work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/ao_consumption_audit.json)、
[相邻层审计](../work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/interface_gap_audit.json)、
[独立复核](../work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/independent_review_decisions.json)和
[根审查](../work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_根审查结论.md)。

## 20. 2026-07-20 WEB-60 R2X 当前 R2J AO 1K 增量

> 稳定记录：`VB-REC-WEB-60-R2X-R2J-AO-SMOKE1K`。R2X 证明 UV2、glTF
> `occlusionTexture` 和 Three.js `aoMap` 消费链已接通，但代表画面没有任何像素
> 差异；因此机器门通过不改变原 45 项视觉/生产合规状态。
> 对应需求：`REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720`；最终候选
> SHA-256 为 `bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00`。

| 关联稳定 ID | R2X 增量证据 | 本附录判断 | 原状态是否改变 |
|---|---|---|---|
| `VB-MAT-003` | 五个 R2J 炉壳保留 V5 BaseColor/Normal/Roughness/Metalness channel 0；R2X 没有改 BaseColor | `baseline_preserved_ao_not_a_material_visibility_fix` | 否；用户“看不到具体材质”仍需检视照明/近景/几何接触源 |
| `VB-MAT-004` | 5/5 primitive 有 finite UV2、`aoMap.channel=2`；off/on 只改 intensity `0→1`，但全景/近景 `changed_pixels=0`、成对 PNG SHA 相同 | `fail_closed_ao_visual_signal_absent` | 否；保持 `noncompliant` |
| `VB-LIGHT-005` | 未出现整体压黑或虚假粗黑圆环，但原因是 AO 开关完全没有栅格差异 | `no_defect_does_not_equal_visible_ao_pass` | 否；接触层次仍未建立 |
| `VB-RUNTIME-002` | 最终候选 `1,115,216` bytes、SHA `bd074c23…1c00`；V5 payload 独审 PASS、Khronos 0/0，Three 机器门 PASS、五类错误 0 | `pass_isolated_machine_consumption_only` | 否；代表视觉门失败，生产未接入 |
| `VB-RUNTIME-006` | V5 Blend/三份 V5 GLB、formal GLB、生产页面 SHA 保持 | `release_boundary_preserved` | 否；正式替换继续 `blocked` |
| `VB-QA-107` | 仅 Chromium `1440×900`，四张 WebGL canvas、两组 off/on；完整矩阵未执行 | `representative_fail_closed_no_golden` | 否；不能宣称跨浏览器、响应式或 Golden View 通过 |

### 20.1 可追踪链

| 类型 | 入口 |
|---|---|
| Requirement / config | [R2X 预注册合同](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_阶段预注册合同.md) |
| Program | [Blender 构建:L2243](../../../tools/build_bf3d_r2x_r2j_ao_candidate.py#L2243)、[V5 重打包:L2202](../../../tools/repack_bf3d_r2x_ao_v5_payload.py#L2202)、[Three AO 开关:L723](../../../高炉前端数据/assets/bf3d-review-renderer-r2x.js#L723)、[代表验证:L990](../../../tools/verify_bf3d_review_r2x_preview.cjs#L990) |
| Artifact | [最终 1K v5payload GLB](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/glb/gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb) |
| Machine test | [V5payload 独立审计](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_ao_smoke1k_v5payload_audit.json)、[Three 代表报告](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/bf3d_review_r2x_representative_report.json) |
| Visual decision | [独立视觉复核](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_independent_visual_review.json)、[根审查](../work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_根审查结论.md) |

首次重打包候选因 `UNAUTHORIZED_EXTRA_AO_CLAMP_SAMPLER` 被失败关闭；最终候选复用
V5 sampler 0，失败历史保留。最终 AO PNG `99.6763%` 为纯白，非白仅 `0.3237%`，
与两组像素零差异共同构成视觉失败证据。

R2X 状态为 `r2x_machine_passed_three_visual_failed_closed`。不得运行完整矩阵来掩盖
代表门失败，不得升 2K，不得批准 P50/P60/生产。下一候选必须先验证当前 R2J 的可见
几何接触源、AO 覆盖/衰减和 UV2 命中，或回到材质检视照明与确定性近景；结构表达
需要权威参考。禁止添加黑圆环、装饰竖线或修改 BaseColor 伪造层次。

## 21. 2026-07-20 WEB-60 R2Y 材质信号可见性诊断增量

阶段：`WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC`。本增量只增加
诊断证据，不升级既有合规状态。

| 条款 | R2Y 新证据 | 当前状态 |
|---|---|---|
| `VB-MAT-003` | PBR raw signal 与绑定存在，但 macro `0.962958 < 1`、anisotropy `1.021708 < 1.03`；Normal/Roughness 周期伪影主导 | `partial`，不升级 |
| `VB-MAT-004` | CPU UV/AO 命中通过；AO WebGL liveness `NOT_EXECUTED` | `noncompliant`，不升级 |
| `VB-LIGHT-003` | 两个 PMREM target 已切换，但 environment A/B 最终差异为 `0` | `noncompliant`，不升级 |
| `VB-LIGHT-005` | 没有 synthetic-black/float/final 8-bit AO WebGL 证据 | 原状态不变 |
| `VB-QA-107` | 仅 Chromium `1440×900` 代表诊断，13 captures；不是 Golden/full matrix | 不满足 |
| `VB-RUNTIME-006` | V5/R2X/formal/生产资产前后哈希不变 | 正式替换继续 `blocked` |

可追踪链：

| 层 | 证据 |
|---|---|
| Requirement / config | [R2Y 预注册合同](../work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/WEB-60_R2Y_阶段预注册合同.md) |
| Program | [CPU AO/UV 审计](../../../tools/audit_bf3d_r2y_ao_uv_hit.py)、[PBR 审计](../../../tools/audit_bf3d_r2y_pbr_texture_signal.py)、[Three renderer](../../../高炉前端数据/assets/bf3d-review-renderer-r2y.js)、[代表 verifier](../../../tools/verify_bf3d_review_r2y_preview.cjs) |
| Machine evidence | [CPU 报告](../work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_ao_uv_hit_raster_audit.json)、[代表报告](../work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/bf3d_review_r2y_representative_report.json) |
| Visual decision | [独立审查](../work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_independent_review_decisions.json)、[根审查](../work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/WEB-60_R2Y_根审查结论.md) |

状态固定为 `r2y_cpu_hit_passed_pbr_visual_failed_ao_webgl_pending_fail_closed`。不得把
CPU 命中、raw signal 或绑定存在扩写成 shader 消费、材质可读、AO 可见、beauty、
Golden、完整矩阵、P50/P60 或生产通过。

# 问题核查追踪

## REQ-QA-EXCLUSIVE-USE-20260916：多角色并发限定

按用户最新限定改为8093全角色共用一个活动问答名额，其他发送409使用中；不排队、不自动重放，取消实际停止才释放。9项独占测试、35项关联回归及独立审查通过；本机已实施，生产尚未更新，QAOPT-O05保留生产待验收。[记录](handoffs/2026-09-16-qa-exclusive-use-local.md)。

## Q-QA-QWEN-READINESS-CONCURRENCY-ORACLE-20260916

- 用户问题：模型驻留波动、多角色并发和知识标准冲突如何解决；要求允许Qwen驻留。
- 本轮只读核对：业务别名模型family=qwen35，实际已驻留并在8093允许清单内；健康API本次正常。
- 诊断更正：前轮model_ok临时false不足以证明模型卸载。当前resolve_resident将查询异常替换为空列表，应分开probe_timeout/failed与成功查询缺席。
- 方案：准确就绪分类及按能力检查依赖、批准Qwen身份/驻留与有界推理队列、owner及共享访客多角色矩阵、30项oracle版本化逐题修正；803原文覆盖不等于全语义通过。
- 权威方案：[2026-09-16 Qwen/并发/oracle解决方案](handoffs/2026-09-16-qa-qwen-readiness-concurrency-oracle-plan.md)。关联QAOPT-O01/O05/T02/T04。
- 本轮无生产修改或新问答POST，后续实施按受控发布与独立答案核查。

## Q-FOREMAN-CURVE-POINT-MAPPING-20260814

- 用户问题：工长趋势中部分曲线和传感器数值没有完全对应，要求重新核查正式点位清单。
- 核查结论：截图中的 `P_top=22.381063` 同时得到 220.12 分钟表和 pSpace 单点原始历史确认，
  `P_top -> SIO_GL02_LD_T0034` 没有串点；页面顶部是 12:29 当前值，曲线是 06:00–08:00
  历史值，两者当前不联动。
- 已确认问题：`GasUtil` 当前卡片按百分比换算而历史提示仍为 0–1 原值；
  `Hopper_weight_set` 未进入 220.12 `sensor_registry`，且没有单一物理点。补充 pSpace 原始
  核查确认它应由 1–11 号布料重量设定状态求和派生。`L_south/L_north` 的 `T0075/T0076`
  点位正确，pSpace 的限位文字是误导性注释；现场值、业务/PLC映射和周期波形均已交叉确认。
- 显示边界：主图纵轴是多量纲泳道归一化坐标，右键提示第三维才是原始值；页面应增加口径说明。
- 后续修复：顶部指标、曲线悬浮和右键点位值已在本机统一为两位小数；`GasUtil` 历史
  `0–1` 比例先乘100再展示，例如 `0.482998 -> 48.30%`。对应需求为
  `REQ-FOREMAN-TREND-TWO-DECIMAL-PERCENT-20260814`，尚未部署220.12。
- 登记更新：2026-08-14 已将 `L_south/L_north`、11 个 `Hopper_weight_set_*` 物理分量及
  派生目录项写入 220.12 `sensor_registry`，登记审计 14/14；既有同步器已成功采集 11/11
  个物理分量。派生总量尚未物化到分钟表，不应在页面冒充已有历史曲线。
- 证据与逐项结果：[工长趋势曲线—点位映射核查](handoffs/2026-08-14-foreman-curve-point-mapping-audit.md)。
- 影响范围：已更新生产点位清单和 `sensor_registry`，并调用既有同步器补入物理分量历史；
  没有修改8093页面、8768/8770程序或计划任务，也没有新增 pSpace 读取进程。详见
  [登记交接](handoffs/2026-08-14-hopper-weight-set-registry-production.md)。

## Q-COHESIVE-ZONE-TREND-CALCULATION-20260808

- 用户问题：当前软熔带上升/下降趋势应该怎样计算。
- 当前结论：项目已有`C2-ROOT-BASELINE-2026.07`，以L7～L13炉体温度
  高度剖面计算炉墙热活动中心，以压差/透气性和三高度A～F静压力辅助
  厚度、偏心和置信度，以风/氧/煤作最大0.35m的有界修正；使用两个中心
  相隔30分钟的15分钟窗口计算速度，按±0.12m/h判定上移/下移/稳定，
  再做15分钟未标定常速外推。
- 方法判断：当前结果适合作为低置信度状态指示和专家弱标签，不是经过真值
  训练的生产预测。主要局限是双窗口差分、热力修正不对称、层温min-max
  丢失绝对变化、压力未充分参与高度估计，以及高度/厚度/偏心共用单一置信度。
- 数据边界：`bf_sensor.one_minute_values`在2026-08-05 21:55前后存在
  `PS_RAW_SAMPLE -> PS_RAW_AVERAGE`语义切换，跨期训练前必须统一或分段审计；
  铁水Si/S和炉渣属于炉次后验，只能用于回看标定与漂移监测。
- 推荐升级：持久化一分钟状态序列，以稳健平滑/状态空间模型融合温度中心与
  压力阻力中心，再预测15/30/60分钟`ΔH`及方向概率；取得专家弱标签或
  探针真值后再训练和比较监督模型。
- 详细分析：[软熔带趋势计算与升级分析](软熔带趋势计算与升级分析_20260808.md)。
- 实现位置：[估计器](../炉况规则引擎/features/cohesive_zone_estimator.py)、
  [参数](../炉况规则引擎/config/cohesive_zone_estimator.yaml)、
  [8767适配](../自动诊断服务/local_pg_ws_bridge.py)、
  [专项测试](../tests/test_cohesive_zone_estimator.py)。
- 影响范围：仅分析和文档追踪；未修改模型、数据库、API、页面、生产服务或
  计划任务。

## Q-HEAT-QUALITY-REPAIR-CLOSED-LOOP-20260807

- 用户问题：总结 `workdate + meltno` 炉次时间修复的全部可能情况，并修复修复状态被覆盖、未来数据、缺口清单、异常原因、指标命名和固定 `LIMIT 500` 问题。
- 结论：089/090 的日期重基准和跨午夜算法保留；普通同步现在只更新迟到化验/出铁事实，不覆盖 `time_anomaly_repaired` 谱系。未来时间与双日期锚点冲突默认隔离，无证据不写，扫描分页并报告截断。
- 实现：[聚合存储](../高炉前端数据/智能助手/backend/heat_performance_quality.py)、[同步器](../tools/sync_22012_heat_performance_quality.py)、[迁移](../tools/migrate_heat_quality_time_repair_columns_22012.py)、[专项交接](handoffs/2026-08-07-heat-quality-repair-closed-loop.md)。
- 验证：本机 17 项专项测试与 `py_compile` 通过；未部署 220.12、未执行生产 DDL 或重启服务。

## Q-DIAG-RULES-FAST-RELIABLE-SSH-DEPLOY-20260806

- 用户问题：诊断功能每次部署过慢，希望制作一个规则引擎更新部署器并一键发布，且必须基于本机 `reliable_ssh` 访问220.12执行命令。
- 结论：已建立统一入口 `python .\tools\deploy_diag_rules.py`；默认只做测试和dry-run，追加 `--apply`才上传并部署。传输不再使用Paramiko，也不需要逐文件、多次SSH往返。
- 性能设计：9个业务文件、清单、远端安装器和两个代理构建器压成一个ZIP；同一进程只校验一次身份，然后一次原子上传、一次远程执行。代理在远端以当前生产版本合并，避免先下载和避免覆盖新MCP能力。
- 安全：8093按既有守卫停—改—启，8094只精确重启自身任务；8768/8770/11434受PID保护；修改前备份，失败回滚。
- 验证：47项测试和dry-run通过；本机 `reliable_ssh` 已成功确认220.12主机身份。额外MCP argv调用因30秒客户端窗口超时，未造成写入；一键入口为远程执行预留240秒。
- 当前边界：2026-08-06已执行生产 `--apply --verify fast`；部署收据和远端运行态验收见[正式交接](handoffs/2026-08-06-8093-8094-diagnosis-assets-repair.md)。

## Q-RECOMMENDATION-FULL-AUDIT-20260806

- 用户问题：220.12实际数据库能否保存所有建议，并要求立即开始完整、逐条、全字段、可审计的入库标准。
- 实库核查：诊断主表和问答快照没有完整建议动作；大模型分析快照只有归一化摘要，会丢失顺序及完整触发值。因此不能把原状态表述为全字段入库。
- 实施：新增不可变批次表、逐动作表、审计视图、策略哈希、幂等写入、最小权限迁移和8768失败关闭逻辑；完整保留四种状态和全部动作字段。
- 本地验证：新增7项合同及相关26项回归通过，真实夹具为8炉况35动作。
- 远端边界：首次SSH前置检查因aTrust VNIC没有系统路由而超时；部署包没有上传，220.12数据库和服务尚未发生修改。恢复系统隧道后继续受控迁移和运行验收。

## Q-8093-8094-DIAGNOSIS-AI-UNAVAILABLE-20260806

- 用户问题：截图中的“当前炉况分析”为什么显示“暂不可用”，并要求在实验配置完成后把数据模块、弹窗评分、单炉况特征和建议复盘加入8093/8094。
- 结论：8093是共享代理与旧分析模块版本错位；8094是功能开关未启用，不是Ollama服务故障。
- 处理：两端统一到v3单炉况分析；异常可自动弹窗，八类卡可手动打开；评分/建议可选、关闭不写，免登录提交；系统分、人工分和时间戳分别保存。
- 验收：两端页面已注入模块，评分上下文 `enabled/can_submit=true`、`login_required=false`；智能分析已生成并带变量、调剂引擎1、知识依据。8094只更换自身PID，其他关键服务未变化。

## Q-8093-DIAGNOSIS-AI-FIVE-MINUTE-20260805

- 用户问题：除数据标注和弹窗评分外，增加智能助手每5分钟对各炉况的判断，点击炉况即可查看分析。
- 处理：该功能现已升级为v3；一次模型请求只生成用户当前所选炉况的分析，并按生产诊断时间的5分钟桶和目标炉况持久化。诊断卡打开组合窗口，智能分析和人工评分互不覆盖。
- 安全：浏览器只能选择八类标签；生产快照、八类规则分、证据和历史全部由服务端重读。模型分析只读，不是概率，不改变主诊断或生产控制。
- 数据：新表 `bf_assistant.diagnosis_ai_analysis_snapshots` 保存派生状态；人工评分继续写原两张事件表。
- 验证：36项合同、Chromium九视口及Firefox/WebKit八个代表视口通过；详情见[专项说明](8093_每5分钟八炉况智能分析_20260805.md)。

## Q-8093-DIAGNOSIS-REVIEW-NO-LOGIN-20260804

- 用户问题：允许把炉况数据标注、异常弹窗评分和八卡手动评分增加到8093，同时取消必须高炉长登录后才能评分。
- 处理：8093两个评分POST在显式免登录开关下使用服务端固定 `onsite_8093/现场高炉长/onsite_anonymous` 身份；前端按 `can_submit`直接显示表单。历史评分GET和其他后台接口仍受登录保护。
- 数据：服务端重读诊断快照并向220.12回环PostgreSQL的两张追加事件表写入；浏览器不能覆盖系统八类分或伪造评分身份。
- 部署：只暂停并恢复 `BFV4PreviewProxy8093`；8768和8094进程、8094页面哈希不变。失败路径已验证可自动回滚，最终部署未回滚。
- 验收：22项测试、远端API/表结构、真实8093免登录手动评分和9视口通过；验收后两表均0行。当前诊断正常，未伪造异常生产快照。详见[部署说明](8093_异常炉况评分免登录部署_20260804.md)。

## Q-BF3D-8093-FURNACE-SUMMARY-TEXT-CLIPPING-20260802

- 用户问题：8093 总览中煤气顶压、压差透气、喷煤、料线、热制度、送风供氧、出铁口温度共 7 张外围数据浮层偏小，字段被遮挡，希望进一步放大。
- 现象名称：响应式压缩导致的文本截断（responsive text clipping / ellipsis truncation），不是 121 个点位 Billboard 的悬停或抖动问题。
- 根因：旧样式在 `max-height:760px` 时把卡片宽度压到 `116px`，同时字段名、数值、单位三列都启用 `overflow:hidden + text-overflow:ellipsis`；字段列宽不足时只能显示为“综…”等缩写。
- 处理：[8093 专用可读性样式](../高炉前端数据/assets/bf3d-furnace-summary-readability-8093.css)将 7 卡扩大至桌面 `208–242px`、紧凑桌面 `198px`、低高度 `190px`，删除不可恢复省略号并在所有断点保留单位；跟随模型的定位循环继续按实际 `offsetWidth/offsetHeight` 自动避让。
- 隔离：不匹配 `.furnace-billboard` 和 `.core-group-row`，所以 121 点与左侧 28 变量不变；8094 页面和共享资源由部署器哈希保护。
- 验收：本地专项与悬停回归共 `11 passed`；远端页面/CSS HTTP 200，8093/8768 均监听。Chrome 重资源页本轮重载等待超时，视觉截图待刷新稳定后补录。

## Q-BF3D-8093-BILLBOARD-EMPHASIS-20260802

- 用户问题：扩大炉体点位广告牌，使点位信息更加醒目。
- 处理：仅对 8093 的 121 个可见 Billboard 设置 `1.22×` 适度比例；纹理、中文语义、实时数据和命中对象不变，8094 不受影响。
- 验收：Chrome 实际页面显示 `loaded/121/measured-121-8093/1.22/moderate-8093`；远端资源与本机 SHA-256 一致，服务和端口正常。
- 已知边界：独立 Chromium 冷启动仍可能遇到 8093 静态依赖 `ERR_EMPTY_RESPONSE`，该基础链路问题与尺寸实现分开追踪。

## Q-BF3D-8093-TOOLTIP-JITTER-20260802

- 用户问题：鼠标在密集点位附近轻微移动时，广告牌详情上下左右频繁颤动，要求修复并重新部署 8093。
- 结论：属于 tooltip jitter / hover flapping / hit-test thrashing；根因是三个写入路径竞争同一 DOM、坐标空间混用和逐帧最近点切换。
- 处理：[稳定悬停运行时](../高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js)、[部署器](../tools/remote_deploy_8093_stable_tooltip_hover.py)、[守卫停—改—启脚本](../tools/remote_guarded_redeploy_8093_tooltip.ps1)已完成，5 项测试通过。
- 部署边界：2026-08-02 已暂停并恢复且仅处理 `BFV4PreviewProxy8093`；8768 未停止，8093/8768 最终均监听，HTTP 200，8094/共享资源哈希未变。

## Q-IMES-ACCOUNT-PERMISSION-BURDEN-LINEAGE-20260726

- 用户问题：核查本机两个 IMES Vastbase 账号的权限分布，并尝试完善
  “烧结矿/炉料批次→料仓→入炉批次→炉次”精确谱系。
- 实测身份：`gl2#dmx` 只读6个运行/批次/原始化验对象；`lg_fq` 只读5个最终
  化验视图。两者 `transaction_read_only=on`，可见对象的写权限均为0。
- 已贯通：`batch_input` 的 `prodcentercode+lot+charge`、三个事件时间、
  24通道值和矿/焦汇总。异常炉次开堵口窗口内实读2号高炉18条事件，矿/焦
  各9条。
- 断点：数据库账号不可见料仓和变料历史；IMES Web 有 `pes_bin`、
  `pes_bin_material` 和配料方案接口，但本轮没有可用Web会话。炉次
  `sumbatchstart/end` 为空，不能用出铁时间窗冒充炉次—料批精确关系。
- 证据与方案：[权限和谱系审计摘要](../logs/imes_accounts_burden_lineage_audit_20260726.summary.md)、
  [可复跑审计程序](../tools/audit_imes_accounts_and_burden_lineage.py)。
- 结论：已形成可审计的批次事件层；精确谱系还必须补齐带有效期的
  通道—料仓—物料字典，以及炉次起止料批强键。未满足前只能标
  `estimated`，不得标 `exact`。

## Q-IMES-ABNORMAL-HEAT-332-20260726

- 用户问题：查清异常炉次 `2#20260726-332` 在 IMES 中的所有相关信息。
- 只读证据：[完整 JSON](../logs/imes_abnormal_heat_2_20260726_332.json)、
  [审计摘要](../logs/imes_abnormal_heat_2_20260726_332.summary.md)、
  [可复跑脚本](../tools/audit_imes_abnormal_heat_332.py)。
- 结论：这是跨午夜日期写错。主表开口时间被写成
  `2026-07-26 23:30`，堵口为同日 `00:43`，产生 `-1367` 分钟；三条称量、
  两条铁水化验和记录创建时间共同支持真实开口高度疑似为
  `2026-07-25 23:30`。
- 关联记录：`t_ipes_cond` 1条、`t_ipes_out_put` 3条、
  `t_qpes_inner_batch` 2条、铁水最终视图2条、`slag_inspection` 1条空占位；
  炉渣最终视图0条。铁量合计 `399.950 t`，铁水 Si 两样为 `0.20%/0.33%`。
- 边界：当日16条烧结矿数据没有炉次键，仅可作为时间背景；未对 IMES
  做任何写入。源数据修正应由 IMES 负责人执行并保留审计记录。

## Q-HEAT-SI-THERMAL-DIAGNOSIS-ALIGNMENT-20260726

- 用户问题：数据库仪表盘中的实际“热制度下行/热制度上行”判断，是否与同炉次
  铁水 Si 含量相对应。
- 核查口径：只读取得最近 96 个正式炉次，以同炉全部有效 Si 样本的中位数作为
  炉次 Si；诊断表按 `diagnosis_ts` 只保留 `updated_at/id` 最新版本。分别对齐
  开口前 120 分钟 `pre_tap` 和开口至堵口 `tapping`，计算每炉
  `raw_scores.hot - raw_scores.cold` 的平均值，并检查主诊断出现次数、Pearson/
  Spearman 相关、方向一致率、上下四分位和反例。96 炉均有 Si，92 炉在目标
  窗口有完整诊断分数，共覆盖 `2208` 条开口前诊断和 `1916` 条出铁过程诊断。
- 开口前 120 分钟结果：Si 与热减凉得分差的 Pearson `r=0.192`、Spearman
  `ρ=0.181`，以全体 Si 中位数为相对分界的方向一致率 `55.1%（49/89）`。
  热得分差最低/最高四分位的 Si 中位数均为 `0.30`，说明该提前窗口只有弱
  对应，不能用来声称 Si 已被当前诊断准确解释。
- 出铁过程结果：Pearson `r=0.324`、Spearman `ρ=0.336`，方向一致率
  `60.9%（56/92）`；热得分差最低四分位 Si 中位数 `0.29`，最高四分位
  `0.35`。这表明有符合冶金机理的正向趋势，但强度仅为弱到中等，仍不是
  一一对应。
- 主诊断样本稀少：92 炉中，出铁窗口只有 2 炉出现 `hot` 主诊断、5 炉出现
  `cold` 主诊断，其余 85 炉没有以二者为主诊断；开口前窗口为 1/5/86。
  因此不能用主标签组均值给出稳定阈值或生产判据。
- 反例：出铁窗口中 `2#20260721-265` 出现 `hot` 主诊断，但 Si 中位数仅
  `0.20`（三样范围 `0.20—0.36`）；`2#20260722-278` 和
  `2#20260720-255` 出现 `cold` 主诊断，但 Si 中位数分别为
  `0.355` 和 `0.35`。相反，`2#20260719-245` 出现 `hot` 且 Si 中位数
  `0.61`，方向一致，但同炉三样范围高达 `0.17—0.74`，显示样本阶段差异
  不能忽略。
- 根因与系统边界：当前 `cold/hot` 规则没有读取 Vastbase 铁水 Si，使用的是
  顶温趋势、炉体温度、出铁口温度代理、压差/透气性、风压、煤气利用率及
  操作热量变化。因此现有对应关系来自共同炉况机理，不是“Si 驱动诊断”。
  同时 `result_ts` 是结果判定时间，不是已确认取样时间，001/002/003 的现场
  取样阶段尚不明确。
- 结论：当前数据库证据支持“热制度得分整体升高时，Si 倾向升高”，尤其在
  出铁过程窗口更明显；但相关度、方向一致率和主标签样本量均不足以把 Si
  当作单独真值或验收当前冷热判断。生产化前应取得真实取样时间/罐次，
  以全部样本及阶段权重做更长时间回测，并把 Si 作为滞后校验量而不是即时
  控制输入。
- 数据与实现位置：[炉次聚合](../db_dashboard/heat_service.py)、
  [规则阈值](../炉况规则引擎/config/thresholds.yaml)、
  [规则权重](../炉况规则引擎/config/rule_weights.yaml)、
  [Si时间对齐边界](铁水硅炉况传感器数据集.md#3-防止标签泄漏)。核查全程
  只读，未修改诊断规则、数据库或生产服务。

## Q-SI-THERMAL-DIAGNOSIS-AND-MULTISAMPLE-20260726

- 用户问题：本机知识库如何利用铁水硅判断热制度上行/下行，现场如何调节
  生成的铁水硅，以及同一炉次多个 Si 试样是否在炉次仪表盘展示。
- 知识库结论：铁水 Si 是有滞后的综合结果指标。连续升高可作为热状态偏富余
  的佐证，连续下降可作为热状态走弱的提示，但都不能单独定性，必须同时核对
  铁水/渣铁温度、顶温、炉体温度、压差与透气性、料速、风温、富氧、喷煤、
  煤气流和原燃料变化。《三规二制》原文明确把“渣铁温度升高、生铁含硅升高”
  列为炉热征兆；炉凉原文列的是渣铁温度下降、硫升高、渣 FeO 升高、炉体温度
  普降等，没有把“低 Si”写成独立硬判据。
- 当前系统边界：实时 `cold/hot` 规则当前使用顶温趋势、炉体温度偏差、
  出铁口温度代理、风压、透气性、煤气利用率和操作热量变化，没有直接读取
  Vastbase 铁水 Si。内部键继续保留 `cold/hot`，正式界面显示为
  “热制度下行/热制度上行”。现有铁水 Si 数据集使用保守时间退让，可用于
  探索和建模基线，但在取得真实取样时间前不得宣称已经是生产 Si 预测或
  诊断金标准。
- 调控边界：Si 不是直接执行量。知识库给出的方向是通过风温、喷煤、富氧、
  风量/料速、焦炭负荷与净焦等热制度手段间接影响；必须先判定炉况阶段和
  顺行边界。热制度上行时知识库建议按程度减煤、酌情降风温，持续性偏热再
  调负荷；热制度下行初期强调先稳顺行，再分步补热。剧凉与初期向凉的喷煤、
  富氧策略不同，不得把一个动作套用于所有阶段；所有动作仍需高炉长确认。
- 仪表盘升级：`REQ-HEAT-SI-DISTRIBUTION-20260726` 已将列表和图表从
  “仅最后一个 Si”升级为全部样本散点、每炉中位数和最小—最大范围；详情继续
  逐条显示全部样号和 C/Si/Mn/P/S/Ti，并增加有效样本数、中位数、范围和极差。
  `2#20260725-329` 实测显示 3 条：
  `22607-329-001/002/003` 的 Si 分别为 `0.21/0.19/0.59`。
  当前代表中位数为 `0.21`，范围为 `0.19—0.59`。代码位置为
  [后端统计](../db_dashboard/heat_service.py)、
  [Si分布图与列表](../db_dashboard/heat.html)和
  [后端保留全部试样](../db_dashboard/heat_service.py)。
- 时间语义：当前 `result_ts` 是结果判定/审核时间，不是已确认取样时间；
  `001/002/003` 只表示同炉次试样记录顺序，不能擅自解释为第一罐、第二罐、
  复验样或出铁前中后段，也不应在缺少业务规则时静默平均。
- 页面竞态已修复：`selectHeat()` 使用递增 `detailRequestId`，旧响应只有在
  请求编号和当前选中炉次仍一致时才能渲染。初始详情未完成时立即点击 `329`
  的浏览器反例中，标题、选中行和三条样本始终保持为 `329`。
- 验证：2026-07-26 只读调用
  `/api/heat-detail?meltno=2%2320260725-329&window=pre_tap&group=core`
  返回 3 条试样及完整 Si 统计；Chromium 九视口、Firefox/WebKit 各四个代表
  视口和 Edge 冒烟均通过，DOM 和截图确认全部样本、中位数与范围可见。
  生产数据库、规则和控制系统均未写入。

## Q-IMES-SAMPLE-HEAT-RELATION-20260719

- 用户问题：`234` 批次与 `02/002` 试样是什么关系，为什么又称
  “检验批”“试样组”“第二个样次”，以及它们是否对应正式炉次。
- 数据源：铁水化验标签 `si_sample_no/si_result_ts/C/Si/Mn/P/S`，
  以及 IMES `public.t_ipes_cond` 的
  `meltno/opentime/closetime/tappingtime`。
- 实测结论：`22607-234-002` 的中间段 `234` 对应正式炉次
  `2#20260719-234` 的炉次尾号，末段 `002` 是该炉次下第 2 个试样
  记录，不是“02 炉次”或另一个检验批。2026-07-12～18 对齐的
  89 个正式炉次中，89/89 都找到相同的试样组尾号；每炉匹配
  1/2/3/4 个试样的炉次数分别为 9/39/32/9。
- 术语修正：“检验批”和“试样组”是未取得正式炉次对照前对中间段
  `NNN` 的备选称呼，不是两个独立层级；现统一称为炉次号或炉次样品组。
  `SSS` 只证明样品记录次序，不能单独证明第二罐、复验或具体取样阶段。
- 时间边界：234 炉次开口 `2026-07-19 00:30:00`、堵口
  `02:27:00`；`001/002/003` 的 `si_result_ts` 为
  `01:54:12/02:32:11/03:04:02`，但这是判定/审核时间，不是
  `takesampletime`，不得据此拆分炉次归属。
- 实现与证据：[试样号审计](../tools/audit_imes_sample_no.ps1)、
  [专项报告](../reports/试样号234炉次关系_20260719.md)、
  [7 天炉次对齐](../reports/出铁口温度炉次对齐_20260712_20260718/heat_alignment.csv)、
  [数据集口径](铁水硅炉况传感器数据集.md#31-试样号书写规则2026-07-19-实测)。
- 安全边界：IMES 和 PostgreSQL 均只读；未写数据库、未改 schema、
  未修改生产服务。

## Q-TAPHOLE-HEAT-INFERENCE-20260719

- 用户问题：能否分析 pSpace 中 1、2 号出铁口数据，推断具体炉次及对应
  出铁口时间。
- 数据源：pSpace 镜像
  `bf_sensor.one_minute_values` 的 `T_taphole_1/2`，以及 IMES
  `public.t_ipes_cond` 的 `meltno/opentime/closetime/tappingtime`。
- 实测结论：2026-07-12～18 两点各 10,080 个分钟值，对齐 89 个 2#
  正式炉次。≥100℃ 温度跳变在开口 ±15/±30/±60 分钟内只覆盖
  26/49/82 炉次；53/89 炉次在开口附近两条温度信号无法明确区分。
  因此温度可做候选窗口和交叉验证，不能单独恢复正式炉次号、精确开堵口
  时间或现场实际使用铁口。
- 推荐口径：正式炉次与开堵口时间直接取 IMES `t_ipes_cond`；pSpace
  温度作为该炉次的传感器特征。IMES 缺失时，必须再增加开口机、泥炮、
  铁口选择状态或现场日志才能形成生产标签。
- 实现与证据：[只读对齐工具](../tools/analyze_taphole_heat_alignment.py)、
  [专项测试](../tests/test_analyze_taphole_heat_alignment.py)、
  [7 天报告](../reports/出铁口温度炉次对齐_20260712_20260718/report.md)、
  [数据集边界](铁水硅炉况传感器数据集.md#32-12-号出铁口温度能否推断炉次2026-07-19-实测)。
- 安全边界：PostgreSQL 和 Vastbase 均只读；未修改 pSpace、IMES、
  数据库 schema、VPN 策略或生产服务。

## Q-IMES-WEB-ACCESS-AND-SAMPLE-NO-20260719

- 用户问题：检查 `http://10.10.181.209:8080/imes.web/` 为什么无法在
  网页访问，并解释铁水硅数据中每个试样号的书写规则。
- 网页结论：`.209:8080` 当前 TCP 可建连且走
  `10.10.0.0/16 -> Meta`，但 Chrome 返回 `ERR_EMPTY_RESPONSE`，
  curl 返回 `Empty reply from server`；问题发生在 TCP 建连后的
  HTTP 服务/访问路径层，不是 404、登录或验证码。220.12 同时不可达，
  本地 18080 备用转发无法建立，尚不能从第二来源最终区分 Meta 路径与
  IMES Web 服务端。
- 试样号结论：5,699/5,699 符合 `FYYMM-NNN-SSS`，炉号一致、
  无重复；后续通过正式炉次对齐确认 `NNN` 是月内炉次序号/正式
  `meltno` 尾号，`SSS` 是该炉次下的试样记录顺序。14 条跨自然月
  边界，故编号年月和结果判定时间仍不能替代真实取样、出铁时间。
- 实现与证据：[试样号只读审计](../tools/audit_imes_sample_no.ps1)、
  [数据集口径](铁水硅炉况传感器数据集.md#31-试样号书写规则2026-07-19-实测)、
  [IMES 网络排障](IMES网络与Vastbase直连排障.md)。
- 安全边界：只读核查；未登录 IMES、未提交账号或验证码、未写生产库、
  未修改 VPN/代理/服务器配置。

## Q-IMES-GRANTED-VIEWS-DATA-DICTIONARY-20260716

- 用户需求：确认截图授予 `lg_fq` 的五个视图确实能取数，使用该账号实查数据，并把每个变量解释加入 PT 的 IMES 配置和 MES 数据集说明。
- 真实结论：`lg_fq` 成功登录 `10.10.181.195:5432/vastbase`，会话 `transaction_read_only=on`；五个视图均存在且 `SELECT=true`，共核查 123 个视图字段。行数分别为 49,356、49,356、10,179、4,939、212,136。
- 关键辨析：`v_qpes_mat_final` 与完整铁水视图同源，不是原料成分；`v_qpes_steel_final` 是炼钢试样；炉渣视图真实拼写为 `v_qpes_slag_insoection_final`；化学值和时间大多存为文本。
- 实现与证据：[只读审计脚本](../tools/audit_imes_granted_views.py)、[审计 JSON](../logs/imes_granted_views_audit_20260716.json)、[专项测试](../tests/test_audit_imes_granted_views.py)。
- 文档落点：[PT 连接与授权视图](../PT/imes.md#lg_fq-已授权查询视图2026-07-16-实测)、[五视图逐变量字典](mes数据集.md#9-lg_fq-五个授权视图与逐变量字典2026-07-16)、[AGENTS 长期规则](../AGENTS.md)。
- 安全边界：未执行截图中的 `CREATE ROLE`/`GRANT`，未执行 DDL/DML；密码未进入审计报告、普通文档或控制台输出。

## Q-IMES-VASTBASE-CONNECTION-CONFIG-20260716

- 用户需求：把一期 MES 正式库的 Vastbase 配置加入 `AGENTS.md`，并把直连及 220.12 转发连接方式保存在 `PT` 目录。
- 配置结论：目标为 `10.10.181.195:5432/vastbase`，Navicat 连接名为“一期MES正式库”；截图所示 `vbadmin` 按高权限管理账号处理，业务只读角色为 `lg_fq`（小写字母 `l` 开头）。首次误按数字 `1g_fq` 登录返回认证失败，修正后重新核查。
- 安全边界：用户后续明确授权把完整凭据保存到本机 `PT/imes_vastbase.local.env`；该文件由 `.gitignore` 排除，通过加载脚本注入当前进程，不在普通 Markdown、日志或命令行中重复口令。未执行生产连接、建角色、授权、DDL 或 DML。
- 文档与配置落点：[AGENTS.md 长期规则](../AGENTS.md)、[PT 连接方式](../PT/imes.md#一期-mes-正式库-vastbase-连接方式2026-07-16)、[本机加载器](../PT/load_imes_vastbase_local.ps1)、[数据库账号配置说明](数据库账号配置说明.md#一期-mes-正式库-vastbase)。
- 验证方式：静态核对目标地址、端口、数据库名、两种连接路径和环境变量；确认敏感配置被 Git 忽略；在隔离 PowerShell 子进程加载配置，只输出 `password=SET`，不输出密码值。

## Q-8093-OVERVIEW-ADAPTIVE-CLIP-20260716

- 用户问题：页面在不同显示器尺寸下反复出现文字截断，首页部分核心变量不可见。
- 根因：后置 `.overview-three-column-v12` 固定最小栏宽覆盖旧窄屏规则；核心变量行固定列宽超过实际左栏；`1280×720` 未命中原 `min-width:1281px` 的短屏压缩条件。
- 修复：[总览最终响应式覆盖](../高炉前端数据/frontend_dashboard_v3.server.html#L10656) 将桌面改为可收缩三栏，`<1280px` 改为纵向单列，核心变量使用容器查询和弹性列，并补齐手机历史基线图单列规则。
- 验收：[专项脚本](../tools/verify_overview_adaptive_layout.py) 覆盖总览、炉况诊断、优化建议、趋势分析、智能问答；Chromium `45/45`，Firefox/WebKit/Edge 合计 `45/45`，无横向溢出、核心变量两页各 14 行无裁切、详情弹层可开关。
- 运行边界：本次基于本机静态页面验证，未写生产数据库、未修改接口、未部署 220.12。

## Q-8093-THERMAL-DIAGNOSIS-NAMING-20260716

- 用户需求：将前端页面中的炉热、炉凉改为“热制度上行”“热制度下行”，并把规则纳入项目约束。
- 处理边界：这是现场展示名称调整，不调整 `hot/cold` 内部键、诊断得分、规则阈值、数据库历史快照或 WebSocket/API 契约。
- 落点：[8093 正式页面](../高炉前端数据/frontend_dashboard_v3.server.html#L10457)、[front2 页面](../高炉前端数据/front2/frontend_dashboard_front2.server.html#L2289)、[AGENTS.md 展示约束](../AGENTS.md)；建议、证据、告警、问答渲染文本亦同一映射。
- 验收入口：[verify_8093_thermal_diagnosis_display.py](../tools/verify_8093_thermal_diagnosis_display.py)，以 8093 的真实 8768 数据验证新名称可见、旧名称不可见及页面基本可用性。

## Q-8093-CORE-SPARK-VISIBILITY-20260716

- 用户问题：为什么实际打开 8093 总览后看不到核心指标的迷你曲线。
- 只读核查结论：远端 `BFV4PreviewProxy8093`、`BFV4PreviewWs8768` 均为 `Running`，8093/8768 均监听；浏览器实际连到 `ws://10.30.220.12:8768/`。核心曲线的 ECharts canvas 已创建且存在非透明绘制像素，并非服务未更新、WebSocket 未连接或数据完全为空。
- 根因：为避免核心指标末行裁切，详情功能的紧凑断点把 `.core-spark-button` 压到 `height:15px!important`；远端 Chromium `1366×768` 实测按钮约 `94×19px`、画布约 `92×17px`。虽然有曲线，视觉高度不足，现场很容易把它当作空白或无法点中的区域。
- 代码入口：[默认 8768 WebSocket 与历史缓冲区](../高炉前端数据/frontend_dashboard_v3.server.html#L8639)、[迷你曲线渲染](../高炉前端数据/frontend_dashboard_v3.server.html#L9950)、[点击入口与详情弹层](../高炉前端数据/frontend_dashboard_v3.server.html#L10445-L10448)、[造成过度压缩的响应式样式](../高炉前端数据/frontend_dashboard_v3.server.html#L10452)。
- 最小修复建议：将核心曲线交互入口在紧凑断点保持至少约 `28px` 高，并通过压缩非关键列或让行高随之增加来保留可读折线；不能只增大 canvas 而继续由父级裁切。修复后需用 1366×768、676px 宽窄屏和现场 Edge 复验曲线可见、可点击及无末行裁切。

## Q-DIAG-COLD-HOT-SENSITIVITY-20260714

- 用户问题：正常顺行情境下一天内为什么会多次出现炉凉和炉热，炉凉/炉热判断是否过于敏感。
- 核查对象：`bf_sensor.diagnosis_snapshots` 只读查询，生产环境当前诊断源为 `source.rule_profile=full115`。
- 代码/配置入口：[诊断调度配置](../自动诊断服务/config.yaml#L20-L25)、[诊断调度器](../自动诊断服务/diagnosis_scheduler.py#L202-L318)、[诊断结果表](../自动诊断服务/schema.sql#L3-L31)、[炉凉/炉热阈值](../炉况规则引擎/config/thresholds.yaml#L68-L98)、[炉凉/炉热权重](../炉况规则引擎/config/rule_weights.yaml#L49-L65)。
- 2026-07-14 生产库日内统计：共 287 条 5 分钟诊断点，`normal=144`、`cold=96`、`hot=47`；`cold` 分成 26 段，平均约 18.5 分钟；`hot` 分成 17 段，平均约 13.8 分钟。
- 敏感性信号：`hot` 中 29 条分数在 40 分边界附近，42 条低于 45 分；`cold` 中 21 条低于 45 分；43 条 `normal` 的原始异常分曾高于 `normal` 分但未触发主标签，说明存在异常触发门槛，但缺少跨点持续性/滞回确认。
- 代表样本：`2026-07-14 00:10` 主诊断 `cold`，`cold=49.21`、`normal=45.35`，证据为低炉体温度、顶温下降、补热不足；`2026-07-14 00:40` 主诊断 `hot`，`hot=42.28`、`normal=28.75`，证据为高炉体温度、顶温上升、透气性转差；`2026-07-14 21:45` 主诊断 `hot`，分数为边界 `40.00`。
- 初步结论：炉凉/炉热不是空数据或重复版本造成；数据覆盖率为 1.0，窗口为 60 分钟，间隔为 5 分钟，基线为 30 天。频繁切换主要来自 5 分钟逐点判定、阈值边界较低，以及炉体温度/顶温趋势/操作补热指标对分数贡献较大；建议后续在主标签发布层增加持续性、滞回和边界置信分层，而不是直接删除炉凉/炉热规则。

## Q-DIAG-NORMAL-SCORE-TUNING-20260715

- 用户问题：如何让 `正常顺行` 分数总体更高，如何修改正常权重，并提高异常分数入选阈值。
- 调整对象：当前仓库 `炉况规则引擎/config/thresholds.yaml`、`炉况规则引擎/config/rule_weights.yaml`，以及实际运行版 V4 的同名配置和 `炉况规则引擎/engine/resolver.py`。
- 正常分数公式仍为 `100 * sum(g_N(feature, threshold) * weight) / sum(weight)`；本次把 `normal` 稳定阈值从 `0.8/0.18/0.25/0.5` 放宽到 `1.0/0.22/0.30/0.6`，让轻微波动下的稳定度更高。
- 正常权重从 `15,15,15,10,15,20,10,5` 调整为 `18,18,18,12,12,14,10,8`，即提高顶压、压差、透气、冷风压力和料线稳定项占比，降低炉顶温度离散和炉身温度单项对正常分的拖拽。
- 异常主炉况候选阈值从 `score >= 40` 提高到 `score >= 45`；次炉况条件保持 `second_score >= 55` 且与主炉况差值 `< 10`，只是把数字改成 resolver 内部常量，便于后续继续调参。

## Q-DIAG-RECENT-10D-DISTRIBUTION-20260715

- 用户问题：数据库中已有实际传感器数据，测试最近 10 天实际炉况分布。
- 核查口径：`bf_sensor.diagnosis_snapshots` 按同一 `diagnosis_ts` 只取 `updated_at/created_at/id` 最新快照；窗口使用数据库最新诊断点往前 10 天，即 `(2026-07-05 00:10, 2026-07-15 00:10]`，共 `2880` 个 5 分钟诊断点。
- 数据质量：全部为 `source.rule_profile=full115`、`rule_profile_variables=all_enabled_physical`、`baseline_days=30`、`window_minutes=60`，平均 `coverage_ratio=1.0000`。
- 当前落库分布：`normal=2294`（`79.7%`）、`cold=333`（`11.6%`）、`hot=252`（`8.8%`）、`channel=1`（约 `0.03%`）。
- 仅用现有 `raw_scores` 模拟异常主炉况阈值从 `40` 提到 `45` 后：`normal=2603`（`90.4%`）、`cold=217`（`7.5%`）、`hot=60`（`2.1%`）；会有 `116` 个 `cold->normal`、`192` 个 `hot->normal`、`1` 个 `channel->normal`。
- 按日看异常集中在 `2026-07-12` 到 `2026-07-14`：当前正常率分别为 `55.9%`、`50.7%`、`50.3%`；45 分门槛模拟后分别提高到 `78.1%`、`74.0%`、`72.2%`。
- 限制说明：上述 45 分门槛模拟可直接由落库 `raw_scores` 复算；正常顺行阈值/权重变更会改变 `raw_scores.normal` 本身，需要调度器指向可运行的 V4 规则引擎并 dry-run 重算后才能得到完整新规则分布。当前仓库 `炉况规则引擎` 缺少 `main.py`，实际可运行规则引擎位于 `D:\文件\服务器实际运行版V4\炉况规则引擎`。

## Q-DIAG-RECENT-6H-DISTRIBUTION-20260715

- 用户问题：部署 `N>=A+3` 竞争规则后，最近6小时炉况诊断分布如何。
- 查询口径：生产库 `bf_sensor.diagnosis_snapshots` 同一 `diagnosis_ts` 只取最新版本，以数据库最新诊断点 `2026-07-15 07:40:00` 为终点，统计 `(01:40, 07:40]`。
- 完整性：共72个五分钟点，期望72点，平均 `coverage_ratio=1.0000`。
- 主诊断：正常顺行56点（77.78%），平均分57.22；炉凉16点（22.22%），炉凉分均为53.31；没有炉热或其他异常主诊断。
- 次诊断：12点为“主正常、次炉凉”，占全部点16.67%，表明新灰区竞争规则已实际产生次诊断。
- 炉凉分段：`02:55-03:15` 5点、`05:40-05:55` 4点、`06:05-06:30` 6点、`07:15` 1点；主标签共切换8次。
- 炉凉为主时正常分范围35.56至56.14、均值47.64；最新 `07:40` 为正常顺行60.35分。最后一段仅一个五分钟点，说明3分竞争门槛不等同于连续两点确认。

## Q-DIAG-DATA-WINDOW-BASELINE-20260715

- 用户问题：炉况测试是否需要 30 天历史基线、最近 1 小时数据计算派生特征以及当前数据；数据库是否具备这些历史数据。
- 程序口径：`自动诊断服务/config.yaml` 配置 `baseline_days=30`、`window_minutes=60`；`diagnosis_scheduler.py` 在诊断点 `ts` 上构造 `baseline_start = ts - 60min - 30days`、`baseline_end = ts - 60min`、`window_start = ts - 60min`、`window_end = ts`，再用 `FeatureAggregator.aggregate(current)` 计算近 60/30/20/15 分钟派生特征。
- 数据库核查：`bf_sensor.one_minute_values` 当前范围为 `2026-02-08 19:06:00` 到 `2026-07-15 00:14:00`，共 `18,627,678` 行、`115` 个物理点；足够支撑最新诊断点的 30 天历史基线和 1 小时窗口。
- 最新诊断点 `2026-07-15 00:10:00` 的诊断窗口为 `2026-07-14 23:10:00` 到 `2026-07-15 00:10:00`，115 个启用物理点都有窗口数据；诊断快照记录 `coverage_ratio=1.0`、缺失变量数 `0`。
- 最新基线日 `2026-07-15` 的 30 天基线窗口为 `2026-06-15 00:00:00` 到 `2026-07-14 23:59:00`；`daily_baselines` 有 `115` 个启用物理点对应基线，另有派生/聚合基线变量 `T_top`。最近 10 个基线日均有基线记录，平均覆盖率约 `0.7147~0.7238`，低覆盖点主要是个别炉喉/炉身温度点，但并未导致最新诊断缺变量。

## Q-DIAG-8093-RULE-DEPLOYMENT-20260715

- 用户问题：正常顺行提分、异常入选阈值提高这组规则是否已经部署到 8093 服务器。
- 核查对象：远端 `10.30.220.12` 的 8093 预览目录 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW`；服务 `BFV4PreviewProxy8093` 与 `BFV4PreviewWs8768` 均为 `Running`、`Automatic`。
- 核查结论：尚未部署到 8093。远端 `rule_engine` 目录不存在；远端中文 `炉况规则引擎` 目录仍是旧规则，`engine/resolver.py` 仍为 `score >= 40`，`config/rule_weights.yaml` 中正常权重仍为 `15,15,15,10,15,20,10,5`，`config/thresholds.yaml` 中正常稳定阈值仍为 `0.8/0.18/0.25/0.5`。
- 当前已修改位置仍在本机当前仓库和本机 `D:\文件\服务器实际运行版V4\炉况规则引擎`；若要让 8093 生效，需要把这三份规则文件同步到远端 8093 目录，并重启涉及规则加载的诊断/预览服务。
- 2026-07-15 00:25 已同步到 8093 预览目录并备份旧文件到 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\rule_engine_20260715_002505`；远端 `resolver.py` 已为 `main_candidate_threshold = 45.0`，正常权重为 `18,18,18,12,12,14,10,8`，正常稳定阈值为 `1.0/0.22/0.30/0.6`，`python -m py_compile` 通过。
- 热重载结论：8093/8768 服务没有规则文件监听；Python 已导入模块不会自动重载。已受控重启 `BFV4PreviewWs8768` 和 `BFV4PreviewProxy8093`，重启后两服务均 `Running`，端口 `8768/8093` 均监听，`http://127.0.0.1:8093/` 返回 `200`。
- 影响边界：8093 预览目录已生效；但当前真正写入 `bf_sensor.diagnosis_snapshots` 的计划任务 `\GL02AutoDiagnosis\RunOnce` 指向 `F:\高炉炼铁项目-real-sensor-v2_V3\auto_diagnosis_service\run_auto_diagnosis_once.ps1`，不是 8093 预览目录。若要让后续数据库落库诊断也按新规则生成，需要另行同步实际计划任务目录。
- 2026-07-15 00:34 已继续同步实际落库计划任务目录 `F:\高炉炼铁项目-real-sensor-v2_V3\rule_engine`，备份旧文件到 `F:\高炉炼铁项目-real-sensor-v2_V3\backups\rule_engine_20260715_003415`；远端 `rule_engine/engine/resolver.py` 已为 `main_candidate_threshold = 45.0`，`rule_engine/config/rule_weights.yaml` 与 `rule_engine/config/thresholds.yaml` 已同步新正常权重和新稳定阈值，`python -m py_compile` 通过。
- 实际落库链路验证：`\GL02AutoDiagnosis\RunOnce` 当前是一次性计划任务，每次执行拉起新 Python 进程，不存在需要热重载的常驻诊断进程；同步时任务状态为 `Ready`，无需先停止。远端导入 `F:\高炉炼铁项目-real-sensor-v2_V3\rule_engine` 验证 `threshold=45.0`、`case_44=normal`、`case_45=hot`。
- 已手动触发一次 `\GL02AutoDiagnosis\RunOnce`，任务从 `2026-07-15 00:36:36` 运行后回到 `Ready`，`LastTaskResult=0`。数据库最新写回快照为 `diagnosis_ts=2026-07-15 00:35:00`、`updated_at=2026-07-15 00:36:39.94875`、`main_label=normal`、`main_score=56.36`、`rule_profile=full115`、`coverage_ratio=1.0`、缺失变量 `0`。
- 2026-07-15 00:54 继续核查“规则已更新但页面仍显示炉凉”：`00:45` 快照确为 `cold=50.00`，达到新异常门槛 45，因此当时显示炉凉是新规则的真实结果；`00:50` 快照为 `cold=43.74`、`normal=29.65`，由于异常分低于 45，主标签已回到 `normal`。8767 最新 `init` 已返回 `diagnosis_ts=00:50`、`main_label=normal`，同一URL的 Chromium 实测显示“正常顺行/维持当前顺行”。旧页面停留炉凉的原因是它在 `00:48` 加载时数据库最新诊断仍是 `00:45`，而页面此前只显示传感器时间。优化页现同时显示“诊断时间”和“数据时间”，避免把5分钟诊断档位与1分钟数据刷新混淆。

## Q-OPT-FULL-ENGINE-DOCS-PT-20260715

- 用户问题：完整建议引擎原始契约是否已经写入 PT 文件夹、docs，以及是否有独立 `suggestionengine` 或类似代码目录保持对应实现。
- 核查结论：代码已落地为独立目录 `调控结论生成引擎`，未另建 `suggestionengine`；8767 已通过 `自动诊断服务/recommendation_adapter.py` 和 `自动诊断服务/local_pg_ws_bridge.py` 接入，但此前 docs/PT 没有完整可追踪说明。
- 已补充文档：[docs 可追踪说明](调控结论生成引擎可追踪说明.md)、[PT 交接说明](../PT/调控结论生成引擎可追踪说明.md)，并在 [automation_traceability](automation_traceability.md) 追加 `REQ-OPT-FULL-ENGINE-20260715`。
- 代码映射：八类动作模板在 `调控结论生成引擎/recommendation/action_templates.py`，严重度在 `severity_mapper.py`，主次组合在 `combination.py`，安全门禁在 `safety_gate.py`，8767 适配在 `自动诊断服务/recommendation_adapter.py`，payload 注入在 `自动诊断服务/local_pg_ws_bridge.py`。
- 验证入口：`python tools\verify_8093_recommendation_engine_contract.py`，覆盖八类炉况、组合规则、安全门禁、8767 `recommendation_status` 和前端绑定。
- 2026-07-15 00:52 再次做部署闭环复核：8093 预览目录和 V3 实际落库目录的 `resolver.py`、`rule_weights.yaml`、`thresholds.yaml` 三个 SHA-256 均与本机 V4 修复版一致；两处均确认主异常门槛 `45`、次炉况门槛 `55`、主次分差 `<10`，远端 `py_compile` 通过。读取规则的 8768 数据桥进程启动于 `00:26:35`，晚于文件同步时间 `00:25:10`，8093 代理进程启动于 `00:48:09`，不存在运行进程继续缓存旧规则的问题。`BFV4PreviewProxy8093`、`BFV4PreviewWs8768` 均为自动启动且正在运行，`8093/8768` 均监听；远端本机和运维本机访问 `http://10.30.220.12:8093/` 均为 HTTP `200`。实际落库任务最近一次 `2026-07-15 00:51:51` 执行结果为 `0`，状态已回到 `Ready`。
- 2026-07-15 01:10 已把完整建议引擎部署到 220.12 的 8093 V4 预览目录：页面、`local_pg_ws_bridge.py`、`recommendation_adapter.py` 和独立 `调控结论生成引擎` 同步完成，`BFV4PreviewProxy8093/BFV4PreviewWs8768` 重启后均为 `Running`。远端 8768 实测当前炉况 `cold`，建议状态 `ready`，引擎版本 `v4-complete`，目标为“先稳顺行，再补热，防止风口灌渣”，共返回 6 条结构化动作；回退目录为 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\full_recommendation_engine_20260715_011058`。

## Q-DIAG-SELECTION-NORMAL-CALIBRATION-20260715

- 用户问题：分析主炉况/次炉况选择是否合理，核查正常顺行分数偏低原因，并优先用历史数据测试提高方案。
- 只读历史回放：`2026-06-15 01:15:00` 至 `2026-07-15 01:10:00` 共 `8640` 个五分钟点；最高异常分 `<45` 的正常代理点 `7597` 个。当前正常分中位数 `49.03`，`31.7%` 低于 40。
- 根因：正常规则对三段炉体温度波动和十层圆周变异系数均取最大值；正常代理点中炉体温度项 `35.3%` 清零、圆周均衡项 `80.9%` 清零。截图对应 `2026-07-15 00:50:00`，`normal=29.65`、`cold=43.74`，炉体温度、圆周均衡、料线三项贡献均为零。
- 规则审查：主炉况只用异常 `>=45` 门槛且不与正常分竞争；次炉况 `>=55` 且分差 `<10`，30 天仅触发 `13/8640` 点；声明的优先级未真正参与并列消解，状态机计算结果未进入最终输出且每个诊断点都会重建引擎。
- 候选回放：仅改权重后正常代理点中位数 `54.75`、低于 40 占 `25.6%`；改用炉体 P75/圆周 P80 并适度放宽阈值后中位数 `62.06`、低于 40 占 `6.0%`。更宽松方案会使 `72.6%` 的正常代理点达到 60，存在过度抬分风险。
- 适度阈值 + 稳健聚合的一月分布：正常代理点 `7597` 个，均值 `59.06`、P10 `42.79`、中位数 `62.06`、P90 `71.00`；其中 `60-69` 占 `43.58%`，`70-79` 占 `13.31%`，`50-59` 占 `19.48%`，`40-49` 占 `17.64%`，低于 40 共 `5.99%`。
- 主炉况候选策略“异常 `>=60` 直接触发；`45-59` 需至少高于正常分 5 分；连续两个五分钟点确认”在 30 天回放中将切换次数从 `368` 降至 `221`，小于 15 分钟异常段从 `67` 降至 `25`；没有炉长人工标签，暂不据此修改生产规则。
- 完整报告：[炉况主次选择与正常顺行分数审计](../logs/diagnosis_selection_normal_score_audit_20260715.md)。
- 2026-07-15 用户确认部署“适度阈值 + 稳健聚合”版本：炉体三段改取 P75、十层圆周改取 P80，阈值改为 `1.25/1.25/1.25/1.25/0.28/1.25/0.38/0.80`，权重及主次竞争规则不变。已同步 8093 预览和 V3 实际落库目录，双目录远端验证通过；落库任务结果 `0`，随后自然调度生成的 `01:35` 快照 `normal=61.64` 与同一特征复算一致。完整三版参数、竞争公式、备份和哈希见 [正常顺行积分与主次炉况竞争规则汇总](正常顺行积分与主次炉况竞争规则汇总.md)。

## Q-DIAG-NORMAL-ABNORMAL-CONFLICT-20260715

- 用户问题：异常炉况高于45时正常顺行分是否仍可能很高，过去一个月是否发生，冲突代表什么。
- 复核口径：固定窗口 `2026-06-15 01:15:00` 至 `2026-07-15 01:10:00` 共 `8640` 点；使用当前已部署 P75/P80 正常规则对历史 `feature_snapshot` 重新计算，不复用部署前旧版 `raw_scores.normal`。
- 结果：异常最高分 `>=45` 共 `1043` 点；正常分高于最高异常分 `594` 点（`56.95%`），正常分仍 `>=60` 有 `409` 点（`39.21%`）。冲突分类为炉凉 `514`、炉热 `55`、边缘发展 `25`。
- 边界：异常 `>60` 的 `211` 点中，最终正常分最高 `39.97`，没有点达到40，强异常抑制有效；异常恰好等于60的9点中有4点正常分仍高于等于60，因为抑制条件是严格 `>60`。
- 解释：正常分衡量最近窗口相对30天基线的波动稳定度，异常分衡量水平、趋势和事件偏离；两者不是互斥概率。代表点 `2026-07-03 07:35` 为 `normal=89.90/cold=50.38`，表示顶压、压差和透气性很稳，但炉体温度、风压和补热水平稳定地偏冷。
- 建议：页面区分“运行稳定度”和“异常诊断分”；若要求主炉况竞争互斥，应在45-60灰区加入正常分差和连续确认，而不是只为视觉一致压低正常分。完整数据见 [冲突复核](../logs/diagnosis_selection_normal_score_audit_20260715.md#异常达到45后的正常分冲突复核)。

## Q-DIAG-NORMAL-ABNORMAL-COMPETITION-DEPLOY-20260715

- 用户需求：在异常 `45-60` 灰区允许“主正常、次异常”，并用 `N>=A+3` 消解正常与异常冲突；部署到 220.12 的 8093 预览和实际诊断落库链路。
- 实现：[Resolver.resolve](D:/文件/服务器实际运行版V4/炉况规则引擎/engine/resolver.py) 新增 `strong_abnormal_threshold=60` 与 `normal_lead_margin=3`。`A<45` 为正常主诊断；`45<=A<60` 且 `N>=A+3` 时主正常、次异常；`A>=60` 或正常领先不足3分时异常为主。
- 保持项：异常为主时，第二异常仍需 `>=55` 且与第一异常分差 `<10`；没有引入连续两个五分钟点确认。
- 30天回放：`8640` 点中正常主诊断 `7595->8140`，异常主诊断 `1045->500`，主标签切换 `369->294`；“主正常、次异常”共 `558` 点。小于15分钟异常段 `66->81`，说明本规则不能替代持续性状态机。
- 验证：[专项边界测试](../tools/verify_resolver_normal_abnormal_competition.py) 覆盖 `44.99/45/59.99/60`、恰好领先3分、领先不足3分和第二异常规则；本机及远端两个目录均通过。
- 部署：双目录 `resolver.py` SHA-256 均为 `F90BF6CE6D19505422038E9B3ED2EB92E69320343DB957D2BCB092667CCD3BBE`；预览与落库备份时间戳均为 `20260715_020445`。8768 重启后运行，8093 HTTP 200。
- 落库：`\GL02AutoDiagnosis\RunOnce` 于 `02:08:08` 正常结束，结果码0；新快照 `02:05` 为 `N=36.12/A=33.31`，正确输出主正常、无次诊断。完整公式和备份位置见 [规则汇总](正常顺行积分与主次炉况竞争规则汇总.md#2026-07-15-0204-正常异常竞争规则部署)。

## Q-8094-FURNACE-ASSET-SYNC-20260715

- 用户问题：本机 8094 页面里的实际 8 张炉况图片是否已经放到 220.12 对应目录，并要求再次同步。
- 同步来源：本机 [front2 炉况图片目录](../高炉前端数据/front2/assets/furnace-conditions/)，文件为 `normal.png`、`lowline.png`、`edge.png`、`center.png`、`channel.png`、`cold.png`、`hot.png`、`column.png`。
- 同步目标：220.12 8093 预览页实际引用的静态目录 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\assets\furnace-conditions`；远端页面引用 `/assets/furnace-conditions/${name}`。
- 2026-07-15 01:18 已通过 `tools\remote_22012_exec.py --upload` 重新上传 8 个 PNG；远端 `Get-FileHash` 确认大小和 SHA-256 与本机一致。
- 验证：`http://10.30.220.12:8093/assets/furnace-conditions/*.png` 八个 URL 全部返回 `200 image/png`，大小分别为 `2127071/2293674/2369364/2378266/2335123/2279142/2411181/2311097` 字节；`python tools\verify_8093_diagnosis_furnace_assets.py --base-url http://10.30.220.12:8093` 返回 `ok=true`、`http_assets=true`。

## Q-8093-DECISION-BASIS-DISPLAY-20260715

- 用户问题：去掉参数优化页“版本：v4-complete”，并判断当前固定四指标加一句动作理由的“决策依据”是否合理。
- 结论：版本号属于接口与运维审计元数据，不应占用炉长决策区；旧决策依据固定展示总压差、顶压、透气性、顶温，对低料线、管道、崩滑料等炉况并不匹配，而且文字随候选动作选择变化，容易把动作理由误认为诊断依据。
- 修改：版本号只保留在 8768 `recommendation.engine_meta.version`；前端按八类炉况选择四个证据指标，并固定展示“规则判据/处置逻辑”。点击下方建议候选只更新建议详情，不再改变上方诊断依据。
- 部署验证：220.12 8093 HTML SHA256 从 `8B5871DBA4A567DEB7253C8C666A9881628D1832D1DB52532E8068D910453C6E` 更新为 `C4B621E54BFEFCAC4C14DA11E0FDC8B754DD8A8B967CC0FD881260615B2640F1`；`BFV4PreviewProxy8093=Running`、8768 持续监听、HTTP 200。远端 `1366×768` 验证版本不可见、证据卡 4 张、依据不随动作点击变化，无横向溢出、文字裁切、页面或控制台错误。

## Q-8093-OVERVIEW-OPTIMIZATION-CONSISTENCY-20260715

- 用户问题：8093 参数优化页的建议是否与首页建议一致。
- 当前结论：已统一。首页与参数优化页都直接调用 `bfRecommendationEngineView(diagnosis)`，消费 8768 `diagnosis.recommendation` 的同一标准化动作数组。
- 首页只截取 `engine.actions.slice(0,3)`：标题使用真实 `action.name`，摘要使用 `action.stage + action.reason`；不再使用固定的“优化送风制度/调整布料策略”等标题。参数优化页继续展示前 4 条完整候选及现场边界。
- 状态边界：首页在引擎等待时显示“等待完整建议引擎返回”，失败时显示“建议引擎暂不可用，请进入参数优化页查看状态”，不再退回本地拼装建议。
- 验证：远端 220.12 的 `1280×720`、`1366×768`、`1920×1080` 均实测首页三条标题与参数优化页前三条逐字一致，无横向溢出、卡片裁切、页面错误或控制台错误；截图位于 `logs/8093_overview_shared_recommendations_remote_*.png`。

## Q-8093-OPTIMIZATION-PANEL-DYNAMIC-20260715

- 用户问题：参数优化建议页各板块如何讲解；炉况诊断变化后哪些内容会变化。
- 页面入口：[标准化建议视图与参数优化页](../高炉前端数据/frontend_dashboard_v3.server.html#L2374-L2404)。页面接收 8768 的诊断、建议和传感器缓冲区；前端只做排序、格式化、趋势绘制和状态提示。
- 诊断驱动项：顶部总体状态/告警，左侧炉况等级、运行状态、异常信号和诊断时间，中部决策目标、复查周期、证据指标组合、规则判据/处置逻辑，右侧安全门禁/现场确认，以及底部四条标准化引擎建议、执行阶段和现场边界。2026-08-06 按现场要求统一取消页面上的诊断把握百分比展示；底层诊断得分仍保留用于规则计算、趋势和审计，不再作为“100%”结论呈现。
- 实时数据驱动项：决策依据卡和右侧固定监测指标的当前值、15分钟变化、微型趋势，以及底部四条风险趋势和数据时间；这些通常随1分钟数据更新，即使主炉况没有切换也会变化。
- 固定项：右侧监测变量固定为总压差、综合顶压、透气性指数、综合顶温、煤气利用率；底部趋势固定取其中前四项；页面布局、只读边界和生产控制不因炉况改变。
- 建议生成链：[RecommendationEngine.generate](../调控结论生成引擎/recommendation/core.py#L22-L57) 先按主炉况选择八类动作模板和严重度，再应用[主次组合规则](../调控结论生成引擎/recommendation/combination.py#L8-L31)与[安全门禁](../调控结论生成引擎/recommendation/safety_gate.py#L24-L74)。当前显式组合包括低料线+炉凉、炉凉+边缘发展；安全门禁可能把强制动作置于普通建议之前。
- 时间口径：诊断快照按5分钟档位更新，传感器缓冲通常按1分钟更新，因此页面上的“诊断时间”和“数据时间”可以不同；候选建议点击只改变当前查看详情，不会重新计算诊断或执行生产控制。

## Q-IMES-DATA-SOURCE-20260715

- 用户问题：把 IMES/Vastbase 账号信息加入 docs 与 `PT/imes.md`；判断基于 `2gldmx` 如何获取数据，以及能否取得对应程序源码。
- 连接结论：IMES Web 为 `http://10.10.181.209:8080/imes.web/`；仓库既有 Vastbase 目标为 `10.10.181.195:5432/vastbase`。2026-07-15 两端 TCP 均可达，Web 首页 HTTP 200，未登录 desktop 返回 302 到登录页。
- 账号结论：`2gldmx` 已成功登录 Web，但直连既有 Vastbase 目标返回 `Invalid username/password, login denied`，所以它不能当数据库账号使用。明文口令未写入仓库。
- Web 契约：登录页向 `POST /imes.web/login.do` 提交 `username/password/captchaInput`，成功后进入 `/imes.web/mes/desktop.do` 并使用 `JSESSIONID`；账号可见 10 个业务菜单。12 个已验证查询数据集统一使用 POST 表单，分页参数 `_size/_index`，响应为 `{total,rows}` 或数组。
- 新增程序：[Web 白名单只读导出:L41-L485](../tools/export_imes_web_readonly.py#L41-L485) 与 [专项测试:L42-L163](../tests/test_export_imes_web_readonly.py#L42-L163)；现有程序还有 [Vastbase 直连导出](../tools/export_vastbase_direct.py)、[用户批准保留硬编码的历史本机特例](../tools/export_vastbase_local.py)、[PostgreSQL 镜像表导出](../tools/export_imes_to_excel.py)、[环境与 TCP 检查](../tools/check_vastbase.ps1)。
- 验证结果：新客户端单元测试 9/9；真实只读冒烟导出 `2026-07-14` 至 `2026-07-15` 的 `output` 数据集 22 行、22 字段；批次多日查询 334 行，临时原始数据验证后已删除。
- 截图边界：“23488高炉炉身中部静压力检测”及 `PE424022A-F` 不在当前 10 个菜单中；要取得该画面数据仍需实际页面 URL或现场网络取证。
- 源码边界：可以取得并继续开发数据读取客户端源码；仅凭 Web 账号不能取得 IMES Java 服务端源码，完整服务端代码需要系统所有方提供源码仓库或在明确授权下提供部署产物。
- 完整说明：[docs/imes.md](imes.md)；交接摘要：[PT/imes.md](../PT/imes.md)。

## Q-IMES-UNIFIED-TIME-QUERY-20260715

- 用户问题：为 12 个 MES 数据集编写 `docs/mes数据集.md`，并提供可方便读取任意数据集、任意时间范围的查询接口。
- 结论：已新增 [MES 数据集说明](mes数据集.md)，逐项记录业务含义、接口、时间模式、时间字段、响应和已观察字段；统一客户端支持单数据集、多个 `--dataset` 和 `--all-datasets`。
- 时间模型：7 个 `range` 数据集直接查询包含首尾日期的 `startDate/endDate`；3 个 `workdate` 数据集自动把日期范围拆为逐日请求；`pes_bin` 与 `production_month_plan` 没有服务端历史区间参数。
- 实现：[build_query_windows:L200-L211](../tools/export_imes_web_readonly.py#L200-L211)、[query_dataset:L244-L269](../tools/export_imes_web_readonly.py#L244-L269)、[export_one:L272-L316](../tools/export_imes_web_readonly.py#L272-L316)、[CLI:L319-L470](../tools/export_imes_web_readonly.py#L319-L470)。
- 验证：[专项测试:L42-L163](../tests/test_export_imes_web_readonly.py#L42-L163) 9/9；真实 `batch_mining` 范围 `2026-07-13~2026-07-14` 生成 2 个查询窗口并返回 334 行（165+169），临时数据已删除。
- 影响边界：日期粒度为业务日；`heat_lab/heat_lab_all` 当前是化验索引，不含全部元素下钻明细；任意时间仍受 MES 保留期和账号权限限制。

## Q-IMES-HEAT-CHEMISTRY-20260716

- 用户问题：检查 IMES/Vastbase 是否能取得每个炉次的进料化学成分，以及每炉出料铁水硅含量。
- 结论：已发布化验结果的炉次可读取铁水硅；`heat_lab/heat_lab_all` 带 `meltNo/sumBatch/value_01...value_11`，其中 `value_02=Si`。未化验或尚未发布的最新炉次可能只有索引、Si 为空，不能承诺所有炉次实时 100% 有值。当前 12 个数据集不能直接取得每炉进料化学成分，只能取得物料、料仓、干重/称量和批次投料量。
- 关键辨析：批次投料的 `value_01...value_24` 是 24 个料仓/称量通道，不是化学元素；炉次化验的 `value_01...value_11` 才是 C、Si、Mn、P、S 等元素映射，禁止跨数据集按同名列误配。
- 离线证据：本机 2026-05-13 保存的真实 IMES 导出中，炉次 `2#20260510-147` 的 `value_02=0.24`；2026-05-10 的 12 个炉次化验索引中 10 个 Si 非空，两个最新炉次为空；3 个月铁水元素包 3,280 条记录的 Si 均非空，但缺少 `heatno/meltNo`，不能直接证明全部 1,320 炉次均有化验。3 个月 `batch_input` 共 51,516 行但没有化学元素字段或直接 `meltNo`。`t_ipes_cond` 有 `sumBatchStart/sumBatchEnd/meltNo`，只能辅助投料归炉，不能提供原料成分。
- 在线边界：2026-07-16 对 Web `10.10.181.209:8080` 与 Vastbase `10.10.181.195:5432` 的只读连接均超时；本次结论基于既有真实导出，网络恢复后仍需补做原燃料质检接口、字段字典和炉次加权对账。
- 完整说明：[炉次进料化学成分与铁水硅核查](mes数据集.md#8-炉次进料化学成分与铁水硅核查2026-07-16)。

## Q-IMES-VASTBASE-LOCAL-SCOPE-20260716

- 用户问题：`tools/export_vastbase_local.py` 是否能直连 Vastbase 检查生产实绩、批次投料、炉次化验、炉渣检验、原料投入、配料方案、料仓和计划八类数据。
- 结论：不能。该脚本只实现生产实绩、炉次条件、铁水元素/炉次化验和炉渣检验四组导出；八类中的批次投料、原料投入、配料方案、料仓和计划没有 SQL。
- 实现证据：[连接与固定日期配置](../tools/export_vastbase_local.py#L18-L36)、[生产实绩](../tools/export_vastbase_local.py#L83-L94)、[炉次条件](../tools/export_vastbase_local.py#L97-L108)、[铁水元素](../tools/export_vastbase_local.py#L111-L144)、[炉渣检验](../tools/export_vastbase_local.py#L147-L162)。
- 替代入口：批次投料由 [export_batch_input.py](../tools/export_batch_input.py#L57-L114) 单独查询 `public.batch_input`；Web 账号已授权的八类/12数据集由 [export_imes_web_readonly.py](../tools/export_imes_web_readonly.py#L41-L124) 统一查询；已同步镜像可由 [export_imes_to_excel.py](../tools/export_imes_to_excel.py#L48-L77) 展开。
- 验证：`python -m py_compile .\tools\export_vastbase_local.py` 通过。2026-07-16 Vastbase 网络连接超时，因此本次确认的是代码能力范围，不是当天在线数据可用性。

## Q-IMES-VASTBASE-EXPAND-AND-CLASH-20260716

- 用户需求：扩展 Vastbase 直连程序，尽可能查询数据库账号可访问的所有 MES 数据；同时判断已连接 SSL VPN 仍无法访问是否由 Clash Meta 导致。
- 程序结果：[export_vastbase_local.py](../tools/export_vastbase_local.py) 已改为先发现全部可见表/视图、逐对象验证 `SELECT`、自动归类八类 MES 对象并支持按分类/对象/日期有界导出。默认每对象1000行；未分类和无限制导出需要显式参数。
- 网络结论：不是 Clash 私网代理导致。系统代理确由 Clash Verge 设置为 `127.0.0.1:7897`，但绕过项包含 `10.*`；目标流量实际从 WLAN `192.168.43.140` 经默认网关 `192.168.43.1` 发出。`Sangfor aTrust VNIC` 为 `Disconnected`，没有目标专用 VPN 路由，Web/Vastbase TCP 均失败。
- 根因：SSL VPN 数据隧道没有真正建立，或账号/资源策略没有下发 `10.10.181.0/24`；客户端页面显示已登录不能替代路由和虚拟网卡验收。
- 证据：[网络诊断脚本](../tools/diagnose_imes_network.ps1)、[诊断 JSON](../logs/imes_network_diagnosis_20260716.json)、[排障手册](IMES网络与Vastbase直连排障.md)。

## Q-IMES-22012-RELAY-MCP-20260716

- 用户需求：使用220.12转发本机到 pSpace 与 IMES 数据库的访问，并将规则写入 `AGENTS.md`，提供对应脚本和 MCP 服务。
- 实现：[Paramiko本机回环转发器](../tools/imes_22012_relay.py)、[220.12目标探针](../tools/probe_22012_imes_relay_targets.py)、[只读 IMES MCP](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)。端口固定为15433 Vastbase、18080 IMES Web、18889 pSpace，只监听127.0.0.1。
- 真实验证：220.12 到三个目标均TCP成功；本机经 `127.0.0.1:18080` 获取 IMES HTTP 200；经15433发现260可见对象、9可读、6个MES对象；MCP 查询返回 `2#20260508-120` 的 `Si=0.27`。
- 安全边界：不允许0.0.0.0监听、任意SQL、写操作或非业务对象；原料投入、配料方案、料仓、计划未获直连数据库读取权限，继续使用Web白名单或申请权限。
- 运行说明：[220.12 IMES跳板转发与MCP](22012_IMES跳板转发与MCP.md)。

## Q-8093-MCP-FOUR-PROMPT-RETEST-20260715

- 用户问题：重新测试南北探尺、A-D 上升管煤气压力、冷风管道压力、富氧流量/富氧率四条 8093 口语是否成功，并继续扩展 MCP 绘图。
- 真实接口结论：绘图扩展最终部署后再次复测为 4/4，均为 HTTP 200、无敏感信息泄漏；完整结果见 [8093_mcp_four_prompt_retest_after_chart_expansion_20260715.json](../logs/8093_mcp_four_prompt_retest_after_chart_expansion_20260715.json)。
- 精确路由：南北探尺为 `L_south,L_north`；A-D 顶压的对外标准名为 `P_top_A-D`，
  旧 `P_top_gas_A-D` 仅作兼容别名，底层映射 pSpace `SIO_GL02_LD_T0067..T0070`；
  冷风压力为 `P_blast_cold`；富氧为 `Q_O2,O2_rate`。权威目录实读与迁移边界见
  [MCP 多轮规划与顶温/顶压点位审计](handoffs/2026-08-13-mcp-point-name-planning-audit.md)。
- 数据事实：最终复测采样时间为 `2026-07-15 15:23-15:25`；预取类型分别为 `multi_latest/multi_latest/latest/multi_latest`。
- 绘图扩展需求映射：[REQ-8093-MCP-CHART-003](提高MCP口语调用准确率计划.md#req-8093-mcp-chart-003-数据绘图能力扩展)。
- 回归脚本已补充 `mcp_latest_cold_blast_pressure`，并记录 `mcp_prefetch_variables` 与 `tool_names`，避免只按回答关键词判定成功。
- 绘图验收结论：确定性路由修复后双轴、三分面、相关散点、相关矩阵、分布直方、箱线图 6/6 产图成功，见 [现网报告](../logs/8093_mcp_chart_expansion_remote_after_deterministic_20260715.json)。

## Q-8093-BODY-TEMPERATURE-MATRIX-20260715

- 用户问题：绘制炉身、炉腹、炉缸 7–16 层、A–F 不同点位的热力大矩阵，每个小格带最近 1 小时趋势曲线和当前值。
- 需求映射：[REQ-8093-MCP-BODY-MATRIX-004](提高MCP口语调用准确率计划.md#req-8093-mcp-body-matrix-004-炉体温度热力趋势矩阵)。
- 实现：新增 `plot_gl02_body_temperature_matrix`，实际点位为 `T_body_L7_A` 至 `T_body_L16_F` 共 60 点；工具能力保留到 A–H。
- 自动验收：原句 1/1，工具名、层范围、方位、60 分钟参数与图片 URL 均通过；报告：[8093_body_temperature_matrix_prompt_visual_final_20260715.json](../logs/8093_body_temperature_matrix_prompt_visual_final_20260715.json)。
- 数据验收：最终窗口 60/60 点有效，0 缺测；PNG 和 JSON 均 HTTP 200。
- 视觉验收：[最终矩阵图](../logs/gl02_body_temperature_matrix_20260715_171338_c8e8e1a5.png)完整展示 10×6 格、当前值、采样时刻、格内曲线、升降方向和独立色标，无第 16 层遮挡。
- 运行边界：只滚动重启 8093 代理，8768 实时数据服务未重启。

## Q-8093-GENERIC-SENSOR-ACCESS-20260716

- 用户问题：扩展 MCP，使任意单个或多个传感器都能查看数据、绘图并支持口语调用；同时解释并修复“7层炉温”没有实际回答。
- 需求映射：[REQ-8093-MCP-GENERIC-SENSOR-005](提高MCP口语调用准确率计划.md#req-8093-mcp-generic-sensor-005-任意单个多个传感器查询与绘图)。
- 根因：旧炉体温度口语函数只返回第一个“层号+方位”，整层简称没有变量；A到H也只取首个 A 点。
- 实现：`query_gl02_sensors` 统一单/多点查询；复数炉温解析展开 A–H；运行期目录解析支持任意配置传感器；绘图按单位和数量级自动选轴。
- 真实结论：7层 A–H 八点均返回最新值；任意组合 `T_body_L7_A/P_top_gas_B/Q_O2` 当前值和趋势图均成功。
- 验收报告：[三类口语 3/3](../logs/8093_generic_sensor_access_20260716.json)、[最终绘图 1/1](../logs/8093_generic_sensor_chart_final_20260716.json)、[视觉验收 PNG](../logs/gl02_generic_sensor_small_multiples_20260716_114257_ff84d6c1.png)。
- 运行边界：只读查询；无数据库 schema/config 变化；只滚动重启 8093，8768 未重启。

## Q-IMES-VARIABLE-EXPLANATION-20260716

- 用户问题：逐项解释 IMES Vastbase 中生产实绩、批次投料、炉次作业、化验索引、铁水元素和炉渣编号指标，并写入 MES 数据集说明。
- 文档落点：[Vastbase变量逐项简明解释](mes数据集.md#22-vastbase-变量逐项简明解释)。
- 解释范围：炉次、铁量、毛/皮重、班次、称重时间；矿/焦批、批号、合计和24个料仓通道；炉次起止批次、开/堵铁口、出铁时长/温度、理论/实际铁量和渣比；化验批号、取样/判定；C/Si/Mn/P/S/Ti/V/Cr/Cu/Ni/As。
- 可信边界：`batch_input.value_01...value_24` 是投料通道值而非化学元素；`slag_inspection.value_01...value_12` 缺少化验室字典，保持 unknown，禁止猜测成分和单位。

## Q-BF3D-CUTAWAY-INTERNAL-MATERIAL-20260717

- 用户问题：当前内切面中的蓝线、圆环和柱状体分别是什么，为什么与软熔带、料线、鼓风和喷煤没有明显关系；此前 Blender 截图中的粗糙哑光表面为什么在浏览器中不明显；炉壳是否应该具有类似砂粒、砖或水泥的密集微凹凸。
- 结论：用户的语义和视觉质疑成立。当前 45 个内部对象是带 `APPROX_GL02_` 前缀的参数化工艺示意，不是现场实测料面、实时软熔带或 CFD 流场。蓝色竖线是固定生成的逆流煤气流线，下部蓝色环/管是冷风供给流；棕灰圆环是炉料参考环，矿/焦环是固定交替圆环；橙色圆环和中央双圆台共同组成固定标高的软熔带示意。生成位置见 [visual_glb.py:L706-L804](D:/文件/pythonCAD/src/geometry/visual_glb.py#L706-L804)，材质定义见 [visual_glb.py:L492-L500](D:/文件/pythonCAD/src/geometry/visual_glb.py#L492-L500)。
- 数据边界：`L/L_south/L_north`、鼓风、富氧和喷煤目前只生成传感器球形标记及 `extras`，没有驱动料面、矿焦批次、单风口羽流或喷煤枪。传感器节点生成见 [visual_glb.py:L819-L844](D:/文件/pythonCAD/src/geometry/visual_glb.py#L819-L844)，配置边界见 [sensor_layout.gl02.115.yaml:L86-L124](D:/文件/pythonCAD/input/sensor_layout.gl02.115.yaml#L86-L124)。
- 动画边界：浏览器只按计时器改变三类内部对象的透明度、轻微缩放和上下偏移，没有读取 WebSocket 工艺变量；进入内切面还会隐藏热风围管、风口连接、平台和支撑等五组外部附件，因此鼓风系统的业务联系反而更弱。实现见 [内切面显示顺序:L11181-L11190](../高炉前端数据/frontend_dashboard_v3.server.html#L11181-L11190)与[附件隐藏及裁剪:L11200-L11208](../高炉前端数据/frontend_dashboard_v3.server.html#L11200-L11208)。
- 贴图结论：8094 当前映射的是 32,748,944 字节的 P60 4K 隔离候选，不是正式无贴图 GLB。BaseColor、NormalGL 和 ORM 均已内嵌；运行报告确认炉壳的 `map/roughnessMap/metalnessMap/normalMap/aoMap` 全部存在且炉壳不透明，见 [P60 运行报告:L43-L117](../logs/bf3d_cutaway_runtime_20260717/p60_4k_report.json#L43-L117)。真正执行的 v2 只在缺图时补回退纹理，保留已有 PBR 通道，见 [炉壳材质保留逻辑:L11081-L11103](../高炉前端数据/frontend_dashboard_v3.server.html#L11081-L11103)。
- “仍然过于光滑”的根因：NormalGL 本来就以 `0.25` 强度运行，AO 绝大部分接近白；页面没有 IBL/PMREM 环境反射，完整高炉在中栏只占较少像素，4K 高频纹理被 mipmap 汇聚；当前内切面还加入强暖/冷补光和多组发光对象，并切掉一半炉壳。此前粗糙感明显的 P40 图是近距离棚拍，且明确隐藏全部内部对象，见 [P40 拍摄隐藏规则:L51-L78](../PT/高炉3D模型/skills/bf3d-light-render/scripts/p40_fixed_lookdev_candidate.py#L51-L78)。
- 材质边界：炉体外侧应保持“风化喷涂钢壳”身份，通过板缝、焊缝、氧化、积灰、涂层剥落和细颗粒微法线表达粗糙感，不应整面伪装成混凝土。砖、浇注料、碳砖和更明显的砂粒/孔隙质感应位于剖切后的耐火内衬层；后续内切面应把钢壳、冷却壁、耐火内衬和炉料空间分开建模。
- 最小改造顺序：先默认关闭现有参考环与固定蓝线；再增加带图例和可信度标识的料面、软熔带推断及 26 风口/喷煤羽流；材质侧先补 PMREM 工业环境光、贴图各向异性和材质近看模式，再加入“宏观板片/中尺度氧化积灰/微尺度砂粒法线”三尺度表面。未知单风口分配和未知软熔带边界不得伪造为实时结果。

## Q-BF3D-DATA-SOURCES-BC-ANIMATION-20260717

- 用户问题：PT 中新增了料线、静压力、炉渣/铁水化验、炉次和上料时间等数据，是否足以做好方案 C；认可 B/C 后，现有计划是否足以设计专业 3D 动画，一般 3D 动画怎样制作。
- 数据结论：现有数据足够实施 `BF3D-IN-C1-OPS` 数据驱动运营孪生，也足够启动 `BF3D-IN-C2-ESTIMATED`；不足以直接宣称完成 `BF3D-IN-C3-PHYSICS` 校准 CFD/DEM 孪生。完整矩阵见[高炉内部数据驱动 3D 动画总设计](../PT/高炉3D模型/高炉内部数据驱动3D动画总设计.md)。
- 已确认输入：主料线 `L`；20.350/23.488/28.976m 三高度×A～F 的 18 个静压力点；L7～L16 共 80 个炉体温度点；`batch_input` 上料事件；`t_ipes_cond` 炉次和开/堵铁口时间；生产实绩；铁水、炉渣和烧结矿化验。
- 强制边界：`L_south/L_north` 源描述仍像限位信号，现场对表前不能驱动倾斜料面；现有样本的 `sumbatchstart/end` 为空，不能强行做炉次—料批关联；化验必须按取样/判定/发布时间处理；静压力连续场是插值，不是 CFD 速度场。
- 文档判断：此前计划足以指导资产、PBR、十层高亮和演示性剖切，不足以指导数据驱动动画。新主规格已补充统一时钟、事件、证据等级、状态机、映射规则、分镜、Blender/Three.js/CFD 分工、回放重建和验收停止线。
- 制作路线：真实参考与分镜 → 预演 → 建模 → UV/PBR → 骨骼或 Morph → 关键帧/程序动画/物理模拟 → 灯光相机 → GLB 导出 → Three.js 数据接线 → 逐帧、跨浏览器和性能验收。工业数字孪生额外增加时间对齐、状态估计和可信度。

## Q-BF3D-INTERNAL-SIM-SURFACE-PLAN-20260718

- 用户需求：把完整的高炉内部仿真建模和外部细颗粒细腻建模方案写入 PT，并更新既有高炉 3D 模型设计文档。
- 主文档：[高炉内部仿真与外部细颗粒建模总方案](../PT/高炉3D模型/高炉内部仿真与外部细颗粒建模总方案.md)。
- 炉内方案：建立钢壳内表面、冷却壁/水道、耐火内衬、剖切盖片和工艺空间；料面、矿焦层、软熔带、风口回旋区、煤气场、滴落带和炉缸作为独立时变对象。C1 使用实测/事件，C2 使用带置信度的状态估计，C3 使用离线 CFD/DEM、降阶场和场景库。
- 外壳方案：保持风化喷涂钢身份；板片、焊缝、加强圈等进入几何，氧化/积灰/老化进入 PBR 遮罩，3～12mm 颗粒进入 Detail Normal 与微 Roughness。Structural Normal 与 Detail Normal 使用 RNM 合成，并根据颗粒屏幕像素尺寸动态衰减。
- 炉衬边界：砖、碳砖、浇注料孔隙和更强砂粒属于剖切内衬，不覆盖外钢壳；未取得图纸的厚度、材料牌号和侵蚀轮廓标为参数化近似。
- 实施顺序：先锁定当前 P40/P50/P60 粗糙材质基线，再并行制作单炉壳段细颗粒小样和炉内四层结构灰模；用户视觉通过后才扩展全炉、C1、C2、C3 与 Web 交付。
- 保护与批准：115 个传感器、80 个炉体温度点、L7～L16、五段炉型和坐标合同保持不变；本轮只改文档，未执行 Blender、CFD/DEM、页面、GLB 或生产部署；P50/P60/P70 状态不变。

## Q-BF3D-INTERNAL-RUNTIME-6X-20260719

- 用户需求：基于现有 3D 高炉和 `高炉内部仿真与外部细颗粒建模总方案` 6.1～6.6，用 Three.js 完成料面/料柱、矿焦分层、软熔带、26 风口与喷煤、18 点静压力、滴落带、铁水和炉渣动画。
- 结论：已在正式 GLB 之外增加独立运行时场景层，并接入现有 8092 页面。数据态不伪造未知工艺对象；教学态用固定种子完整展示且明确标为 `illustrative`。
- 核心实现：[运行时模块](../高炉前端数据/assets/bf3d-internal-simulation.js)、[运行配置](../高炉前端数据/config/bf3d_internal_simulation.v1.json)、[页面接入](../高炉前端数据/frontend_dashboard_v3.server.html)、[完整交接](../PT/高炉3D模型/docs/WEB-60_炉内仿真运行时说明.md)。
- 已验证：旧内切面回归、专项状态/资源/事件合同、50 次模式切换资源稳定；Chromium/Firefox/WebKit 17 个运行覆盖五页共 85 个页面组合。
- 数据边界：当前 8767 只有总风/富氧/喷煤和原有 3 个高度平均静压力；不能复制成 18 点。18 点、MES 上料、开堵铁口和 C2/C3 必须通过 `bf3d:snapshot/bf3d:event` 接入。
- 门禁：`L` 的零点/方向/量程和 `L_south/L_north` 现场语义未确认，数据态保持禁用；正式 GLB、生产库和 P50/P60/P70 状态未改变。

## Q-BF3D-R5-R2J-R2K-STRUCTURAL-REVIEW-20260719

- 用户需求：把 R5 表面、R2J 五区实体和 R2K 墙体内部层统一导出为新的受控 Web GLB；增加“纯材质审查”和“结构剖面”，材质审查时隐藏传感器、数据引线、黄色轮廓和工艺粒子。
- 需求映射：`REQ-BF3D-STRUCTURAL-REVIEW-20260719`。
- 资产结论：新文件为 [gl02_blast_furnace_structural_review.v1.glb](../高炉前端数据/models/gl02_blast_furnace_structural_review.v1.glb)，SHA `859819f415feee0533018daf3290c65c69b607352d8e8e34735e952d8f3772fd`；历史正式 GLB 未覆盖，可直接回滚。
- “线条”处理：旧 INT10/INT20 剖面卡和导引线、重复压力标记及调试体已从新 GLB 本体删除；旧 45 个固定内部装饰对象不再由旧内切面显现，运行时只保留 6.1～6.6 的受控工艺系统。
- 表面处理：纯材质审查只显示 R5 五区烘焙 PBR，叠加 R2H RNM 细节法线；采用近景、低环境光和掠射审查灯，允许 OrbitControls 继续旋转/缩放。
- 剖面处理：结构剖面显示 R2J 五区实体钢壳与 R2K 背衬、铜/铸铁冷却壁、热面嵌入和残余耐火层；局部炉腰镜头用于读薄层，结瘤层因状态缺失保持隐藏。
- UI 处理：运行态入口并入原“炉体/测温层/剖面”控制区，避免遮挡内部仿真按钮；进入审查态后旧控制、测点卡、引线和工艺面板自动隐藏。
- 验证：模式隔离 17/17 跨引擎/视口通过，五业务页回归 85/85，通过旧内切面回归；证据见 [R2O 阶段总结](../PT/高炉3D模型/work/WEB_60_20260719_R2O_STRUCTURAL_REVIEW/WEB-60_R2O_阶段成果总结.md)。
- 边界：墙体层尺寸仍是 E/illustrative，不能作为施工或生产测厚；本轮没有生产服务器部署，也没有新增数据库/API 写入。

## Q-BF3D-V1-RINGS-LINES-MATERIALS-20260719

- 用户问题：为什么结构审查 GLB 中仍有内部圆环、竖向线条，为什么没有显示具体炉体内部材质。
- 根因：V1 复用了带 115 个传感器、工艺圆环/流线/颗粒和旧装饰对象的运行场景，依靠 Three.js 模式控制器隐藏；Blender glTF 导入器不会运行网页控制器。R2K 是完整闭合层，导入后又被外钢壳遮挡。
- 修复：[V2 资产级导出器](../tools/export_bf3d_structural_review_v2.py) 使用严格对象允许列表，并分别输出 5 节点完整材质资产和 10 节点物理半剖资产；[阶段总结](../PT/高炉3D模型/work/WEB_60_20260719_R2P_CLEAN_STRUCTURAL_REVIEW/WEB-60_R2P_阶段成果总结.md) 记录材质身份、使用方式和回滚边界。
- 材质：外壳保持 R5/R2H 粗糙 PBR；内部为内钢面、背衬浇注料、铸铁/铜冷却壁、耐火层和暗色热面 PBR。无图纸部分继续标记 `E/illustrative`，不得解释为施工材料牌号或真实侵蚀线。
- 验证：[Blender 复开验证](../tools/verify_bf3d_structural_review_v2_blender.py) 与 GLB factory-startup 直接导入均通过，禁止对象计数为 0。
- 2026-07-19 补充问题“为什么看不到具体渲染材质”：复开审计确认 27 张图像已打包、12 个内部材质 ID 和 14 个结构 GLB 材质均存在；直接原因是 Blender 打开文件时沿用“布局/实体”着色，实体模式不计算 PBR 贴图。按 `Z → M` 进入材质预览，或进入顶部“着色”工作区即可显示；Blender 不可靠持久化 Layout 的着色类型，因此不能把“自动切到渲染模式”作为资产合同。
- 2026-07-20 截图取证：文件选择窗口实际选中的是历史 `gl02_blast_furnace_structural_review.v1.glb`，且右下角“导入 glTF 2.0”尚未执行；因此该画面既不是当前 V3，也不是导入后的材质视图。当前直接入口是 [gl02_blast_furnace_review.v3.blend](../高炉前端数据/models/gl02_blast_furnace_review.v3.blend)，GLB 审查必须选择名称带 `.v3.glb` 的文件。另已核实 8092 总览默认 `CadFurnaceViewer` 仍请求旧 V1，V3 只在选择“纯材质审查/结构剖面”后懒加载；默认运行画面出现旧线条是资产路由事实，不是 V3 禁用对象回归。
- V3 资产事实：[禁用对象报告](../PT/高炉3D模型/work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reports/role_forbidden_validation.json)确认三个 V3 GLB 的传感器、引线、黄色轮廓、压力/流线、颗粒、参考带和旧环线禁用命名均为零；[GLB 通道报告](../PT/高炉3D模型/work/WEB_60_20260719_R2Q_INTERNAL_MATERIAL_LOOKDEV/reports/glb_channel_texcoord_validation.json)与隔离审查合同确认主 V3 有 `13` 个 PBR 材质、`39` 个 texture、`21` 个 image，六材质族 PBR 通道有效。V3 中仍可见的五区接缝和物理层边界不能自动等同于旧圆环/竖线。
- Web 侧根因：当前 [结构审查控制器](../高炉前端数据/assets/bf3d-structural-review.js)仍使用三 SUN + AmbientLight、清空 `scene.environment`、缺 P40 TOP Area，并使用 ACES `1.05`；这会让高金属薄层缺少 PMREM 反射且中灰/高光压缩不同。完整证据见 [R2T 材质可见性诊断](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/material_visibility_diagnosis.md)。
- 修正进度：R2S 已完成真实生产页双门、输入锁、递归冻结和无副作用硬化验证，但没有创建生产审查图像 API；R2T 已生成 Blender 5.2 精确 AgX Medium Low GLSL + 37³/57³ LUT，并通过 8 个 CPU oracle。最新 [WebGL oracle 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/ocio_webgl_oracle_report.json)显示：exact generated shader 在 Chromium、WebKit 通过，在 Firefox 因黑点 RGBA32F 为 `0`、CPU oracle 约 `0.0002386` 而失败，即 `2 PASS / 1 FAIL`，exact 硬门整体 FAIL；其余 7 点及全部 RGBA8 通过。literal-nextafter 候选同为 `2 PASS / 1 FAIL`；共享 highp uniform `0x00800001` 候选虽为 `3/3 PASS` 且非黑点副作用门通过，仍是 `candidate_not_approved`，不能覆盖 exact 失败。`node tools/verify_bf3d_r2t_ocio_webgl.cjs` 当前预期退出 `1`。
- LTC runtime 最新答复：[runtime oracle 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/ltc_runtime_oracle_report.json)对应 `node tools/verify_bf3d_r2t_ltc_runtime.cjs` PASS；Chromium、Firefox、WebKit 各两次，合计 `6/6 PASS`。六次均使用同一 Three ESM，有效 addon init 为 `1`，重复探针在 addon 前拒绝；四张 `64×64` Float/Half texture 的 payload/SHA 全通过，运行选择均为 `float` 分支。`metalness=1` 且无 environment、AmbientLight、emissive 的单 RectAreaLight 镜面 fixture 非黑，零强度为黑，同一引擎重复读回字节一致，console/page/HTTP/external 四类错误均为 `0`。这只批准 runtime prerequisite，审批状态仍为 `candidate_not_approved`（报告顶层 `status=runtime_prerequisite_verified_candidate_not_approved`）；不证明 Blender/Three 光度等价或 RectAreaLight 阴影，不解除 capture、production integration、next stage，也不改变 exact OCIO 硬门整体 FAIL。独立 V3 页面现已解决只读材质/结构可见性，但 8092 生产默认 V1 仍未修复或替换；十阶段仍为 `5` 完成、`2` 部分完成、`3` 未开始。
- 光度复核最新答复：[冻结 fixture](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/photometric_fixture/fixture_definition.json)为 `103102` bytes、SHA-256 `8d43067c8875c4e677330e830eda079b841d5d8a6fad05f13b26200f349bbcfd`。Blender Cycles `67/67`、Eevee WORLD held-out `8/8`、Three 三引擎各两次共 `6/6`，错误 `0`；WLS 得到 `k_sun=0.9414175269608743`、`k_area=0.9450029255130412`、`k_env=0.9299202953495894` 且三个分母非零。但 fit/held-out 没有预注册接受阈值，[验证状态](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/photometric_verification_report.json)只能是 `candidate_evidence_verified_not_approved`；DISK/square 是 known non-equivalence，`photometric_equivalence_approved=false`、`capture_eligible=false`、`production_integration_allowed=false`。
- 独立查看最新答复：[隔离审查页](../高炉前端数据/bf3d_review.server.html)只加载 SHA-256 `7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b` 的 `review.v3`，以 `response.arrayBuffer()` 完整消费 GLB，使用独立 Scene/Renderer/Camera/RAF，提供纯材质审查、内部层近景和结构剖面。[arrayBuffer ×2 最终主日志](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/root_arraybuffer_stability_x2.stdout.log)汇总[第 1 轮](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/bf3d_review_stability_run_1.json)和[第 2 轮](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/bf3d_review_stability_run_2.json)：两轮各 `17/17`、`51` 图，合计 `34/34` viewport runs、`102` captures；`34/34` review GLB 均 `requestfinished=1`、`request_failed=0`，console/page/HTTP/external/request_failed 五类错误累计 `0`。外表面横向变化是 R2J 五区实体交界/原始纹理，不是数据圆环/引线；底部深色楔是现有 V3 GLB 十个 Section 封口面共面叠合/遮挡，不是内腔，Web 未修复该几何。该独立页已解决 `E/illustrative`、`REF-PENDING` 的只读可见性；正式 GLB SHA-256 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6` 未变，8092 生产默认 V1 仍未修复或替换，不能据此宣称 photometric equivalence、capture、production 或阶段批准。

## Q-BF3D-C2-ROOT-MOTION-20260719

- 用户需求：先做软熔带“根部上移/下移、厚度和偏心”的实用预测。
- 需求映射：`REQ-BF3D-C2-ROOT-MOTION-20260719`。
- 专项实现记录：[PT/软熔带移动预测趋势.md](../PT/软熔带移动预测趋势.md)。
- 实现边界：第一版将 L7～L13 炉体温度高度×周向场作为炉墙侧根部代理，
  以压差/透气性和 18 点静压力辅助厚度与偏心，以鼓风热状态作小幅有界
  修正；不把炉墙温度解释为炉内真实软熔温度。
- 输出：当前根部标高、`up/down/stable`、`m/h` 速度、未经校准的 15 分钟
  常速外推、厚度、相对 A 点的偏心量/角度、八扇区上/下沿、覆盖率、
  置信度和误差带。
- 安全边界：固定 `estimated`、`uncalibrated`、`control_use=prohibited`、
  `confidence<=0.45`；输入不足或陈旧时返回 `unavailable`，Three.js 隐藏
  几何而不是补造结果；A 点绝对厂区方位尚未确认。
- 实现：[估计器](../炉况规则引擎/features/cohesive_zone_estimator.py)、
  [参数](../炉况规则引擎/config/cohesive_zone_estimator.yaml)、
  [8767 快照适配](../自动诊断服务/local_pg_ws_bridge.py)、
  [Three.js 运行时](../高炉前端数据/assets/bf3d-internal-simulation.js)、
  [页面快照发布](../高炉前端数据/frontend_dashboard_v3.server.html)。
- 验证：后端估计器与桥接测试联跑 `34 passed`，覆盖未来数据隔离、
  陈旧热力驱动忽略、缺失/陈旧降级、方向、厚度、偏心、15 分钟外推、
  缓存和真实公共 API 端到端桥接；Three.js 专项 `ok=true`，并证明
  `confidence=0.9/control_use=allowed` 等越权快照会被前端独立拒绝；
  C2 三引擎代表视口 12/12，全站矩阵完成 17 个运行、85 个页面组合，
  结果记录在 `docs/test_reference.md`。
- 现场边界：本机 PostgreSQL 16 当前监听 `18000`，但本机 `bf_trend`
  缺少 `bf_sensor`；本轮 220.12 直连超时。因此代码和确定性数据链已完成，
  但没有把 fixture 结果表述为当前在线炉况。恢复只读数据链后应使用
  `tools/check_v3_ws_bridge_python.py --require-bf3d-snapshot --require-cohesive-zone`
  做现场冒烟，再进入专家标定和历史回测。

## Q-HOT-METAL-SI-DATASET-20260719

- 用户需求：制造好当前炉况、传感器数据与铁水硅含量的联合数据集。
- 需求映射：`REQ-HOT-METAL-SI-DATASET-20260719`。
- 结果：已从 2# 高炉 IMES 铁水命名视图取得 5,699 个 Si 标签，并与
  220.12 PostgreSQL 炉况快照和分钟传感器历史只读对齐；完整集 5,699 条、
  严格训练版 4,090 条、完整字段 312 列。
- 时间边界：IMES“发布时间”是结果判定/审核时间代理；当前向前退让
  120 分钟作为特征截止，炉况最大向前 15 分钟、传感器最大向前 10 分钟，
  不使用截止时刻后的数据。取得真实取样/出铁时间后必须重建。
- 实现：[构建器](../tools/build_hot_metal_si_dataset.py)、
  [验证器](../tools/validate_hot_metal_si_dataset.py)、
  [数据口径与重建手册](铁水硅炉况传感器数据集.md)。
- 验证：单元测试 `3 passed`；产物验证 `PASS`；样本主键重复、未来时间、
  炉况间隔、传感器年龄和 `cold/hot` 展示映射违规均为 0。
- 影响：只新增本地文件和只读程序；未修改生产库、schema、API、计划任务、
  前端或模型。

## Q-IMES-LOCAL-VASTBASE-RELAY-20260719

- 用户需求：VPN 连接后，在本机快速建立
  `127.0.0.1:15433 -> 10.30.220.12 -> 10.10.181.195:5432`
  的 IMES Vastbase 转发。
- 实现：[本机一键启动入口](../tools/start_imes_vastbase_relay_local.cmd) 调用
  [现有 Paramiko 转发器](../tools/imes_22012_relay.py)，仅启用 Vastbase
  这一条映射；SSH 密码只从 `BF_22012_SSH_PASSWORD` 读取或在控制台交互输入。
- 使用边界：`15433` 是 PostgreSQL/Vastbase 协议端口，供 Navicat、DBeaver、
  `psql` 和程序连接，普通浏览器不能直接显示；浏览器访问 IMES Web 应另启
  `imes` profile，并访问 `http://127.0.0.1:18080/imes.web/`。
- 安全边界：监听地址固定为 `127.0.0.1`，不新增防火墙入站规则，不写入
  生产库，也不把密码写入脚本、文档或日志。
- 验证：转发单元测试 4/4 通过，自定义 `15433` 映射解析通过；经 220.12
  对 `10.10.181.195:5432` 的真实只读通道检查返回 `all_ok=true`。
- 需求映射：沿用 `REQ-IMES-22012-RELAY-MCP-20260716`。

## Q-BF3D-V4-MATERIAL-NOT-VISIBLE-20260720

- 用户问题：为什么 GLB 中仍有内部圆环、垂直/竖向线条，为什么看不到炉体内部的具体
  渲染材质和分层。
- 查看根因：截图实际选中历史 `gl02_blast_furnace_structural_review.v1.glb`，且仍在
  glTF 导入窗口、尚未点击“导入 glTF 2.0”；Blender 主视图为 Solid/实体模式。GLB
  需要导入而不是直接打开，导入后还需切到材质预览或渲染。
- 几何根因：V3 十个 Section 封口确有 `18` 对、`87.53379024081863 m²` 跨对象
  共面叠合，造成底部黑楔和内部层遮挡，不能只归因于查看模式。
- 修复：R2U V4 将十个剖面体闭合并做封口所有权控制，得到 `10/10` 闭合正体积、
  boundary/non-manifold `0`、跨对象封口 `0`。六类 PBR 内材质保留，传感器、引线、
  黄色轮廓、工艺粒子、旧圆环和竖向流线不进入受控资产。
- 正确入口：优先直接打开
  [gl02_blast_furnace_review.v4.blend](../高炉前端数据/models/gl02_blast_furnace_review.v4.blend)；
  GLB 审查必须选择文件名带 `.v4.glb` 的版本。隔离 Web 入口为
  [bf3d_review_v4.server.html](../高炉前端数据/bf3d_review_v4.server.html)。
- 验证：Blender 重开、三 GLB factory import、独立拓扑/视觉验证通过；Khronos
  `0 errors`；Chromium/Firefox/WebKit 两轮合计 `34/34` runs、`102` captures，
  五类错误为 `0`。
- 边界：[R2U 根审查结论](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/WEB-60_R2U_根审查结论.md)
  明确仅批准 `E/illustrative`、`REF-PENDING` 的只读候选；P60、生产 8092、正式 GLB、
  切线 warning、绝对路径 extras、外壳 AO、现场 Edge 和数值光度等价仍未完成。

## Q-BF3D-V5-RENDERED-MATERIAL-VISIBILITY-20260720

- 用户问题：为什么仍看不到具体渲染材质；内部圆环、垂直/竖向线条为何还在。
- 查看事实：原截图选中历史 `structural_review.v1.glb`，仍停留在导入对话框且 Blender
  主视图为 Solid。历史 V1 依赖 Three.js 控制器隐藏运行对象，Blender 不执行该控制器。
- 当前入口：优先直接打开
  [gl02_blast_furnace_review.v5.blend](../高炉前端数据/models/gl02_blast_furnace_review.v5.blend)；
  如导入 GLB，应选择 `.v5.glb`，点击“导入 glTF 2.0”，再用 `Z → M` 进入材质预览。
- V5 结果：受控资产不含传感器、数据引线、黄色轮廓、工艺粒子、旧固定圆环或装饰性
  竖向流线；外表面有细颗粒/粗糙度响应，内部可辨钢灰、锈红颗粒、浅棕耐材和深棕内层。
- R2W 可读性修正：新
  [隔离页](../高炉前端数据/bf3d_review_r2w.server.html)只增加外表面材质近景和受控
  相机框景，没有更换 GLB、材质、灯光、曝光、环境或 Tone Mapping。独立复核确认
  外表面近景可读但无 AO 时仍显平，内部材质族可以区分。
- “线”的结构修正：横向明暗带仍按 R2J 五区实体/材质交界解释；内部可见带不能再写成
  “两个已验证相邻实体之间的间隙”。只读审计证明 L03 为 `z=-20…7.55 m`、L04 为
  `z=16…20 m`，高度重叠和覆盖率均为 `0`，真实相邻链不可测。L03→L05 的
  `14.816–49.456 mm` 只是跳过 L04 的非相邻诊断；`z=-1.2 m` 异常是冷却壁
  拼缝/端面与剖面的交点。正式文案统一为“内部层边界 REF-PENDING，非数据竖线”。
- AO 事实：当前 4K ORM.R 全部为 `255`，V5 glTF 没有 `occlusionTexture`，
  Blend ORM.R 也未接入。旧 P50 R3 的 `P50_UV0/APPROX_GL02_*` 与 V5 R2J
  UV/对象不兼容；必须为当前 R2J 独立 AO UV 重新烘焙，不能直接套旧图集。
- 验证：R2W Three.js 三引擎连续两轮为 `34/34` runs、`136` captures、五类错误
  `0`，PBR 改写、禁止对象和黄色轮廓为 `0`；这只批准镜头可读性候选。
- 结论：R2W 状态为 `r2w_camera_readability_passed_ao_and_structure_blocked`。
  AO、相邻层连续性、施工尺寸、P50/P60/P70/QA-70、正式 GLB、生产 8092、现场性能
  和数值光度等价均未批准。详见
  [R2W 根审查](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_根审查结论.md)。

## Q-BF3D-R2X-AO-AND-RENDERED-MATERIAL-NOT-VISIBLE-20260720

- 用户问题：为什么仍看不到具体渲染后的材质；为当前 R2J 炉壳补做 AO 后是否已经解决。
- 对应需求：`REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720`。
- 结论：没有。R2X 已证明 1K AO 的 UV2、GLB 绑定和 Three.js 运行时切换在机器层面正确，
  但没有形成可见像素差异，因此不能把 AO 写成“材质可见性已修复”。
- 资产事实：最终候选
  [R2X V5-payload GLB](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/glb/gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb)
  为 `1,115,216` bytes，SHA-256
  `bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00`；
  五个 mesh/primitive binding 复用两个 V5 共享 `MeshStandardMaterial`；5/5 binding
  均有非空 AO map、`aoMap.channel=2` 和 finite `uv2`，其它 PBR map 继续使用
  channel `0`。Khronos 为 `0 errors / 0 warnings`，
  [独立机器审计](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_ao_smoke1k_v5payload_audit.json)
  通过。
- 历史失败必须保留：首次 V5-payload 重打包候选
  `c8b748ef03b516a78de658a3b25a5f2265fef9bd34cea334a3490fba1fbab139`
  越权新增第二个 clamp sampler，已按
  `UNAUTHORIZED_EXTRA_AO_CLAMP_SAMPLER` 失败关闭；最终候选只复用 V5 sampler
  `0`，没有抹除首次失败证据。
- 浏览器事实：[代表报告](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/bf3d_review_r2x_representative_report.json)
  只在 Chromium `1440×900` 采集全景 off/on 与近景 off/on 四图。运行时只把
  `aoMapIntensity` 从 `0` 切到 `1`，五类错误均为 `0`，但两组
  `changed_pixels=0`，配对 PNG SHA 完全相同。
- 直接原因：[独立视觉复核](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_independent_visual_review.json)
  记录 AO PNG `99.6763%` 为纯白、非白像素仅 `0.3237%`，稀疏且很浅的遮蔽信号
  经过 UV 采样、过滤、照明和 8-bit 输出后在当前代表视图中不可见；结论为
  `fail_closed_ao_visual_signal_absent`。
- 正确后续：先补足真正可产生局部遮蔽的可见几何接触源，并用受控材质检视照明和近景
  模式复核 BaseColor/Roughness/Normal/AO 的联合响应；内部层边界仍需权威结构参考。
  禁止添加黑色圆环、装饰性竖线，或改 BaseColor 来掩盖 AO 信号缺失。
- 发布边界：[R2X 根审查](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_根审查结论.md)
  固定 `r2x_machine_passed_three_visual_failed_closed`。未运行完整矩阵，不升级 2K，
  不批准 P50/P60/生产或正式资产替换；V5/formal 保持不变。

## Q-BF3D-R2Y-CPU-HIT-PASS-BUT-MATERIAL-NOT-APPROVED-20260720

**问题**：为什么 CPU 已证明 AO 命中，仍然看不到具体渲染材质，也不能批准
AO/PBR？

**可追踪回答**：

- [CPU 光栅审计](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_ao_uv_hit_raster_audit.json)
  只证明固定相机的可见片元会命中非白 AO texel，排除了当前视角下单纯的
  `uv_or_camera_miss`。它没有执行 WebGL 合成黑 AO、浮点线性或最终 8-bit off/on，
  所以不能在 shader consumption、量化损失和信号过弱之间定因。
- [代表 PBR 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/bf3d_review_r2y_representative_report.json)
  证明 BaseColor/Normal/Roughness 数据、CPU 采样和 Three.js 绑定存在，但没有逐通道
  off/on 证明；因此三个通道均为 `consumed=null`、`visible=false`。
- 代表门明确失败：macro `0.962958 < 1`、anisotropy
  `1.021708 < 1.03`、environment A/B 最终图像为 `0` 差异。两个不同环境 target
  实际已切换，零差只说明在锁定 fixture 中 IBL 不可观测，不能直接断言 shader 或
  PMREM 损坏。
- [独立视觉审查](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_independent_review_decisions.json)
  确认当前可见信号主要是重复竖纹、Normal 网格和 Roughness 周期竖波；它们是运行时
  近似纹理伪影，不是可信板缝、焊缝、旧化或炉墙分层。
- 所以正确结论不是“材质已经可见”，也不是“已经确定 shader 坏了”，而是：
  `r2y_cpu_hit_passed_pbr_visual_failed_ao_webgl_pending_fail_closed`。下一阶段要先替换
  周期性材质源并补逐通道 shader/AO liveness；禁止用黑环、装饰竖线、整体压暗或
  BaseColor 改色伪造层次。

## Q-BF3D-ASSET-CONTROLLED-MASTER-R1-20260721

- 用户要求：整理合并已有高炉 3D 资产，建立资产登记表、母版目录并生成第一版受控候选。
- 需求编号：`REQ-BF3D-ASSET-CONTROLLED-MASTER-R1-20260721`。
- 母版：[BF3D_CONTROLLED_MASTER_R1.blend](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/blends/BF3D_CONTROLLED_MASTER_R1.blend)；以锁定 V5 的 R5/R2J/R2K 为静态结构基线，并把 VIS30 十八点静压力作为独立 `07_GAS_PRESSURE` 集合并入。
- 登记入口：[bf3d_asset_registry.v1.json](../PT/高炉3D模型/asset_registry/bf3d_asset_registry.v1.json)；十个模块中 R5/R2J/R2K/静压力已经晋级，料柱、软熔带、风口/喷煤和炉缸液体保持 `registered_deferred`。
- Web 输出：[基础](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/glb/bf3d_base.r1.glb)、[传感器](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/glb/bf3d_sensors.r1.glb)、[组合审查](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/glb/bf3d_combined_review.r1.glb)、[结构剖面](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/glb/bf3d_structural_section.r1.glb)。
- 验证：[复开/工厂导入](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/controlled_master_r1_reopen_validation.json)为通过，网格计数 `5/18/23/10`；[Khronos](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/khronos_gltf_validator_r1.json)四资产均 `0 errors / 0 warnings`。
- 发布边界：仅候选可审查，不替换正式 GLB，不切换 8092；R5/R2J/R2K 仍为 `E/illustrative`、不可用于施工。

### 浏览器组件复核补充

- 新增隔离入口：[bf3d_controlled_master_r1.server.html](../高炉前端数据/bf3d_controlled_master_r1.server.html)与[预览控制器](../高炉前端数据/assets/bf3d-controlled-master-r1-preview.js)，只读加载 ASSET-10 四个候选 GLB。
- [浏览器复核报告](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/browser_component_review.json)确认组合、基础炉体、静压力、结构剖面四个按钮均可切换，运行状态均为“可用”，浏览器错误/警告为0。
- 结构剖面计数口径：Blender/源对象为10个；因多材质 primitive 拆分，Three.js运行网格为25个。预览合同采用 `10对象 / 25 Web网格`，不得再用10个Three.js mesh误判加载失败。
- 该页面已在本机 `8095` 隔离静态服务打开；未改变8092正式路由。

### “为什么没有合成一个高炉整体”修正

- 根因：旧 `bf3d_combined_review.r1.glb` 只导出了5个外炉壳对象和18个静压力点，R2J/R2K结构仍在独立剖面GLB中，因此只能称为外壳+传感器审查包，不能称为完整总装。
- 修正资产：[bf3d_full_assembly.r1.glb](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/glb/bf3d_full_assembly.r1.glb)在单个GLB中包含5个外壳、10个R2J/R2K结构对象和18个静压力点，共33个源对象、48个Three.js网格、15个材质。
- 浏览器模式：“整体高炉”显示外壳+传感器并保留内部对象在同一已加载总装中；“整体剖切”隐藏完整外壳并显示R2J/R2K剖面+传感器。二者使用同一个总装GLB，不再用两个文件假装合并。
- 验证：[总装Khronos报告](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/khronos_gltf_validator_full_assembly_r1.json)为0错误、0警告；Blender工厂导入为33对象、18个静压力；浏览器两种整体模式均为48/48网格可用，控制台错误/警告为0。

### “打开后提示不是有效 Blender 文件”修正

- 根因：`bf3d_full_assembly.r1.glb` 是有效的 Web glTF 2.0 二进制资产，但截图中使用了 Blender 的“文件→打开”；该入口只接受 Blender 原生工程，因而把 GLB 报为“不是有效的 Blender 文件”。这不是 GLB 损坏。
- GLB 正确入口：在 Blender 中使用“文件→导入→glTF 2.0（.glb/.gltf）”。总装 GLB 文件头为 `glTF / version 2`，声明长度与实际长度均为 `4,973,160` bytes，SHA-256 为 `76a7ec528346f08db33784e58c85c99adb1149db1253d3b9698114180e74bd1a`。
- 为避免再次选错入口，新增可直接“文件→打开”或双击的 [BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/blends/BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend)。初版错误地把只有 R5/R2J/R2K 与静压力的结构总装称为“完整模型”，且默认显示整壳，造成“打开后只有一个壳子”的交付回归；把整壳和内部对象简单同时显示仍会发生深度遮挡，不能解决问题。
- 最终直接打开工程提供三个真实 Blender 视图层：默认 `内部工艺_默认` 显示墙体剖面、矿焦料柱/料面、布料溜槽、软熔带、26 个统一响应回旋区、死料柱、24 个滴落液滴、铁水/炉渣独立液面和 18 个黄色静压力点；`完整外观` 显示整壳与静压力点；`墙体分层` 只显示 R2J/R2K 剖面实体与静压力点。视图层通过集合排除实现，渲染与视口一致；旧工艺圆环、竖向引线及辅助路径不进入默认层。
- 证据边界：R5/R2J/R2K 是受控结构候选；料柱/料面和布料对象继承 R2L/R2M 受控示意资产；软熔带、回旋区、死料柱、滴落和双液面均标记 `illustrative + simulated`、场景版本 `BF3D_COMPLETE_VISUAL_SIM_R1`、`control_use=prohibited`，不得解释为实测场、CFD 结果或生产控制量。
- [直接打开工程复开报告](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/direct_open_blend_reopen_validation.json)由 Blender 5.2 后台复开并通过：默认可见网格 `113`，其中料柱/料面 `11`、墙体剖面 `10`、静压力 `18`、布料溜槽 `9`、内部仿真 `54`，失败项与可见辅助线均为 `0`。[视觉门报告](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/direct_open_internal_default_visual_gate.json)和[预览图](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/direct_open_internal_default_preview.png)同步通过；构建过程见[构建报告](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/direct_open_blend_build_report.json)。
- 当前 `bf3d_full_assembly.r1.glb` 仍是结构 Web 总装，未包含上述新增工艺仿真模块；在重新执行受控 Web 导出和 Khronos/浏览器验收前，不得宣称 GLB 已同步为完整内部模型。

## Q-BF3D-COMPLETE-EXTERIOR-COHESIVE-DRIP-ANIMATION-R2-20260721

- 用户问题：同一高炉是否有不带剖口的完整外部显示；软熔带能否移动，并模拟铁水从软熔带下缘滴落。
- 根因取证：旧 `BF3D_V5_FULL_MATERIAL` 虽命名为完整材质集合，但五区源网格的最大圆周覆盖只有 `301.5°`，保留 `58.5°` 纵向审查开口；它不能作为 360° 外炉交付。读取与角度审计入口为[几何检查脚本](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/scripts/inspect_full_material_geometry.py)。
- 完整外观实现：[build_complete_exterior()](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/scripts/create_full_assembly_direct_open_blend.py#L315-L423)从五区受控外表面的高度—最大半径轮廓生成 `144` 圆周段、`5` 个 360° 闭合外壳对象，沿用各区既有 PBR 材质并生成圆柱 UV。`完整外观` 视图层只显示该集合与 18 个黄色静压力点；旧 301.5° 审查壳、剖面和内部仿真全部排除。
- 动画实现：[animate_simulated_internal_modules()](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/scripts/create_full_assembly_direct_open_blend.py#L425-L512)建立 `1–480` 帧、`24 fps`、20 秒循环。软熔带以五个受控关键状态连续升降并轻微改变径向/厚度尺度；24 颗液滴按 4 帧相位差、96 帧周期从软熔带下缘落向炉缸，铁水液面有轻微积累响应。
- 数据边界：外炉 360° 几何是由当前 R2J 外轮廓旋转重建的 `E/illustrative` 候选，不是施工模型；软熔带与滴落仍是 `simulated` 场景动画，场景版本 `BF3D_COMPLETE_VISUAL_SIM_R2`、`control_use=prohibited`，未接 C2/CFD/真实瞬时液滴输入。
- 验证：[复开报告](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/direct_open_blend_reopen_validation.json)确认完整外观可见 `5` 个闭合外壳、`18` 个静压力，剖面/仿真对象均为 `0`；软熔带中心高度样本为 `0 / +0.55 / -0.35 / +0.38 / 0 m`，单颗液滴从 `+4.35 m` 落到 `-16.85 m`。[完整外观视觉门](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/direct_open_complete_exterior_visual_gate.json)与[动画视觉门](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/direct_open_animation_visual_gate.json)均 `passed=true`。

## Q-BF3D-MISSING-TOP-HEARTH-TAPHOLE-TUYERE-20260721

- 用户问题：炉顶、炉缸底部、两个出铁口和一圈风口在哪里；如何取得真正完整高炉并切换切面。
- 合并前基线：设备存在性审计曾确认 R2 直接打开母版中的炉顶、独立炉缸底部、铁口和风口硬件均为 `0`。`SIM_R1_RACEWAY_01–26` 只是炉内回旋区发光模拟，不能当作26套风口设备；铁水/炉渣对象也不能当作炉缸底部结构。
- 历史来源：旧 [P40 风口候选](../PT/高炉3D模型/work/P40_TUYERE_PREVIEW_20260717_1434/P40_FIXED_LOOKDEV_CANDIDATE.blend)含 `26` 个风口位置及法兰/螺栓/围管近似对象，旧 [P40 铁口候选](../PT/高炉3D模型/work/P40_TAPHOLE_PREVIEW_20260717_1515/P40_FIXED_LOOKDEV_CANDIDATE.blend)含两个近似铁口对象；P40 还含无料钟炉顶/放散与上升管近似对象。它们均未经过当前 R5/R2J/R2K 受控合并，不能把旧候选直接称为当前完整母版。炉缸底部独立设备在 P40 也没有可直接晋级对象。
- 丢失原因：旧 ASSET-10 合并范围只晋级 R5/R2J/R2K、18点静压力和后续 SIM 场景；设备并非被视图层隐藏，而是尚未进入母版。
- R3 修正：新的 [BF3D_CONTROLLED_MASTER_R3_EQUIPMENT_MERGED.blend](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/blends/BF3D_CONTROLLED_MASTER_R3_EQUIPMENT_MERGED.blend)按来源哈希和对象白名单正式合并炉顶 `2` 个网格、两个铁口相关 `3` 个网格、26套风口/围管可见总成 `3` 个网格，并保留 `26` 个按圆周顺序编号的位置锚点。另新增 `1` 个炉缸底部临时闭合体，使外观不再敞底；它明确标记为后续单独炉缸底部建模的边界占位，不包含冷却壁、炉底砖衬、基础或施工细节。
- 来源与隔离：[P40设备几何审计](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/p40_equipment_geometry_audit.json)锁定设备来源、坐标和26个位置；[R3复开报告](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/direct_open_blend_reopen_validation.json)确认 `完整外观` 为 `5` 个闭合炉壳、`18` 个黄色静压力点和 `9` 个设备网格，共 `32` 个可见网格，剖面与工艺仿真均为 `0`。`内部工艺_默认` 保留同一套设备并显示内部工艺；`墙体分层` 隐藏设备，只审查 R2J/R2K 墙体。
- 当前可用操作：Blender 右上角 `View Layer/视图层` 下拉选择 `完整外观` 查看360°炉壳和全部已合并设备；选择 `内部工艺_默认` 查看工艺剖面、设备和动画；选择 `墙体分层` 只查看 R2J/R2K 墙体剖面。按 `Space` 播放/暂停时间轴，`Z → M` 进入材质预览。
- 发布边界：本次解决的是 Blender 受控母版设备合并，所有 P40 来源设备仍为 `illustrative/static_reference`、`control_use=prohibited`。现有结构 Web GLB 未同步 R3 设备，不得宣称浏览器 GLB 已升级。炉缸底部精细建模继续按用户要求单独立项。

## Q-BF3D-IMG2THREEJS-SEMANTIC-IMPLEMENTATION-20260724

- 用户问题：img2threejs 高炉原型具体如何实现；能否继续细分 L7～L16、炉喉、炉身、炉腰、炉腹、炉缸、2 个出铁口、风口、进料口以及大量传感器点位。
- 实现结论：可以，且已在
  [WEB_60_IMG2THREEJS_20260724_R1](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/)
  中升级为 R2 语义原型。一级为 8 个工艺大区；二级为 L7～L16 十层、每层 A～H 八点；三级为设备和数据实例。
- 程序方法：[model.js](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/preview/model.js)
  用 `LatheGeometry` 旋转炉型剖面，用 `TorusGeometry` 建平台/法兰/层带，用
  `TubeGeometry` 建下降管，用端点间圆柱建梯道/支管；26 风口、80 炉体测温、18 静压力、其余正式点位和平台重复件用 `InstancedMesh`。所有设备和点位挂入对应 `THREE.Group` 工艺父级，分区展开时保持语义关系。
- 数据合同：正式 `115 = 80 炉体测温 + 35 其余点位`；新增 18 点静压力是独立 Overlay，不覆盖正式 115 中的 3 个旧静压力节点。26 个风口目前只允许统一响应总风/氧/煤，2 个出铁口设备与 `T_taphole_1/2` 温度点分开建模。
- 交互：[app.js](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/preview/app.js)
  提供工艺区、L 层、设备、点位开关，80 点总控、逐层定位、八区展开、灰模、自动旋转和风口/出铁口/进料口近景。
- 实测合同：8 个工艺区、10 层/80 点、115 正式点位、18 静压力、26 风口、2 出铁口；浏览器运行统计为 284 网格、599 实例、198,456 三角面。
- 验证：[浏览器矩阵](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.md)
  为 Chromium 9 视口、Firefox 4 视口、WebKit 4 视口，共 `17/17` 通过；页面、控制台、资源错误和横向溢出均为 0。
- 边界：点位身份和数量是受控事实，但当前外壳半径、设备尺寸、安装位置仍为 `E/illustrative`。A～H / A～F 只有相对顺序，绝对厂区方位未确认，不能输出东南西北结论，也不能把 80 点/18 点插值解释为真实炉内温度场或 CFD 速度场。

## Q-SI-TEMPORAL-NEURONS-AND-005-TOLERANCE-20260726

- 用户问题：将铁水Si预测误差主范围从`±0.10`收紧到`±0.05个Si百分点`；130个
  pSpace高延迟传感器应派生哪些时序信息；规则引擎特征是否可视为有意义神经元。
- 结论：规则特征可以视为可解释微神经元输入，但只有经过分组响应、时间外消融、
  跨月稳定性和专家方向复核后，才能称为有效语义神经元。不能把260列机械地
  宣称为260个生产有效神经元。
- 实现：[单点多窗口派生](../PT/预测铁水Si含量/src/si_semantic_engine/temporal_features.py)
  覆盖水平、离散、趋势、动态、记忆、异常和数据质量；[跨点物理派生](../PT/预测铁水Si含量/src/si_semantic_engine/physics_neurons.py)
  覆盖压力裕度、压差分配、南北料线差、顶温/顶压离散、静压力和炉体纵向梯度；
  [21组映射](../PT/预测铁水Si含量/src/si_semantic_engine/expanded_neurons.py)
  将148/148规则特征唯一归组。
- 实验：21组模型测试MAE从6组模型的`0.0551`改善到`0.0500`，R²从
  `-0.1166`改善到`0.1202`，但`±0.05`命中仍为`60.2%`；260特征模型为
  `62.2%`，仍是当前最佳。
- 数据边界：本机`127.0.0.1:18000` PostgreSQL 16没有`bf_sensor` schema，
  因此真实130点30/60/120/240分钟特征尚未物化。当前结果是代理离线实验，
  不接生产MCP或操作建议。完整方法见
  [V2实验方法](../PT/预测铁水Si含量/docs/experiment_method_v2.md)。

## Q-BF3D-8093-DUAL-CAMERA-ROTATION-20260801

- 用户问题：8093 既要以炉体中心持续旋转 360°，又要在点击 Billboard 后围绕点位局部观察；局部旋转时不能沿用首次命中的固定炉壳法线。
- 原因：旧 `bf3d.surface-camera-shell-guard.8093.v1` 把 `OrbitControls.target` 长期锁在一个炉壳表面点，并把首次命中的表面法线作为相机安全方向。这样虽然能限制近距离穿壳，却把全景轨道改成了局部切平面轨道；方位变化后固定法线也不再代表当前可见炉壳表面。
- 修复：[8093 独立双模式运行时](../高炉前端数据/assets/bf3d-surface-camera-guard-8093.js)升级为 `bf3d.camera.dual-mode.8093.v2`。全炉模式以炉体中心为 target，并用覆盖整个炉体包围球的半径限制 `minDistance`，方位角不设上下限；点位模式从实际 Billboard 进入，每次相机变化都按当前方位重新向炉壳 Raycast，更新表面点、外法线和安全观察位置。
- 交互边界：点位模式滚轮推进前检查当前炉壳交点，法向间距小于 `1.2m` 时停止；近裁剪面固定为 `0.05m`。按钮、Esc 或全景复位均退出点位模式，恢复炉心 target。该实现只属于 8093，不导入、不修改 8094 运行时。
- 模型纠错：首次专项页错误加载了本机 `高炉前端数据/models/gl02_blast_furnace.glb`（`4,314,736` bytes），它不是远端 8093 同 URL 下实际部署的正式资产；因此首次得到的 `650.8°`、`8→125` 和包围半径只证明算法原型，不能作为正式模型验收。现已把[专项验收页](../高炉前端数据/bf3d_8093_dual_camera_harness.html)改为直接加载资产库 `GL02_FURNACE_BODY_R1.glb`，并在解析前强制核对 `8,229,120` bytes、资产 ID 和 SHA-256 元数据。
- 正确资产复验：真实浏览器显示 `modelAssetId=GL02_FURNACE_BODY_R1`、`loadedBytes=expectedBytes=8229120`、`assetVerified=true`、133 点、`overview/furnace-center`、near `0.050m`、正确模型包围半径 `25.769`，浏览器 error/warning 为 0。完整旋转、点位动态法线和滚轮碰撞仍需在这个正确模型上重新跑完后才能形成新的生产候选证据。
- 部署状态：本机代码、语法、契约和隔离部署测试已完成。220.12 的 SSH 协议头在单次 3～4 秒限制内超时，SMB 管理共享拒绝访问，因此远端 8093 尚未覆盖，仍保留历史 `near-plane-r4/v1`；8094 未改变。远端通道恢复后必须用原子部署器部署并重新运行真实页面验收。

## Q-BF3D-8093-MEASURED-121-NO-FOCUS-20260801

- 用户问题：左侧 28 个变量面板完全不动，只把其中的计算、设定和汇总变量从炉体去掉；炉体仍显示 121 个物理/设备测点，并去除点位聚焦。
- 回答：共享数据合同仍为 133 点；8093 在 adapter 之后执行独立后置筛选，保留 `80 炉体温度 + 18 静压力 + 2 出铁口温度 + 21 设备/管线/炉顶实测点 = 121`，只从三维场景排除 12 个抽象/汇总点。左侧 28 变量的数据、分类、顺序和布局均未改动。
- 相机：此前的双模式点位聚焦口径被本节取代。8093 当前只保留炉心全景模式，Billboard 仍可悬停查看数值，但点击不再改变相机 target；整体包围半径限制滚轮进入炉内，方位角无限制。
- 实现：[点位筛选器](../高炉前端数据/assets/bf3d-physical-point-filter-8093.js)、[全景相机](../高炉前端数据/assets/bf3d-surface-camera-guard-8093.js)、[部署器](../tools/remote_deploy_8093_physical_points_overview.py)。
- 部署结论：已覆盖 220.12 的 8093 页面；8094 页面、共享 adapter 与 8094 相机哈希保持不变。上一个问题条目中“远端尚未覆盖”的状态仅为当时历史状态。

## Q-BF3D-8093-BOTTOM-GAP-AND-GUARD-PARITY-20260802

- 用户问题：8093 初始画面中的炉体底部是否缺失，能否默认放大，并确认线上代码是否与本机一致、是否被守卫覆盖。
- 判断：炉底、支腿和地面网格都在，视觉空白来自整体包围球适配的额外构图余量，不是 GLB 底部缺面。
- 修复：相机 fit margin 从 `1.08` 降为 `1.0`，约放大 8%；防穿透最小轨道半径未变。
- 一致性：相机、点位筛选、tooltip、汇总 CSS、共享 adapter 和受控 GLB 均与本机 master 哈希一致；整页 HTML 因远端专用注入与本机主 HTML 不同，不能宣称逐字节一致。
- 守卫：部署前页面哈希仍等于上一轮已知哈希；暂停守卫写入并恢复后，新相机哈希仍不变，因此没有守卫覆盖证据。

## Q-BF3D-8093-CAD-BOTTOM-BAND-20260804

- 用户问题：8093 三维页面底部为什么出现空白，能否更新 8094？
- 判断：最初发现 `.cad-furnace-viewer bottom:5%/6%`，但只修该项仍会留下大空带。最终确认旧 `.overview-grid>.panel:last-of-type .panel-body` 在当前布局误命中炉况总览，额外产生 `46px/66px` 底部 padding，这才是用户截图中大块深蓝空白的主要来源。
- 后续授权：用户确认可以重启 8094、更新 8093、补充 `AGENTS.md` 并继续截图直到视觉验收成功。
- 处置：R2 共用补丁器按 `--scope` 同时将 viewer bottom inset 与炉况总览直属 panel-body padding 设为 `0`，保持左右 24%；8094 更新完成，8093 通过暂停/恢复 `BFV4PreviewProxy8093` 的守卫闭环上线。
- 证据：[根因与部署记录](handoffs/2026-08-04-8094-cad-bottom-band-fix.md)、[共用补丁器](../tools/patch_8094_cad_bottom_band.py)、[8094 重启入口](../tools/restart_22012_8094_preview.ps1)、[8093 守卫部署器](../tools/remote_guarded_deploy_8093_cad_bottom_band.ps1)、[8094 合同测试](../tests/test_8094_cad_bottom_band_fix.py)、[8093 合同测试](../tests/test_8093_cad_bottom_band_fix.py)。
- 结论：旧 stage/viewer 验收口径已作废。Chrome 两页 `1552×816` 实测 canvas 到 panel-body 底差均为 `0.606px`、`padding-bottom=0px`、横向溢出为 0，截图中白色画布已直达面板底部；底部空白专项视觉验收通过。完整跨浏览器矩阵不在本次通过范围内。

## Q-8096-DIAGNOSIS-MANUAL-SCORE-AND-SUGGESTION-20260804

- 用户问题：高炉长能否在异常弹窗里打分和提建议，也能在没有弹窗时点击任一炉况手动打分；关闭时不强制提交；系统分与人工分同时保存并可在炉况数据仪表盘查询。
- 结论：已在本机8096原型实现。异常弹窗保留三态复核并增加可选人工分/建议；诊断页八卡均有独立评分入口；评分或建议至少一项才写库，直接关闭不产生记录。
- 数据：系统八类分、主诊断和诊断时间由服务端重新读取并不可被浏览器覆盖；人工分/建议作为追加事件独立保存。未打分时间点仍显示系统分和“未打分”。
- 查询：炉况数据仪表盘新增“高炉长评分”，真实诊断与 `local_fixture` 分源查看，可导出CSV/XLSX。
- 验证：18项测试、本机PostgreSQL两类事件实写、浏览器交互、关闭不写库、仪表盘查询/导出和Chromium规定视口均通过。Firefox/WebKit自动矩阵因依赖下载网络中断未执行。
- 边界：本次只涉及本机8096/8769和本机PostgreSQL；没有修改220.12的8093、8094、8768或生产数据库。

## Q-LOCAL-PG-PLAINTEXT-CREDENTIAL-POLICY-20260804

- 用户问题：定位本机psql密码，并修改协作约束，允许把本机PostgreSQL明文密码写入数据库账号配置说明。
- 结论：已用配置说明中的凭据实际登录`127.0.0.1:18000/postgres`，确认服务为PostgreSQL 16.13、账号为`postgres`；明文值只保留在[数据库账号配置说明](数据库账号配置说明.md#原生-postgresql-16-管理员连接)。
- 规则变更：[AGENTS.md](../AGENTS.md#本机-postgresql-维护口径2026-07-11)仅允许本机回环原生PostgreSQL和本地Docker管理/测试凭据集中写入该配置说明；禁止复制到其他普通文档、脚本、前端、日志、截图和接口响应。
- 历史边界：当时220.12密码仍禁止入库；该限制已被2026-08-04后续明确授权取代，当前只允许在 `docs/数据库账号配置说明.md` 集中明文记录220.12 PostgreSQL三类实际账号，其他普通文档仍禁止复制。
- 验证：Windows服务`postgresql-x64-16`为Running；`psql -w -h 127.0.0.1 -p 18000 -U postgres`登录`postgres`和`bf_trend`均成功，`bf_assistant` schema存在。

## Q-8096-DATABASE-CONFIG-AND-DEVELOPMENT-20260804

- 用户问题：`BF_DIAG_REVIEW_PG*`数据库变量如何定义、定义在哪里，以及开发功能时应该怎样使用数据库。
- 结论：这些字段是8096应用自定义的进程环境变量，不是PostgreSQL内置配置。PowerShell负责给当前进程赋值，启动器复制并补充非密码默认值，后端使用`os.getenv()`读取并限制为回环数据库，最终通过`psycopg.connect()`连接本机PostgreSQL。
- 实现：[启动器配置传递](../tools/start_diagnosis_review_preview.py#L51-L75)、[配置读取与本机边界](../高炉前端数据/智能助手/backend/diagnosis_review.py#L96-L136)、[连接与自动建表](../高炉前端数据/智能助手/backend/diagnosis_review.py#L475-L575)、[API鉴权与写入](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L5343-L5433)、[表结构](../高炉前端数据/智能助手/backend/schema/postgresql_diagnosis_review.sql#L1-L65)。
- 开发口径：前端只调用同源API，禁止接触数据库密码；8096后端优先复用`DiagnosisReviewStore`和现有校验；其他业务模块使用独立变量前缀、参数化SQL、迁移脚本及最小权限角色。
- 配置说明：[8096变量定义与开发调用链](数据库账号配置说明.md#8096变量定义与开发调用链)。
- 后续实测：用户在新PowerShell环境中未重新赋值，导致`-h`后的空值引发psql参数错位；小写`-w`同时禁止密码提示，继而报告未提供密码。已确认本机PostgreSQL 16.13及两张复核表正常，修正命令记录于[ERR-LOCAL-PSQL-EMPTY-ENV-ARGSHIFT-20260804](error_traceability.md#err-local-psql-empty-env-argshift-20260804)。

## Q-22012-POSTGRES-PLAINTEXT-CREDENTIALS-20260804

- 用户问题：确认220.12服务器实际数据库，并把真实数据库账号密码明文写入数据库账号配置说明。
- 实测结论：220.12运行PostgreSQL 16.13，服务器回环为`127.0.0.1:5432/bf_trend`，主要业务schema为`bf_sensor`；实际登录角色为`postgres`、`gl02_sync`和`gl02_reader`。
- 权限：`postgres`为超级管理员；`gl02_sync`是服务器运行写账号且可写`bf_sensor.diagnosis_snapshots`；`gl02_reader`可查询该表但不可插入，本机经SSLVPN使用`10.30.220.12:5432`连接。
- 凭据落点：用户明确授权三套完整密码只写入[220.12 PostgreSQL 16实际账号](数据库账号配置说明.md#22012-postgresql-16-实际账号)；`AGENTS.md`已同步允许这一单文件例外，禁止复制到其他普通文档、脚本、前端、日志、截图、接口响应或公开仓库。
- 验证：[只读账号探针](../tools/remote_probe_22012_pg_accounts.ps1)分别完成三套账号登录与权限查询，只输出密码长度和SHA-256，不输出正文；未修改远端数据库、账号、密码、服务或防火墙。

## Q-THREE-RULES-FOUR-ADJUSTMENTS-20260804

- 用户问题：先把三规二制文件转换为 Markdown 并验证文字一致，再基于其中
  四种炉况调剂方案，逐条说明实际建议引擎怎样升级为完全一致。
- 转换结论：4,934 个顶层段落中有 4,663 个可见文字段落、270 个空段落、
  1 个仅含空白；另有 122 张表、6,943 个真实单元格。源/写入有序文本片段
  哈希相同，校验通过。
- 规则结论：四种调剂是上部、下部、负荷和碱度四个动作维度，不是四种炉况。
  当前引擎按八类主诊断选择静态模板，无法表达跨维度顺序和条件。
- 关键冲突：热制度下行原文顺序为加风温→加煤→控氧减风→减轻负荷→加净焦，
  当前却先减风/减氧并禁止立即恢复喷煤；热制度上行原文先加风加氧、再加重
  负荷、减煤、减风温，当前从减煤/减风温开始。
- 用户追问：为什么组合规则只有两种，是否原文也只有两种，并要求立即升级建议引擎。
- 回答：两种只是旧 `combination.py` 手写了两个 `if`，不是《三规二制》只有两个组合。
  四类调剂是交叉动作维度，同一炉况可同时命中多个维度和多个安全/设备条件。
- 本地升级：新增[四类策略目录](../调控结论生成引擎/policy/three_rules_two_systems.yaml)、
  [动作合同](../调控结论生成引擎/recommendation/action_contract.py)、
  [策略评估](../调控结论生成引擎/recommendation/policy_evaluator.py)、
  [顺序规划](../调控结论生成引擎/recommendation/sequence_planner.py)和
  [冲突解析](../调控结论生成引擎/recommendation/conflict_resolver.py)；组合摘要改为
  任意主次标签通用合并。适配器版本升为 `v5-three-rules-two-systems`。
- 返回值：每条动作固定带 `source_refs/trigger_evidence/preconditions/blocking_reasons/
  delta/sequence/missing_inputs/observation_window/approval/read_only`，状态固定为
  `eligible/blocked/needs_data/manual_confirm`。
- 验证：[v5合同测试](../tests/test_three_rules_recommendation_engine.py) `10 tests / OK`。
- 边界：本次已改本地建议逻辑和适配器，但未部署远端8768/8093，未改正式页面，
  未做浏览器矩阵或现场工艺签字。

## Q-8093-ASSISTANT-NO-REPLY-20260804

- 用户问题：8093 页面中的智能助手再次无法回复，并要求把入口名称统一为“智能助手”、把固定检查流程写入 `AGENTS.md`。
- 修复前状态：8093、11434、8768 服务均为 Running；`2026-08-04 21:25` 第一层探针确认 `/api/ollama/status` HTTP 200、`proxy_ok/ollama_ok/model_ok=true`，11434 `/api/ps` 只驻留批准的 `chiqiong-blast-furnace:latest` 27.8B。绿灯只能说明探测时点可用，不能排除分钟级守卫重启。
- 本次无回复的直接原因：`proxy_8093.health.log` 在 `20:46`、`20:47`、`20:51`、`20:56`、`21:48` 因 `tcp_down_127.0.0.1_8093` 立即触发重启，`20:59` 因 `/api/automation/status` 不可达触发重启，`21:15` 又因 `/api/ollama/status` 与 `/api/automation/status` 同时不可达触发重启；runner 日志存在对应重新拉起记录。代理重启会直接切断在途 `/api/qa/chat` SSE，所以页面表现为请求已发出但没有回复。
- 次级风险：8093 实际进程的 `BF_QA_KNOWLEDGE_SEARCH_MODE` 为空，代码回退 `hybrid`；11434 实际 `OLLAMA_MAX_LOADED_MODELS=1`。该组合可能让知识问答在同端口调用 embedding 并与单一 27B 驻留槽争用，是后续仍需受控 SSE 复现确认的配置风险，不能替代本轮已经确认的守卫重启证据。
- 实现位置：[前端入口](../高炉前端数据/frontend_dashboard_v3.server.html)、[问答代理](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[第一层健康探针](../tools/probe_8093_assistant_health.ps1)、[日志尾部探针](../tools/probe_8093_assistant_log_tail.ps1)、[固定流程](../AGENTS.md#8093-智能助手无回复固定检查流程2026-08-04)。
- 名称部署：8093 页面已热更新为“智能助手”，远端备份为 `backups\8093_assistant_name_20260804\20260804_212113`，新页面 SHA-256 为 `E091DDC33FC279F4A9EA67AA45F0417A1DCC7EF83A0A72B4E520867C8BF7EBCB`；cache-bust HTTP 与浏览器截图均确认旧名称为 0、新名称可见，8094 页面 SHA-256 保持不变。
- 正式修复：22:54 已把 8093 守卫调整为 `3 次连续失败 + 15 秒二次确认 + 10 分钟重启冷却`，服务真正停止仍 1 次恢复；状态文件为 `logs/proxy_8093.health.state.json`。部署没有重启 8093、11434、8768、8094 或 8770，相关 PID 与页面哈希均保持。
- 真实验收：23:03 只提交 1 次新会话 SSE，收到 `start(preparing/prepared) -> delta -> final -> done`；首个 delta `6321.2ms`、final `6583.6ms`，回答非空，验收期间没有守卫重启，模型前后都只驻留批准的 27.8B。远端报告为 `logs/acceptance/8093_health_guard_sse_20260804_20260804_230300/assistant_sse_once.json`。
- 后续处理：本轮守卫修复当时没有修改知识模式；2026-08-05 已按 `OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805` 把 8093 显式切为 `keyword`，消除了空值回退 hybrid 与单驻留组合风险，且没有修改 embedding 布局或 `OLLAMA_MAX_LOADED_MODELS=1`。
- 长期查找入口：复发时直接读取 [AGENTS 固定流程](../AGENTS.md#8093-智能助手再次不可用时的直接修复记录长期固定)和 [DOCX 修复手册](8093智能助手不可用原因与正式修复手册_20260804.docx)，先判断是否存在守卫重启证据，再决定恢复守卫合同还是转查模型/RAG/MCP/数据库；不得以稍后状态全绿替代历史日志核查。

## Q-8093-8094-PROMPT-RAG-RUNTIME-20260805

- 用户问题：固定 Prompt 是否等于固定注意力分数，以及当前从 8093/8094 提问是否会加载对应 Prompt 模板和知识库回答链路。
- 结论：固定的是身份、安全边界、回答规则和固定工艺规则组成的公共 token 前缀顺序，不是模型内部 attention score。两端口每次 `/api/qa/chat` 都构造同一公共 Prompt；RAG 按问题意图条件触发，数据问题优先 MCP，问候/状态/身份/安全问题跳过 RAG。
- 实现：[Prompt 与固定规则](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L188-L270)、[知识意图门控与检索](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4771-L4876)、[单轮上下文拼装](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4880-L4938)、[PostgreSQL RAG](../高炉前端数据/智能助手/backend/bf_knowledge_rag.py#L666-L724)。
- 当前运行态：2026-08-05 06:54 的变更前只读核查确认两端口共用后端且知识链路可访问；07:25 已把 8093 从空值回退 `hybrid` 受控切为显式 `keyword`，8094 仍为 `keyword`。两个端口的知识总开关/意图门控/MCP 均启用，`top_k=6`。
- 验收边界：11434 仍为单 27B 驻留，8093/8094 当前知识链路只做关键词/词法检索。08:44 只发送 1 次真实知识问答，准备态显示 `parameter_optimization` 知识意图、知识检索启用且命中 2 条证据，MCP 工具调用关闭；完整收到 SSE，期间未加载 embedding、未发生守卫重启。
- 专项记录：[8093/8094 Prompt 固定 KV 前缀与知识库回答链路](8093_8094_Prompt固定KV前缀与知识库回答链路_20260805.md)；运行探针：[probe_8093_8094_prompt_rag_runtime.ps1](../tools/probe_8093_8094_prompt_rag_runtime.ps1)。

## Q-8093-KNOWLEDGE-KEYWORD-MODE-20260805：把 8093 设置为关键词模式

- 用户问题：把 8093 显式设置为关键词模式，让知识库做关键词和词法检索。
- 实现：在 8093 服务启动环境中固定 `BF_QA_KNOWLEDGE_SEARCH_MODE=keyword`；没有修改公共 Prompt、知识意图门控、PostgreSQL `bf_assistant.rag_*` 数据、共享后端/RAG 代码或 11434 单 27B 策略。
- 部署：使用 [受控部署器](../tools/remote_guarded_deploy_8093_keyword_knowledge_mode.ps1)只停止/启动 8093，失败自动回滚；配置 SHA-256 更新为 `8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE`，备份在 `logs/deploy_backups/8093_knowledge_keyword_20260805_072445`。8768/8094/8770/11434 PID 和受保护文件均未变化。
- 结果：实际监听进程环境和默认知识搜索接口都显示 `keyword`，默认检索命中 2 条证据。08:44 的唯一真实问答 POST 完整收到 `start(preparing/prepared) -> delta -> final -> done`，总耗时 `23.8856s`；准备态证明知识链路确实参与而不是仅检查独立搜索接口。远端报告在 `logs/acceptance/8093_keyword_knowledge_20260805_20260805_084403/assistant_keyword_knowledge_sse_once.json`。
- 为什么可行：keyword 继续保留 PostgreSQL 词法候选与证据注入，但不调用 embedding，因此不会在 `OLLAMA_MAX_LOADED_MODELS=1` 的共享 11434 上与已驻留 27B 抢模型槽；实时数据问题仍按既有意图门控走 MCP/数据库，不被强制改成知识检索。

## Q-8093-MCP-SERVICE-COUNT-AND-HEAT-QUERY-20260805

- 用户问题：当前一共运行了多少个MCP服务，为什么“当前炉次+上一炉次Si平均值”返回数据库查询轮数超过上限，以及通常应怎样设计MCP服务和工具调用方案。
- 数量口径：源码与220.12部署中有2个正式FastMCP实现，分别为18工具的数据MCP和13工具的IMES只读MCP，共31个工具；8093问答当前只挂载1个数据MCP；两个stdio MCP均按请求启动，所以空闲时常驻MCP进程数为0，不能用进程数判断能力是否部署。
- 结论：原问题范围明确，失败不是数据库无数据，而是单服务工具暴露、跨服务目录执行断链、炉次工具名漂移、缺少复合业务工具与两轮规划上限共同造成。详细根因见[错误追踪](error_traceability.md#err-8093-mcp-heat-composite-round-limit-20260805)。
- 设计口径：按数据源/权限边界拆MCP服务，按完整业务任务设计复合工具；编排层先做确定性高频路由，再用模型规划兜底；跨服务问题由显式聚合器/DAG执行，工具返回统一结构化来源、时间、样本数和质量，错误码与完整调用轨迹持久化。
- 本轮边界：只读核查代码、目录、工具清单、220.12部署文件/进程/端口；未修改8093代码、配置、数据库或服务，未执行新的生产问答。07:07:27逐工具轨迹因SSLVPN/远端连接超时未读回。

## Q-8093-MCP-ON-DEMAND-MES-ORCHESTRATION-20260805

- 用户问题：附件提出的按需调用MCP服务策略是否合理，为什么8093不能根据MES/IMES查询结果继续交互，以及应如何优化。
- 判断：附件的Host/Client/Server、规则筛选、模型选工具、结构化反馈、风险分级和渐进式披露方向合理；对当前2服务/31工具规模，不应先引入模型生成代码执行或把三个元工具作为必经步骤，应先完成Host侧多Client、领域路由、命名空间注册表、复合业务工具和证据状态。
- 当前根因：8093只有一个`MCP_DATA_SERVER_PATH`，一次问答仅启动`bf_data_mcp_server.py`并列出其工具；IMES MCP没有加入同一Host工具集合。业务对象目录虽然声明`executor.service=imes-relay-mcp`，Host却没有按服务路由Client，且炉次目录引用不存在的`query_imes_business`。
- 对话缺口：现有状态主要保存传感器对象、相对时间和图表偏好，没有炉次号、试样号、取样时间、MES profile与可复用`evidence_id`，所以即使独立取得MES结果，也不能稳定支持“与上一炉比较”“把这些炉次画出来”等追问。
- 推荐：P0先实现两服务registry/client manager、IMES确定性领域路由、目录工具名修正和`get_current_previous_heat_si_summary`复合工具；P1补证据存储与审计；P2再做连接TTL、Schema缓存和大规模渐进式发现。
- 专项复核：[8093 MCP按需服务发现与MES多服务编排复核](8093_MCP按需服务发现与MES多服务编排复核_20260805.md)。本轮只改文档，未修改8093、MCP、数据库或服务。

## Q-8093-CORE-METRIC-DELAY-20260804

- 用户问题：核心指标与现场实时数据差距大，要求当前值改为 pSpace 秒级流，历史分析继续使用 PostgreSQL 分钟数据，并显示数据时间、年龄、质量和明确降级状态。
- 根因：旧核心指标当前值取自 8768/PostgreSQL 分钟镜像，本身存在分钟采样与同步延迟；页面还用无时间戳语义的 `Object.assign` 合并历史，较短或不完整的 trend 数组可能覆盖 8768 完整数组。
- 修复：8770/pSpace 只覆盖当前值；8768 继续承担历史、火花线、趋势、诊断和基线；历史改为时间戳对齐且 8768 重叠点优先，不完整序列忽略。实时链路依据传输年龄而不是“最后变化时间”降级，避免稳定值被误判断流。
- 结果：生产 28/28 实时覆盖，实测传输年龄 `0–2.4 秒`；主动断流后 28/28 切换到带时间戳的分钟镜像。完整证据见[专项记录](8093_核心指标pSpace秒级实时与分钟镜像降级_20260804.md)。

## Q-8093-MULTI-MCP-HOST-IMPLEMENTATION-20260805

- 用户要求：在完成按需多 MCP 策略复核后开始实施。
- 已实现：两服务注册表、确定性领域路由、命名空间 Client Manager、8093 工具循环多服务接入、当前炉次工具、当前/上一炉 Si 复合工具、目录合同修正和精简炉次证据。
- 高频口语：“当前属于第几个炉次？上一个炉次铁水的硅含量平均值是多少？”固定生成一次 `imes__get_current_previous_heat_si_summary`，不再消耗两轮模型试探。
- 安全：生产 Host 明确排除任意只读 SQL；跨源服务部分失败时整体拒绝返回，避免用单侧数据生成不完整结论。
- 验证：本地相关回归 `38 passed`；真实 MCP SDK 服务发现三组均成功，分别暴露 IMES 14、GL02 18、跨源 32 个工具。
- 当前结果：2026-08-05 已受控部署到 220.12；真实 MES 单次 SSE HTTP 200，命中 `imes__get_current_previous_heat_si_summary`，返回当前 `2#20240805-056`、上一炉 `2#20240805-055`。上一炉有效 Si 试样数为 `0`，系统返回 `NO_SI_SAMPLES`，没有伪造平均值。
- 保护结果：8093 PID `15352→7348`；8768=`15824`、8094=`9976`、8770=`12956` 保持不变。备份与验收见[交接记录](handoffs/2026-08-05-8093-multi-mcp-deploy.md)。
- 记录：[专项文档](8093_MCP按需服务发现与MES多服务编排复核_20260805.md)、[ADR-0001](adr/0001-8093-multi-mcp-host.md)。

## Q-8093-TOP-PRESSURE-DIRECTION-AND-CLOCK-LAG-20260805

- 用户问题：核对现场画面中四个方向顶压数值是否在 pSpace 出现，据此判断 A/B/C/D 对应方向，并解释 8093 右上角时间及核心指标仍明显落后于电脑时钟的原因。
- pSpace 证据：只读直连 `10.22.181.243:8889` 查询 `2026-08-05 09:00:00～09:08:30` 原始历史，四点分别为 `T0067/T0068/T0069/T0070`。例如 `09:02:57` 的 A/B/C/D 为 `256.1849/255.6858/256.1198/255.3494`，一位小数为 `256.2/255.7/256.1/255.3`；`09:07:28` 为 `256.0/255.5/255.8/255.3`。这些组合与三张现场照片的东北/东南/西北/西南数值及相对高低关系一致。
- 方向判断：高置信度映射为 `A=东北、B=东南、C=西北、D=西南`，对应 `P_top_gas_A/B/C/D`。现有[班长变量审计脚本](../tools/audit_foreman_49_variables.py)第 32～33 行把压力 A/B 暂定为东南/东北，且注释明确称方位未确认；该暂定关系与本次 pSpace/现场同步数值证据相反，后续修复应交换压力 A/B，C/D 不变，并补充回归合同。本轮只读核查未改脚本或生产映射。
- pSpace 源点时效：8770 启动器固定 `RealReadList` 轮询为 1 秒；实抓 5 帧约每 1.5 秒到达，链路没有 30 秒队列积压。220.12 系统时间与 pSpace `GetServerTime()` 同秒，但四点当前源时间在查询时落后约 33 秒；09:00～09:08 原始点时间也主要按约 33～40 秒间隔成批更新。因此页面显示的约 30～40 秒“年龄”主要是 243/pSpace 上游点值刷新周期，不是 8770 WebSocket 传输延迟。
- 顶部时钟根因：[前端 Header](../高炉前端数据/frontend_dashboard_v3.server.html)把右上角“时间/刷新”绑定到 `currentTime`，而 `handleInit/handleTick` 又从 8768 的 `msg.timestamp` 赋值。8768 是 PostgreSQL 分钟镜像，不是 pSpace 或系统时钟。`09:48:37` 浏览器实测时，顶部显示 `09:47:02`，pSpace 横幅为 `09:48:02`、指标年龄 34 秒；另一次 8768 直连在 `09:49:56` 收到的最新时间仍为 `09:48:00`，落后约 116 秒。
- 结论与建议：核心指标数值当前确实走 pSpace，但其上限实时性受源点约 33～40 秒刷新周期限制；右上角时间还混用了分钟镜像语义。后续应把顶部“系统时间”改为浏览器/服务器校时后的墙钟，另行显示“分钟数据时间”和“pSpace数据时间/源年龄/传输年龄”；若要求指标接近现场秒级变化，还需继续排查 243 侧 SIO/OPC 到 pSpace 标签的采集/压缩/例外归档周期，单纯提高 8770 轮询频率不会消除这 30～40 秒。
## Q-IMES-LOCAL-MULTI-MCP-RELAY-20260805

- 用户问题：把 8093 已有 MCP 加载到本机，并同时通过 MCP 访问 IMES Web 与 Vastbase；
  核实 SSLVPN 是否足以直连 Vastbase，以及此前 GUI 转发为什么只看到 Web、现在是否已修复。
- 结论：本机注册表现有 `gl02-data`、`imes-readonly`、`imes-web-readonly` 三个服务，
  Host 可见工具总数为 35。生产 8093 目前仍是已部署的 GL02+IMES 两服务；本机 Web 服务
  是只读白名单扩展，缺少验证码/受控会话时返回 `IMES_WEB_CAPTCHA_REQUIRED`。
- 网络结论：SSLVPN 只提供“可能存在路由”，不保证目标 ACL/防火墙允许直连。当前可靠合同
  是本机经 220.12 建立 `15433` Vastbase 与 `18080` Web 回环转发；MCP 不自动切直连。
- GUI 根因与修复：旧命令用单个 `--forward` 覆盖了 `--profile all` 的默认转发列表，
  只启动 Web；现改为 `--profile imes`，并在状态页同时探测 HTTP/TCP。实现和组合入口见
  [imes_web_launcher.py](../tools/imes_web_launcher.py) 与
  [start_imes_web_vastbase_relay_local.cmd](../tools/start_imes_web_vastbase_relay_local.cmd)。
- 边界：本轮只完成本机代码、注册表、转发入口和交接文档，未把 Web MCP 部署到 8093，
  也未重启 220.12 上的生产服务。

## Q-8093-SYSTEM-CLOCK-AND-5S-DATA-20260805

- 用户问题：把 8093 改成真正系统时钟；确认 pSpace 到 220.12 是否半小时一次、8093 是否只读该数据库；说明如何保持 5 秒实时并合理保存数据，以及长期数据是否为分钟平均值。
- 时钟结果：顶栏“时间”现由浏览器终端 `new Date()` 每秒更新；8768 的最新 PostgreSQL 时间独立显示为“分钟数据”。2026-08-05 10:26 通过守卫闭环上线，备份 `backups\8093_core_metrics_pspace_live_20260804\20260805_102647`；`guard_paused=true`、`guard_restored=true`、8093 HTTP 200，8768/8770/8094 PID 与受保护哈希未变化。
- 周期结论：不存在“半小时一次”的主同步。8770 当前对 pSpace `RealReadList` 的轮询周期为 1 秒；PostgreSQL 持续同步进程的循环休眠为 30 秒，源读取配置是 5 秒 raw、目标粒度 60 秒；同步看门狗每 5 分钟运行，pSpace reconciliation 每 60 分钟仅做显式低频核对，不是主采集。
- 页面链路：核心指标当前值是 `10.22.181.243 pSpace -> 220.12:8770 -> 8093 浏览器`，不读取 PostgreSQL；火花线、趋势、诊断、基线和降级镜像才是 `pSpace历史 -> PostgreSQL one_minute_values -> 8768 -> 8093`。
- 保存口径实施：长期主表一点一分钟、保留3年；自2026-08-05 21:55起已用`PS_RAW_AVERAGE/valid_raw_mean_v1`保存有效Good raw分钟平均，并带`min/max/last/count/good_count/coverage/window_complete`审计。旧`PS_RAW_SAMPLE`段不改名。`raw_5s_values`已恢复持续写入并保留30天。
- 5 秒方案实施：页面继续直走8770内存流；历史同步同一次SDK raw读取同时写短期明细和分钟平均，没有为保存raw增加第二次pSpace读取。上游点位源时间仍可能慢于5秒，最终实时性继续用源时间戳与8770传输时间分别验收。完整记录见[pSpace分钟语义统一](pSpace分钟语义统一_20260805.md)。
- 当前限制：8770 已经每 1 秒轮询，实际帧传输约 1–2 秒，但顶压等源点约 33–40 秒才更新一次。把 PostgreSQL 的 30 秒循环改成 5 秒只会增加重复查询和写入压力，不会让现场值变新；必须先改 243 上游发布周期并用源时间戳验收。
- 浏览器验收：Edge `1366×768` 通过，系统时钟秒差 `1.231s`、分钟数据 `11:03`、pSpace `28/28`、横向溢出 0、页面/控制台错误 0。Chrome `1920×1080` 和 `1366×768` 的秒差分别为 `1.084s/1.380s`。连续矩阵期间 8093 静态代理对 ECharts/OrbitControls 间歇返回空响应，窄屏矩阵未记为通过，见错误追踪。

## Q-IMES-HEAT-LAB-65-VS-MCP-20260805

- 用户问题：IMES Web 已能看到最新约 65 炉次的化验结果，为什么 MCP 查询不到。
- Web 证据：截图中的 `2#20260805-065` 显示 `C=4.99、Si=0.23、Mn=0.22、P=0.157、S=0.04`；
  `069`～`066` 仍是索引但元素为空。
- 远端只读复核（2026-08-05 10:50～10:52）：220.12 实际 MCP 连接 `10.10.181.195:5432/vastbase`
  的 `operations/gl2#dmx` 账号可以直接读到 `2#20260805-065` 的 3 条正式化验记录，
  Si 为 `0.20、0.25、0.24`，算术平均为 `0.23%`；`2#20240805-056` 为 0 条。
  因此数据库中并非没有 065，之前把 operations 账号判断为错误账号是不准确的。
- 实际根因：`get_current_heat_context`/`get_current_previous_heat_si_summary` 的
  `_query_recent_heat_context_rows` 先按“未关口 (`closetime IS NULL`)”排序，把历史的
  `2#20240805-056` 误判为当前活动炉次；随后复合工具查询 `055`，返回 `NO_SI_SAMPLES`。
- 修复：当前/上一炉选择改为先按正式 `COALESCE(opentime, workdate) DESC, meltno DESC`，
  再单独判断活动状态，并增加 72 小时默认新鲜度上限；化验专用账号保持可配置，默认使用
  已实测可读到 065 的 `operations`，本机 `IMES_DB_*` 仍会覆盖历史回退账号。
- 验收目标：指定 `2#20260805-065` 返回 3 个 Si 样本及均值 `0.23%`；当前/上一炉不再返回
  2024 年历史未关口炉次。Web MCP 的浏览器会话隔离仍需验证码或受控 Cookie，不能自动
  读取浏览器 `JSESSIONID`。

## Q-8093-DIAGNOSIS-SCORE-HISTORY-20260805

- 用户问题：IMES Web 可以看到炉次化验结果，但智能助手报轮数上限；进一步询问“之前一阵的管道分数上升”时是否无法获取前几次炉况分数。
- 化验结论：`2#20260805-065` 的正式 Si 试样为 `0.20/0.25/0.24%`，平均 `0.23%`；之前取不到不是化验表缺数，而是当前/上一炉选择把2024年遗留未关口行排在2026年炉次之前。详见[ERR-8093-MCP-STALE-OPEN-HEAT-20260805](error_traceability.md#err-8093-mcp-stale-open-heat-20260805)。
- 炉况分数结论：不是“前几次分数完全无法获取”。`ollama_proxy_server.py` 的 `recent_pg_diagnosis_snapshots_for_qa` 已能读取 `bf_sensor.diagnosis_snapshots` 的最近8小时、5分钟诊断时间线，隐藏上下文能够提供 `main_score` 和 `raw_scores.channel`；远端状态接口也确认数据库正常且诊断队列持续写入。
- 失败原因：当前8093 MCP没有历史诊断分数专用工具，只有最新快照工具；“管道分数”没有确定性对象映射，带“分析”的问题进入通用MCP规划。默认两轮规划耗尽后，循环返回“数据库查询轮数超过上限”，因此表现为无法回答。
- 建议：增加历史诊断分数MCP工具和“管道分数/炉况分数/诊断分数”确定性路由，默认把“之前一阵”解释为最近8小时或要求用户给出明确窗口；一次工具调用后再做趋势/原因分析。增加轮数只能缓解偶发复杂问题，不能替代工具合同。
- 本轮边界与验证：本轮只读核查代码、`/api/automation/status` 和数据目录，未修改8093、数据库或服务。建议修复后的验收固定覆盖：返回至少3个历史点、包含时间戳与 `channel` 分数、能识别上升区间，并且不再出现 `PLAN_ROUND_LIMIT_EXCEEDED` 文案。

## Q-8093-ASSISTANT-AUTO-RECOVERY-20260805

- 用户要求：建立统一的一键智能助手诊断入口，远端操作前检查 VPN/SSH/8093/11434/PostgreSQL；预置 SHA-256 包；加入真实 PowerShell 5.1 数字键 JSON 模拟；固定完整流水线并把服务恢复与文档生成分开；keyword 漂移不再重复排查。
- 实现：[assistant_8093_auto_recovery.py](../tools/assistant_8093_auto_recovery.py) 提供 `prestage/diagnose/recover/docs`；远端合并诊断、守卫/keyword 部署和唯一 SSE 都从不可变包以短 `-File` 运行。
- 分类策略：现行状态 healthy；已知空值/hybrid 直接 keyword；已知守卫合同漂移直接守卫部署；未知哈希拒绝。健康 recover 不部署、不重启，但仍完成默认知识搜索和唯一 SSE。
- 测试：组合 `22 passed`，其中两个用例实际调用 Windows PowerShell 5.1 验证数字端口键数组化和 UTF-8 BOM。
- 真实结果：包 `20260805_v1_22e4eb675eee` 校验完成；diagnose 约 67 秒为 healthy；recover 前后 healthy、无修复动作，服务阶段 184.618 秒；唯一 SSE 22.1859 秒、keyword 命中 2 条证据，所有保护检查通过。
- 记录：[专项文档](8093智能助手自动诊断修复验收工具_20260805.md)、[CLI](cli_usage.md)、[自动化追踪](automation_traceability.md#ops-8093-assistant-auto-recovery-20260805)、[DOCX](8093智能助手不可用原因与正式修复手册_20260804.docx)和源报告 `logs/assistant_8093_auto_recovery/20260805_110327_recover.json`。

## Q-OPT-MULTI-CONDITION-LLM-REVIEW-20260805

- 用户问题：建议分析页能否随不同炉况显示不同建议及曲线；能否把其他炉况建议也放入页面，并增加后台高炉大模型对该炉况诊断分数的判断；随后明确要求开始实施。
- 结论：可以，但必须区分“当前有效方案”和“条件预案”。当前主/次炉况仍由确定性规则统一合并和安全门禁处理；选择其他炉况时展示的是“若该炉况成立”的独立只读预案，不能混入当前执行顺序。
- 实现：8767 返回八炉况 `recommendation_bundle`；页面顶部矩阵可切换八类炉况，原优化驾驶舱接收所选炉况投影，所以建议标题、证据、分数、基线/时间曲线和完整动作详情一起变化。页面始终标明 `active/supporting/hypothetical`。
- 每条建议实际返回并显示：原文章节、触发证据、前置条件、阻断原因、调剂幅度、执行顺序、缺失数据、观察窗口、审批要求、执行边界；四态分别显示为条件满足、安全阻断、缺少数据和人工确认。阻断或缺数据的动作不会被删除。
- 模型边界：模型返回 `agree/partial_agree/disagree/insufficient_data`、支持程度、支持/矛盾证据、缺失数据、观察重点和人工复核标记；它不替代规则分数，不生成或修改调剂动作。模型失败、停止或未启用时，规则建议仍完整可用。
- 当前范围：本轮已完成本机代码、测试、隔离浏览器验收和文档；未重启或部署 220.12 的 8093/8768，也未写生产数据库。

## Q-FOREMAN-TREND-STANDALONE-PREVIEW-20260805

- 用户问题：先不删除当前趋势页，单独制作一个新的工长趋势页，先对比现场实际效果，并询问打开地址。
- 交付：新增 `高炉前端数据/foreman_trend_preview.html` 独立预览页；原正式趋势页仍通过 `frontend_dashboard_v3.server.html#trend` 使用，未被替换。
- 查看地址：`http://127.0.0.1:8092/foreman_trend_preview.html?fixture=1` 用于固定布局比较；`http://127.0.0.1:8092/foreman_trend_preview.html?ws_port=8767` 用于现有 8767 实时流。
- 现场复刻口径：顶栏、7×7 变量表、灰色 HMI 工具栏、上方多通道长趋势、下方阶梯/脉冲周期趋势、底部导航均独立实现；夹具状态明确标注“非生产”，不把示例值伪装成实时数据。
- 验收：静态 `4 tests / OK`；Edge/Chromium、Firefox、WebKit 共 `17 checks / PASS`，无页面/控制台错误。完整报告位于 `logs/foreman_trend_preview_20260805/report.json` 与 `logs/foreman_trend_preview_20260805/viewport_matrix/report.json`。
- 220.12 交付：2026-08-05 已发布到既有 8093 静态服务；直接访问 `http://10.30.220.12:8093/foreman_trend_preview.html?ws_port=8768`。该地址使用 220.12 的既有 8768 PostgreSQL 分钟流，不是 8770 pSpace 秒级直连。生产冒烟数据时间为 `14:30:00`，29 项有实际值、20 项保持 `--`，`12/12` 主趋势和 `5/5` 下方趋势完整，浏览器错误为 0；证据见 [远端报告](../logs/foreman_trend_preview_20260805/remote_8093_live_report.json)。
## Q-20260805-22012-DIRECT-IMES-PSPACE

- 用户问题：能否不再把 220.12 仅当 SSH 跳板，而让 VPN 客户端直接打开
  `220.12:18080` 的 IMES Web，并通过 220.12 使用 Vastbase/pSpace？
- 结论：已实现。Web 使用 Nginx 路径代理，Vastbase/pSpace 使用固定 TCP
  portproxy，来源限定到当前 VPN 客户端；客户端无需再常驻本机 SSH 回环进程。
- 实现与验收：[需求追踪](requirements_traceability.md#ops-22012-direct-source-relays-20260805)、
  [运行手册](22012_IMES跳板转发与MCP.md#0-2026-08-0522012-vpn-直达入口已经上线)、
  [交接记录](handoffs/2026-08-05-22012-direct-source-relays.md)。
- 边界：15433/18889 不是浏览器页面；仍必须使用只读数据库账号与 pSpace SDK/MCP
  业务账号。IMES 验证码不会写入文档或服务配置。

## Q-8093-PSPACE-CONNECTION-AND-MINUTE-SEMANTICS-20260805

- 用户问题：8093 看起来无法访问 pSpace，可能是网络阻塞或 8770 读取通道关闭；希望尝试修复，并先明确现有分钟表的语义。
- 当前状态：8093 的 pSpace 通道实际在线。浏览器总览为 `pSpace秒级实时 28/28`，7秒内最新时间从 `20:58:57` 推进到 `20:59:03`；当前可见14项均显示 pSpace 数据时间、秒级年龄和“良好”质量，没有降级标记。
- 网络解释：本机没有 `10.22/10.30` 系统路由、aTrust VNIC 处于断开状态，所以 PowerShell/普通本地进程直连 8093 会失败；但已认证的 aTrust“高炉模型”应用代理仍可让 Chrome 访问 8093。两类路径必须分开判断。
- 服务处理：页面已给出 8770→浏览器持续收帧的直接证据，且没有 8770/pSpace/WebSocket 控制台错误，因此没有重启生产服务，也没有写数据库。
- 分钟表实施结果：历史`PS_HIS_AVERAGE`和截止2026-08-05 21:54的`PS_RAW_SAMPLE`保持真实标签；自21:55起新增量统一为`PS_RAW_AVERAGE/valid_raw_mean_v1`，值为同分钟有效Good raw算术平均。
- 原始与审计：同一次pSpace raw读取持续写30天`raw_5s_values`，分钟行保存样本数、Good数、覆盖率、min/max/last、60秒闭窗状态；没有把缺失样本补零。
- 运行修复：清除了两个孤儿包装器造成的重复读取，两套目录现共用项目根排他锁；当前一个包装器、133点同步错误0。
- 验收：生产分钟值与raw重算1,159行差异0；8770秒流133/133，8768继续是PostgreSQL分钟流，8093明确连接8770。完整记录见[pSpace分钟语义统一](pSpace分钟语义统一_20260805.md)。

## Q-22012-IMES-MCP-PRODUCTION-SYNC-20260805

- 用户问题：是否只有本机存在 MES/IMES（口语中称 MAS）数据库 MCP；要求把本机依赖服务增加到 220.12 生产服务配置，让服务器模型可以调用。
- 核查结论：220.12 已有早期 `imes-readonly`，但注册表只有两个服务且 MES MCP/语义目录落后于本机；因此问题不是“完全没有”，而是生产目录和版本没有同步齐全。
- 实施：将生产注册表扩为 `gl02-data`、`gl02-extended`、`imes-readonly`、`imes-web-readonly`，采用 220.12 厂内直连端点；只重启 8093，并恢复健康守卫。
- 验收：模型在不强制指定工具时，能自动回答当前/上一炉次和上一炉 Si 均值，也能自动查询炉身 13 层 C 点温度。8768/8094/8770 未重启。
- 记录：[需求](requirements_traceability.md#req-22012-imes-mcp-sync-20260805)、[生产交接](handoffs/2026-08-05-22012-imes-mcp-production-sync.md)。

## Q-8093-CROSS-DATABASE-MCP-ON-DEMAND-20260805

- 用户问题：在8093多用几种复杂口语，核查模型能否按需调用两个不同数据库，并解释按需调用机制。
- 实测结论：工具层能够在同一问答调用 `imes-readonly` 与 `gl02-data/gl02-extended`，但复杂口语可靠性不足；常见复合问题会被 MES 或传感器的单一确定性快捷计划提前截获，另一个数据库被遗漏。
- 多规划器边界：未触发快捷计划时，模型可以跨服务调用，但出现目录查询占轮数、重复MES调用、工具超时、炉次号丢失 `2#`、`P_top`误派到历史炉况工具和最终回答截断。
- 状态边界：本轮没有修改生产代码或重启服务；8093 PID `14352` 未变化。完整问题、工具轨迹与修复优先级见[跨库口语验收](handoffs/2026-08-05-8093-cross-database-mcp-audit.md)。
## Q-OPT-VISUAL-COCKPIT-REGRESSION-20260806

- 用户问题：升级 8 类炉况建议后，原建议页的数字卡、迷你趋势、炉况演化和基线偏离图为何大量不可见，优化后页面应采用什么结构。
- 核查结论：图表主体仍由 `OptimizationEngineCockpitLayout` 生成，但新矩阵、标题、驾驶舱、审计和模型复核共同进入固定高度网格；1366×768 实测驾驶舱顶部高度为 0，底部图表与审计区域重叠。新版证据卡还遗漏了旧版 `ChartBox` 迷你趋势。
- 推荐结构：首屏恢复可视驾驶舱；8 类炉况改为紧凑切换条；动作完整审计和模型复核进入第二屏/详情抽屉。所有图表随所选炉况更新证据变量、得分历史、基线偏离、门禁和动作队列。
- 实施结果：[建议工作台](../高炉前端数据/frontend_dashboard_v3.server.html#L10530)已改为单一纵向滚动；首屏恢复4张主证据迷你曲线、实时监测、风险门禁、两张历史图和建议队列；动作审计与模型复核改为右侧抽屉。
- 证据扩展：固定19项核心变量默认折叠，展开后提供当前值、15分钟变化及百分比、30天基线、数据时间/年龄、60分钟曲线、单变量详情及四点顶压/顶温对比；所选炉况的4项主证据仍独立保留。
- 验收：本地真实页面逐一切换8种炉况；19项变量唯一且齐全；九个Chromium视口及Firefox/WebKit代表视口无横向溢出。只读探针仍为 [probe_remote_recommendation_layout.cjs](../tools/probe_remote_recommendation_layout.cjs)。

## Q-DIAGNOSIS-CORE-19-EVIDENCE-TRENDS-20260806

- 用户问题：所选炉况只显示约4项证据过少，希望继续保留这4项，同时可展开查看19项核心变量，并点击查看曲线及变化。
- 结论：4项是所选规则的主证据，不能被统一集合替代；新增的19项是跨炉况固定观察面，两者同时保留。
- 实施：评分弹窗先展示所选炉况主证据，再提供固定19项展开区；每项显示当前值、5分钟变化、30天基线和数据时间，点击显示最近60分钟曲线。
- 可用性修复：19项改由独立轻量只读接口提供，不再被完整智能分析、调剂引擎或知识库耗时阻塞。
- 本机优先：源代码、生成产物、合同测试和部署脚本均先更新在本项目，再上传220.12；8093远端主产物SHA-256与本机生成产物一致。

## Q-IMES-MATERIAL-SPEED-FUEL-RATIO-20260806

- 用户问题：IMES 是否已经提供料速、燃料比；要求把完整数据库同步配置和程序同步到当前项目，并再次核查生产落库闭环。
- 只读结论：Vastbase 正式表与 220.12 IMES 镜像均无料速/燃料比直接字段。批次时间、矿焦批重量、原料干量和铁量可支撑派生；完整燃料比还需要 pSpace 喷煤累计，因此是跨源指标。
- 本地交付：已按白名单同步 V4 `数据库同步和存取` 模块 43 个文件，排除秘密、日志、数据和备份；清单为 `数据库同步和存取/module_sync_manifest.json`。
- 生产复核：243 可达，Watchdog 运行、旧任务禁用、单同步链；分钟与5秒表均为148点，新增15个物理点全部有15:02实际值，当前小时喷煤派生视图通过。
- 边界：pSpace 落库闭环通过；料速/燃料比尚未建立正式派生表/API，必须先统一批/小时与干焦/湿焦、班/日/炉次等语义。完整记录见 [IMES料速与燃料比只读核验](IMES料速与燃料比只读核验_20260806.md)。

## Q-8093-8094-DIAGNOSIS-ASSET-PARITY-20260806

- 用户问题：本机新版与8093页面资源不一致，导致智能分析显示“暂不可用”，并且更新其它功能后评分弹窗/手动评分模块丢失；要求用本机新版同时修复8093和8094。
- 根因：远端页面在 `</head>` 前注入诊断脚本，远端旧脚本在 `document.body` 尚未创建时直接执行并抛错；本机新版已增加 `bootWhenBodyReady`，但此前没有随资源同步到220.12。后端配置、代理诊断块和评分接口并非主要故障点。
- 处理：使用本机 `reliable_ssh` 一键包，以220.12当前代理为基线合并9个白名单业务文件，受控更新8093/8094并保留已有跨数据库MCP代码；不更新8768规则引擎或8770/11434。
- 验收：两页HTTP 200；页面均包含本次asset version，review/manual脚本均返回200且包含 `bootWhenBodyReady`；评分上下文启用、免登录可提交；8768、8770、11434 PID前后不变。浏览器连接在本机初始化时遇到ACL环境错误，未以浏览器截图冒充通过；当前结论以远端实际HTTP、脚本内容、API和PID验收为准。

## Q-MCP-IMES-HEAT-SI-SAMPLES-20260807 如何查询当前炉次或大概时间段的逐罐 Si？

- 结论：当前炉次调用 `imes__query_current_heat_chemistry`，尚未堵口也返回当前已发布试样的阶段性均值；大概时间段调用 `imes__query_heat_chemistry_by_time_range`，先匹配正式炉次，再返回逐罐/逐试样 Si。
- 时间口径：优先真实取样时间；缺失时明确显示“化验判定时间”或“结果发布时间”。铁罐号只通过 `batchno -> thankno` 精确关联。
- 口语：支持“当前鸬鹚的硅含量”“昨天上午4点到7点是哪几个炉次”“最近3小时各炉次的Si”等；“鸬鹚”只作为语音别名，不写入正式数据。
- 实现：[IMES MCP](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)、[口语路由](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[专项测试](../高炉前端数据/智能助手/tests/test_imes_heat_summary_tools.py)。

## Q-PSPACE-22012-18889-UPSTREAM-20260807

- 用户问题：pSpace 是否可直接从 `10.30.220.12:18889` 访问，客户端是否无需再直连备用数采 `10.22.181.243:8889`。
- 结论：客户端可以把 pSpace SDK/MCP 的服务器与端口配置为 `10.30.220.12:18889`，无需具备到 `10.22.181.243:8889` 的直接网络路由；但 `18889` 只是 220.12 上的 Windows TCP portproxy，不是独立 pSpace 实例，其实际上游仍为 `10.22.181.243:8889`。
- 2026-08-07 运行态证据：本机 `Test-NetConnection 10.30.220.12 -Port 18889` 成功；220.12 只读探针确认 `10.30.220.12:18889` 正在监听，`netsh interface portproxy show v4tov4` 显示目标为 `10.22.181.243:8889`。
- 服务边界：运行在 220.12 上的 8770 秒级桥接和 PostgreSQL 同步链仍按现有配置直连 `10.22.181.243:8889`，不应改成回连本机 `18889`；这样不会新增 pSpace 读取程序，也不会减少或增加现有上游采集连接数。
- 配置与验收：[直达入口配置](config_reference.md#22012-vpn-直达数据源入口2026-08-05)、[交接记录](handoffs/2026-08-05-22012-direct-source-relays.md)、[运行态探针](../tools/remote_probe_22012_direct_relays_minimal.ps1)、[验收口径](test_reference.md#test-22012-direct-source-relays-20260805)。

## Q-FOREMAN-CO2-PSPACE-POINT-20260807

- 用户问题：工长趋势中的CO2是否为pSpace实际数据，并要求确认后加入正式点位清单。
- 结论：是。真实点位为 `\冀南钢铁\SIO\CC\GF2\SIO_CC_GF2_T0113`，描述“2号炉干法除尘_二氧化碳”；2026-08-07 11:05经 `220.12:18889` 实读为 `22.100332260131836%`、质量 `Good`。
- 原状态：页面已有 `CO2_top/CO2` 候选字段，但正式TSV、220.12 `sensor_registry` 和分钟表均未接入，所以此前页面不能把该格的缺失值当作pSpace已落库数据。
- 本机实施：已把 `CO2_top`、`CO_top`、`H2_top` 加入正式TSV、可重复补丁器和现有8770桥接映射；清单变为153行，其中151个物理点、2个派生点。相关7项测试通过。
- 部署边界：本轮未修改220.12生产文件、数据库注册表或服务；远端8770与分钟同步仍需后续受控部署，不能在部署前宣称生产页面已显示该实时值。
- 追踪：[需求](requirements_traceability.md#req-foreman-co2-formal-point-20260807)、[点位说明](工长趋势2号炉点位与整点喷煤量_20260806.md)、[正式清单](../数据库同步和存取/config/点位清单.tsv)。

## Q-FOREMAN-CO-H2-WIND-PSPACE-COLLECTABILITY-20260807

- 用户问题：一氧化碳、氢气，以及按“鼓风东南/标准分素”理解的鼓风动能、标准风速、实际风速，是否均可采集到。
- pSpace 只读实测结论（均通过 `10.30.220.12:18889`，未启动新的常驻采集程序）：
  - `H2_top`：`\\冀南钢铁\\SIO\\CC\\GF2\\SIO_CC_GF2_T0111`，最新值 `4.6997971534729`，`2026-08-07 12:49:03.313`，质量 `Good`。
  - `CO_top`：`\\冀南钢铁\\SIO\\CC\\GF2\\SIO_CC_GF2_T0112`，最新值 `26.68294334411621`，`2026-08-07 12:49:16.565`，质量 `Good`。
  - `BlastEnergy`：`\\冀南钢铁\\SIO\\GL02\\BT\\SIO_GL02_BT_T0136`，最新值 `11554.9853515625`，`2026-08-07 12:49:29.254`，质量 `Good`。
  - `BlastSpeedStd`：`\\冀南钢铁\\SIO\\GL02\\BT\\SIO_GL02_BT_T0133`，最新值 `251.80020141601562`，`2026-08-07 12:49:42.498`，质量 `Good`。
  - `BlastSpeedActual`：`\\冀南钢铁\\SIO\\GL02\\BT\\SIO_GL02_BT_T0134`，最新值 `261.6787109375`，`2026-08-07 12:49:55.750`，质量 `Good`。
- 220.12 正式入库边界（部署前）：`bf_sensor.sensor_registry` 与 `one_minute_values` 当时只有三个 BT 点有最新值，CO/H2/CO2 尚未进入分钟表。
- 2026-08-07 受控部署后：六点均已注册并产生最新 `Good` 分钟值；最近完整同步轮次 `tags_ok=151,tags_error=0`，来源仍为既有 `10.22.181.243:8889`，没有新增 pSpace 常驻读取程序。
- 页面/代码边界：本机正式清单和8770桥已接入三个风速/动能点以及 CO/H2/CO2；220.12入口与配置已通过 SHA-256 对账。
- 证据脚本：[pSpace元数据检索](../tools/search_pspace_metadata_keywords.py)、[pSpace最新值查询](../高炉前端数据/智能助手/mcp/gl02_pspace_direct_query.py)、[220.12生产注册表核验](../tools/remote_probe_22012_co2.ps1)。

## Q-FOREMAN-PSPACE-EXTRA-METRICS-LIVE-20260808

- 用户问题：把工长趋势列出的鼓风动能/风速、水系统、氮气、富氧阀压力、罐重及 CO/H2/CO2 的真实 pSpace 数据接入页面，确认不是静态或补零值。
- 结论：已接入既有 8770 pSpace 秒级流；没有启动第二个读取程序。远端 8770 现在返回157个流值，17个新增/确认工长值全部为数值，页面显示 `pSpace秒级已连接 · 分钟历史已连接`。
- 远端验证：`verify_billboard_pspace_8770.py` 返回 `foreman_keys_present=true`、`foreman_numeric_count=17`、`passed=true`；浏览器点位检查确认 CO/H2/CO2、鼓风、水、氮气和富氧阀压力均为 `source=pspace`，`PCI_current_hour` 保持时间积分派生口径。
- 部署边界：替换的是既有 `V4BillboardPspace8770` 任务使用的桥接脚本及工长趋势静态资源；最终 8093/8094/8768/8770 监听保持正常，未增加 pSpace 上游连接。
- 证据：[8770验证器](../tools/verify_billboard_pspace_8770.py)、[页面检查器](../tools/inspect_foreman_trend_remote_points.cjs)、[受控部署器](../tools/remote_deploy_foreman_pspace_extra_metrics_20260806.ps1)。

## Q-FOREMAN-TREND-MINUTE-AVERAGE-20260808

- 用户问题：工长趋势时间轴上的历史数据，是否按 1 分钟平均值实时采集，时间轴不同刻度是否重新聚合。
- 结论：历史曲线由 8768 的 `local_pg_ws_bridge.py` 读取 220.12 PostgreSQL `bf_sensor.one_minute_values`；生产配置为 `source_mode=raw`、`source_aggregate=average`、`target_aggregate=PS_RAW_AVERAGE`、`target_interval_seconds=60`，因此每个时间点是该分钟有效 raw 样本的算术平均。
- 前端口径：90/分钟等时间轴刻度只是 ECharts 时间轴标签和窗口裁剪；数据点仍是一分钟粒度，不会因为刻度变大而重新计算5分钟/10分钟平均。`sampling=lttb`只用于绘制降采样，不改变 tooltip 原始值。
- 实测：2026-08-08 220.12 主表存在 `PS_RAW_AVERAGE` 最新数据至 `16:35:00`，数据库相对本地时间延迟约 `6.655` 分钟；因此“分钟平均语义正确”，但当前同步延迟不满足严格秒级实时，应继续观察同步任务/上游 pSpace 链路。
- 对照：8770 是页面当前值的 pSpace 秒级链路，不参与8768历史分钟曲线；页面状态同时显示“pSpace秒级已连接 · 分钟历史已连接”。
- 证据：[分钟配置](../数据库同步和存取/config/sync_config.json)、[8768历史桥](../自动诊断服务/local_pg_ws_bridge.py)、[前端历史接入](../高炉前端数据/assets/foreman-trend-preview.js)、[分钟语义测试](../tests/test_pspace_minute_average_semantics.py)、[远端只读探针](../tools/remote_query_minute_aggregate.ps1)。

## Q-BODY-TEMP-INFRARED-REPLAY-20260808

- 用户问题：能否把数据库里的炉体温度转换为红外颜色，快速回放过去时间段的延时变化，并在220.12提供视频演示窗口。
- 结论：已上线`http://10.30.220.12:8892/`。页面使用L7～L16、A～H共80个数据库实测点，可选1～30分钟取帧、1～20帧/秒播放、区域筛选、时间轴拖动和Edge WebM导出；下方新增按层位选择的温度A～H八线图、按20.350/23.488/28.976m选择的静压力A～F六线图，游标跟随回放帧。
- 解释边界：这是离散测点插值的历史伪彩色回放，不是红外相机，也不直接等同软熔带或炉内连续温度场；当前可选根部代理未安装且已显式禁用。
- 验证：最终部署时真实生产最新时间`2026-08-08 12:39:00`；15分钟验收返回80个温度点、18个静压力点所在完整载荷、3帧、温度覆盖率`0.904167`；本地17项与远端4项浏览器矩阵通过。

## Q-8093-DIAGNOSIS-DATA-LIMITS-20260808

- 用户问题：既然文档所需变量和 220.12 实际数据都存在，为什么智能分析仍显示数据限制？
- 结论：`variable_coverage` 反映采样密度，不等于变量可用性；只要服务端确认当前值或 60 分钟趋势存在，就不应标为数据限制。
- 核验：`L_north`、`L_south`、`T_top_A-D` 均为启用点位，最近 60 分钟有有效分钟值和原始采样；修复交接见[这里](handoffs/2026-08-08-8093-ai-data-limit-fix.md)。
## Q-SI-V20-WORKBENCH-20260808

- 用户问题：历史炉次实际 Si 与当时预测是否可并列查看；新炉尚未开口或尚未化验时能否先预测，化验到库后能否自动补齐；为什么部署命令会长时间等待。
- 结论：V20 工作台以炉号并集展示实际实绩和预测审计；候选来自220.12本地 `bf_imes.raw_rows`，预测发起后保留 `requested_at`，后续 `si_avg` 到库后自动完成误差/命中对比。长等待来自 SSH、服务停启、端口释放、冷启动和重试，不是单炉推理耗时。
- 入口：[独立工作台](../高炉前端数据/si_v20_workbench.html)、[8093快速部署](../tools/deploy_si_v20_workbench_8093.ps1)。
## Q-SI-V20-WHY-QUALITY-NOT-AUTO-UPDATED-20260809

- 问题：220.12 已自动同步 IMES 炉次化验，为什么 `si_v20_workbench.html` 没有自动出现最新质量数据。
- 结论：五分钟数据库链路正常，故障发生在浏览器缓存、跨日查询范围和旧候选排序；不是页面再次直连 IMES 失败。
- 证据：19:21 计划任务结果 0；history API 返回 125 炉 `si_avg=0.23`，来源时间 19:20:22；真实 Chrome 修复后显示最新三炉。
- 实现与测试：[V20服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)、[浏览器逻辑](../高炉前端数据/assets/bf-si-v20-workbench.js)、[合同测试](../tests/test_si_v20_shadow_workbench.py)、[交接记录](handoffs/2026-08-08-si-v20-independent-workbench.md#自动刷新故障修复2026-08-09-1928)。
## Q-SI-V20-STRICT-HOURLY-ACCURACY-20260809

- 问题：V20 是否严格每小时执行预测，这些预测与真实炉次的时间/Si差距及命中率如何。
- 结论：没有服务器整点计划任务；页面自动模式只在页面保持打开时运行。8月1日至9日审计表仅1条 `hourly_schedule`，且请求发生在目标炉实际开口后37.567分钟，严格开口前在线小时预测样本为0，因此没有可报告的有效在线命中率。
- 唯一记录：113炉，截止17:00、当时估计开口18:14、实际开口17:15；预测0.332155、实际0.42、绝对误差0.087845，±0.02与±0.05均未命中。估计开口晚59分钟，截止相对实际开口仅提前15分钟。
- 对照：开口前60分钟历史回放按炉次去重112炉，MAE 0.049087，±0.02命中26.79%，±0.05命中63.39%；这是回放指标，不能冒充实时整点运行准确率。
- 证据：[整点任务审计](../tools/remote_audit_si_v20_hourly_tasks.ps1)、[预测节拍审计](../tools/audit_si_v20_prediction_cadence.ps1)、[页面小时触发](../高炉前端数据/assets/bf-si-v20-workbench.js)、[V20服务](../高炉前端数据/智能助手/backend/si_v20_shadow.py)。
# Q-SI-V20-CONFIGURABLE-CADENCE-AND-REPLAY-20260809

- 问题：页面能否把自动Si预测调整为1分钟、10分钟、30分钟、1小时或1天，并保存每次预测；能否按任意历史时间范围/粒度批量预测或指定时刻预测并绘制曲线。
- 结论：本机代码已实现。页面改数据库配置，固定一分钟后台分发器执行；预测配置、运行批次和逐点预测分别入三张规范化表。实时点匹配发起后下一真实开口，历史点匹配时间槽后下一真实开口。
- 证据：[需求](requirements_traceability.md#req-si-v20-configurable-schedule-20260809)、[API](api_reference.md)、[数据表](data_schema_reference.md)、[测试](test_reference.md#test-si-v20-configurable-schedule-20260809)。
- 状态：`local_implementation_ready_not_deployed`。

## Q-COHESIVE-ZONE-DOCX-TO-CODE-20260810

- 用户问题：如何在本机把《1780级高炉软熔带移动预测特征总结与智能诊断模型》转化为代码。
- 结论：已实现独立的解释型特征融合诊断、YAML参数、CSV CLI、既有C2几何组合包装和专项验证。它按15分钟当前窗口、15分钟隔离区和15分钟参考窗口计算文档特征，输出上移/稳定/下移概率与管道、悬料、边缘气流、热制度下行关联证据。
- 实现依据：[主诊断函数](../炉况规则引擎/features/cohesive_zone_intelligent_diagnosis.py#L214-L432)、[特征配置](../炉况规则引擎/config/cohesive_zone_intelligent_diagnosis.yaml#L33-L209)、[本机CLI](../tools/run_cohesive_zone_intelligent_diagnosis.py#L24-L88)、[专项测试](../tests/test_cohesive_zone_intelligent_diagnosis.py#L84-L161)。
- 关键边界：Word只给出特征和经验方向，没有真实`H_cz`标签、样本、模型参数或回测结果；因此当前代码不能被称为已训练的Chronos-2/TabPFN/Transformer，也不能用于自动控制。取得真值后，可直接复用输出的`feature_vector/trend_vector`训练候选模型并按时间切分回测。
- 验证：PowerShell 7专项入口结果为`30 passed`，CLI端到端写出UTF-8 JSON；未修改本机/远端数据库、生产端口、服务或页面。

## 2026-08-10 无真实HCZ时由高炉长人工标注并部署

- 用户问题：先制作没有真实HCZ标签时可用的代码，后续由高炉长人工标注；制作完成后直接部署。
- 回答落点：采用独立、盲化、版本化的`expert_weak_label`，不把当前C2/HCZ估计当真值；通过实测回放选时、服务器实测哈希、追加式审计、手填实际标注人和修订链收集。
- 生产入口：`http://10.30.220.12:8892/hcz-labeling.html`。
- 完整实现与验收：[2026-08-10 HCZ专家弱标签生产交接](./handoffs/2026-08-10-hcz-expert-weak-label-production.md)。

## Q-HCZ-UPWARD-FOREMAN-COMPOSITE-RULE-20260810

- 用户问题：按“平均顶温升15℃、至少12小时、24小时均值对比前5天、全压差升5、透气性降0.5、煤气利用率降1个百分点、风压升5、7～13层至少2～3层升10～20℃”汇总为一个软熔带上移判断规则并部署8093。
- 回答落点：已固化为`HCZ-UP-FOREMAN-001`严格AND规则；3层且至少1层升20℃作为强证据，不替代2层升10℃触发门；缺数不补0。
- 生产入口：`http://10.30.220.12:8093/hcz_upward_rule.html`。当前真实数据覆盖充足但未达到组合，状态为`not_triggered`，不能反推稳定或下移。
- 证据：[规则文档](./GL02软熔带上移综合趋势经验规则_20260810.md)、[需求追踪](./requirements_traceability.md#req-hcz-upward-expert-rule-20260810)、[生产交接](./handoffs/2026-08-10-hcz-upward-expert-rule-8093.md)。
## Q-ABC33-B-KEY-VARIABLE-AUDIT-20260810

- 用户问题：料速权重20加入A2/B4/B5后，B类关键变量是否准确。
- 结论：B1—B13运行时校准权重均合计100，已有因子方向基本正确；但主复核传感器清单普遍不完整，B4/B5尚无新料速因子与MES派生数据，不能视为已经准确接入。
- 证据：[B类目录与权重](../自动诊断服务/abc_rule_catalog.py#L71-L123)、[复合特征计算](../自动诊断服务/abc_feature_builder.py#L381-L673)、[因子传感器依赖](../自动诊断服务/abc_factor_audit.py#L35-L73)。
- 逐条结果：[ABC33 B类关键变量核对](./ABC33_B类关键变量核对_20260810.md)。
- 后续：建立MES大小批料速派生表，实现`BurdenRateDev/Slow/Fast`，同步A2/B4/B5在线权重并补齐B1—B13复核变量后，再做历史回放和生产部署。

## Q-8093-GUARDED-UPDATE-SKILL-20260810

- 用户问题：如何把本机修改后的代码上传到8093，暂停持续回滚守卫，让新程序实际运行，再恢复保护，并把整套流程固化为Skill。
- 回答落点：已创建全局可发现Skill `deploy-8093-guarded-update`，固化本机验证、远端upload-only暂存、部署互斥、基线哈希、备份、只暂停/恢复`BFV4PreviewProxy8093`、原子安装、HTTP/API/受保护PID验收及失败回滚。
- 关键澄清：8093页面/静态JS没有独立文件锁或自动回退守卫；用户口径中的守卫按现行项目合同对应托管服务`BFV4PreviewProxy8093`。健康检查可监督服务，但不能替代部署互斥和受控停—改—启。
- 实现证据：[Skill](C:/Users/hmw20/.codex/skills/deploy-8093-guarded-update/SKILL.md)、[项目合同](C:/Users/hmw20/.codex/skills/deploy-8093-guarded-update/references/project-contract.md)、[测试参考](./test_reference.md#test-8093-guarded-update-skill-20260810)。
- 状态：Skill与模板已完成本机只读验证；本轮没有连接、上传、停启或修改220.12。

## Q-22012-PERSISTENT-SSH-AND-PYTHON-PROTECTION-20260810

- 用户问题：持续维护220.12 SSH会话，避免每次上传/命令重新连接，并加入8093 Skill；上传程序后能否转成“pyb”使别人看不到源码再运行。
- 回答落点：新增`remote_22012_session.py`本机localhost代理，持有一个认证transport并用keepalive维护，后续上传和payload执行走独立channel但复用连接；部署完继续保留代理。远端命令中断绝不自动重放。
- 源码结论：不存在标准保护`.pyb`；`.pyc`仍可检查/反编译，不等于源码保密。需要降低源码暴露时，应在本机按目标ABI用Nuitka/Cython构建`.exe`/standalone/`.pyd`并通过同一受控部署流程只上传产物；二进制仍只能提高逆向成本。
- 证据：[会话代理](../tools/remote_22012_session.py)、[Skill](C:/Users/hmw20/.codex/skills/deploy-8093-guarded-update/SKILL.md)、[保护合同](C:/Users/hmw20/.codex/skills/deploy-8093-guarded-update/references/python-artifact-protection.md)、[测试](./test_reference.md#test-22012-persistent-ssh-session-20260810)。

## Q-8093-SKILL-AUTO-TRIGGER-SPEED-LEARNING-RSSH-20260810

- 用户问题：把独立UTF-8 `.ps1`经`pwsh -File`双次复用加入Skill；以后更新8093是否自动调用；异常弹窗与ABC热制度上行分数不一致修复多久；Skill如何从高频错误学习并量化节约时间；Reliable SSH MCP是否可保活降延迟。
- 回答：8093变更意图已成为隐式触发，但Skill不会替用户自动授权生产写。双次`.ps1`验证、阶段计时、冷/热基线、受控失败候选与评审规则库已固化。MCP单服务器220.12实例启用1连接池、30秒协议keepalive和60秒只读应用心跳，配置需MCP进程重新加载后生效。
- 分数根因：弹窗读取旧8类诊断快照`raw_scores.hot`，ABC读取独立ABC33 B4批次；不同窗口/版本/调度会造成差异。预计只读复现30–60分钟、切换展示源60–120分钟、统一后端合同并上线2–4小时、统一业务评分0.5–1工作日。
- 初次性能：Paramiko `.ps1`复用单样本节约23.6%；MCP握手19.7秒后，复用调用约0.3秒。长期收益必须至少5组同范围交错测试，用median/p90比较。
- 证据：[需求](./requirements_traceability.md#ops-8093-skill-reuse-metrics-learning-and-rssh-mcp-20260810)、[测试](./test_reference.md#test-8093-skill-reuse-metrics-and-rssh-mcp-20260810)、[性能/学习合同](C:/Users/hmw20/.codex/skills/deploy-8093-guarded-update/references/deployment-performance-and-learning.md)。

- 实施结果：原生构建器已支持Nuitka standalone/module与Cython extension的计划/构建清单；5冷+5复用基准中冷命令中位2600ms、复用1536ms，单命令中位节约1064ms（40.92%），新会话盈亏平衡为1条命令。B4统一已上线：批次839中弹窗与ABC均为14.9623，旧分28.12归档，8093守卫恢复且受保护服务未重启。

## Q-8093-SIMPLIFY-VALIDATION-AND-LOAD-20260810

- 用户问题：小改动是否可以免跑85个组合；如何降低生产大屏及跨内核验收的加载负担。
- 回答落点：小改动默认`quick` 4项，中等单路由改动`standard` 17项，只有共享布局、导航、三维/浏览器运行时或多页基础设施改动才跑`full` 85项。任何失败或影响边界不清自动升级，部署事务安全门禁不简化。
- 流程实测：4项跨内核定向检查9.019秒且全部通过，组合数减少95.3%；按内核复用context，避免85次人为冷缓存。
- 页面加载审计：当前生产HTML约907KB、无内容压缩且`no-store`，浏览器还加载Babel并现场编译大段`text/babel`，本地React开发版、Babel、ECharts约5.35MB，首屏三维GLB约8.23MB。优先改为构建期打包、React生产版、路由按需加载、HTML压缩和三维延迟加载；这些是现状瓶颈证据，不冒充已测得的性能回归或上线收益。

## Q-CODEX-CLI-MODEL-DELEGATION-20260810

- 用户问题：能否保证后续小功能本地修改到8093更快；Codex CLI有哪些能力和模型；能否固化Skill并把低智能工作分配给Luna等低token模型。
- 回答：可以保证默认走“quick验证+持久SSH+在线预暂存+一次守卫临界区”的快路径和全阶段计时，不能保证每次绝对耗时，因为测试失败、网络重试、服务启动和基线冲突仍是外部变量。
- CLI核查：本机`codex-cli 0.144.3`支持交互TUI、`exec/review/resume/fork/debug models/doctor/mcp/plugin/app/cloud/apply/sandbox/features`等；当前账号实时目录包含`gpt-5.6-sol/terra/luna`等。官方模型指导将Luna定位为高吞吐经济型、Terra为平衡型、Sol为旗舰型。
- 实施：新增`codex-economical-delegation` Skill并与8093 Skill建立安全边界。实测最小上下文Luna任务29.2秒、输入38309 tokens，说明只应委派需要语义判断且可并行的任务；哈希、格式化、固定命令等直接执行更省。

## Q-8093-85-MATRIX-AND-LUNA-20260810

- 用户问题：85组合是什么、为什么多、是否耗token，以及能否先做核心程序、最后再兼容并默认让Luna执行低风险任务。
- 解释：Chromium为9视口×5路由=45；Firefox和WebKit各4视口×5路由=20，总计85。路由是总览、诊断、优化建议、趋势和问答；视口是桌面、平板、手机内容区尺寸。
- 决策：核心开发默认仅运行Chromium 1366x768；85项只在最终兼容阶段显式运行。浏览器脚本自身不消耗模型token。
- Luna实测：一次受限只读诊断耗时139636ms，输入72377（缓存40448）、输出520；因此保留Luna处理需要语义判断的本地任务，机械矩阵继续用零模型调用的脚本。

## Q-8093-TWO-PHASE-FAST-DEPLOYMENT-20260811

- 用户问题：把“准备一次、快速上线”、不可变产物清单、差量上传、Luna low最小diff与只读远端预检并行、确定性HTTP/API优先、UI才跑浏览器、生产成功立即通知固化进8093部署Skill。
- 实现：[两阶段合同](../.codex/skills/deploy-8093-guarded-update/references/two-phase-fast-deployment.md)和[发布清单脚本](../.codex/skills/deploy-8093-guarded-update/scripts/release_manifest.py)新增四个schema；本机/远端模板分别消费准备清单和差量计划。有效清单不重复Phase A；任何绑定字节/验证/基线变化立即失效。
- 安全边界：Luna只读且不接触凭据/生产控制；最新远端基线、互斥、备份、原子替换、`finally`恢复、回滚、HTTP/API和受保护PID仍是强制门禁。差量为空不重启。
- 验证：清单脚本自测、Skill合同验证、PowerShell 7/Core UTF-8检查和Skill Creator结构验证均通过；`remote_write_performed=false`，未连接或修改220.12。

## Q-8093-SKILL-PROJECT-MIRROR-20260811

- 用户问题：把8093部署Skill和机械化框架同时保存到本项目文件夹，并与全局Codex Skill同步更新。
- 决策：仓库[项目Skill](../.codex/skills/deploy-8093-guarded-update/SKILL.md)是唯一版本源；用户目录同名Skill是运行镜像。日常只编辑项目副本，验证后通过[同步脚本](../tools/sync_deploy_8093_guarded_update_skill.ps1)单向发布，禁止两边独立编辑。
- 验证：首次导入、项目合同/结构校验、`PublishProjectToGlobal`和独立`Verify`均通过；两侧14文件bundle SHA-256为`F75B6DA1C3FC1F410A5DF6FAC4C09D42E67459B9E5BCF20471B4A6EC9B6FA323`，`remote_write_performed=false`。

## Q-HCZ-THREE-MONTH-MOVEMENT-AUDIT-20260811

- 用户问题：按照软熔带综合趋势经验规则，核对过去三个月是否出现上移动和下移动。
- 核对窗口：`2026-05-11 10:00`至`2026-08-11 10:00`，逐小时评价2209次；2168小时覆盖合格，覆盖率98.14%。
- 结论：生产上移规则完整触发0次；把煤气利用率正确换算为百分点后，上移仍为0次；对称镜像下移候选也为0次。上移最接近`2026-05-17 21:00`，核心3/5、炉壁1层、连续1小时；下移最接近`2026-05-21 16:00`，核心4/5、炉壁0层、连续0小时。
- 发现：`GasUtil`存储为比例值，当前8093规则缺少`×100`百分点换算，登记`BUG-HCZ-GASUTIL-UNIT-20260811`；本次单位校正未改变0次总结果，但生产实现尚未修复。
- 证据：[三个月历史核对报告](./HCZ软熔带上下移动三个月历史核对_20260811.md)、[规则文档](./GL02软熔带上移综合趋势经验规则_20260810.md)。本次只读数据库并在本机回放，没有修改220.12或重启任何服务。

## Q-HCZ-AUG9-AUG10-TOP-TEMP-COMPARISON-20260811

- 用户反馈：2026-08-09至08-10实际出现过一次软熔带上移，要求比较平均顶温变化。
- 数据核对：08-09 20:00四点平均顶温`109.329℃`，22:00为`124.728℃`，两小时`+15.399℃`；23:00为`125.640℃`；08-10 06:00为`129.350℃`，较低点`+20.020℃`。A～D四点同步上升。
- 窗口差异：以前后12小时均值比较只`+5.822℃`；08-10整日较08-09整日`-0.139℃`；两天各自24小时对前5天分别`-3.378℃/-3.626℃`。短时+15℃信号被长窗口稀释。
- 数据边界：08-09 00:00～04:00顶温全缺；人工弱标签表仍为0条，当前没有准确标注时刻。本次以用户反馈作为现场确认，以20:00至次日06:00作为顶温变化段，不把它升级为直接HCZ真值。
- 影响：三个月报告的0次只代表严格规则命中0次，不代表物理事件0次。建议保留24小时背景量，新增3～12小时短时顶温抬升特征后结合其他指标重新标定；本次未修改生产规则或8093。
- 证据：[平均顶温专项对比](./HCZ上移事件平均顶温对比_20260811.md)、[三个月规则回放](./HCZ软熔带上下移动三个月历史核对_20260811.md)。

## Q-HCZ-COLD-BLAST-PRESSURE-20260811

- 用户问题：把软熔带上移规则中的风压改成冷风风压。
- 回答落点：不能只把“热风压力”改名；项目变量映射确认`P_blast`是热风压力、`P_blast_cold`才是冷风压力，因此生产规则显示名改为“冷风风压”，实际数据源同步切换为`P_blast_cold`，阈值保持上升`+5kPa`。
- 生产结果：8093 API已返回“冷风风压”，部署时变化`+0.589619kPa`、状态`not_triggered`；守卫恢复、未回滚，六个受保护PID未变化。
- 证据：[配置](../炉况规则引擎/config/hcz_upward_expert_rule.yaml)、[专项测试](../tests/test_hcz_upward_expert_rule.py)、[生产交接](./handoffs/2026-08-11-hcz-cold-blast-pressure-8093.md)。

## Q-HCZ-AUG9-PSPACE-LABEL-UP-20260811

- 用户要求：从pSpace找到四个顶温数据，并把2026-08-09定义为软熔带上升。
- pSpace直读：08-09 20:00四点均温`109.330℃`，22:00为`124.728℃`、约`+15.399℃`，23:00为`125.640℃`；A～D四点同向上升，无解析错误。
- 生产标签：已追加`id=1`、`reference_id=HCZ-28cf0aad-63af-4e64-a27d-679ca79dbfdd`；观察时刻08-09 22:00，证据窗口20:00至次日06:00，`movement=up`、`root_level=uncertain`、可信等级4。
- 边界：这是高炉长确认的`expert_weak_label`，不是直接HCZ高度实测；标签盲于模型，使用事后证据上下文，禁止用于自动控制。
- 证据：[顶温与标签报告](./HCZ上移事件平均顶温对比_20260811.md)、[生产写入交接](./handoffs/2026-08-11-hcz-aug9-upward-expert-label.md)。

## Q-HCZ-RULE-SENSITIVITY-GASUTIL-PERCENT-20260811

- 用户需求：在8093页面手动调整经验阈值并查看真实历史上移/下移诊断量变化；把0～1的煤气利用率乘100并加`%`显示。
- 回答落点：已新增7/30/90天只读历史试算。输入值只用于本次计算，不保存生产阈值；下移仅显示符号对称候选。`GasUtil`在API入口乘100一次，当前值/基线用`%`，变化量和阈值用“个百分点”。
- 生产结果：近90天把平均顶温阈值`15→10℃`，完整上移事件`0→0`、对称下移候选事件`0→0`；现场煤气利用率约`45.83%`，前五天约`46.38%`，变化约`-0.55个百分点`。
- 证据：[需求追踪](./requirements_traceability.md#req-hcz-rule-sensitivity-20260811)、[API合同](./api_reference.md#get-apihcz-rule-sensitivity2026-08-11)、[生产交接](./handoffs/2026-08-11-hcz-rule-sensitivity-8093.md)。
## Q-QA-SHARED-GUEST-AND-MCP-FALLBACK-20260813

- 用户问题：希望局域网同地址访问者默认共享匿名智能助手窗口，问答和时间戳入本地数据库；并要求 MCP/数据库工具失败时仍由模型给出有限回答。
- 结论：工具规划与最终回答不需要拆成两个用户会话；采用同一请求内的“工具回合→最终无工具模型回合”。工具错误和轨迹保留用于审计，最终模型只能使用已取得事实、页面炉况、keyword知识与通用知识。
- 实现：[共享访客与降级后端](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)、[共享访客界面](../高炉前端数据/frontend_dashboard_v3.server.html)、[数据库唯一房间约束](../高炉前端数据/智能助手/backend/schema/postgresql_assistant.sql)。
- 边界：未登录用户共享可见，不适合输入个人信息或敏感项目材料；登录模式仍按 `owner_subject` 私有隔离。

## Q-8093-MCP-POINT-NAME-PLANNING-20260813

- 用户问题：当前模型是否具备多轮工具规划；顶温/顶压 A-D 是否可查；并要求直接核对
  pSpace 权威点名，纠正 `P_top_gas_A-D` 拼写。
- 权威核查：通过 220.12 官方 pSpace SDK 只读查询 `10.22.181.243:8889` 的
  `\冀南钢铁\SIO\GL02\LD`。pSpace 物理属性名为 `SIO_GL02_LD_T0067..T0070`，描述为
  `2号炉炉顶_上升管煤气压力A..D`；pSpace 本身不存在 `P_top_A` 或 `P_top_gas_A` 这种属性名。
- 项目决策：业务/MCP 对外标准名统一为 `P_top_A-D`；旧 `P_top_gas_A-D` 仅作输入兼容别名，
  两者过渡期映射到相同四个 pSpace 长名。历史模型特征暂保留旧字段，通过边界适配接收新名，
  避免破坏训练产物和历史序列。
- 验证：模型“查目录→用标准 ID 查询”两轮规划通过；MCP 与口语解析聚焦回归 `40 passed`；
  “顶温 A-D + 顶压 A-D”已生成八个新标准 ID 和一次 `query_gl02_sensors` 计划。
- 证据：[MCP 多轮规划与顶温/顶压点位审计](handoffs/2026-08-13-mcp-point-name-planning-audit.md)。
- 边界：本轮完成本机修复，没有部署或重启 220.12 的 8093；生产仍需走受控部署验收。

## Q-8093-CROSS-MCP-COMPUTATION-20260813

- 用户问题：当前模型是否真正测试过多轮 MCP，以及能否组合不同 MCP 服务的返回值计算后回答。
- 真实验收：8093 共享访客会话只提交一次有效 SSE 问答；并发调用 `imes-readonly` 获取上一炉
  `si_avg=0.3%`，调用 `gl02-data` 获取 `P_top=255.29724799262152`，模型计算
  `255.29724799262152 / 0.3 = 850.9908266420717`，与独立复算完全一致。
- 结论：系统已具备“跨 MCP 取证 → 汇总事实 → 模型运算解释”的组合能力；跨服务选路和工具参数由
  确定性 `CrossSourcePlan` 约束，不能表述成模型完全自由编排。此前另有同服务“目录→点位查询”两轮
  规划实测，两者共同覆盖多轮与跨服务两种能力。
- 回归：多服务主机与并行规划合同 `22 passed`；本次未部署或重启生产服务。
- 证据：[跨 MCP 组合计算验收](handoffs/2026-08-13-cross-mcp-computation-audit.md)。

## Q-MCP-SEMANTIC-POINT-ROUTER-20260813

- 用户问题：如何衡量工具/MCP 智能体能力；能否把唯一语义点位目录作为固定上下文，让模型先定位
  点位，再调用对应 MCP。
- 结论：方向可行，但应采用“单一权威目录 → 规则/词法/可选语义检索 → Top-K 候选 → 模型消歧 →
  服务端校验 ToolPlan → MCP”的分层方案。公共 Prompt 固定的是 token 前缀，不是 attention 分数；
  当前也没有应用可寻址的持久 KV cache。完整目录不应默认塞进每轮 Prompt。
- 当前基础：已有统一业务对象目录、标准名/历史别名解析、目录 MCP 工具、多轮规划、并行调用和跨源
  DAG；主要缺口是多来源尚未收敛为唯一版本源、没有独立目录语义索引和系统化金标评测。
- 评测：同时覆盖点位 Top-1/Recall@K/拒识、工具与参数 exact-match、可执行成功、多轮 `pass^k`、
  数值忠实、失败安全、延迟/token/KV、并发和权限审计。
- 详细设计：[智能体工具能力评测与唯一语义点位路由](handoffs/2026-08-13-semantic-point-router-agent-evaluation.md)。
- 边界：本轮是设计审计，没有修改或部署 8093/8094。

## Q-MCP-SEMANTIC-POINT-CATALOG-IMPLEMENTATION-20260813

- 用户要求：把十类指标做成“智能体工具能力评估”Skill；为全部点位设计口语别称，评估单点、多点组合计算，并把稳定公共 Prompt 方案保存到 PT。
- 结果：权威清单实际为151个物理点位+2个派生变量，共153条；为全部变量生成无歧义短别称和每项4个完整问法。全量本地评测153/153覆盖、全部精确别称、153/153唯一问法、6/6严格组合路由，未知点位拒绝。
- 修复发现：补齐本机缺失映射时49个点位不进fallback的问题；修复倒装炉温、物理静压与旧mean重复、喷煤小时口径及富氧阀前后多查。
- Skill：[agent-tool-capability-evaluation](../.codex/skills/agent-tool-capability-evaluation/SKILL.md)；PT：[153点位稳定Prompt路由](../PT/智能体工具能力评估与153点位稳定Prompt路由方案.md)。
- 边界：本轮未部署8093/8094；全量为路由/参数合同，生产MCP实取需按点位族受控抽样。

## Q-MCP-SENSOR-REASONING-20260813

- 用户问题：扩充 PT MCP 调用模板，并真实测试传感器证据推断、一小时均值/标准差/波动计算、
  多工具和额外计算工具调用。
- 类型：智能体工具使用能力评估，具体包含 sensor-grounded reasoning、tool-augmented deterministic
  computation 与 multi-tool orchestration。
- 真实结果：8093 三次明确编号 SSE 均完成，MCP 执行 3/3；T3 的 IMES 与 GL02 两个工具并行。
  但最终答案合同 0/3：T1/T2 被简版确定性格式化器截断，T3 未把 correlation derived 事实注入模型。
- 独立复算：T2 极差 `3.6837902222221715`，CV `0.36898366819258316%`；T3
  `Pearson r=-0.13431331121165607`、对齐 60 点，只能描述为很弱负相关，不能表述为因果。
- 证据：[PT 第16节](../PT/MCP可执行功能及口语调用模板.md#16-传感器推断统计计算与多工具编排测评模板2026-08-13)、
  [实施记录](handoffs/2026-08-13-mcp-sensor-reasoning-evaluation.md)、
  [机器摘要](../logs/mcp_sensor_reasoning_20260813/report.json)。
- 边界：本轮没有部署或修改 220.12；pass^5、六并发、失败注入、对抗输入和 token/KV 成本未测。

## Q-MCP-TEMPLATE-LINE-EVALUATION-20260813

- 用户要求：编写程序逐行执行 PT MCP 调用模板，逐项比较预期与实际；把传感器证据落地推断、
  确定性工具增强计算、多工具跨 MCP 编排、最终答案证据忠实度写入评估 Skill。
- 实现：新增逐行评估器、稳定 `case_id`、占位/重复分类、单次 SSE、无自动重试、JSONL 检查点、
  `--resume/--case-id/--limit` 和 JSON/Markdown 报告。Skill 项目副本已发布到全局镜像并验证哈希一致。
- 全量实测：160 行全部分类；125 个唯一请求、11 个重复复用、24 个跳过。工具合同 103/125，
  最终答案忠实度 28/123（另2条执行错误），综合 24/125。
- 关键发现：主要问题是答案漏来源（89）、时间（48）、单位（13）和公式（5），不是所有工具都不可用；
  两条静压力题返回 `TaskGroup` 子异常。四类固定题严格重评均未通过答案门禁。
- 证据：[完整实施记录](handoffs/2026-08-14-mcp-template-line-evaluation.md)、
  [PT模板第16.6节](../PT/MCP可执行功能及口语调用模板.md#166-全模板逐行实测2026-08-14)、
  [逐行Markdown报告](../logs/mcp_template_line_eval/report_full_20260813.md)。
- 边界：本轮未部署、未停启服务、未修改远端文件或数据库结构。

## Q-MCP-WHAT-COUNTS-AS-SPOKEN-POINT-NAME-20260814

- 用户纠正：`P_top`、`T_top_A` 等内部英文点位名不属于口语；现场人员会说“炉顶压力”“顶温 A 点”。
- 固定口径：纯口语 Prompt 只能使用中文物理含义；A-H 可以作为独立方位字母，但不得嵌入英文/
  下划线技术标识。该规则对完整 153 点位目录生效，不仅检查本题 expected object。
- 实现：[执行前门禁](../tools/evaluate_mcp_extended_production.py)、
  [评估 skill](../.codex/skills/agent-tool-capability-evaluation/SKILL.md)和
  [口语题集](../PT/智能体工具能力口语化生产回归.v1.json)。
- 验证：8 项聚焦测试通过；当前 42 个口语 Prompt 全部通过全目录技术 ID 扫描，违规样例在网络
  请求前拒绝，模型请求数为 0。

## Q-MCP-BODY-LAYER-AVERAGE-AMPLITUDE-STDDEV-20260814

- 用户问题：怎样询问 7–13 层平均温度、每层平均、幅值变化、标准差变化，以及某层某点某时段平均。
- 当前答案：已支持。生产 8093 会把逐层或单点统计口语路由到一次只读复合工具，由确定性代码返回
  平均、总体标准差、极差、首末变化、斜率、CV、滚动波动和质量，不把原始序列交给模型心算。
- 生产证据：7–13 层 A–H 与第 10 层 C 点各执行 1 次真实 SSE，均恰好 1 个工具调用、0 个模型请求；
  后者 60/61 个有效/期望分钟，平均 `39.60467341351319 ℃`、STDDEV_POP
  `0.020773105250294396`，质量为 Good 34/Held60 24/Held120 2。
- 推荐口语：“查询最近一小时第 7 层到第 13 层各层 A 到 H 的平均温度、极差、首末变化和总体
  标准差，并比较 15 分钟滚动标准差”；或“查询今天 8 点到 9 点第 10 层 C 点的平均温度、总体
  标准差、最高、最低、极差和样本数”。内部变量名只在服务端映射中出现。
- 实施：[专项交接](handoffs/2026-08-14-body-temperature-layer-statistics.md)。
- 16:28 人工复核推翻了“所有自然问法均可用”的过早结论：省略“炉体/炉身”的层范围问法会漏路由，
  第 12 层 A–H 会把层平均复制为方位值，大结果截断后会显示“模型未返回内容”。修复必须以用户
  原始问法逐项真实验收，不能继续沿用带“炉体”的较窄部署 Prompt 代替。
- 后续闭环：确认 A/B/C 评分整文件发布覆盖了此前代理路由；R4/R5 生产验收分别暴露扩展 MCP 未选中
  和跨源 DAG 抢先展开 56 点，均已自动回滚。最终本机顺序固定为“中文层号选服务 → 单个复合工具
  → 其余跨源 DAG”，`116 passed`；直接只读 MCP 7 层/3248 行耗时 `2520.9ms`。R6 已密封，等待
  恢复 220.12 SSH 凭据会话后发布，当前生产不可表述为已修复。
## Q-QA-MCP-EXECUTION-VISIBILITY-20260814

- 用户问题：能否把执行命令、MCP 和 tools 调用过程显示在“思考过程中”，并让炉体多层问题按
  中文别称、确定性解析、单次复合 MCP、数据库批量计算和模型解释完成？
- 结论：可以显示可审计执行轨迹，但不能展示模型隐藏思维链。本机现按五类 SSE 事件实时展示
  对象范围、工具、调用次数、点数、行数、来源、耗时、缓存和失败边界。
- 实现：后端 [ollama_proxy_server.py](../高炉前端数据/智能助手/backend/ollama_proxy_server.py)
  生成脱敏 `public_trace` 并确保一次矩阵统计；前端
  [frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html)
  只消费该摘要，不展示原始参数和返回。
- 安全：确定性统计为权威答案；模型解释最多一次，出现未核实新数字时拒绝采用。SQL、DSN、密码、
  Cookie、Token、内部路径和隐藏推理均不进入界面。
- 状态：本机已实现并通过聚焦与扩展回归，尚未部署 220.12。
# Q-QA-MCP-MATRIX-HEATMAP-AND-RECOMMENDATIONS-20260814

- 原始问题：如何把查询结果绘制成矩阵热度图，并把常用 MCP 调用模板、自动相关问题、固定问题和
  自定义问题放入可滚动推荐列表？
- 回答：输入“绘制最近一小时第7层到第13层A到H炉体温度矩阵热度图，每格显示当前温度和变化
  趋势。”会直接调用复合矩阵工具；生成的同源 PNG 在答案内显示。推荐区可滚动，点击问题只会
  填入输入框，不会自动发送；星标用于固定，自定义问题添加后默认固定。
- 实现：[图表路由](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4662-L4712)、
  [图表显示](../高炉前端数据/frontend_dashboard_v3.server.html#L8881-L8882)、
  [推荐问题](../高炉前端数据/frontend_dashboard_v3.server.html#L9223-L9252)。
- 验证：[合同测试](../tests/test_qa_mcp_visual_recommendations.py#L23-L81) 与
  `logs/qa_mcp_visual_recommendations_1366x768_final2/report.json`。

## Q-QA-MESSAGE-COPY-20260814

- 用户问题：允许发出去的问题和回复均可以复制。
- 回答：已在本机实现。每条用户消息右上角显示“复制问题”，每条助手消息显示“复制回复”；成功后短暂
  显示“已复制”。复制回复会保留可见正文，若包含 MCP 矩阵图则在正文末尾附上安全同源图表地址。
- 不复制：消息时间、流式状态、按钮文字、隐藏上下文、脚本和样式；复制操作不会再次发送问题，也不会
  调用模型或更改数据库。
- 验证：聚焦合同 `14 passed`；浏览器报告
  `logs/qa_message_copy_1366x768/report.json` 为 `1/1 passed`，两种按钮的实际剪贴板内容均通过，
  `real_sent=0`。当前仅本机完成，尚未部署 220.12。

## Q-QA-PRESERVE-OLD-RECOMMENDED-QUESTIONS-20260814

- 用户问题：之前几个常用问题也要放进推荐区，不能因新增 MCP 模板而丢失；列表需要支持用户自行滚动。
- 结论：已在本机改成来源明确的分区。原有炉况动态问题显示在“原有常用问题”，固定 MCP 问法显示在
  “常用 MCP 模板”；两者都在同一个推荐区内，原有问题排在前面。已固定、本轮相关追问和自定义问题
  仍然保留。
- 交互：推荐列表具备独立纵向滚动条，支持鼠标滚轮、触控板/触屏以及聚焦后的键盘滚动；点击任何问题
  仍只填入输入框，不会自动调用模型。
- 验证：`15 passed`；浏览器报告
  `logs/qa_local_recommendations_1366x768_final/report.json` 为 `1/1 passed`，旧问题分区、MCP 分区、
  实际滚动与键盘可访问性均为 `true`，`real_sent=0`。当前尚未部署 220.12。

## Q-FURNACE-RULE-FORMULA-EXPORT-20260814

- 用户问题：把原炉况诊断8类和ABC33规则制作成Markdown并导出PDF，能够看到具体数学公式以及
  公式中每项的含义。
- 回答：已生成41规则公式手册。每条规则包含总分公式、各项权重、0～1变换、物理含义、来源变量和
  ABC33建议复核顺序；另外说明两套体系的重合关系、发布边界与缺失实现证据。
- 产物：[Markdown](./炉况诊断8类与ABC33规则数学公式手册_20260814.md)和
  [PDF](./炉况诊断8类与ABC33规则数学公式手册_20260814.pdf)。
- 边界：ABC33是当前代码的直接导出；原8类普通公式按现存YAML还原，硬门与最终主次Resolver没有
  足够本地代码证据，手册明确标注未核实而没有猜测。
- 验证：8+33章节完整，PDF 55页、约1.46MB，封面、B4和C11页面视觉检查通过；没有连接或修改220.12。

## Q-QA-VERIFIED-ISSUE-PLAN-20260917

- 用户问题：统计全部智能助手问题，并给出逐条可核对的路由与助手完善方案。
- 关联需求：REQ-QA-FULL-ISSUE-INVENTORY-20260916。
- 答复入口：[全量统计与实施方案](handoffs/2026-09-17-qa-verified-issue-plan.md)。
- 可核对产物：[1418条索引与机器统计](../tests/qa_regression/verified_inventory_20260917.json)、[33项验收清单](../tests/qa_regression/verified_optimization_checklist_20260917.md)、[20类语义标签与9题待归类清单](../tests/qa_regression/semantic_issue_crosswalk_20260917.md)。
- 验证：对账脚本核对1233条最终判定、分母恒等式、唯一ID和原结果哈希；14条金标结构校验通过。生产仅作Reliable SSH只读核查，V26恢复批次显示发送0、模型身份门禁阻断，不能报告新版全量准确率。
- 边界：保留初次不确定发送题，禁止自动重放；模型及其他服务变更另按授权；本次统计与方案不改变生产。

## Q-QA-LOCKED-QWEN38-LINEAGE-20260917

- 用户问题：启动独立子智能体调查模型频繁切换，并确认 220.12 是否有 Qwen3.8 约 27B、锁定底座是否来自该模型。
- 结论：已实际读取冻结 `31629f…` GGUF 的 `general.name=Qwen3.8-27B`；冻结版本 `:1/e4ad…` 仍存在。另一份 `:0/9111…` 的 API 来源标记为 `qwen3.5:27b`，不能以同名 `latest` 或 `qwen35` 架构标记混同底座。
- 证据与边界：[来源核验](handoffs/2026-09-17-locked-qwen38-lineage-verification.md)、[固定底座合同与候选](handoffs/2026-09-17-qa-single-base-model-policy.md)。来源记录支持固定 GGUF 导入；业务微调血缘未核实。
- 验证：Reliable SSH 读取 API、manifest/config 和 GGUF 头部/元数据，并核对固定上游 revision 文件摘要；未加载、切换或删除模型。[独立调查](handoffs/2026-09-17-model-identity-switch-independent-audit.md)确认每分钟 Repair 在后续检查失败后跨底座 fallback、成功前不写期望状态的循环。五组固定身份合同61项本机回归通过，生产永久锁定尚未验收。

## Q-QA-MANAGER-PRODUCTION-INSTALL-20260917

- 用户要求：完成生产安装，然后复测线上回答效果。
- 已实施：新管理器独立安装成功，读回完整摘要与候选一致；受保护服务 PID 不变。r4 安装器缺陷替换前失败，经真实原子替换回归及独立审查修复，以新 r5 操作成功安装，未重放旧操作。
- 剩余边界：实际旧错误驻留尚未恢复；11434 单次卸载与冻结底座预热另行明确授权后执行。822 原题计划已重新按单一 e4、当前生产源码和原题/结果摘要绑定准备，尚未发问，不能报告新的准确率。
- 权威证据：[生产安装、失败记录与复测边界](handoffs/2026-09-17-qa-single-base-manager-production-install.md)。

## Q-QA-QUIET-ORIGINAL-RETEST-20260918

- 用户要求：启动程序，让远程服务器默默复测原题。
- 实施：独立隐藏后台进程PID9808已实际启动；822原失败/部分题封存，当前GET-only等待唯一锁定底座。源/目录漂移及发送不确定停止，不重启或重放，正常等待/运行无过程通知。
- 边界：不将启动程序解释为11434卸载恢复授权；当前错误驻留未纠正，发题为0。生产助手应用仍V26。
- 证据：[启动、检查、进度与静默跟进](handoffs/2026-09-18-qa-quiet-background-retest.md)。

## Q-QA-AUTHORIZED-BASE-RESTORE-20260918

- 用户明确允许底座恢复；范围为既定e4的驻留和latest别名恢复，不更换权重，不删除模型，不停启服务。
- 生产CIM禁用状态码1兼容修复、单次卸载效果的只读恢复、新生产请求重载与连贯恢复证据见[授权恢复记录](handoffs/2026-09-18-qa-authorized-frozen-base-restore.md)。恢复后继续现有822原题进程，不能重复启动或重放状态不确定题。

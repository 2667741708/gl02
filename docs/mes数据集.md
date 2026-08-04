# MES 数据集说明

更新时间：2026-07-16  
需求编号：`REQ-IMES-UNIFIED-TIME-QUERY-20260715`  
运维编号：`OPS-IMES-VASTBASE-20260715`

## 1. 结论

当前账号 `2gldmx` 已验证可读取 12 个白名单 MES 数据集。统一客户端位于 [数据集白名单 tools/export_imes_web_readonly.py:L41-L137](../tools/export_imes_web_readonly.py#L41-L137)，可以通过同一命令选择任意数据集、一个或多个数据集、或全部数据集。

这 12 个数据集是 **IMES Web 会话**的数据范围，不等同于 Vastbase 直连权限。2026-07-16 经 220.12 跳板对 Vastbase 做了零行 `SELECT` 权限验证：260 个可见对象中只有 9 个可读取，其中 6 个是 MES 业务对象。直连结果和转发方式见 [220.12 IMES 跳板转发与 MCP](22012_IMES跳板转发与MCP.md)。因此，下面的表要按“Web 已验证”阅读；数据库直连的实测范围以第 2.1 节为准。

“任意时间”的准确边界如下：

- 7 个 `range` 数据集直接接受 `startDate/endDate`，首尾日期均包含。
- 3 个 `workdate` 数据集的原接口一次只接受一个业务日；客户端会把 `--start-date/--end-date` 自动拆成逐日请求并合并，所以使用者仍可直接输入任意日期范围。
- 2 个 `none` 数据集没有历史日期查询参数：`pes_bin` 是当前料仓主数据，`production_month_plan` 返回当前账号可见的月计划集合。它们可以读取，但不能伪装成历史时间序列。
- 实际可追溯多早仍受 MES 数据保留期和账号权限限制；客户端不能读取服务端已经删除或账号无权查看的数据。

## 2. 12 个数据集总表

所有路径均相对于 `http://10.10.181.209:8080/imes.web/`，业务查询统一使用 `POST application/x-www-form-urlencoded`。

| key | 中文名称 | 时间模式 | 主要时间字段 | 查询接口 | 响应 |
|---|---|---|---|---|---|
| `pes_bin` | 2#高炉料仓 | `none` | 无历史时间；含创建/更新时间 | `mes/ipes/pesBin/listPageData.do` | `{total,rows}` |
| `pes_bin_material` | 2#高炉料仓变料 | `range` | `businessDate` | `mes/ipes/pesBinMaterial/listPageData.do` | `{total,rows}` |
| `production_month_plan` | 2#高炉生产月计划 | `none` | `planMonth` | `mes/cpes/productionPlanMonth/listMonthData.do` | JSON 数组 |
| `dosing_scheme` | 2#高炉配料方案 | `range` | `businessDate` | `mes/ipes/dosingScheme/listPageData.do` | `{total,rows}` |
| `input` | 2#高炉原料投入 | `range` | `workDate` | `mes/ipes/input/listPageData.do` | `{total,rows}` |
| `batch_all` | 2#高炉批次投料合并 | `workdate` | `workdate/workdate2` | `mes/ipes/input/listPageData2.do` | `{total,rows}` |
| `batch_mining` | 2#高炉批次投料矿批 | `workdate` | `workdate/workdate2` | `mes/ipes/input/listPageData3.do` | `{total,rows}` |
| `batch_coke` | 2#高炉批次投料焦批 | `workdate` | `workdate/workdate2` | `mes/ipes/input/listPageData4.do` | `{total,rows}` |
| `output` | 2#高炉生产实绩 | `range` | `workDate` | `mes/ipes/outputM/listCondData.do` | `{total,rows}` |
| `heat_lab` | 2#高炉炉次化验索引 | `range` | `workDate` | `mes/ipes/outputM/listCondDataAvg2.do` | `{total,rows}` |
| `slag_lab` | 炉渣检验结果 | `range` | `publishtime/workDate` | `mes/qpes/productManage/listInspData3.do` | `{total,rows}` |
| `heat_lab_all` | 2#高炉炉次化验全量索引 | `range` | `workDate/createTime` | `mes/ipes/outputM/listCondDataAvg2New.do` | JSON 数组 |

分页数据集固定使用 `_size/_index`，客户端单页最大 50 行并自动翻页。时间窗口生成见 [build_query_windows:L200-L211](../tools/export_imes_web_readonly.py#L200-L211)，分页读取见 [fetch_dataset:L214-L241](../tools/export_imes_web_readonly.py#L214-L241)，统一程序调用接口见 [query_dataset:L244-L269](../tools/export_imes_web_readonly.py#L244-L269)。

### 2.1 Vastbase 直连：当前实际可读范围（2026-07-16）

以下结论来自 `127.0.0.1:15433 -> 220.12 -> 10.10.181.195:5432` 的只读实测，不是根据表名推测。查询应继续使用只读事务、日期范围与行数上限；不要把 Web 的 12 类数据集直接视为都能用 SQL 直连读取。

| Vastbase 对象 | 已确认数据 | 可用于回答的问题 | 关键关联/时间字段 |
|---|---|---|---|
| `public.t_ipes_out_put` | 出铁/生产实绩、炉次、铁量、班次、计量与出库状态 | 每炉或某时间段的生产实绩、铁量 | `workdate`、`meltno`、`ironquan`、`workshift` |
| `public.batch_input` | 料批/焦批、24 个料仓通道投料量及合计 | 每批投了多少、矿批/焦批汇总 | `workdate`、`lot`、`charge`、`value_01...value_24`、`value_sum` |
| `public.t_ipes_cond` | 炉次作业、开关炉/出铁时间、批次起止、理论/实际铁量及渣比 | 把批次投料按批次范围关联到炉次 | `workdate`、`meltno`、`sumbatchstart`、`sumbatchend`、`sumbatch` |
| `public.t_qpes_inner_batch` | 炉次对应的化验批号、取样/判定时间及状态 | 由炉次定位铁水化验批号 | `businessdate`、`heatno`、`batchno` |
| `public.inner_batch_insp_bb` | 铁水化验结果与判定/发布时间 | 已发布炉次的 C、Si、Mn、P、S 等化验值；其中 `value_02` 已实测为 Si | `batchno`、`judgetime`、`publishtime`、`value_01...value_11` |
| `public.slag_inspection` | 炉渣试样、炉次与化验结果 | 按炉次或日期查询炉渣检验 | `workdate`、`meltno`、`sampleno`、`value_01...value_12` |

当前 **未被直连账号验证为可读**：原料投入、配料方案、料仓、料仓变料、生产计划。这些数据仍可以通过本节的 IMES Web 白名单接口读取；如需 SQL 直连，需要另行增加数据库 `SELECT` 权限并重新生成权限目录。原料化学成分表也尚未发现，因此不能将 `batch_input.value_01...value_24` 误读为化学元素。

实际数据存在性也已按 `2026-05-01` 至 `2026-07-16` 复核：前五个对象均取到 100 行受限样本；`t_qpes_inner_batch` 有读取权限但该时间窗取到 0 行。详细行数、字段与导出文件见 [220.12 IMES 跳板转发与 MCP：受限样本复核](22012_IMES跳板转发与MCP.md#31-受限样本实际读取复核2026-07-16)。

### 2.2 Vastbase 变量逐项简明解释

本节用于把数据库字段翻译成现场容易理解的说法。字段含义来自当前实测对象、既有程序映射和字段结构；单位以源系统返回为准。没有现场字段字典支撑的内容会明确标为“待确认”。

#### 2.2.1 生产实绩 `public.t_ipes_out_put`

| 现场说法 | 数据库字段 | 简明解释 | 使用提示 |
| --- | --- | --- | --- |
| 炉次 | `meltno` | 一次出铁作业的编号，可理解为这炉铁的唯一业务标签，例如以 `2#` 开头表示2号高炉炉次。 | 关联炉次作业、铁水化验和炉渣检验时优先使用。 |
| 铁量 | `ironquan` | MES 记录的该炉次实际铁水量，也就是这炉实际出了多少铁。 | 通常用于炉次产量统计；单位需以现场系统字典为准，现有界面通常按吨理解。 |
| 毛重 | `grossweigh` | 铁水罐装有铁水时的总称重，包含容器自身重量和铁水重量。 | 不能直接当作净铁量。 |
| 皮重 | `tareweigh` | 空罐或容器自身的称重。 | 理论上毛重减皮重可得到净重，但正式统计应优先使用 MES 已确认的 `ironquan`。 |
| 班次 | `workshift` | 该条生产实绩属于哪个生产班次，如白班、夜班或甲乙丙班的时间段。 | 不要与 `workclass` 混淆。 |
| 班组 | `workclass` | 实际承担该炉次作业的人员班组。 | 班次描述时间段，班组描述人员组织。 |
| 称重时间 | `weighttime` | 铁水罐通过计量装置完成称重的时间。 | 可用于核对出铁时间与计量入账时间的先后关系。 |

#### 2.2.2 批次投料 `public.batch_input`

| 现场说法 | 数据库字段 | 简明解释 | 使用提示 |
| --- | --- | --- | --- |
| 矿批 | `charge` + `mining_batch_sum` | 以矿石、烧结矿、球团等含铁料为主体的一批装料；`mining_batch_sum` 是该矿批的合计值。 | 具体物料组成需要结合料仓物料配置，当前直连表本身不提供原料化学成分。 |
| 焦批 | `charge` + `coke_charge_sum` | 以焦炭为主体的一批装料；`coke_charge_sum` 是该焦批的合计值。 | 反映焦炭投料量，不等同于焦比；焦比还需要结合铁量计算。 |
| 批号/料批序号 | `lot` | 装料批次的顺序编号，用来表示第几批料。 | 可与炉次作业表的起止批次关联，判断哪些投料批次归属于某个炉次。 |
| 投料合计 | `value_sum` | 该条批次记录中各料仓/称量通道投料值的合计。 | 应核对是否等于有效通道之和；源系统单位需现场确认。 |
| 1—24号料仓通道 | `value_01...value_24` | 分别记录第1至第24个料仓或称量通道在该批次中的投料值。 | 这些字段是投料量，不是 C、Si、CaO 等化学成分；每个通道实际装什么物料要关联料仓配置。 |
| 投料时间 | `workdate/workdate2` | 该批次的业务时间或辅助时间。 | 跨表关联时还应结合 `lot` 和炉次批次范围，不能只按时间近似匹配。 |

#### 2.2.3 炉次作业 `public.t_ipes_cond`

| 现场说法 | 数据库字段 | 简明解释 | 使用提示 |
| --- | --- | --- | --- |
| 炉次 | `meltno` | 一次出铁作业的业务编号。 | 是关联生产实绩和炉渣检验的主要键。 |
| 起始批次 | `sumbatchstart` | 该炉次所对应投料范围的第一批。 | 与 `batch_input.lot` 配合使用。 |
| 结束批次 | `sumbatchend` | 该炉次所对应投料范围的最后一批。 | 起止批次共同界定该炉次包含的投料批次。 |
| 批次数 | `sumbatch` | 该炉次记录的累计批次数或炉次批次序号。 | 与起止批次的精确关系仍应按现场业务规则核对。 |
| 开铁口 | `opentime` | 打开铁口、开始出铁的时间。 | 可作为一次出铁作业的开始时间。 |
| 堵铁口 | `closetime` | 完成堵口、结束该次出铁的时间。 | 可作为一次出铁作业的结束时间。 |
| 出铁时长 | `tappingtime` | 从开始出铁到结束出铁的持续时长。 | 字段数值单位应以源系统字典为准，不应仅凭数值猜分钟或秒。 |
| 出铁温度 | `tappingtemp` | 该炉次铁水出铁时的温度。 | 通常按摄氏度理解，但正式报表仍应以现场字段字典为准。 |
| 理论铁量 | `theoryquan` | 按计划、模型或物料平衡估算的该炉次应出铁量。 | 用来和实际铁量比较，不代表最终计量结果。 |
| 实际铁量 | `ironquan` | 该炉次实际记录的铁水量。 | 可与生产实绩表的铁量交叉核对。 |
| 渣比 | `slagrate` | 炉渣量相对于铁水产量的比例，用于描述每生产一定铁水产生多少炉渣。 | 比值口径和单位可能是 kg/t 或其他形式，必须以现场定义为准。 |

#### 2.2.4 化验索引 `public.t_qpes_inner_batch`

| 现场说法 | 数据库字段 | 简明解释 | 使用提示 |
| --- | --- | --- | --- |
| 炉次 | `heatno` | 被取样和化验的铁水炉次号。 | 用它把化验结果归到具体炉次。 |
| 化验批号 | `batchno` | 化验室为这次样品或检验任务分配的批号。 | 通过它关联 `inner_batch_insp_bb.batchno` 获取具体元素值。 |
| 取样时间 | `takesampletime` | 从铁水或指定位置取得化验样品的时间。 | 它表示样品产生时间，不等于结果发布时间。 |
| 判定时间 | `judgetime` | 化验结果完成判定或审核的时间。 | 与取样时间的差值可反映化验周转时间。 |
| 检验状态 | `teststatus/judgeresult` | 样品当前是否已检验、结果是否已经判定。 | 结果为空时先检查状态，不能把“未发布”当成元素值为0。 |

#### 2.2.5 铁水元素 `public.inner_batch_insp_bb`

这些值是铁水化学成分结果，现有程序按质量百分含量 `%` 展示；正式单位仍以化验室字段字典为准。

| 元素 | 数据库字段 | 中文名称 | 通顺解释 |
| --- | --- | --- | --- |
| C | `value_01` | 碳 | 铁水中的主要元素之一，影响铁水性质和后续炼钢脱碳负荷。 |
| Si | `value_02` | 硅 | 高炉热制度的重要结果指标之一；现场常用铁水硅变化辅助判断炉缸热状态。 |
| Mn | `value_03` | 锰 | 反映锰元素进入铁水的程度，也会影响后续炼钢成分调整。 |
| P | `value_04` | 磷 | 通常属于需要控制的杂质元素；含量过高会增加后续脱磷负担。 |
| S | `value_05` | 硫 | 需要重点控制的杂质元素；可反映炉内脱硫效果并影响后续炼钢。 |
| Ti | `value_06` | 钛 | 铁水中的钛含量，可能与含钛炉料使用、炉缸状态及护炉操作有关。 |
| V | `value_07` | 钒 | 铁水中的钒含量，常与含钒原料及后续钒资源利用相关。 |
| Cr | `value_08` | 铬 | 铁水中的铬含量，可能来自原料或合金元素背景，需要结合原料来源理解。 |
| Cu | `value_09` | 铜 | 铁水中的残余铜元素；通常较难在常规炼钢中去除，因此需要关注原料带入。 |
| Ni | `value_10` | 镍 | 铁水中的镍含量，可能来自原料背景，也可能影响后续钢种成分控制。 |
| As | `value_11` | 砷 | 铁水中的残余砷元素，通常作为有害残余元素进行监控。 |

元素值必须同时保留 `batchno`、炉次和判定/发布时间。空值表示可能尚未检验、尚未发布或源数据缺失，不能解释为0。

#### 2.2.6 炉渣指标 `public.slag_inspection`

| 现场说法 | 数据库字段 | 简明解释 | 当前边界 |
| --- | --- | --- | --- |
| 炉次 | `meltno` | 该炉渣样品对应的出铁炉次。 | 可与炉次作业、生产实绩关联。 |
| 试样号 | `sampleno` | 化验室给炉渣样品分配的编号。 | 同一炉次可能存在多个样品，应保留试样号。 |
| 发布时间 | `publishtime` | 炉渣检验结果正式发布的时间。 | 不等于取样时间。 |
| 炉渣指标1—12 | `value_01...value_12` | 旧原始表保存的12个炉渣化验结果槽位。 | 只读取旧表时仍不能仅按编号猜测；优先改用第9节已验证的命名视图。 |

2026-07-16 新授权的 `public.v_qpes_slag_insoection_final` 已通过视图定义把源检验元素名明确透视为 `tfe/feo/cao/mgo/sio2/al2o3/tio2/r2/r3/r4/mgo_al2o3/sio2_al2o3`，新开发应优先查询该命名视图，详细解释见第9.5节。旧 `public.slag_inspection.value_01...value_12` 若继续使用，仍需单独取得编号映射，不能倒推二者顺序完全一致。

## 3. 各数据集字段说明

以下字段来自 2026-07-15 授权只读响应。字段名保持 MES 原样，便于后续与页面、Vastbase 或 `bf_imes.raw_rows` 对照。

### 3.1 `pes_bin`：料仓主数据

- 业务含义：当前 2#高炉料仓、所装物料和仓位基础配置。
- 时间边界：接口没有业务日期过滤；`createTime/updateTime` 是记录审计时间，不代表可以按其查询历史版本。
- 核心字段：`id`、`binCode`、`binName`、`binType`、`binDistance`、`mateCode`、`mateName`、`prodCenterCode`、`prodCenterName`、`useStatus`、`picPt`。
- 审计字段：`createTime/createTimes`、`updateTime/updateTimes`、`creator/creatorId`、`updater/updaterId`、`status`、`remark2/remark3`。
- 2026-07-15 样本验证：当前可见 24 行。

### 3.2 `pes_bin_material`：料仓变料记录

- 业务含义：料仓在某业务日切换或指定物料的记录。
- 时间过滤：`startDate/endDate`，对应 `businessDate`，首尾日期均包含。
- 核心字段：`id`、`businessDate`、`binCode`、`binName`、`binType`、`mateCode`、`mateName`、`schemeNo`、`callStatus`、`workClass`、`workShift`、`workStaff`、`prodCenterCode`。
- 审计字段：`createTime/createTimes`、`updateTimes`、`creator/creatorId`、`status`、`remark2/remark3`、`picPt`。

### 3.3 `production_month_plan`：生产月计划

- 业务含义：2#高炉月计划数量、设计人与审核状态。
- 时间边界：接口一次返回当前账号可见的计划集合，没有 `startDate/endDate`；可在导出后按 `planMonth` 本地筛选。
- 核心字段：`id`、`monthPlanCode`、`planMonth`、`planMonthNumbers`、`planMonthNumbersG`、`numbers/numbersD/numbersG`、`daySum`、`sinteringMachineCode`、`sinteringMachineName`、`unitCode`、`unitName`。
- 流程字段：`designDate`、`designPersonCode`、`designPersonName`、`examineDate`、`examinePersonName`、`examineStatus`。
- 审计字段：`createTime/createTimes`、`updateTime/updateTimes`、`creator/creatorId`、`updater/updaterId`、`status`。

### 3.4 `dosing_scheme`：配料方案

- 业务含义：2#高炉配料方案编号、业务日期和布料/批距相关信息。
- 时间过滤：`startDate/endDate`，对应 `businessDate`，首尾日期均包含。
- 核心字段：`id`、`schemeNo`、`business`、`businessDate`、`distance`、`prodCenterCode`、`prodCenterName`、`workClass`、`workShift`、`workStaff`。
- 审计字段：`createTime/createTimes`、`updateTime/updateTimes`、`creator/creatorId`、`updater/updaterId`、`remark/remark1/remark2`。

### 3.5 `input`：原料投入

- 业务含义：按业务日记录各料仓、物料与批次的实际投入量。
- 时间过滤：`startDate/endDate`，对应 `workDate`，首尾日期均包含。
- 核心字段：`id`、`workDate`、`charge`、`binCode`、`binName`、`materialCode`、`materialName`、`inputScQuan`、`inputScQuanK`、`inputScale`、`dryQuan`、`unitName`、`prodCenterCode`、`prodCenterName`、`workStaff`。
- 状态字段：`adjustStaff`、`adjustStatus`、`arriveStatus`、`handleStatus`、`status`。
- 审计字段：`createTimes`、`updateTimes`、`remark3/remark4`。

### 3.6 `batch_all`：批次投料合并

- 业务含义：指定业务日内矿批和焦批合并后的批次、料仓 1-24 投料值及合计。
- 时间过滤：原接口使用单个 `workdate`；客户端对日期范围逐日查询并合并。
- 核心字段：`workdate`、`workdate2`、`lot`、`charge`、`prodcentercode`、`value_01` 至 `value_24`、`value_sum`、`mining_batch_sum`、`coke_charge_sum`、`remark3`。

### 3.7 `batch_mining`：批次投料矿批

- 业务含义：指定业务日内矿批明细。
- 时间过滤与字段：与 `batch_all` 相同；接口只返回矿批子集。
- 2026-07-14 只读验证：169 行。

### 3.8 `batch_coke`：批次投料焦批

- 业务含义：指定业务日内焦批明细。
- 时间过滤与字段：与 `batch_all` 相同；接口只返回焦批子集。
- 2026-07-14 只读验证：168 行；同日 `batch_all` 为 337 行。

### 3.9 `output`：生产实绩索引

- 业务含义：按炉次展示 2#高炉生产实绩的日期、班次、批次汇总和任务状态。
- 时间过滤：`startDate/endDate`，对应 `workDate`，首尾日期均包含；可用 `meltNo` 进一步限定炉次。
- 核心字段：`id`、`workDate`、`meltNo`、`sumBatch`、`workClass`、`workStaff`、`prodCenterCode`、`prodCenterName`、`taskStatus`、`clearStatus`。
- 审计字段：`createTime/createTimes`、`updateTimes`、`creator/creatorId`。
- 边界：这是生产实绩的条件/索引表，不等于页面中所有下钻子表字段。

### 3.10 `heat_lab`：炉次化验索引

- 业务含义：按日期和炉次列出炉次化验批次入口。
- 时间过滤：`startDate/endDate`，对应 `workDate`，首尾日期均包含；可用 `meltNo` 限定炉次。
- 字段：`id`、`workDate`、`meltNo`、`sumBatch`、`prodCenterCode`、`createTime`。
- 边界：本数据集是化验索引，不包含 C、Si、Mn、P、S 等全部元素值；元素明细需要页面的炉次下钻接口，尚未纳入这 12 个白名单数据集。

### 3.11 `slag_lab`：炉渣检验结果

- 业务含义：炉次、试样号、发布时间及炉渣化验值。
- 时间过滤：`startDate/endDate`，以 `workDate/publishtime` 为主要时间；`prodCenterCode=JLZ2`，可用 `meltNo` 限定炉次。
- 字段：`workDate`、`publishtime`、`meltNo`、`sampleno`、`value_02` 至 `value_11`。
- 元素映射需以后端/化验室字段字典为准，不能仅按列序号猜测化学成分。

### 3.12 `heat_lab_all`：炉次化验全量索引

- 业务含义：非分页返回指定时间范围内的炉次化验索引集合。
- 时间过滤：`startDate/endDate`，首尾日期均包含；可用 `meltNo` 限定炉次。
- 字段：`id`、`workDate`、`meltNo`、`sumBatch`、`prodCenterCode`、`createTime`。
- 边界：名称中的“全量”表示该页面索引集合的全量返回，不代表响应中已经包含所有化学元素明细。

## 4. 统一查询接口

### 4.1 环境变量

```text
IMES_WEB_URL=http://10.10.181.209:8080/imes.web/
IMES_WEB_USER=2gldmx
IMES_WEB_PASSWORD=<只在当前进程环境中设置>
IMES_WEB_CAPTCHA=<登录页当前4位验证码>
```

密码和会话 Cookie 不写入代码、文档、manifest 或控制台。登录实现位于 [login:L151-L171](../tools/export_imes_web_readonly.py#L151-L171)。

### 4.2 查看数据集

```powershell
python .\tools\export_imes_web_readonly.py --list-datasets
```

输出列依次为 `key / 中文名称 / 时间模式 / 时间字段 / 查询接口`，此命令不登录系统。

### 4.3 查询一个任意日期范围

```powershell
$env:IMES_WEB_USER = '2gldmx'
$env:IMES_WEB_PASSWORD = '<当前终端输入>'
$env:IMES_WEB_CAPTCHA = '<当前4位验证码>'

python .\tools\export_imes_web_readonly.py `
  --dataset output `
  --start-date 2026-06-01 `
  --end-date 2026-06-30 `
  --output-dir .\exports\imes_output_202606
```

### 4.4 查询批次数据的任意日期范围

```powershell
python .\tools\export_imes_web_readonly.py `
  --dataset batch_all `
  --dataset batch_mining `
  --dataset batch_coke `
  --start-date 2026-07-01 `
  --end-date 2026-07-15 `
  --output-dir .\exports\imes_batch_20260701_0715
```

程序会自动生成 15 个 `workdate` 请求并分别分页，使用者无需自己写循环。若只要某一天，可加 `--workdate 2026-07-14`。

### 4.5 查询全部 12 个数据集

```powershell
python .\tools\export_imes_web_readonly.py `
  --all-datasets `
  --start-date 2026-07-14 `
  --end-date 2026-07-15 `
  --output-dir .\exports\imes_all_20260714_0715
```

每个数据集输出一个 UTF-8 `.jsonl` 文件；`manifest.json` 记录数据集、时间模式、实际请求窗口、行数、字段和文件名。导出实现见 [export_one:L272-L316](../tools/export_imes_web_readonly.py#L272-L316)，CLI 入口见 [main:L389-L470](../tools/export_imes_web_readonly.py#L389-L470)。

### 4.6 供其他 Python 程序调用

```python
import os
import requests

from tools.export_imes_web_readonly import DEFAULT_BASE_URL, login, query_dataset

session = requests.Session()
login(
    session,
    DEFAULT_BASE_URL,
    os.environ["IMES_WEB_USER"],
    os.environ["IMES_WEB_PASSWORD"],
    os.environ["IMES_WEB_CAPTCHA"],
    timeout=20,
)

rows = query_dataset(
    session,
    DEFAULT_BASE_URL,
    key="output",
    start_date="2026-07-01",
    end_date="2026-07-15",
)
for row in rows:
    print(row)
```

`query_dataset()` 返回迭代器，适合流式处理，不要求一次把全部数据放入内存。调用方用完后负责 `session.close()`。

## 5. 时间与完整性边界

- `range` 查询实测为包含首尾日期。例如 `output` 的 `startDate=endDate=2026-07-14` 只返回 `workDate=2026-07-14` 的 13 行。
- `workdate` 查询实测有效。`batch_all` 在 2026-07-13、14、15 日分别返回 331、337、225 行，首行日期均与请求日一致。
- 日期参数粒度是业务日，不是任意秒级时间戳；需要日内时段时，先按日取回，再在本地按 `workDate/workdate/publishtime` 过滤。
- `pes_bin` 没有历史版本接口；只能读取当前主数据。
- `production_month_plan` 没有服务端起止日期参数；可按响应中的 `planMonth` 本地筛选。
- `heat_lab/heat_lab_all` 在尚未发布化验值的炉次上可能只返回索引字段；本机历史导出已确认，化验完成后同一响应可带 `value_01` 至 `value_11`。其中铁水 `Si` 为 `value_02`，详见下方炉次化学成分核查。
- “任意时间”不突破 MES 保留期、停机时段、缺失记录或账号权限。

## 6. 安全边界

- 白名单只包含查询接口；不得把页面中的 `edit/delete/add/save/send/examine` 等写接口加入普通查询程序。
- 默认单页最大 50 行；大范围查询应保留 `manifest.json` 并核对行数。
- 不在日志或异常中打印密码、`JSESSIONID`、验证码或完整登录表单。
- 本客户端只导出文件，不写 Vastbase、PostgreSQL、IMES 或生产控制系统。

## 7. 验证

测试文件：[tests/test_export_imes_web_readonly.py:L42-L163](../tests/test_export_imes_web_readonly.py#L42-L163)。

```powershell
python -m py_compile .\tools\export_imes_web_readonly.py .\tests\test_export_imes_web_readonly.py
python .\tools\export_imes_web_readonly.py --help
python .\tools\export_imes_web_readonly.py --list-datasets
python -m unittest .\tests\test_export_imes_web_readonly.py -v
```

覆盖项包括：分页 `_size/_index`、数组/分页响应归一化、三类批次日期范围逐日展开、显式 `--workdate`、多日结果合并、未知数据集拒绝、写接口白名单检查和 manifest 序列化。

更多系统边界、Vastbase 直连和镜像表路径见 [IMES / Vastbase 数据访问说明](imes.md)。

## 8. 炉次进料化学成分与铁水硅核查（2026-07-16）

### 8.1 结论

- **已发布化验结果的炉次可以读取铁水硅。** `heat_lab`/`heat_lab_all` 的已完成化验记录包含 `meltNo`、`sumBatch` 和 `value_01` 至 `value_11`；字段映射为 `value_01=C`、`value_02=Si`、`value_03=Mn`、`value_04=P`、`value_05=S`。应以 `meltNo` 为炉次主键，并保留 `sumBatch/workDate` 做交叉核对。未化验或尚未发布的最新炉次会保留索引但 `value_02` 为空，不能承诺所有炉次实时 100% 有值。
- **当前 12 个数据集不能直接给出每炉进料的化学成分。** `input` 提供物料、料仓、时间和干重/称量；`batch_all/batch_mining/batch_coke` 的 `value_01` 至 `value_24` 表示 24 个料仓/称量通道的投料量，不是化学元素。
- 因而目前可以形成“每炉投了什么、投了多少”和“每炉出铁 Si 是多少”两类数据，但不能据此计算可靠的“每炉入炉 Fe、SiO2、Al2O3、CaO、MgO 等化学成分”。禁止把批次投料 `value_01...value_24` 与化验数据的同名 `value_01...value_11` 混为一谈。

### 8.2 离线实证

本机保存的 2026-05-10 IMES 导出中：

- 炉次化验记录包含 `meltNo/sumBatch/workDate/value_01...value_11`。例如炉次 `2#20260510-147` 的 `value_02` 为 `0.24`，即铁水 Si 为 `0.24`。
- 2026-05-10 的 `heat_lab` 离线响应有 12 个炉次，其中 10 个 `value_02` 非空；最新的 `2#20260510-148`、`2#20260510-149` 仍只有炉次索引。`heat_lab_all` 的 35 个炉次中有 33 个 Si 非空，缺失的也是这两个最新炉次。
- 3 个月铁水元素离线包共有 3,280 条检验记录，`Si` 均非空；但该导出只保留 `batchno`，没有同时保留 `heatno/meltNo`，不能仅凭这份文件证明 1,320 个炉次全部都有检验记录。在线按炉次完整率仍需通过 `t_qpes_inner_batch.heatno` 与 `t_ipes_cond.meltno` 对账。
- 3 个月 `batch_input` 导出共有 51,516 行，字段为 `workdate/workdate2/lot/charge/value_01...value_24/value_sum`，没有原料化验元素字段，也没有直接的 `meltNo`。
- `t_ipes_cond` 带 `meltNo/sumBatchStart/sumBatchEnd/sumBatch`，可用于研究批次到炉次的范围关联；但这种关联只解决“投料归属哪个炉次”，不会凭空补出原料化学成分。

2026-07-16 较早的实时复核中，`10.10.181.209:8080` 和 `10.10.181.195:5432` 曾因 VPN 路由缺失连接超时，因此本节前述结论最初来自 2026-05-13 保存的真实 IMES 导出。同日 15:08 本机经 Meta 私网路径已使用新增只读账号 `lg_fq` 成功直连 Vastbase，并核实第 9 节五个授权视图；这不会改变“批次投料字段不是原料化学成分”的结论。

### 8.3 要实现每炉进料化学成分还缺什么

至少需要新增并验证以下数据链：

1. 原燃料检验/质检数据：物料编码、供应批次或堆批号、取样/发布日期，以及 Fe、SiO2、Al2O3、CaO、MgO、S、水分等元素或成分字段。
2. 物料批次追踪：把检验批次映射到料仓变料时间段和实际投料记录。
3. 炉次归属：按 `t_ipes_cond.sumbatchStart/sumbatchEnd` 或经过现场确认的时间窗口，把投料批次归入 `meltNo`。
4. 加权计算：按干基投料量对各物料成分加权，并明确缺失检验值、混仓、跨炉次和库存滞后的处理规则。

在上述链路没有取得现场字段字典和样例对账前，只能称为“炉次投料量”，不能称为“炉次进料化学成分”。

### 8.4 铁水硅读取口径

数据库直连可使用 `public.inner_batch_insp_bb`：`value_02 AS Si`，先从 `public.t_qpes_inner_batch` 按日期和 `heatno LIKE '2#%'` 获取 `batchno`，再逐批次精确查询，避免大范围聚合视图超时。Web 查询可读取 `heat_lab` 或 `heat_lab_all`，并过滤 `meltNo`；未完成化验的炉次可能暂时没有 `value_02`，调用方必须区分“尚未发布”与数值 0。

## 9. `lg_fq` 五个授权视图与逐变量字典（2026-07-16）

### 9.1 在线核查结论与口径

2026-07-16 15:08 使用 `lg_fq` 对 `10.10.181.195:5432/vastbase` 做真实只读核查：登录成功，`transaction_read_only=on`，截图所列五个视图全部存在且均有 `SELECT` 权限。核查脚本为 [audit_imes_granted_views.py](../tools/audit_imes_granted_views.py)，证据为 [imes_granted_views_audit_20260716.json](../logs/imes_granted_views_audit_20260716.json)。

所有化学结果列在数据库中实际均为 `varchar/text`，不是数值类型；下游计算前必须把空字符串和非数值状态处理为缺失值，再显式转换为数值。化学成分按当前 MES 业务和样本量级解释为质量百分含量，正式报表单位仍须以化验室字段字典为准。行数、最大时间和非空数是核查时点快照，不是固定常量。

| 视图 | 行数 | 字段数 | 数据性质 |
| --- | ---: | ---: | --- |
| `v_qpes_inner_batch_insp_final_sample` | 49,356 | 20 | 高炉铁水化验完整展示视图 |
| `v_qpes_mat_final` | 49,356 | 16 | 同一铁水化验源的精简投影 |
| `v_qpes_sinter_machine_sample_insp_final` | 10,179 | 29 | 烧结机试样化验 |
| `v_qpes_slag_insoection_final` | 4,939 | 16 | 高炉炉渣化验；名称按数据库现有拼写使用 |
| `v_qpes_steel_final` | 212,136 | 42 | 炼钢试样化验，不是高炉铁水专表 |

### 9.2 `public.v_qpes_inner_batch_insp_final_sample`

来源视图定义直接投影 `t_qpes_inner_batch_insp_final_sample`，覆盖 2024-08-19 至 2026-07-16。`发布时间` 实际映射源字段 `judgetime`，更准确理解为结果判定/审核完成时间；`发布日期` 映射源字段 `publishtime`，当前仅保留日期。

| 字段 | 非空/总行数 | 变量解释 | 使用提示 |
| --- | ---: | --- | --- |
| `id` | 49,356/49,356 | 化验结果内部记录 ID | 技术键，不替代试样号 |
| `试样号` | 49,356/49,356 | 铁水试样/检验批号 | 对应源字段 `batchno` |
| `发布时间` | 49,356/49,356 | 结果判定或审核完成时间 | 源字段为 `judgetime`，含时分秒 |
| `发布日期` | 49,356/49,356 | 结果发布日期 | 源字段为 `publishtime`，当前为日期字符串 |
| `高炉` | 49,356/49,356 | 高炉编号 | 实测为 `1`、`2` |
| `罐号` | 31,990/49,356 | 铁水罐号 | 源字段拼写为 `thankno`；空值不能当作 0 |
| `班次` | 49,356/49,356 | 化验判定所属甲/乙/丙班 | 源字段 `judgeclass` |
| `检验人` | 40,429/49,356 | 执行检验人员 | 个人信息，仅在授权运维/质量场景使用 |
| `审核人` | 40,429/49,356 | 审核发布人员 | 个人信息，仅在授权运维/质量场景使用 |
| `cvalue` | 49,356/49,356 | 铁水碳 C | 化学成分值，通常按质量百分含量理解 |
| `sivalue` | 49,356/49,356 | 铁水硅 Si | 高炉热制度的重要结果指标 |
| `mnvalue` | 49,356/49,356 | 铁水锰 Mn | 反映锰进入铁水的程度 |
| `pvalue` | 49,356/49,356 | 铁水磷 P | 后续炼钢脱磷负荷相关指标 |
| `svalue` | 49,356/49,356 | 铁水硫 S | 高炉脱硫与后续炼钢相关指标 |
| `tivalue` | 49,356/49,356 | 铁水钛 Ti | 与含钛炉料和护炉背景相关 |
| `vvalue` | 49,356/49,356 | 铁水钒 V | 与含钒原料背景相关 |
| `crvalue` | 49,356/49,356 | 铁水铬 Cr | 残余/合金元素 |
| `nivalue` | 49,356/49,356 | 铁水镍 Ni | 残余/合金元素 |
| `cuvalue` | 49,356/49,356 | 铁水铜 Cu | 难去除残余元素，关注原料带入 |
| `asvalue` | 14,103/49,356 | 铁水砷 As | 仅约部分记录有值；空值表示未检/未发布/历史缺失，不是 0 |

### 9.3 `public.v_qpes_mat_final`

该视图同样来自 `t_qpes_inner_batch_insp_final_sample`，与上一视图行数完全相同，是去掉判定时间、班次和人员字段后的精简投影。它虽然名为 `mat_final`，但实测内容是铁水试样元素，不是矿石、焦炭或烧结矿等原料化学成分。

| 字段 | 非空/总行数 | 变量解释 | 使用提示 |
| --- | ---: | --- | --- |
| `id` | 49,356/49,356 | 化验结果内部 ID | 与完整视图同源 |
| `batchno` | 49,356/49,356 | 铁水试样号/检验批号 | 对应完整视图“试样号” |
| `publishtime` | 49,356/49,356 | 发布日期 | 当前是 `YYYY-MM-DD` 文本，不含具体发布时间 |
| `prodcentercode` | 49,356/49,356 | 高炉编号 | 实测为 `1`、`2` |
| `thankno` | 31,990/49,356 | 铁水罐号 | 源字段沿用 `thankno` 拼写 |
| `cvalue` | 49,356/49,356 | 碳 C | 与完整视图同源 |
| `sivalue` | 49,356/49,356 | 硅 Si | 与完整视图同源 |
| `mnvalue` | 49,356/49,356 | 锰 Mn | 与完整视图同源 |
| `pvalue` | 49,356/49,356 | 磷 P | 与完整视图同源 |
| `svalue` | 49,356/49,356 | 硫 S | 与完整视图同源 |
| `tivalue` | 49,356/49,356 | 钛 Ti | 与完整视图同源 |
| `vvalue` | 49,356/49,356 | 钒 V | 与完整视图同源 |
| `crvalue` | 49,356/49,356 | 铬 Cr | 与完整视图同源 |
| `nivalue` | 49,356/49,356 | 镍 Ni | 与完整视图同源 |
| `cuvalue` | 49,356/49,356 | 铜 Cu | 与完整视图同源 |
| `asvalue` | 14,103/49,356 | 砷 As | 稀疏字段，不能以空值代替 0 |

### 9.4 `public.v_qpes_sinter_machine_sample_insp_final`

覆盖 2025-04-21 至 2026-07-16，包含 1、2号烧结机的试样流转和烧结矿化验。`R2`、镁铝比、铝硅比为无量纲比值；`QD` 的确切试验名称和单位在当前数据库注释中缺失。

| 字段 | 非空/总行数 | 变量解释 | 使用提示 |
| --- | ---: | --- | --- |
| `试样单id` | 10,179/10,179 | 试样单内部 ID | 技术键 |
| `试样单号` | 10,179/10,179 | 烧结试样单编号 | 可追踪单次试样 |
| `业务日期` | 10,179/10,179 | 样品所属生产业务日 | 文本日期 |
| `检验批号` | 10,179/10,179 | 化验检验批次号 | 当前样本通常与试样单号一致，仍应保留原字段 |
| `加工中心编码` | 10,179/10,179 | 烧结机/加工中心编码 | 实测 `JS1`、`JS2` |
| `加工中心名称` | 10,179/10,179 | 烧结机名称 | 实测“1号烧结机”“2号烧结机” |
| `制样时间` | 10,179/10,179 | 样品制备时间 | 含时分秒 |
| `接样人` | 10,179/10,179 | 化验室接收样品人员/账号 | 个人/账号信息，限制使用 |
| `接样时间` | 10,179/10,179 | 化验室接样时间 | 可与发布时间计算周转时长 |
| `接样班次` | 10,179/10,179 | 白班/夜班时段 | 不同于甲乙丙班组 |
| `接样班别` | 10,179/10,179 | 甲/乙/丙班组 | 人员组织班组 |
| `发布人` | 10,179/10,179 | 发布化验结果的人员/账号 | 个人/账号信息，限制使用 |
| `发布时间` | 10,179/10,179 | 结果正式发布时间 | 最新实测到 2026-07-16 14:43:56 |
| `tfevalue` | 10,179/10,179 | 全铁 TFe | 烧结矿总铁含量 |
| `caovalue` | 10,179/10,179 | 氧化钙 CaO | 烧结矿主要碱性氧化物 |
| `mgovalue` | 10,179/10,179 | 氧化镁 MgO | 炉料/炉渣制度相关成分 |
| `sio2value` | 10,179/10,179 | 二氧化硅 SiO2 | 主要酸性氧化物 |
| `al2o3value` | 10,179/10,179 | 三氧化二铝 Al2O3 | 影响炉渣性质的成分 |
| `pvalue` | 10,176/10,179 | 磷 P | 3 条记录为空 |
| `tio2value` | 10,179/10,179 | 二氧化钛 TiO2 | 含钛成分指标 |
| `mnovalue` | 10,179/10,179 | 氧化锰 MnO | 锰氧化物含量 |
| `znvalue` | 9,979/10,179 | 锌 Zn | 循环富集/有害元素关注项 |
| `crvalue` | 9,979/10,179 | 铬 Cr | 残余元素指标 |
| `r2value` | 10,179/10,179 | 二元碱度 R2 | 样本数值与 `CaO/SiO2` 一致；无量纲 |
| `feovalue` | 10,179/10,179 | 氧化亚铁 FeO | 反映烧结矿氧化程度等性质 |
| `svalue` | 10,179/10,179 | 硫 S | 烧结矿硫含量 |
| `mgalvalue` | 10,179/10,179 | 镁铝比 | 样本数值与 `MgO/Al2O3` 一致；无量纲 |
| `alsivalue` | 10,179/10,179 | 铝硅比 | 样本数值与 `Al2O3/SiO2` 一致；无量纲 |
| `qdvalue` | 8,858/10,179 | QD 强度类指标 | 样本常见约 78；确切试验名、算法和单位待烧结/化验室字典确认 |

### 9.5 `public.v_qpes_slag_insoection_final`

该视图从通用试样及检验明细按 `JLZ1/JLZ2` 过滤并把元素行转成列，覆盖 2024-08-30 至 2026-07-16。数据库对象名确实拼作 `insoection`，程序和 SQL 必须原样使用。R2/R3/R4 是源系统已存结果，样本数值分别与下述常用公式吻合，但正式公式仍以化验室标准为准。

| 字段 | 非空/总行数 | 变量解释 | 使用提示 |
| --- | ---: | --- | --- |
| `sampleno` | 4,939/4,939 | 炉渣试样号 | 样品主标识 |
| `meltno` | 4,850/4,939 | 对应高炉炉次号 | 89 条为空；关联炉次前必须排除空值 |
| `prodcentercode` | 4,939/4,939 | 炉渣加工中心/高炉编码 | `JLZ1`、`JLZ2` 对应 1、2号炉渣 |
| `publishtime` | 4,928/4,939 | 化验结果发布时间 | 11 条为空 |
| `tfe` | 565/4,939 | 全铁 TFe | 历史覆盖很低，不能作为每炉必有指标 |
| `feo` | 4,918/4,939 | 氧化亚铁 FeO | 炉渣含铁/氧化性相关指标 |
| `cao` | 4,930/4,939 | 氧化钙 CaO | 主要碱性氧化物 |
| `mgo` | 4,930/4,939 | 氧化镁 MgO | 炉渣流动性和炉衬相关成分 |
| `sio2` | 4,930/4,939 | 二氧化硅 SiO2 | 主要酸性氧化物 |
| `al2o3` | 4,930/4,939 | 三氧化二铝 Al2O3 | 影响黏度等炉渣性质 |
| `tio2` | 4,930/4,939 | 二氧化钛 TiO2 | 含钛炉料背景指标 |
| `r2` | 4,930/4,939 | 二元碱度 | 样本与 `CaO/SiO2` 吻合；无量纲 |
| `r3` | 4,927/4,939 | 三元碱度 | 样本与 `(CaO+MgO)/SiO2` 吻合；正式口径待确认 |
| `r4` | 4,927/4,939 | 四元碱度 | 样本与 `(CaO+MgO)/(SiO2+Al2O3)` 吻合；正式口径待确认 |
| `mgo_al2o3` | 4,929/4,939 | 镁铝比 `MgO/Al2O3` | 无量纲 |
| `sio2_al2o3` | 0/4,939 | 硅铝比 `SiO2/Al2O3` | 列存在但当前全为空，现阶段不可用 |

### 9.6 `public.v_qpes_steel_final`

该视图来自 `t_qpes_steel_making_sample_insp_final`，覆盖炼钢多个工序中心，实测工序编码包括 `CY/LF/H/CP/Q` 等。它包含钢液/钢样成分和钢种判定，不应与 1、2号高炉铁水化验混用。化学字段中的 `mdvalue` 是源系统命名后缀，不代表单位。

| 字段 | 非空/总行数 | 变量解释 | 使用提示 |
| --- | ---: | --- | --- |
| `id` | 212,136/212,136 | 炼钢试样检验记录 ID | 技术键 |
| `sampleno` | 212,136/212,136 | 炼钢试样号 | 样品主标识 |
| `femdvalue` | 158,145/212,136 | 铁 Fe | 部分样品不发布 Fe |
| `cmdvalue` | 212,130/212,136 | 碳 C | 化学成分 |
| `simdvalue` | 212,130/212,136 | 硅 Si | 化学成分 |
| `mnmdvalue` | 212,130/212,136 | 锰 Mn | 化学成分 |
| `pmdvalue` | 212,130/212,136 | 磷 P | 化学成分 |
| `nimdvalue` | 212,127/212,136 | 镍 Ni | 合金/残余元素 |
| `momdvalue` | 211,967/212,136 | 钼 Mo | 合金元素 |
| `cumdvalue` | 212,127/212,136 | 铜 Cu | 残余/合金元素 |
| `almdvalue` | 212,129/212,136 | 总铝 Al | 根据字段组合和样本关系解释；正式名称待化验室确认 |
| `alsmdvalue` | 168,080/212,136 | 酸溶铝 Als | 推断口径；与总铝、不溶铝关系需按化验标准确认 |
| `timdvalue` | 212,128/212,136 | 钛 Ti | 合金元素 |
| `vmdvalue` | 211,969/212,136 | 钒 V | 合金元素 |
| `nbmdvalue` | 211,965/212,136 | 铌 Nb | 微合金元素 |
| `wmdvalue` | 167,890/212,136 | 钨 W | 合金元素，部分样品为空 |
| `comdvalue` | 166,232/212,136 | 钴 Co | 合金元素，部分样品为空 |
| `bmdvalue` | 211,739/212,136 | 硼 B | 微量元素 |
| `camdvalue` | 212,073/212,136 | 钙 Ca | 微量/处理元素 |
| `sbmdvalue` | 166,211/212,136 | 锑 Sb | 残余元素 |
| `asmdvalue` | 183,442/212,136 | 砷 As | 有害残余元素 |
| `snmdvalue` | 167,348/212,136 | 锡 Sn | 残余元素 |
| `pbmdvalue` | 166,232/212,136 | 铅 Pb | 残余元素 |
| `bimdvalue` | 165,961/212,136 | 铋 Bi | 残余元素 |
| `znmdvalue` | 165,676/212,136 | 锌 Zn | 残余元素 |
| `insptime` | 212,136/212,136 | 检验完成时间 | 最新实测 2026-07-16 15:01:09 |
| `smdvalue` | 212,130/212,136 | 硫 S | 化学成分 |
| `crmdvalue` | 212,127/212,136 | 铬 Cr | 合金/残余元素 |
| `alismdvalue` | 167,287/212,136 | 不溶铝结果 | 由字段名及 `总铝-酸溶铝` 样本关系推断，通常为舍入值；待化验室确认 |
| `alisinvalue` | 167,287/212,136 | 不溶铝原始/高精度结果 | 与上一字段数值接近但精度更高；具体仪器/计算口径待确认 |
| `nmdvalue` | 165,657/212,136 | 氮 N | 气体元素/成分指标 |
| `ceq` | 45,621/212,136 | 碳当量 CEQ | 派生指标，具体公式随钢种标准可能不同 |
| `businessdate` | 212,136/212,136 | 生产业务日期 | 文本日期，覆盖自 2024-10-10 |
| `steelgrade` | 109,710/212,136 | 计划/申报钢种 | 实测含 `Q235B`、`Q355B`、`SPHC` 等；部分工序不填 |
| `judgingsteelgrade` | 45,711/212,136 | 化验判定钢种 | 根据结果判定或发布的钢种，覆盖率低于 `steelgrade` |
| `heatno` | 211,833/212,136 | 源系统炉位/工序代码字段 | 实测为 `1H/2H/1LF/2C` 等，不是唯一炉号，禁止单独作炉次主键 |
| `prodcentercode` | 212,136/212,136 | 炼钢工序/加工中心编码 | 实测 `CY/LF/H/CP/Q` 等，精确中文映射待 MES 字典确认 |
| `publishtime` | 212,136/212,136 | 结果发布时间 | 最新实测 2026-07-16 15:01:08 |
| `receivesampleclass` | 212,136/212,136 | 接样班组 | 甲/乙/丙班 |
| `furnacenumber` | 173,309/212,136 | 实际炉号/生产炉次号 | 比 `heatno` 更接近业务炉号；仍应与生产系统主键对账 |
| `receivesampletime` | 168,583/212,136 | 接样时间 | 可与检验/发布时间计算化验周转时间 |
| `prodname` | 40,638/212,136 | 源系统产品/产线名称代码 | 当前实测多为 `1/2`，确切中文含义待 MES 字典确认 |

### 9.7 使用边界

- 五个视图明确可用于只读查询，但不是生产控制接口；不得对其底层表执行写入。
- `v_qpes_mat_final` 与完整铁水视图同源，不能把两者相加统计，否则会重复计数。
- `v_qpes_steel_final` 属于炼钢样品，不能当作高炉铁水数据；高炉铁水优先使用 `v_qpes_inner_batch_insp_final_sample`。
- 所有时间字段和多数化学值是文本；范围筛选应先确认格式，数值计算要使用可失败的安全转换策略。
- 空值表示未检、未发布、不适用或历史缺失，不能自动填 0。`sio2_al2o3` 当前 4,939 行全空，`tfe` 仅 565 行非空。
- `QD`、炼钢工序代码、`prodname` 及铝的细分口径仍缺少正式字段字典；本文已标出推断，不得把推断升级为生产标准。

## 10. 软熔带趋势模型数据源复核（2026-07-19）

追踪编号：`Q-COHESIVE-ZONE-DATA-SOURCES-20260719`。

本次重新通过 220.12 转发只读核查 Vastbase，确认需要区分两套权限面：

- `lg_fq` 当前可读五个命名化验视图，结果更新到 2026-07-19；
- 项目受控历史只读配置当前可读六个业务原表，但不能读取上述命名化验视图。

因此软熔带模型的数据适配不能假定一个数据库账号可同时读取批次、炉次和全部
命名化验视图。应把两类来源做成独立 adapter，并在上层按业务键和发布时间合并。

新增只读证据：

- 命名视图行数：铁水化验 49,573、烧结矿 10,253、炉渣 4,967；
- `batch_input` 在 2026-05-01 至 2026-07-19 有 27,319 条 2# 记录，
  `workdate/workdate2/remark3/lot/charge/value_sum/mining_batch_sum/coke_charge_sum`
  均非空；
- `t_ipes_cond` 同期有 1,084 条 2# 炉次记录，开炉/堵口/出铁时间基本完整；
- `t_ipes_cond.tappingtemp` 在当前可见的 2# 全历史 9,373 条中非空数为 0，
  不能把“字段存在”写成“铁水温度数据可用”；
- `t_qpes_inner_batch` 在上述窗口为 0 行，当前不能靠它完成
  `heatno -> batchno -> 铁水元素` 的稳定关联。

完整逐项结论和证据路径见
[软熔带数据源只读核查](软熔带数据源只读核查_20260719.md)。

## 11. 铁水硅—炉况—传感器时间对齐数据集（2026-07-19）

需求编号：`REQ-HOT-METAL-SI-DATASET-20260719`。

已使用 `v_qpes_inner_batch_insp_final_sample` 的 2# 高炉铁水 Si 与
220.12 `bf_sensor.diagnosis_snapshots/one_minute_values` 生成本地数据集：

- 完整标签和宽表 5,699 条；
- 4,103 条可以匹配到结果时间之前的炉况快照；
- 严格训练版 4,090 条，要求炉况存在且每条至少有 115 个传感器值；
- 完整宽表 312 列，包括 134 个注册传感器列、规则特征、8 种炉况分数
  和铁水化验标签。

时间口径不是按“发布时间直接最近邻”：

1. `si_result_ts` 来自命名视图“发布时间”，其源语义是判定/审核完成时间；
2. `feature_end_ts = si_result_ts - 120 分钟`；
3. 炉况只向前匹配 15 分钟，传感器只向前匹配 10 分钟；
4. 不取未来值，不把历史新增点前向填充到过去；
5. 取得 `meltNo/heatno -> batchno -> takesampletime/tappingtime` 后必须按
   真实取样/出铁时刻重建。

构建、字段、产物、训练排除列和验证命令见
[铁水硅炉况传感器数据集](铁水硅炉况传感器数据集.md)。

## 12. 炉次中心化五表与烧结矿时间背景（2026-07-25）

需求编号：`REQ-HEAT-CENTRIC-DASHBOARD-20260725`。

当前 8890 已增加以 IMES 正式炉次为中心的只读聚合接口和页面：

- `heat_master`：来自 `t_ipes_cond` 的炉次、开口、堵口和批次摘要；
- `heat_hot_metal_chemistry`：铁水试样明细及其炉次映射证据；
- `heat_slag_chemistry`：按 `meltno` 精确关联的炉渣化验；
- `heat_sensor_window_features`：133 点在 `pre_tap/tapping/inter_heat`
  窗口中的统计与覆盖率；
- `heat_alignment_audit`：每个来源的映射方式、置信度、缺失和歧义。

`v_qpes_sinter_machine_sample_insp_final` 确认包含 1/2 号烧结机的 TFe、FeO、
CaO、MgO、SiO2、Al2O3、P、S、TiO2、MnO、Zn、Cr、R2 及比例/强度字段。
因为没有 `meltno` 或已核实的料批谱系键，它不进入上述五张核心表的精确质量
关联，只作为开口前 12 小时上游背景，并标记低置信度时间关联。

详细字段、API 和使用边界见
[五张核心表与133点时间窗口说明](以炉次为中心的五张核心数据表与133点时间窗口说明_20260725.docx)
及 [本机数据库转发与炉况汇总页面](本机数据库转发与炉况汇总页面_20260725.md)。

## 13. 2#铁水Si正式标签合同复核（2026-07-26）

需求编号：`REQ-SI-FORMAL-LABEL-CONTRACT-V3-20260726`。

本次重新通过220.12转发只读核查，修正第10节在旧日期条件下
“`t_qpes_inner_batch`为0行”的阶段性结论。当前全表可见：

- `t_qpes_inner_batch`中2#正式化验24,821条、9,337个正式`heatno`；
- 24,705条可精确连接`t_ipes_cond.meltno`，覆盖99.53%；
- `takesampletime`非空0条，`takesamplesite`非空0条；
- 结果时间位于开堵口区间13,503条、堵口后10,780条、开口前611条，进一步
  证明`judgetime`不能冒充取样时间；
- `t_ipes_cond`当前可见2#正式炉次9,475炉；`tappingpitch/angle/tappingtemp`
  在该范围均为0条，不能从这些字段取得可信铁口编号或温度；
- 全历史正式化验按`batchno`连接`v_qpes_mat_final.thankno`覆盖16,400条
  （66.07%），无一批次多罐冲突；
- 与PostgreSQL传感器历史相交的V3范围内，5,936条正式试样的铁罐号精确连接
  覆盖100%，但该比例只适用于当前相交范围；
- 该相交范围有161条结果记录早于或等于本炉`opentime`，其中66炉的完整目标
  在预测截止前已全部可见；V3训练层将这66炉作为非前瞻样本排除。

固定使用边界：

1. 炉次必须使用`t_qpes_inner_batch.heatno`精确连接`t_ipes_cond.meltno`；
2. 禁止从试样号文本推断正式炉次；
3. `takesampletime`为空时必须保留为空，禁止用`judgetime/publishtime`代替；
4. 铁口编号当前记为缺源，禁止从`T_taphole_1/T_taphole_2`测温点猜测；
5. 出铁阶段只有在真实取样时间与开堵口时间都存在时才能计算；
6. “整炉代表Si”“下一试样Si”“整炉Si分布”必须作为三个独立目标。

完整合同、数据清单和训练边界见
[铁水Si正式标签与数据合同V3](../PT/预测铁水Si含量/docs/data_contract.md)。

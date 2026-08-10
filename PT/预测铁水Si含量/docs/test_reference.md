# 测试参考

## TEST-SI-ENGINE-UNIT-001

覆盖需求：`REQ-SI-SEMANTIC-NEURON-ENGINE-20260726`

测试文件：[test_engine.py](../tests/test_engine.py)

运行：

```powershell
python -m unittest discover -s tests -v
```

V1阶段原预期：

```text
Ran 8 tests
OK
```

覆盖内容：

- `design_only_unfitted` 拒绝预测；
- CLI返回结构化未标定错误；
- 缺少特征时拒绝预测；
- 三段概率之和为1；
- 输出保留神经元加权输入和贡献；
- 正向热输入神经元在测试夹具中提高Si中心值。
- 临时炉次组解析；
- 炉次时间切分互斥且有序；
- 前序炉Si必须在当前特征截止前已发布；
- 当前炉次化验字段不会混入模型输入。

2026-07-27 V5多窗口迭代后实测：`Ran 30 tests / OK`。

新增覆盖：

- 主容差固定为`±0.05个Si百分点`；
- 规则特征唯一归入扩展工艺神经元；
- 单点正斜率、覆盖率和缺测段计算；
- Bad质量不进入数值统计；
- 截止时刻之后的极端未来值不能改变任何派生特征；
- 多点、多窗口字段合同数量确定且无重复。
- 风压—顶压、压差分配、料线差、静压力梯度和炉身纵向梯度计算；
- 跨点输入缺失时不允许静默补0。
- 缺少正式meltno时不得从试样号修复炉次；
- 结果时间不得替代真实取样时间；
- 只有真实取样时间才能生成出铁阶段与下一试样目标；
- 整炉代表值和P10/P50/P90/spread定义固定；
- 前序炉Si必须来自更早正式炉次且结果已在当前截止前可见；
- 正式meltno在70/15/15时间切分中互斥且有序。
- 133点目录精确区分`EQ_`静压力与原有压差点；
- 扩展历史不得读取当前炉或尚未发布炉次的Si；
- 物理组合的60/120分钟变化由历史快照重建；
- PostgreSQL多窗口SQL严格使用`v.ts < MES opentime`；
- 多窗口覆盖率、极差和变异系数不把缺失补成0；
- 多窗口宽表截止时刻必须与MES开铁时刻完全一致；
- 神经元相关性排序只读取调用方提供的训练行。

## TEST-SI-ENGINE-COMPILE-002

```powershell
python -m compileall -q src tests
python -m src.si_semantic_engine.cli --help
```

预期：退出码0，无语法错误，帮助文本包含 `--config` 和 `--features`。

## TEST-SI-V20-OPEN-MINUS-20260807

覆盖需求：`REQ-SI-V20-OPEN-MINUS-HITRATE-20260807`

测试文件：[test_v20_open_minus_features.py](../tests/test_v20_open_minus_features.py)

运行：

```powershell
$env:PYTHONPATH='D:\文件\冀南钢铁运行中第二版本\PT\预测铁水Si含量\src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m unittest 'PT\预测铁水Si含量\tests\test_v20_open_minus_features.py'
```

2026-08-07 实测：`Ran 7 tests / OK`。

覆盖内容：

- `open_ts - lead_minutes` 生成预测截止时刻；
- 多提前量样本分别保留；
- 前 1～5 炉平均 Si 来自严格更早且已发布炉次；
- 当前炉目标即便 label 时间早于 cutoff 也不能进入输入；
- 未发布前炉会被跳过，并形成未化验炉次间隔；
- PCI 窗口只读取 cutoff 前分钟值，不用未来分钟值也不补 0；
- 特征合并拒绝 `target__*` 泄漏列；
- ±0.05 命中率按 `abs(prediction-actual) <= 0.05` 计算。

## 后续必须补充

- 数据泄漏反例测试；
- 同炉次分组切分测试；
- 原料谱系置信度测试；
- 滚动月份回测；
- 概率校准与P10-P90覆盖率测试；
- 模型版本哈希和回滚测试；
- MCP只读响应合同测试。

V3已补充前四项中的正式标签泄漏、同炉分组和P10-P90目标定义单元测试；滚动
月份回测已在V5～V9实验中执行，但折边界仍需继续单元化。生产模型回滚及MCP
合同仍待后续阶段。

后续深度混合网络还必须新增：

- 滚动月份切分不可越界（V5已有实际滚动结果，仍需单元化折边界）；
- 自监督预训练不能读取测试月份；
- 概念层方向、范围和缺失门禁；
- 黑箱残差幅度上限与数据质量门控；
- E0～E5同一切分和同一指标合同；
- 逐概念及逐分支消融；
- 尾部Si召回和分布条件覆盖率。

## 2026-07-27 V6～V9 回归

实测：

```text
Ran 36 tests
OK
```

新增覆盖：

- 480分钟窗口会同步扩展数据库回看范围；
- 多尺度神经元确实包含8小时与短窗口差异；
- 出铁口温度字段始终保留“代理”语义，不可冒充真实铁水温度；
- 优势窗口只由训练行相关性选择；
- 前炉化验排除当前炉和截止时刻后才发布的结果；
- 加载多窗口Parquet前重新计算SHA-256，篡改分片会被拒绝。

验证命令：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

## 2026-07-27 V10～V12 回归

实测：

```text
Ran 46 tests
OK
```

新增覆盖：

- 嵌套累计均值可准确恢复五个非重叠时延带；
- 圆周均匀场的一阶谐波幅值为0；
- 已知余弦方位偏流可恢复正确幅值和方向分量；
- 方位有效率不足时保持缺失，不允许输出伪0；
- 中位数—均值训练目标按指定比例计算；
- 多试样且低离散标签获得更高训练可靠性权重；
- 均匀权重不依赖标签统计；
- V12所有非负权重组合严格和为1。
- 前瞻协议中的V9/V10冻结模型SHA-256与实际模型文件一致；
- 前瞻准入边界严格晚于历史数据最大截止时刻，且禁止中途选模。

V10～V12训练还实际执行了4/5/6月逐折特征重建；折边界的独立单元化仍列为
后续工作。

## 2026-07-27 严格历史与V13回归

实测：

```text
Ran 55 tests
OK
```

新增覆盖：

- 同一预测截止时刻的炉次不能互相进入历史；
- 历史Si浮点神经元经CSV往返后逐值一致；
- 非重叠时延带标准差可由累计一阶/二阶矩准确恢复；
- V13派生器不读取任何 `target__*` 字段；
- 配对比较的MAE和窄带命中差方向合同；
- 全部历史/当前前瞻协议冻结模型SHA-256与文件一致；
- 当前V4协议的未来边界晚于历史最大截止时刻且禁止中途选模。
- 达到结算门槛时，V13点预测和P10-P90分布均进入延迟标签评价。

额外集成验收：

```text
V9 max abs replay diff  = 1.6653345369377348e-16
V10 max abs replay diff = 8.326672684688674e-17
V13 max abs replay diff = 8.326672684688674e-17
tolerance               = 1e-10
current heat target used = false
```

## 2026-07-27 V14～V15 回归

实测：

```text
62 passed
源码与测试 compileall 通过
```

新增覆盖：

- 语义组能够识别核心变量、18点静压力场和炉体热场；
- PLS潜因子只在训练折拟合；
- 最佳时延解析保留完整物理变量名、响应族和时段中心；
- 每个变量×响应族只选择一个训练折内最佳时延；
- 低覆盖率、常量和非时延/目标字段不会进入选择；
- 配对比较支持两个预测文件使用同名预测列。

## 2026-07-27 V16～V18 回归

实测：

```text
68 passed
源码、测试及Word报告生成脚本 compileall 通过
```

新增覆盖：

- 重要性选择器使用显式残差目标，而不是隐式读取完整Si；
- 常量和低覆盖率特征不会进入V16排序；
- V13选择缓存重建前校验训练行数、特征数量和字段存在性；
- V18只允许有界200轮Plain残差MAE/RMSE配置；
- Word报告人工/程序核验主标题黑体22磅、正文宋体12磅小四。
- 算法流程图为2400×1350 RGB PNG；Word检测到1个内嵌图形和“图1”题注；
  已实现Si分支使用实线，待真实标签的温度/热状态分支使用虚线。

## TEST-SI-AVERAGE-CURVE-20260806

覆盖需求：`REQ-SI-AVERAGE-CURVE-22012-20260806`

运行：

```powershell
python -m unittest 'PT.预测铁水Si含量.tests.test_si_average_curve' 'PT.预测铁水Si含量.tests.test_formal_v3' -v
python -m py_compile .\tools\audit_22012_si_prediction_sources.py .\tools\audit_22012_imes_sinter_chemistry.py .\tools\run_22012_si_average_curve.py .\tools\rebuild_si_average_curve_from_cache.py
```

2026-08-06实测：`Ran 13 tests / OK`，四个脚本语法检查通过。

新增覆盖：

- 同炉多样本目标使用算术平均而不是中位数；
- 平均值目标同步重建前炉历史；
- 前炉Si只来自更早炉次且已在截止时刻前发布；
- V9残差分量必须加回历史Si基线后再按自适应权重融合；
- 曲线PNG和误差/趋势指标可生成。

## REQ-SI-V19-CONTEXT-ABLATION-20260806

Offline ablation for prior 1-5 heat mean-Si, current/lagged PCI, and IMES sinter chemistry time-background; V9/V13 and production interfaces remain frozen; chronological split is 1603/344/344.

Implementation: v19_context_features.py, train_v19.py, extract_v19_context_v2.py, replay_v19_si_context_v2.py, test_v19_context_features.py.

Result: chemistry ranked first on April/May/June pre-test selection, but frozen-test MAE did not beat V9 and paired bootstrap crossed zero; no shadow promotion. Status remains experimental_offline. Chemistry is time-background only; batch-to-bin-to-charge-to-heat lineage is unverified.

Status: completed_offline_not_promoted.


## REQ-SI-V19-AUGUST-HOLDOUT-20260807

V19 rolling update: July data is included in offline training through 2026-07-26 19:02:00; 158 new August heats are held out as time-out evaluation. Original V19 artifacts remain frozen.

Implementation: train_v19_august_holdout.py and train_v19_august_holdout_v2.py. Results: EXP-SI-V19-AUGUST-HOLDOUT-20260807.

The protocol-selected candidate is pci; all_context is promising on this single August window but cannot be selected from the test result. No production promotion.

Status: completed_offline_time_out_validation.


## TEST-SI-V21-SENSOR-CACHE-20260808

覆盖需求：`REQ-SI-V21-SENSOR-CACHE-20260808`

运行：

```powershell
python -m unittest 'PT\预测铁水Si含量\tests\test_v21_sensor_window_cache.py'
python .\tools\build_v20_sensor_window_cache.py --help
python .\tools\build_open_minus_si_dataset_v20.py --help
python .\tools\materialize_v21_dataset_from_sensor_cache.py --help
python .\tools\train_open_minus_si_v20.py --help
```

2026-08-08 实测：`test_v21_sensor_window_cache.py` 2 项通过；四个 CLI help 均可解析。process133 缓存修正版 stderr 为空。

新增覆盖：

- 传感器窗口只使用 `[cutoff-window, cutoff)`，不读取 cutoff 时刻及之后分钟值；
- 缓存合并优先使用 `v20_sample_id`，避免同一炉次不同提前量串特征；
- `process133` 口径排除 `EQ_` 前缀点位；
- 高维训练器支持候选进度事件和 `--candidate-names` 子集运行。


## TEST-SI-FUELRATIO-V20-SIDE-BY-SIDE-20260808

覆盖需求：`REQ-SI-FUELRATIO-V20-SIDE-BY-SIDE-20260808`

运行：

```powershell
python -m py_compile .\tools\compare_foreman_fuel_vs_v20_history.py
python .\tools\compare_foreman_fuel_vs_v20_history.py --help
python .\tools\compare_foreman_fuel_vs_v20_history.py
```

2026-08-08 实测：语法检查和 CLI help 通过；程序成功按炉号+开口时间一对一匹配
15 炉，其中 V20 validation+confirm 共同样本 7 炉；报表 Si 与 220.12 平均 Si 最大
差值 `0.005`；CSV、JSON、PNG、Markdown 四类产物生成成功。

边界：MES Web 每个日报 HTML 当前只直接暴露一个炉前块，确认段仅 2 个共同样本，
不得据此宣称总体稳定性或调整生产模型。

## TEST-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808

覆盖需求：`REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808`

```powershell
python -m unittest .\tests\test_si_v20_shadow_workbench.py -v
python -m pytest .\tests\test_heat_performance_quality.py .\tests\test_heat_performance_quality_query.py .\tests\test_heat_query_tank_display.py -q
node --check .\高炉前端数据\assets\bf-si-v20-shadow-workbench.js
node .\tools\verify_si_v20_shadow_ui.cjs
node .\tools\verify_si_v20_shadow_remote_ui.cjs
```

结果：原 V20 专项 4 项通过，既有炉次质量 14 项通过；便携模型 256 行与原模型最大绝对差 `2.78e-16`；本地 Chromium/Firefox/WebKit 共 18 个视口通过；远端 8093/8094 各以 `1366x768`、`390x844` 验证入口、抽屉、历史页、状态 API、无横向溢出和零页面错误。2026-08-08 权限调整后新增“默认不要求登录”单测，专项测试总数为5项。远端两端 `status.require_login=false`；未登录对 `2#20260808-109`、截止 `05:50` 的预测成功追加审计，预测 `0.307718`、实际 `0.4025`、绝对误差 `0.094782`、±0.05未命中。该单炉仅用于接口验收，不作为模型效果结论。

证据：`logs/si_v20_shadow_ui_20260808/ui_matrix.json`、`logs/si_v20_shadow_remote_20260808/remote_ui_smoke.json`。


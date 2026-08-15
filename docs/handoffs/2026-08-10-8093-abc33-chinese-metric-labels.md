# 8093 ABC33复核点中文名称统一上线记录

需求编号：`REQ-8093-ABC33-CHINESE-METRIC-LABELS-20260810`

## 结果

8093的33项炉况复核详情现只显示中文点位名称，不再在名称下方显示内部变量键。截图中的`TFT`改为“理论燃烧温度”，`T_blast`改为“热风温度”；同类问题已按33项全量核对修复。

## 全量核对

上线前扫描生产最新33条规则详情：

- 33条详情全部读取成功。
- 共118个唯一复核指标。
- 发现6个未中文化指标，影响7条规则：
  - A2、A5：`TFT`、`T_blast`。
  - A6、B6、B9：`Hopper_weight`、`Hopper_weight_set`。
  - B4：`T_blast`。
  - C10：`P_N2`、`Q_N2`。
- 其余112个唯一指标已使用中文名称。

上线后使用同一审计器再次逐条读取33项详情，结果为：

```text
rule_count=33
detail_error_count=0
unique_metric_count=118
issue_metric_count=0
```

## 实现边界

- 后端补齐6个变量的中文名称和单位。
- 前端以受控中文映射优先，后端中文标签次优；无法得到中文名称时显示“未配置中文名称”，不会把内部键直出给工长。
- 内部变量键只保留在不可见的`data-variable`属性中，供自动审计定位，不作为页面文字显示。
- 未修改ABC33公式、分数、权重、阈值、传感器键或API字段结构。

## 测试

```text
node --check 高炉前端数据/assets/abc-furnace-rules-production.js
pytest tests/test_abc_production_ui.py tests/test_abc_public_review_labels.py -q
```

结果：JavaScript和Python语法通过，合同测试`10 passed`。

## 8093受控部署回执

- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_chinese_metric_labels_20260810_155249`
- `guard_paused=true`
- `guard_restored=true`
- 8093 HTTP：200
- 8093 PID：13064 → 3648
- 8094 PID：2988 → 2988
- 8768 PID：18436 → 18436
- 8770 PID：3732 → 3732
- 11434 PID：5968 → 5968
- 8094页面文件：未改变
- 8093缓存版本：`abc33-20260810-chinese-metric-labels-r1`
- 页面SHA-256：`44A4195A164BF0230A4B46E326DAF5D228CAE7A79908AE05E07E2CE50FA2FEE9`
- 资源SHA-256：`E37CD6A3590DE647E1671FD729E56DB0380EF494EBE3882421D6E3AB25168CAB`
- 后端SHA-256：`C18B16314A399412693A39544B1FDCEFA1809E1E3E8A1BFD73552FD63B96C034`

生产入口：`http://10.30.220.12:8093/?cb=abc33-20260810-chinese-metric-labels-r1#optimization`

浏览器已成功加载新缓存版本；该生产大屏主线程繁忙，自动化深层DOM读取超时。因此最终上线判定采用服务HTTP、33项详情API全量扫描、静态资源合同和守卫部署回执共同完成，不把超时误报为页面失败。

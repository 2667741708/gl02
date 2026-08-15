# 8093 ABC33复核表纵向语义布局上线记录

需求编号：`REQ-8093-ABC33-VERTICAL-METRIC-LAYOUT-20260810`

## 结果

复核详情不再通过增加表格宽度容纳信息。页面允许纵向增长，“实际变化语义”移到每个指标数值行的下一整行并完整换行，不需要拖动横向滚动条才能阅读。

## 布局变化

- 删除表格`min-width:1120px`。
- 删除复核分组内部`max-height:470px`及横向滚动容器。
- 数值信息从9列重组为6列：点位、当前值/时刻、30日基线、15/30/60分钟变化、60分钟波动/历史、60分钟曲线。
- “实际变化语义”单独作为下一行，跨6列显示。
- 详情正文固定`overflow-x:hidden`，只允许纵向滚动。
- 900px以下转为两列信息卡，语义仍独占整行。

以上结构由33项炉况共用，不按规则分别维护，因此A9、B13、C11全部使用相同布局。

## 33项数据完整性

```text
rule_count=33
detail_error_count=0
metric_occurrence_count=473
semantic_count=473
missing_semantic_count=0
duplicate_occurrence_count=0
label_issue_metric_count=0
longest_semantic=A5 / Q_O2 / 128字
```

## 测试与部署

- JavaScript及Python语法通过。
- 专项合同测试：`13 passed`。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_vertical_metric_layout_20260810_164935`
- `guard_paused=true`
- `guard_restored=true`
- 8093 HTTP：200
- 8093 PID：6432 → 19268
- 8094 PID：2988 → 2988
- 8768 PID：18436 → 18436
- 8770 PID：3732 → 3732
- 11434 PID：5968 → 5968
- 8094页面：未改变
- 页面版本：`abc33-20260810-vertical-metric-layout-r1`
- 页面SHA-256：`8CA9139613981F3950C3C3D8ECC50DDA6FC1E619D77B6DAB202E6067C9061064`
- 资源SHA-256：`D9E1BFE17D51848C4532F2C8E71BBA61F7DC56F70D6F1B68CA7FC4AA579265DD`

生产入口：`http://10.30.220.12:8093/?cb=abc33-20260810-vertical-metric-layout-r1#optimization`

浏览器已尝试导航到新缓存版本，但生产大屏主线程繁忙导致交互自动化超时。上线硬门禁已通过HTTP、静态资源结构和33项API全量数据审计；仍需现场浏览器刷新后做一次人工视觉冒烟，重点确认当前实际视口下语义换行和纵向滚动手感。

## 上线后自检

- 可读性：语义从最右列移至独立整行，信息顺序更清晰。
- 性能：DOM行数约增加一倍，但每条规则详情按需加载，未增加接口数据量。
- 风险：超长详情会增加纵向滚动距离；这是用户明确接受的取舍，且优于横向拖动。

# 8093 ABC33复核分组去重上线记录

需求编号：`REQ-8093-ABC33-DISJOINT-REVIEW-GROUPS-20260810`

## 结果

“最重要复核点”已经展示的传感器，不再在下方“其余炉壳温度点位”“其余冷却系统点位”或“其他配套参数”重复显示。截图中的顶温A、B、C、D重复已消除，修复范围覆盖全部33条炉况，而不是只处理当前页面。

## 根因

旧后端先从完整指标集合选出偏离最大的8项作为`main_metrics`，随后又从同一个完整集合构造炉壳、冷却和其他分组。主复核点没有从后续候选中删除，所以每条规则都存在重复。

## 双层修复

1. 后端以`variable_name`作为唯一身份，先生成主复核点，再从剩余指标中构造三个后续分组。
2. 前端按“主复核点→炉壳→冷却→其他”顺序维护`seen`集合；即使浏览器收到旧缓存或异常响应，也不会重复渲染。

四组并集仍等于该规则的完整复核指标集，数据、基线、趋势和语义没有删除，只减少重复展示。

## 33项全量审计

上线前：

```text
rule_count=33
detail_error_count=0
metric_occurrence_count=669
affected_rule_count=33
duplicate_variable_count=39
duplicate_occurrence_count=196
```

上线后：

```text
rule_count=33
detail_error_count=0
metric_occurrence_count=473
affected_rule_count=0
duplicate_variable_count=0
duplicate_occurrence_count=0
label_issue_metric_count=0
```

## 测试与部署回执

- JavaScript及Python语法通过。
- 专项合同测试：`12 passed`。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_disjoint_review_groups_20260810_161857`
- `guard_paused=true`
- `guard_restored=true`
- 8093 HTTP：200
- 8093 PID：3648 → 6432
- 8094 PID：2988 → 2988
- 8768 PID：18436 → 18436
- 8770 PID：3732 → 3732
- 11434 PID：5968 → 5968
- 8094页面：未改变
- 页面版本：`abc33-20260810-disjoint-review-groups-r1`
- 页面SHA-256：`228F83EF7BA72F5606D3E160B4BE3F913084E7CCE394AAC800DA9D4FA978EBDE`
- 前端资源SHA-256：`12EA5D970404BB950FD6DF68B68B2FD310962D9EAF422E2B9A080B317E3D685C`
- 复核后端SHA-256：`31D7E5508B52F59234CA4C96A98772644BD3E83DA61EFAD739AB25971CDC9F1F`

生产入口：`http://10.30.220.12:8093/?cb=abc33-20260810-disjoint-review-groups-r1#optimization`

浏览器成功加载新缓存版本。生产大屏主线程繁忙，自动化深层DOM读取再次超时；因此最终验收以HTTP 200、静态资源标记、33项详情API全量零重复审计及守卫回执为准，不把浏览器自动化超时误判为业务失败。

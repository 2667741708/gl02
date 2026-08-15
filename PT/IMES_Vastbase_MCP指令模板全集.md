# IMES Vastbase MCP 指令模板全集

> - 状态：查询模板参考，不是当前连接状态清单
> - 当前入口：[IMES / Vastbase 交接](imes.md)、[通用 IMES 数据说明](../docs/imes.md)
> - 适用边界：模板必须受当前只读白名单、账号权限、行数上限和时间范围门禁约束。

适用环境：本机 relay 或 220.12 的 `direct_22012`。2026-07-27
起 MCP 同时支持 `operations` 与 `laboratory` 两个命名只读账号；
调用方通过 `account_profile` 选择账号，不传用户名或密码。两个模式均可
读取所选账号实际有 `SELECT` 权限的对象、按具体变量和时间范围查询，也支持
任意单条参数化只读 SQL；所有写入、DDL、事务控制和多语句仍被拒绝。

## 1. 调用前提与规则

- MCP 名称：`imes-22012-readonly-mcp`。
- 工具：`imes_relay_status`、`list_imes_database_profiles`、`list_imes_business_objects`、`search_imes_variables`、`explain_imes_variable`、`resolve_imes_natural_language`、`query_imes_object`、`query_imes_variables`、`query_hot_metal_silicon`、`query_imes_readonly_sql`。
- `query_imes_readonly_sql` 只接受一条 `SELECT` / `WITH` / `SHOW` / `EXPLAIN` / `VALUES` / `TABLE` 查询；末尾单个分号可省略或保留。
- `query_imes_readonly_sql` 使用 `%s` 和 `parameters` 传值；响应默认500、最大5000行，更多数据应分页。
- 账号可见不等于业务上都应使用。查询生产数据时，优先明确账号、对象、日期、2# 条件和所需字段；避免无条件 `SELECT *`。

## 2. 状态与目录

```text
调用 imes_relay_status
```

```text
调用 list_imes_database_profiles
```

```text
调用 list_imes_business_objects，account_profile=operations
```

```text
调用 list_imes_business_objects，account_profile=laboratory
```

自然语言模板：

```text
检查 IMES Vastbase MCP 状态；列出当前数据库账号实际可读的全部对象、字段和日期字段。
```

## 2.1 按具体变量和时间范围查询

```json
{
  "account_profile": "operations",
  "object_name": "public.t_ipes_out_put",
  "variables": ["workdate", "meltno", "ironquan", "workshift"],
  "time_column": "workdate",
  "start_time": "2026-07-25 00:00:00",
  "end_time": "2026-07-27 00:00:00",
  "exact_filters": {"prodcentercode": "2D012"},
  "order_by": "workdate",
  "descending": true,
  "row_limit": 200
}
```

时间窗固定为左闭右开：`start_time <= value < end_time`。

## 2.2 任意参数化只读 SQL

```json
{
  "account_profile": "laboratory",
  "sql": "SELECT sampleno,meltno,tfe,feo,cao,sio2 FROM public.v_qpes_slag_insoection_final WHERE meltno = %s",
  "parameters": ["2#20250126-328"],
  "row_limit": 100
}
```

## 3. 受控对象查询模板

### 3.1 口语化语义调用

你可以直接对代理说：

```text
查一下2号炉昨天每炉出了多少铁。
看看上周2号炉每个炉次的铁水硅。
找出7月1日2号炉的矿批、焦批和每批投料合计。
查询今天2号炉各炉次的开铁口、堵口和出铁持续时间。
告诉我 batch_input 的 value_08 是什么意思。
炉渣 value_03 具体代表什么？如果没有字段字典，不要猜。
```

代理应先调用 `resolve_imes_natural_language`；不确定字段时调用 `search_imes_variables` / `explain_imes_variable`，再调用对象查询、铁水硅专用查询或只读 SQL。相对日期（昨天、上周、最近三天）由调用代理换算为明确的 `YYYY-MM-DD`，MCP 本身不会根据服务器时区猜日期。

语义工具参数模板：

```json
{"question":"查一下2号炉昨天每炉出了多少铁"}
```

```json
{"query":"堵口时间"}
```

```json
{"object_name":"public.inner_batch_insp_bb","field_name":"value_02"}
```

### 3.2 主要变量含义与口语别名

| 对象/变量 | 含义 | 可说的口语 | 可信度 |
| --- | --- | --- | --- |
| `t_ipes_out_put.ironquan` | 铁水量/实际铁量 | 铁量、出铁量、每炉出了多少铁 | 结构已确认 |
| `t_ipes_out_put.grossweigh/tareweigh` | 毛重/皮重 | 总重、空罐重、过磅重量 | 结构已确认 |
| `batch_input.lot/charge` | 料批序号/装料批别 | 第几批、矿批、焦批 | 结构已确认 |
| `batch_input.value_01...value_24` | 1—24号料仓/称量通道投料值 | 8号仓、通道8、第8仓 | 结构已确认；不是元素 |
| `batch_input.value_sum` | 本批投料合计 | 总投料、批次合计 | 结构已确认 |
| `t_ipes_cond.sumbatchstart/end` | 炉次起止投料批次 | 从哪批开始、到哪批结束 | 结构已确认 |
| `t_ipes_cond.opentime/closetime` | 开铁口/堵铁口时间 | 开口、堵口、关口时间 | 结构已确认 |
| `t_ipes_cond.tappingtime` | 出铁持续时间 | 出铁时长 | 结构已确认 |
| `t_ipes_cond.tappingtemp` | 出铁温度 | 铁水温度、出铁温度 | 结构已确认 |
| `t_ipes_cond.slagrate` | 渣比 | 炉渣比、渣比 | 结构已确认 |
| `t_qpes_inner_batch.batchno` | 化验批号 | 检验批号、样品批号 | 结构已确认 |
| `inner_batch_insp_bb.value_01` | 铁水 C | 碳、碳含量 | 已确认 |
| `inner_batch_insp_bb.value_02` | 铁水 Si | 硅、铁水硅、硅含量 | 已确认 |
| `inner_batch_insp_bb.value_03...value_11` | Mn/P/S/Ti/V/Cr/Cu/Ni/As | 锰、磷、硫、钛、钒、铬、铜、镍、砷 | 已确认 |
| `slag_inspection.value_01...value_12` | 炉渣检验编号指标 | 炉渣指标1—12 | 未取得化验室字典，不得猜具体成分 |

### 3.3 原始对象查询

`query_imes_object` 适合按对象和日期取原始行；在 220.12 直连模式，省略 `limit` 即不加行数限制。

```json
{"object_name":"public.t_ipes_out_put","start_date":"2026-07-01","end_date":"2026-07-07"}
```

| 目标 | `object_name` | 常用日期字段 |
| --- | --- | --- |
| 生产实绩 | `public.t_ipes_out_put` | `workdate` |
| 批次投料 | `public.batch_input` | `workdate` |
| 炉次作业/批次范围 | `public.t_ipes_cond` | `workdate` |
| 炉次—化验批号 | `public.t_qpes_inner_batch` | `businessdate` / `judgetime` |
| 铁水化验 | `public.inner_batch_insp_bb` | `judgetime` |
| 炉渣检验 | `public.slag_inspection` | `workdate` |

## 4. 任意只读 SQL 模板

### 4.1 发现表、字段与数据量

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name
```

```sql
SELECT column_name, data_type, ordinal_position
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 't_ipes_out_put'
ORDER BY ordinal_position
```

```sql
SELECT COUNT(*) AS total_rows,
       MIN(workdate) AS earliest_time,
       MAX(workdate) AS latest_time
FROM public.t_ipes_out_put
```

### 4.2 2# 高炉生产实绩

```sql
SELECT workdate, meltno, ironquan, grossweigh, tareweigh,
       workshift, workclass, workstaff, weighttime, outstocktype
FROM public.t_ipes_out_put
WHERE workdate >= DATE '2026-07-01' AND workdate < DATE '2026-07-08'
  AND (prodcentercode = '2D012' OR meltno LIKE '2#%')
ORDER BY workdate, meltno
```

### 4.3 2# 高炉批次投料

```sql
SELECT workdate, lot, charge, value_01, value_02, value_03, value_04,
       value_sum, mining_batch_sum, coke_charge_sum
FROM public.batch_input
WHERE workdate >= DATE '2026-07-01' AND workdate < DATE '2026-07-02'
  AND prodcentercode = '2D012'
ORDER BY lot, charge
```

注意：`value_01...value_24` 是称量/料仓通道投料量，不是原料元素成分。

### 4.4 炉次与投料批次范围

```sql
SELECT workdate, meltno, sumbatchstart, sumbatchend, sumbatch,
       opentime, closetime, tappingtime, ironquan, theoryquan, slagrate
FROM public.t_ipes_cond
WHERE workdate >= DATE '2026-07-01' AND workdate < DATE '2026-07-02'
  AND (prodcentercode = '2D012' OR meltno LIKE '2#%')
ORDER BY workdate, meltno
```

### 4.5 铁水 Si / C / Mn / P / S

优先用专用工具：

```json
{"start_date":"2026-05-01","end_date":"2026-05-31"}
```

调用 `query_hot_metal_silicon`。字段为 `c`、`si`、`mn`、`p`、`s`。

或使用 SQL：

```sql
SELECT q.heatno, q.batchno, q.judgetime,
       b.value_01 AS c, b.value_02 AS si, b.value_03 AS mn,
       b.value_04 AS p, b.value_05 AS s
FROM public.t_qpes_inner_batch q
JOIN public.inner_batch_insp_bb b ON b.batchno = q.batchno
WHERE q.judgetime >= TIMESTAMP '2026-05-01 00:00:00'
  AND q.judgetime < TIMESTAMP '2026-06-01 00:00:00'
  AND q.heatno LIKE '2#%'
ORDER BY q.judgetime, q.heatno
```

### 4.6 炉渣检验

```sql
SELECT workdate, meltno, sampleno, publishtime,
       value_01, value_02, value_03, value_04, value_05, value_06
FROM public.slag_inspection
WHERE workdate >= DATE '2026-07-01' AND workdate < DATE '2026-07-08'
  AND (prodcentercode = '2D012' OR meltno LIKE '2#%')
ORDER BY workdate, meltno, sampleno
```

### 4.7 每日完整性 / 2# 占比

```sql
SELECT SUBSTR(CAST(workdate AS TEXT), 1, 10) AS business_date,
       COUNT(*) AS total_rows,
       SUM(CASE WHEN prodcentercode = '2D012' THEN 1 ELSE 0 END) AS bf2_rows
FROM public.batch_input
WHERE workdate >= DATE '2026-07-01' AND workdate < DATE '2026-07-08'
GROUP BY SUBSTR(CAST(workdate AS TEXT), 1, 10)
ORDER BY business_date
```

## 5. Vastbase → 8093 本地 PostgreSQL 同步口径

目标是 220.12 本机 PostgreSQL 的 `bf_trend`，建议新建 `bf_imes.vastbase_rows`，不要混写 Web 抓取表 `bf_imes.raw_rows`：

| 字段 | 用途 |
| --- | --- |
| `source_object` | Vastbase 表名，例如 `public.t_ipes_out_put` |
| `source_key` | 由对象主业务键/整行哈希生成的稳定幂等键 |
| `business_date` | 对应 `workdate` / `judgetime` 等业务日期 |
| `row_json` | 源记录完整 JSON，保留字段演进能力 |
| `source_updated_at` | 源侧更新时间（有则保存） |
| `synced_at` | 本机同步时间 |

同步流程：从 Vastbase 按对象、业务日期分批 `SELECT` → 生成稳定 `source_key` → 在本机 PostgreSQL 使用 `INSERT ... ON CONFLICT (source_object, source_key) DO UPDATE` 写入 → 写审计日志（窗口、读取数、插入数、更新数、失败原因）。同步程序必须使用 Vastbase 只读连接；写入仅发生在 220.12 本机 PostgreSQL。

建议先用一日 `dry-run` 对比行数，再启用按日补数和增量计划任务。不得把 Vastbase 的账号、密码或 MCP 会话信息写进该文档。

<!-- AUTO:IMES-FULL-VARIABLES:START -->

## 6. 11个真实可读对象、315个实际变量逐项口语调用全集

本节由真实只读目录自动生成。覆盖单位是“对象×字段”：同名字段在不同
对象中分别登记，避免把铁水、炉渣、烧结矿与炼钢变量混用。

固定调用规则：

- 先用 `list_imes_business_objects(account_profile)` 复核实时可读目录；
- 用 `query_imes_variables` 传入下表的实际字段名；
- 时间范围固定为 `[start_time, end_time)`，即左闭右开；
- `operations` 查炉次/投料/实绩/旧化验，`laboratory` 查最终化验视图；
- 表中“待确认/unknown”只表示字段可读，不允许根据名称猜单位、枚举或成分；
- 空值表示未检、未发布、不适用或历史缺失，不能自动当作0。

### 6.1 `public.batch_input`：批次投料

- 账号：`operations`
- 用途：矿批/焦批、1—24号料仓或称量通道及批次合计
- 推荐时间字段：`workdate`
- 推荐主标识：`workdate / lot / charge`
- 典型精确条件：`{"prodcentercode": "2D012"}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "operations",
    "object_name": "public.batch_input",
    "variables": [
      "workdate",
      "lot",
      "charge",
      "prodcentercode"
    ],
    "time_column": "workdate",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {
      "prodcentercode": "2D012"
    },
    "order_by": "workdate",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `prodcentercode` | 生产/加工中心编码 | 中心编码、高炉编码、工序编码、prodcentercode | 查一下2号炉昨天的批次投料的生产/加工中心编码，返回实际字段prodcentercode，并带上workdate、lot。 | `variables=["prodcentercode"]` | structural |
| 2 | `charge` | 装料批别（矿批/焦批） | 矿批、焦批、批别、charge | 查一下2号炉昨天的批次投料的装料批别（矿批/焦批），返回实际字段charge，并带上workdate、lot。 | `variables=["charge"]` | confirmed |
| 3 | `workdate` | 业务时间/生产日期 | 业务时间、生产日期、工作日期、workdate | 查一下2号炉昨天的批次投料的业务时间/生产日期，返回实际字段workdate，并带上workdate、lot。 | `variables=["workdate"]` | confirmed |
| 4 | `remark3` | 备注3 | 第三备注、备注三、remark3 | 查一下2号炉昨天的批次投料的备注3，返回实际字段remark3，并带上workdate、lot。 | `variables=["remark3"]` | structural |
| 5 | `value_01` | 第1号料仓/称量通道投料值 | 1号仓、1号料仓、第1号料仓、通道1、第1仓投料、1号仓投料、value_01 | 查一下2号炉昨天的批次投料的第1号料仓/称量通道投料值，返回实际字段value_01，并带上workdate、lot。 | `variables=["value_01"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 6 | `value_02` | 第2号料仓/称量通道投料值 | 2号仓、2号料仓、第2号料仓、通道2、第2仓投料、2号仓投料、value_02 | 查一下2号炉昨天的批次投料的第2号料仓/称量通道投料值，返回实际字段value_02，并带上workdate、lot。 | `variables=["value_02"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 7 | `workdate2` | 辅助业务时间 | 第二业务时间、辅助时间、workdate2 | 查一下2号炉昨天的批次投料的辅助业务时间，返回实际字段workdate2，并带上workdate、lot。 | `variables=["workdate2"]` | structural；具体口径待MES字典确认 |
| 8 | `lot` | 料批序号/批次标识 | 第几批、料批、批号、lot | 查一下2号炉昨天的批次投料的料批序号/批次标识，返回实际字段lot，并带上workdate、lot。 | `variables=["lot"]` | confirmed |
| 9 | `value_03` | 第3号料仓/称量通道投料值 | 3号仓、3号料仓、第3号料仓、通道3、第3仓投料、3号仓投料、value_03 | 查一下2号炉昨天的批次投料的第3号料仓/称量通道投料值，返回实际字段value_03，并带上workdate、lot。 | `variables=["value_03"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 10 | `value_04` | 第4号料仓/称量通道投料值 | 4号仓、4号料仓、第4号料仓、通道4、第4仓投料、4号仓投料、value_04 | 查一下2号炉昨天的批次投料的第4号料仓/称量通道投料值，返回实际字段value_04，并带上workdate、lot。 | `variables=["value_04"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 11 | `value_05` | 第5号料仓/称量通道投料值 | 5号仓、5号料仓、第5号料仓、通道5、第5仓投料、5号仓投料、value_05 | 查一下2号炉昨天的批次投料的第5号料仓/称量通道投料值，返回实际字段value_05，并带上workdate、lot。 | `variables=["value_05"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 12 | `value_06` | 第6号料仓/称量通道投料值 | 6号仓、6号料仓、第6号料仓、通道6、第6仓投料、6号仓投料、value_06 | 查一下2号炉昨天的批次投料的第6号料仓/称量通道投料值，返回实际字段value_06，并带上workdate、lot。 | `variables=["value_06"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 13 | `value_07` | 第7号料仓/称量通道投料值 | 7号仓、7号料仓、第7号料仓、通道7、第7仓投料、7号仓投料、value_07 | 查一下2号炉昨天的批次投料的第7号料仓/称量通道投料值，返回实际字段value_07，并带上workdate、lot。 | `variables=["value_07"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 14 | `value_08` | 第8号料仓/称量通道投料值 | 8号仓、8号料仓、第8号料仓、通道8、第8仓投料、8号仓投料、value_08 | 查一下2号炉昨天的批次投料的第8号料仓/称量通道投料值，返回实际字段value_08，并带上workdate、lot。 | `variables=["value_08"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 15 | `value_09` | 第9号料仓/称量通道投料值 | 9号仓、9号料仓、第9号料仓、通道9、第9仓投料、9号仓投料、value_09 | 查一下2号炉昨天的批次投料的第9号料仓/称量通道投料值，返回实际字段value_09，并带上workdate、lot。 | `variables=["value_09"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 16 | `value_10` | 第10号料仓/称量通道投料值 | 10号仓、10号料仓、第10号料仓、通道10、第10仓投料、10号仓投料、value_10 | 查一下2号炉昨天的批次投料的第10号料仓/称量通道投料值，返回实际字段value_10，并带上workdate、lot。 | `variables=["value_10"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 17 | `value_11` | 第11号料仓/称量通道投料值 | 11号仓、11号料仓、第11号料仓、通道11、第11仓投料、11号仓投料、value_11 | 查一下2号炉昨天的批次投料的第11号料仓/称量通道投料值，返回实际字段value_11，并带上workdate、lot。 | `variables=["value_11"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 18 | `value_12` | 第12号料仓/称量通道投料值 | 12号仓、12号料仓、第12号料仓、通道12、第12仓投料、12号仓投料、value_12 | 查一下2号炉昨天的批次投料的第12号料仓/称量通道投料值，返回实际字段value_12，并带上workdate、lot。 | `variables=["value_12"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 19 | `value_13` | 第13号料仓/称量通道投料值 | 13号仓、13号料仓、第13号料仓、通道13、第13仓投料、13号仓投料、value_13 | 查一下2号炉昨天的批次投料的第13号料仓/称量通道投料值，返回实际字段value_13，并带上workdate、lot。 | `variables=["value_13"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 20 | `value_14` | 第14号料仓/称量通道投料值 | 14号仓、14号料仓、第14号料仓、通道14、第14仓投料、14号仓投料、value_14 | 查一下2号炉昨天的批次投料的第14号料仓/称量通道投料值，返回实际字段value_14，并带上workdate、lot。 | `variables=["value_14"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 21 | `value_15` | 第15号料仓/称量通道投料值 | 15号仓、15号料仓、第15号料仓、通道15、第15仓投料、15号仓投料、value_15 | 查一下2号炉昨天的批次投料的第15号料仓/称量通道投料值，返回实际字段value_15，并带上workdate、lot。 | `variables=["value_15"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 22 | `value_16` | 第16号料仓/称量通道投料值 | 16号仓、16号料仓、第16号料仓、通道16、第16仓投料、16号仓投料、value_16 | 查一下2号炉昨天的批次投料的第16号料仓/称量通道投料值，返回实际字段value_16，并带上workdate、lot。 | `variables=["value_16"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 23 | `value_17` | 第17号料仓/称量通道投料值 | 17号仓、17号料仓、第17号料仓、通道17、第17仓投料、17号仓投料、value_17 | 查一下2号炉昨天的批次投料的第17号料仓/称量通道投料值，返回实际字段value_17，并带上workdate、lot。 | `variables=["value_17"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 24 | `value_18` | 第18号料仓/称量通道投料值 | 18号仓、18号料仓、第18号料仓、通道18、第18仓投料、18号仓投料、value_18 | 查一下2号炉昨天的批次投料的第18号料仓/称量通道投料值，返回实际字段value_18，并带上workdate、lot。 | `variables=["value_18"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 25 | `value_19` | 第19号料仓/称量通道投料值 | 19号仓、19号料仓、第19号料仓、通道19、第19仓投料、19号仓投料、value_19 | 查一下2号炉昨天的批次投料的第19号料仓/称量通道投料值，返回实际字段value_19，并带上workdate、lot。 | `variables=["value_19"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 26 | `value_20` | 第20号料仓/称量通道投料值 | 20号仓、20号料仓、第20号料仓、通道20、第20仓投料、20号仓投料、value_20 | 查一下2号炉昨天的批次投料的第20号料仓/称量通道投料值，返回实际字段value_20，并带上workdate、lot。 | `variables=["value_20"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 27 | `value_21` | 第21号料仓/称量通道投料值 | 21号仓、21号料仓、第21号料仓、通道21、第21仓投料、21号仓投料、value_21 | 查一下2号炉昨天的批次投料的第21号料仓/称量通道投料值，返回实际字段value_21，并带上workdate、lot。 | `variables=["value_21"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 28 | `value_22` | 第22号料仓/称量通道投料值 | 22号仓、22号料仓、第22号料仓、通道22、第22仓投料、22号仓投料、value_22 | 查一下2号炉昨天的批次投料的第22号料仓/称量通道投料值，返回实际字段value_22，并带上workdate、lot。 | `variables=["value_22"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 29 | `value_23` | 第23号料仓/称量通道投料值 | 23号仓、23号料仓、第23号料仓、通道23、第23仓投料、23号仓投料、value_23 | 查一下2号炉昨天的批次投料的第23号料仓/称量通道投料值，返回实际字段value_23，并带上workdate、lot。 | `variables=["value_23"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 30 | `value_24` | 第24号料仓/称量通道投料值 | 24号仓、24号料仓、第24号料仓、通道24、第24仓投料、24号仓投料、value_24 | 查一下2号炉昨天的批次投料的第24号料仓/称量通道投料值，返回实际字段value_24，并带上workdate、lot。 | `variables=["value_24"]` | structural；是投料量，不是化学元素；物料需关联料仓历史 |
| 31 | `value_sum` | 本批投料合计 | 投料总量、批次合计、value_sum | 查一下2号炉昨天的批次投料的本批投料合计，返回实际字段value_sum，并带上workdate、lot。 | `variables=["value_sum"]` | confirmed |
| 32 | `mining_batch_sum` | 矿批合计 | 矿批量、矿石批量、mining_batch_sum | 查一下2号炉昨天的批次投料的矿批合计，返回实际字段mining_batch_sum，并带上workdate、lot。 | `variables=["mining_batch_sum"]` | confirmed |
| 33 | `coke_charge_sum` | 焦批合计 | 焦批量、焦炭批量、coke_charge_sum | 查一下2号炉昨天的批次投料的焦批合计，返回实际字段coke_charge_sum，并带上workdate、lot。 | `variables=["coke_charge_sum"]` | confirmed |

### 6.2 `public.inner_batch_insp_bb`：铁水旧化验结果

- 账号：`operations`
- 用途：化验批号、取样/判定时间以及C、Si、Mn等元素
- 推荐时间字段：`judgetime`
- 推荐主标识：`batchno / judgetime / publishtime`
- 典型精确条件：`{"prodcentercode": "2"}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "operations",
    "object_name": "public.inner_batch_insp_bb",
    "variables": [
      "batchno",
      "judgetime",
      "publishtime"
    ],
    "time_column": "judgetime",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {
      "prodcentercode": "2"
    },
    "order_by": "judgetime",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `batchno` | 检验批号/试样批号 | 化验批号、检验批号、样品批号、batchno | 查一下2号高炉昨天发布的铁水化验的检验批号/试样批号，返回实际字段batchno，并带上batchno、judgetime。 | `variables=["batchno"]` | confirmed |
| 2 | `judgetime` | 结果判定时间 | 判定时间、审核时间、化验完成时间、judgetime | 查一下2号高炉昨天发布的铁水化验的结果判定时间，返回实际字段judgetime，并带上batchno、judgetime。 | `variables=["judgetime"]` | confirmed |
| 3 | `publishtime` | 结果发布时间 | 发布时间、发布日期、结果发布时刻、publishtime | 查一下2号高炉昨天发布的铁水化验的结果发布时间，返回实际字段publishtime，并带上batchno、judgetime。 | `variables=["publishtime"]` | confirmed |
| 4 | `prodcentercode` | 生产/加工中心编码 | 中心编码、高炉编码、工序编码、prodcentercode | 查一下2号高炉昨天发布的铁水化验的生产/加工中心编码，返回实际字段prodcentercode，并带上batchno、judgetime。 | `variables=["prodcentercode"]` | structural |
| 5 | `inspphyclass` | 检验物理分类/检验类别 | 检验类别、物检分类、inspphyclass | 查一下2号高炉昨天发布的铁水化验的检验物理分类/检验类别，返回实际字段inspphyclass，并带上batchno、judgetime。 | `variables=["inspphyclass"]` | uncertain；正式中文名称待MES字典确认 |
| 6 | `judgeclass` | 判定班组 | 审核班组、判定甲乙丙班、judgeclass | 查一下2号高炉昨天发布的铁水化验的判定班组，返回实际字段judgeclass，并带上batchno、judgetime。 | `variables=["judgeclass"]` | structural |
| 7 | `inspshift` | 检验班次 | 化验班次、inspshift | 查一下2号高炉昨天发布的铁水化验的检验班次，返回实际字段inspshift，并带上batchno、judgetime。 | `variables=["inspshift"]` | structural |
| 8 | `inspstaff` | 检验人员 | 化验人、检验人、inspstaff | 查一下2号高炉昨天发布的铁水化验的检验人员，返回实际字段inspstaff，并带上batchno、judgetime。 | `variables=["inspstaff"]` | structural；人员信息，限制使用 |
| 9 | `takesampletime` | 取样时间 | 采样时间、取铁水样时间、takesampletime | 查一下2号高炉昨天发布的铁水化验的取样时间，返回实际字段takesampletime，并带上batchno、judgetime。 | `variables=["takesampletime"]` | confirmed |
| 10 | `value_01` | 铁水碳C | 碳、C、碳含量、value_01 | 查一下2号高炉昨天发布的铁水化验的铁水碳C，返回实际字段value_01，并带上batchno、judgetime。 | `variables=["value_01"]` | confirmed；通常按质量百分含量 |
| 11 | `value_02` | 铁水硅Si | 硅、Si、硅含量、铁水硅、value_02 | 查一下2号高炉昨天发布的铁水化验的铁水硅Si，返回实际字段value_02，并带上batchno、judgetime。 | `variables=["value_02"]` | confirmed；通常按质量百分含量 |
| 12 | `value_03` | 铁水锰Mn | 锰、Mn、锰含量、value_03 | 查一下2号高炉昨天发布的铁水化验的铁水锰Mn，返回实际字段value_03，并带上batchno、judgetime。 | `variables=["value_03"]` | confirmed；通常按质量百分含量 |
| 13 | `value_04` | 铁水磷P | 磷、P、磷含量、value_04 | 查一下2号高炉昨天发布的铁水化验的铁水磷P，返回实际字段value_04，并带上batchno、judgetime。 | `variables=["value_04"]` | confirmed；通常按质量百分含量 |
| 14 | `value_05` | 铁水硫S | 硫、S、硫含量、value_05 | 查一下2号高炉昨天发布的铁水化验的铁水硫S，返回实际字段value_05，并带上batchno、judgetime。 | `variables=["value_05"]` | confirmed；通常按质量百分含量 |
| 15 | `value_06` | 铁水钛Ti | 钛、Ti、钛含量、value_06 | 查一下2号高炉昨天发布的铁水化验的铁水钛Ti，返回实际字段value_06，并带上batchno、judgetime。 | `variables=["value_06"]` | confirmed；通常按质量百分含量 |
| 16 | `value_08` | 铁水铬Cr | 铬、Cr、铬含量、value_08 | 查一下2号高炉昨天发布的铁水化验的铁水铬Cr，返回实际字段value_08，并带上batchno、judgetime。 | `variables=["value_08"]` | confirmed；通常按质量百分含量 |
| 17 | `value_09` | 铁水铜Cu | 铜、Cu、铜含量、value_09 | 查一下2号高炉昨天发布的铁水化验的铁水铜Cu，返回实际字段value_09，并带上batchno、judgetime。 | `variables=["value_09"]` | confirmed；通常按质量百分含量 |
| 18 | `value_10` | 铁水镍Ni | 镍、Ni、镍含量、value_10 | 查一下2号高炉昨天发布的铁水化验的铁水镍Ni，返回实际字段value_10，并带上batchno、judgetime。 | `variables=["value_10"]` | confirmed；通常按质量百分含量 |
| 19 | `value_07` | 铁水钒V | 钒、V、钒含量、value_07 | 查一下2号高炉昨天发布的铁水化验的铁水钒V，返回实际字段value_07，并带上batchno、judgetime。 | `variables=["value_07"]` | confirmed；通常按质量百分含量 |
| 20 | `value_11` | 铁水砷As | 砷、As、砷含量、value_11 | 查一下2号高炉昨天发布的铁水化验的铁水砷As，返回实际字段value_11，并带上batchno、judgetime。 | `variables=["value_11"]` | confirmed；通常按质量百分含量 |

### 6.3 `public.slag_inspection`：炉渣旧检验

- 账号：`operations`
- 用途：炉次、渣样号以及尚未取得正式编号映射的12个旧指标
- 推荐时间字段：`workdate`
- 推荐主标识：`workdate / meltno / sampleno`
- 典型精确条件：`{"prodcentercode": "2D012"}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "operations",
    "object_name": "public.slag_inspection",
    "variables": [
      "workdate",
      "meltno",
      "sampleno"
    ],
    "time_column": "workdate",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {
      "prodcentercode": "2D012"
    },
    "order_by": "workdate",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `meltno` | 高炉炉次号 | 炉次、炉号、铁次、meltno | 查一下2号炉昨天的旧炉渣检验的高炉炉次号，返回实际字段meltno，并带上workdate、meltno。 | `variables=["meltno"]` | confirmed |
| 2 | `sampleno` | 试样号 | 样品号、试样编号、sampleno | 查一下2号炉昨天的旧炉渣检验的试样号，返回实际字段sampleno，并带上workdate、meltno。 | `variables=["sampleno"]` | confirmed |
| 3 | `prodcentercode` | 生产/加工中心编码 | 中心编码、高炉编码、工序编码、prodcentercode | 查一下2号炉昨天的旧炉渣检验的生产/加工中心编码，返回实际字段prodcentercode，并带上workdate、meltno。 | `variables=["prodcentercode"]` | structural |
| 4 | `workdate` | 业务时间/生产日期 | 业务时间、生产日期、工作日期、workdate | 查一下2号炉昨天的旧炉渣检验的业务时间/生产日期，返回实际字段workdate，并带上workdate、meltno。 | `variables=["workdate"]` | confirmed |
| 5 | `createtime` | 记录创建时间 | 创建时间、录入时间、createtime | 查一下2号炉昨天的旧炉渣检验的记录创建时间，返回实际字段createtime，并带上workdate、meltno。 | `variables=["createtime"]` | structural |
| 6 | `publishtime` | 结果发布时间 | 发布时间、发布日期、结果发布时刻、publishtime | 查一下2号炉昨天的旧炉渣检验的结果发布时间，返回实际字段publishtime，并带上workdate、meltno。 | `variables=["publishtime"]` | confirmed |
| 7 | `value_01` | 旧炉渣检验编号指标1 | 炉渣指标1、value_01 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标1，返回实际字段value_01，并带上workdate、meltno。 | `variables=["value_01"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 8 | `value_02` | 旧炉渣检验编号指标2 | 炉渣指标2、value_02 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标2，返回实际字段value_02，并带上workdate、meltno。 | `variables=["value_02"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 9 | `value_03` | 旧炉渣检验编号指标3 | 炉渣指标3、value_03 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标3，返回实际字段value_03，并带上workdate、meltno。 | `variables=["value_03"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 10 | `value_04` | 旧炉渣检验编号指标4 | 炉渣指标4、value_04 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标4，返回实际字段value_04，并带上workdate、meltno。 | `variables=["value_04"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 11 | `value_05` | 旧炉渣检验编号指标5 | 炉渣指标5、value_05 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标5，返回实际字段value_05，并带上workdate、meltno。 | `variables=["value_05"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 12 | `value_06` | 旧炉渣检验编号指标6 | 炉渣指标6、value_06 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标6，返回实际字段value_06，并带上workdate、meltno。 | `variables=["value_06"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 13 | `value_07` | 旧炉渣检验编号指标7 | 炉渣指标7、value_07 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标7，返回实际字段value_07，并带上workdate、meltno。 | `variables=["value_07"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 14 | `value_08` | 旧炉渣检验编号指标8 | 炉渣指标8、value_08 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标8，返回实际字段value_08，并带上workdate、meltno。 | `variables=["value_08"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 15 | `value_09` | 旧炉渣检验编号指标9 | 炉渣指标9、value_09 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标9，返回实际字段value_09，并带上workdate、meltno。 | `variables=["value_09"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 16 | `value_10` | 旧炉渣检验编号指标10 | 炉渣指标10、value_10 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标10，返回实际字段value_10，并带上workdate、meltno。 | `variables=["value_10"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 17 | `value_11` | 旧炉渣检验编号指标11 | 炉渣指标11、value_11 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标11，返回实际字段value_11，并带上workdate、meltno。 | `variables=["value_11"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |
| 18 | `value_12` | 旧炉渣检验编号指标12 | 炉渣指标12、value_12 | 查一下2号炉昨天的旧炉渣检验的旧炉渣检验编号指标12，返回实际字段value_12，并带上workdate、meltno。 | `variables=["value_12"]` | unknown；缺少旧表编号到化学成分映射，禁止猜测；优先使用命名炉渣视图 |

### 6.4 `public.t_ipes_cond`：炉次作业条件

- 账号：`operations`
- 用途：开堵铁口、出铁时长、批次范围、铁量和渣比
- 推荐时间字段：`workdate`
- 推荐主标识：`workdate / meltno`
- 典型精确条件：`{"prodcentercode": "2D012"}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "operations",
    "object_name": "public.t_ipes_cond",
    "variables": [
      "workdate",
      "meltno",
      "id"
    ],
    "time_column": "workdate",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {
      "prodcentercode": "2D012"
    },
    "order_by": "workdate",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `id` | 内部记录ID | 记录号、内部ID、主键、id | 查一下2号炉昨天的炉次作业的内部记录ID，返回实际字段id，并带上workdate、meltno。 | `variables=["id"]` | structural |
| 2 | `workdate` | 业务时间/生产日期 | 业务时间、生产日期、工作日期、workdate | 查一下2号炉昨天的炉次作业的业务时间/生产日期，返回实际字段workdate，并带上workdate、meltno。 | `variables=["workdate"]` | confirmed |
| 3 | `prodcentercode` | 生产/加工中心编码 | 中心编码、高炉编码、工序编码、prodcentercode | 查一下2号炉昨天的炉次作业的生产/加工中心编码，返回实际字段prodcentercode，并带上workdate、meltno。 | `variables=["prodcentercode"]` | structural |
| 4 | `prodcentername` | 生产/加工中心名称 | 中心名称、高炉名称、工序名称、prodcentername | 查一下2号炉昨天的炉次作业的生产/加工中心名称，返回实际字段prodcentername，并带上workdate、meltno。 | `variables=["prodcentername"]` | structural |
| 5 | `costaccuno` | 成本核算单元编号 | 成本单元、核算单元号、costaccuno | 查一下2号炉昨天的炉次作业的成本核算单元编号，返回实际字段costaccuno，并带上workdate、meltno。 | `variables=["costaccuno"]` | uncertain；按字段名解释，正式字典待确认 |
| 6 | `outputno` | 出铁/产出记录编号 | 产出编号、出铁记录号、outputno | 查一下2号炉昨天的炉次作业的出铁/产出记录编号，返回实际字段outputno，并带上workdate、meltno。 | `variables=["outputno"]` | uncertain；正式字典待确认 |
| 7 | `meltno` | 高炉炉次号 | 炉次、炉号、铁次、meltno | 查一下2号炉昨天的炉次作业的高炉炉次号，返回实际字段meltno，并带上workdate、meltno。 | `variables=["meltno"]` | confirmed |
| 8 | `sumbatchstart` | 炉次起始投料批次 | 起始批次、从哪批开始、sumbatchstart | 查一下2号炉昨天的炉次作业的炉次起始投料批次，返回实际字段sumbatchstart，并带上workdate、meltno。 | `variables=["sumbatchstart"]` | confirmed |
| 9 | `sumbatchend` | 炉次结束投料批次 | 结束批次、到哪批结束、sumbatchend | 查一下2号炉昨天的炉次作业的炉次结束投料批次，返回实际字段sumbatchend，并带上workdate、meltno。 | `variables=["sumbatchend"]` | confirmed |
| 10 | `sumbatch` | 炉次累计批次数 | 批次数、累计料批、sumbatch | 查一下2号炉昨天的炉次作业的炉次累计批次数，返回实际字段sumbatch，并带上workdate、meltno。 | `variables=["sumbatch"]` | structural |
| 11 | `opentime` | 开铁口时间 | 开口时间、开始出铁时间、opentime | 查一下2号炉昨天的炉次作业的开铁口时间，返回实际字段opentime，并带上workdate、meltno。 | `variables=["opentime"]` | confirmed |
| 12 | `closetime` | 堵铁口/出铁结束时间 | 堵口时间、结束出铁时间、closetime | 查一下2号炉昨天的炉次作业的堵铁口/出铁结束时间，返回实际字段closetime，并带上workdate、meltno。 | `variables=["closetime"]` | confirmed |
| 13 | `tappingtime` | 出铁持续时间 | 出铁时长、这一炉出了多久、tappingtime | 查一下2号炉昨天的炉次作业的出铁持续时间，返回实际字段tappingtime，并带上workdate、meltno。 | `variables=["tappingtime"]` | confirmed |
| 14 | `tappingpitch` | 出铁口节距/相关位置量 | 出铁口节距、铁口位置量、tappingpitch | 查一下2号炉昨天的炉次作业的出铁口节距/相关位置量，返回实际字段tappingpitch，并带上workdate、meltno。 | `variables=["tappingpitch"]` | uncertain；字段中文及单位待现场字典确认 |
| 15 | `theorys` | 理论硫S | 理论硫、预计硫、theorys | 查一下2号炉昨天的炉次作业的理论硫S，返回实际字段theorys，并带上workdate、meltno。 | `variables=["theorys"]` | structural |
| 16 | `theorysi` | 理论硅Si | 理论硅、预计硅、theorysi | 查一下2号炉昨天的炉次作业的理论硅Si，返回实际字段theorysi，并带上workdate、meltno。 | `variables=["theorysi"]` | structural |
| 17 | `tappingtemp` | 出铁温度 | 铁水温度、出铁温度、tappingtemp | 查一下2号炉昨天的炉次作业的出铁温度，返回实际字段tappingtemp，并带上workdate、meltno。 | `variables=["tappingtemp"]` | confirmed；通常按℃，正式单位以字典为准 |
| 18 | `isnull` | 源记录空值/完整性标志 | 空值标志、是否缺失、isnull | 查一下2号炉昨天的炉次作业的源记录空值/完整性标志，返回实际字段isnull，并带上workdate、meltno。 | `variables=["isnull"]` | uncertain；业务含义待MES字典确认 |
| 19 | `depth` | 铁口深度 | 泥包深度、铁口深度、depth | 查一下2号炉昨天的炉次作业的铁口深度，返回实际字段depth，并带上workdate、meltno。 | `variables=["depth"]` | structural；单位待确认 |
| 20 | `mudweight` | 堵口泥量/炮泥重量 | 泥量、炮泥重量、mudweight | 查一下2号炉昨天的炉次作业的堵口泥量/炮泥重量，返回实际字段mudweight，并带上workdate、meltno。 | `variables=["mudweight"]` | structural；单位待确认 |
| 21 | `ironquan` | 炉次实际铁量 | 实际铁量、出了多少铁、ironquan | 查一下2号炉昨天的炉次作业的炉次实际铁量，返回实际字段ironquan，并带上workdate、meltno。 | `variables=["ironquan"]` | confirmed；通常按吨 |
| 22 | `theoryquan` | 炉次理论铁量 | 理论铁量、预计产量、theoryquan | 查一下2号炉昨天的炉次作业的炉次理论铁量，返回实际字段theoryquan，并带上workdate、meltno。 | `variables=["theoryquan"]` | confirmed；通常按吨 |
| 23 | `downtime` | 停机/休风相关时长 | 停机时间、休风时长、downtime | 查一下2号炉昨天的炉次作业的停机/休风相关时长，返回实际字段downtime，并带上workdate、meltno。 | `variables=["downtime"]` | uncertain；正式业务口径待确认 |
| 24 | `remark` | 备注 | 说明、备注信息、remark | 查一下2号炉昨天的炉次作业的备注，返回实际字段remark，并带上workdate、meltno。 | `variables=["remark"]` | structural |
| 25 | `remark1` | 备注1 | 第一备注、备注一、remark1 | 查一下2号炉昨天的炉次作业的备注1，返回实际字段remark1，并带上workdate、meltno。 | `variables=["remark1"]` | structural |
| 26 | `remark2` | 备注2 | 第二备注、备注二、remark2 | 查一下2号炉昨天的炉次作业的备注2，返回实际字段remark2，并带上workdate、meltno。 | `variables=["remark2"]` | structural |
| 27 | `remark3` | 备注3 | 第三备注、备注三、remark3 | 查一下2号炉昨天的炉次作业的备注3，返回实际字段remark3，并带上workdate、meltno。 | `variables=["remark3"]` | structural |
| 28 | `remark4` | 备注4 | 第四备注、备注四、remark4 | 查一下2号炉昨天的炉次作业的备注4，返回实际字段remark4，并带上workdate、meltno。 | `variables=["remark4"]` | structural |
| 29 | `creator` | 创建人 | 录入人、创建人员、creator | 查一下2号炉昨天的炉次作业的创建人，返回实际字段creator，并带上workdate、meltno。 | `variables=["creator"]` | structural；人员信息，限制使用 |
| 30 | `creatorid` | 创建人ID | 录入人账号、创建账号、creatorid | 查一下2号炉昨天的炉次作业的创建人ID，返回实际字段creatorid，并带上workdate、meltno。 | `variables=["creatorid"]` | structural；账号信息，限制使用 |
| 31 | `createtime` | 记录创建时间 | 创建时间、录入时间、createtime | 查一下2号炉昨天的炉次作业的记录创建时间，返回实际字段createtime，并带上workdate、meltno。 | `variables=["createtime"]` | structural |
| 32 | `updaterid` | 更新人ID | 修改账号、更新账号、updaterid | 查一下2号炉昨天的炉次作业的更新人ID，返回实际字段updaterid，并带上workdate、meltno。 | `variables=["updaterid"]` | structural；账号信息，限制使用 |
| 33 | `updater` | 更新人 | 修改人、更新人员、updater | 查一下2号炉昨天的炉次作业的更新人，返回实际字段updater，并带上workdate、meltno。 | `variables=["updater"]` | structural；人员信息，限制使用 |
| 34 | `updatetime` | 记录更新时间 | 更新时间、最后修改时间、updatetime | 查一下2号炉昨天的炉次作业的记录更新时间，返回实际字段updatetime，并带上workdate、meltno。 | `variables=["updatetime"]` | structural |
| 35 | `status` | 记录状态 | 状态、有效状态、记录状态、status | 查一下2号炉昨天的炉次作业的记录状态，返回实际字段status，并带上workdate、meltno。 | `variables=["status"]` | structural |
| 36 | `workshift` | 生产班次 | 班次、白班夜班、作业班次、workshift | 查一下2号炉昨天的炉次作业的生产班次，返回实际字段workshift，并带上workdate、meltno。 | `variables=["workshift"]` | structural |
| 37 | `workclass` | 生产班组 | 班组、甲乙丙班、workclass | 查一下2号炉昨天的炉次作业的生产班组，返回实际字段workclass，并带上workdate、meltno。 | `variables=["workclass"]` | structural |
| 38 | `workstaff` | 作业人员 | 操作人、当班人员、workstaff | 查一下2号炉昨天的炉次作业的作业人员，返回实际字段workstaff，并带上workdate、meltno。 | `variables=["workstaff"]` | structural；人员信息，限制使用 |
| 39 | `angle` | 铁口角度 | 铁口角度、出铁口角度、angle | 查一下2号炉昨天的炉次作业的铁口角度，返回实际字段angle，并带上workdate、meltno。 | `variables=["angle"]` | structural；单位待确认 |
| 40 | `clearstatus` | 炉次清账/清除状态 | 清账状态、清除状态、clearstatus | 查一下2号炉昨天的炉次作业的炉次清账/清除状态，返回实际字段clearstatus，并带上workdate、meltno。 | `variables=["clearstatus"]` | uncertain；正式状态枚举待确认 |
| 41 | `meltnoj` | 关联炉次号J字段 | 关联炉次、炉次J、meltnoj | 查一下2号炉昨天的炉次作业的关联炉次号J字段，返回实际字段meltnoj，并带上workdate、meltno。 | `variables=["meltnoj"]` | uncertain；字段用途待MES字典确认 |
| 42 | `changestatus` | 炉次变更状态 | 变更状态、是否改炉次、changestatus | 查一下2号炉昨天的炉次作业的炉次变更状态，返回实际字段changestatus，并带上workdate、meltno。 | `variables=["changestatus"]` | structural |
| 43 | `taskstatus` | 炉次任务状态 | 任务状态、炉次是否完成、taskstatus | 查一下2号炉昨天的炉次作业的炉次任务状态，返回实际字段taskstatus，并带上workdate、meltno。 | `variables=["taskstatus"]` | structural |
| 44 | `ironmaterialbatch` | 铁料批次/铁水物料批次 | 铁料批次、物料批号、ironmaterialbatch | 查一下2号炉昨天的炉次作业的铁料批次/铁水物料批次，返回实际字段ironmaterialbatch，并带上workdate、meltno。 | `variables=["ironmaterialbatch"]` | uncertain；精确谱系含义待确认 |
| 45 | `irondifference` | 实际与理论铁量差值 | 铁量差、产量偏差、irondifference | 查一下2号炉昨天的炉次作业的实际与理论铁量差值，返回实际字段irondifference，并带上workdate、meltno。 | `variables=["irondifference"]` | structural |
| 46 | `irondifference2` | 第二铁量差值口径 | 第二铁量差、铁量差2、irondifference2 | 查一下2号炉昨天的炉次作业的第二铁量差值口径，返回实际字段irondifference2，并带上workdate、meltno。 | `variables=["irondifference2"]` | uncertain；计算公式待确认 |
| 47 | `slagrate` | 渣比 | 炉渣比、每吨铁渣量、slagrate | 查一下2号炉昨天的炉次作业的渣比，返回实际字段slagrate，并带上workdate、meltno。 | `variables=["slagrate"]` | confirmed |
| 48 | `slagloadingtime` | 装渣/渣处理时间 | 装渣时间、渣处理时刻、slagloadingtime | 查一下2号炉昨天的炉次作业的装渣/渣处理时间，返回实际字段slagloadingtime，并带上workdate、meltno。 | `variables=["slagloadingtime"]` | uncertain；正式业务口径待确认 |

### 6.5 `public.t_ipes_out_put`：生产实绩

- 账号：`operations`
- 用途：炉次生产、铁量、称重、铁水罐和出库状态
- 推荐时间字段：`workdate`
- 推荐主标识：`workdate / meltno`
- 典型精确条件：`{"prodcentercode": "2D012"}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "operations",
    "object_name": "public.t_ipes_out_put",
    "variables": [
      "workdate",
      "meltno",
      "id"
    ],
    "time_column": "workdate",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {
      "prodcentercode": "2D012"
    },
    "order_by": "workdate",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `id` | 内部记录ID | 记录号、内部ID、主键、id | 查一下2号炉昨天的生产实绩的内部记录ID，返回实际字段id，并带上workdate、meltno。 | `variables=["id"]` | structural |
| 2 | `workdate` | 业务时间/生产日期 | 业务时间、生产日期、工作日期、workdate | 查一下2号炉昨天的生产实绩的业务时间/生产日期，返回实际字段workdate，并带上workdate、meltno。 | `variables=["workdate"]` | confirmed |
| 3 | `prodcentercode` | 生产/加工中心编码 | 中心编码、高炉编码、工序编码、prodcentercode | 查一下2号炉昨天的生产实绩的生产/加工中心编码，返回实际字段prodcentercode，并带上workdate、meltno。 | `variables=["prodcentercode"]` | structural |
| 4 | `prodcentername` | 生产/加工中心名称 | 中心名称、高炉名称、工序名称、prodcentername | 查一下2号炉昨天的生产实绩的生产/加工中心名称，返回实际字段prodcentername，并带上workdate、meltno。 | `variables=["prodcentername"]` | structural |
| 5 | `materialcode` | 物料编码 | 物料代码、材料编码、materialcode | 查一下2号炉昨天的生产实绩的物料编码，返回实际字段materialcode，并带上workdate、meltno。 | `variables=["materialcode"]` | structural |
| 6 | `materialname` | 物料名称 | 物料、材料名称、materialname | 查一下2号炉昨天的生产实绩的物料名称，返回实际字段materialname，并带上workdate、meltno。 | `variables=["materialname"]` | structural |
| 7 | `meltno` | 高炉炉次号 | 炉次、炉号、铁次、meltno | 查一下2号炉昨天的生产实绩的高炉炉次号，返回实际字段meltno，并带上workdate、meltno。 | `variables=["meltno"]` | confirmed |
| 8 | `heatcode` | 出铁实绩炉位/罐次代码 | 实绩代码、罐次代码、heatcode | 查一下2号炉昨天的生产实绩的出铁实绩炉位/罐次代码，返回实际字段heatcode，并带上workdate、meltno。 | `variables=["heatcode"]` | uncertain；正式字典待确认 |
| 9 | `unitcode` | 计量单位编码 | 单位代码、计量单位编码、unitcode | 查一下2号炉昨天的生产实绩的计量单位编码，返回实际字段unitcode，并带上workdate、meltno。 | `variables=["unitcode"]` | structural |
| 10 | `unitname` | 计量单位名称 | 单位、计量单位、unitname | 查一下2号炉昨天的生产实绩的计量单位名称，返回实际字段unitname，并带上workdate、meltno。 | `variables=["unitname"]` | structural |
| 11 | `ironquan` | 实际铁水量 | 铁量、出铁量、每炉出了多少铁、ironquan | 查一下2号炉昨天的生产实绩的实际铁水量，返回实际字段ironquan，并带上workdate、meltno。 | `variables=["ironquan"]` | confirmed；通常按吨 |
| 12 | `datasour` | 数据来源 | 数据源、来源系统、datasour | 查一下2号炉昨天的生产实绩的数据来源，返回实际字段datasour，并带上workdate、meltno。 | `variables=["datasour"]` | structural |
| 13 | `remark1` | 备注1 | 第一备注、备注一、remark1 | 查一下2号炉昨天的生产实绩的备注1，返回实际字段remark1，并带上workdate、meltno。 | `variables=["remark1"]` | structural |
| 14 | `remark2` | 备注2 | 第二备注、备注二、remark2 | 查一下2号炉昨天的生产实绩的备注2，返回实际字段remark2，并带上workdate、meltno。 | `variables=["remark2"]` | structural |
| 15 | `remark3` | 备注3 | 第三备注、备注三、remark3 | 查一下2号炉昨天的生产实绩的备注3，返回实际字段remark3，并带上workdate、meltno。 | `variables=["remark3"]` | structural |
| 16 | `remark4` | 备注4 | 第四备注、备注四、remark4 | 查一下2号炉昨天的生产实绩的备注4，返回实际字段remark4，并带上workdate、meltno。 | `variables=["remark4"]` | structural |
| 17 | `creator` | 创建人 | 录入人、创建人员、creator | 查一下2号炉昨天的生产实绩的创建人，返回实际字段creator，并带上workdate、meltno。 | `variables=["creator"]` | structural；人员信息，限制使用 |
| 18 | `creatorid` | 创建人ID | 录入人账号、创建账号、creatorid | 查一下2号炉昨天的生产实绩的创建人ID，返回实际字段creatorid，并带上workdate、meltno。 | `variables=["creatorid"]` | structural；账号信息，限制使用 |
| 19 | `createtime` | 记录创建时间 | 创建时间、录入时间、createtime | 查一下2号炉昨天的生产实绩的记录创建时间，返回实际字段createtime，并带上workdate、meltno。 | `variables=["createtime"]` | structural |
| 20 | `updaterid` | 更新人ID | 修改账号、更新账号、updaterid | 查一下2号炉昨天的生产实绩的更新人ID，返回实际字段updaterid，并带上workdate、meltno。 | `variables=["updaterid"]` | structural；账号信息，限制使用 |
| 21 | `updater` | 更新人 | 修改人、更新人员、updater | 查一下2号炉昨天的生产实绩的更新人，返回实际字段updater，并带上workdate、meltno。 | `variables=["updater"]` | structural；人员信息，限制使用 |
| 22 | `updatetime` | 记录更新时间 | 更新时间、最后修改时间、updatetime | 查一下2号炉昨天的生产实绩的记录更新时间，返回实际字段updatetime，并带上workdate、meltno。 | `variables=["updatetime"]` | structural |
| 23 | `status` | 记录状态 | 状态、有效状态、记录状态、status | 查一下2号炉昨天的生产实绩的记录状态，返回实际字段status，并带上workdate、meltno。 | `variables=["status"]` | structural |
| 24 | `grossweigh` | 称重毛重 | 毛重、总重、grossweigh | 查一下2号炉昨天的生产实绩的称重毛重，返回实际字段grossweigh，并带上workdate、meltno。 | `variables=["grossweigh"]` | confirmed |
| 25 | `tareweigh` | 称重皮重 | 皮重、空罐重、tareweigh | 查一下2号炉昨天的生产实绩的称重皮重，返回实际字段tareweigh，并带上workdate、meltno。 | `variables=["tareweigh"]` | confirmed |
| 26 | `workshift` | 生产班次 | 班次、白班夜班、作业班次、workshift | 查一下2号炉昨天的生产实绩的生产班次，返回实际字段workshift，并带上workdate、meltno。 | `variables=["workshift"]` | structural |
| 27 | `workclass` | 生产班组 | 班组、甲乙丙班、workclass | 查一下2号炉昨天的生产实绩的生产班组，返回实际字段workclass，并带上workdate、meltno。 | `variables=["workclass"]` | structural |
| 28 | `workstaff` | 作业人员 | 操作人、当班人员、workstaff | 查一下2号炉昨天的生产实绩的作业人员，返回实际字段workstaff，并带上workdate、meltno。 | `variables=["workstaff"]` | structural；人员信息，限制使用 |
| 29 | `sendstaff` | 发运/送出人员 | 发运人、送出人员、sendstaff | 查一下2号炉昨天的生产实绩的发运/送出人员，返回实际字段sendstaff，并带上workdate、meltno。 | `variables=["sendstaff"]` | structural；人员信息，限制使用 |
| 30 | `senddate` | 发运/送出时间 | 发运时间、送出时间、senddate | 查一下2号炉昨天的生产实绩的发运/送出时间，返回实际字段senddate，并带上workdate、meltno。 | `variables=["senddate"]` | structural |
| 31 | `outstocktype` | 出库类型 | 出库方式、出库类型、outstocktype | 查一下2号炉昨天的生产实绩的出库类型，返回实际字段outstocktype，并带上workdate、meltno。 | `variables=["outstocktype"]` | structural |
| 32 | `status1` | 辅助状态1 | 状态1、第二状态、status1 | 查一下2号炉昨天的生产实绩的辅助状态1，返回实际字段status1，并带上workdate、meltno。 | `variables=["status1"]` | uncertain；状态枚举待确认 |
| 33 | `usestatus` | 使用状态 | 是否使用、使用状态、usestatus | 查一下2号炉昨天的生产实绩的使用状态，返回实际字段usestatus，并带上workdate、meltno。 | `variables=["usestatus"]` | structural |
| 34 | `ladleage` | 铁水罐龄/罐次使用次数 | 罐龄、铁水包龄、ladleage | 查一下2号炉昨天的生产实绩的铁水罐龄/罐次使用次数，返回实际字段ladleage，并带上workdate、meltno。 | `variables=["ladleage"]` | uncertain；正式定义与单位待确认 |
| 35 | `mheatcode` | 关联热次/炉次代码 | 关联炉次代码、M热次代码、mheatcode | 查一下2号炉昨天的生产实绩的关联热次/炉次代码，返回实际字段mheatcode，并带上workdate、meltno。 | `variables=["mheatcode"]` | uncertain；正式字典待确认 |
| 36 | `weightstatus` | 称重状态 | 过磅状态、计量状态、weightstatus | 查一下2号炉昨天的生产实绩的称重状态，返回实际字段weightstatus，并带上workdate、meltno。 | `variables=["weightstatus"]` | structural |
| 37 | `directstatus` | 直送状态 | 是否直送、直送状态、directstatus | 查一下2号炉昨天的生产实绩的直送状态，返回实际字段directstatus，并带上workdate、meltno。 | `variables=["directstatus"]` | structural |
| 38 | `weighttime` | 称重时间 | 过磅时间、计量时间、weighttime | 查一下2号炉昨天的生产实绩的称重时间，返回实际字段weighttime，并带上workdate、meltno。 | `variables=["weighttime"]` | confirmed |
| 39 | `postslag` | 后续渣/带渣记录字段 | 后渣、带渣情况、postslag | 查一下2号炉昨天的生产实绩的后续渣/带渣记录字段，返回实际字段postslag，并带上workdate、meltno。 | `variables=["postslag"]` | uncertain；正式业务含义待确认 |

### 6.6 `public.t_qpes_inner_batch`：炉次化验索引

- 账号：`operations`
- 用途：炉次、化验批号、取样、判定和检验流程状态
- 推荐时间字段：`businessdate`
- 推荐主标识：`businessdate / heatno / batchno`
- 典型精确条件：`{}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "operations",
    "object_name": "public.t_qpes_inner_batch",
    "variables": [
      "businessdate",
      "heatno",
      "batchno",
      "id"
    ],
    "time_column": "businessdate",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {},
    "order_by": "businessdate",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `id` | 内部记录ID | 记录号、内部ID、主键、id | 查一下昨天的铁水化验索引的内部记录ID，返回实际字段id，并带上businessdate、heatno。 | `variables=["id"]` | structural |
| 2 | `batchno` | 检验批号/试样批号 | 化验批号、检验批号、样品批号、batchno | 查一下昨天的铁水化验索引的检验批号/试样批号，返回实际字段batchno，并带上businessdate、heatno。 | `variables=["batchno"]` | confirmed |
| 3 | `businessdate` | 业务日期 | 业务日、生产日期、businessdate | 查一下昨天的铁水化验索引的业务日期，返回实际字段businessdate，并带上businessdate、heatno。 | `variables=["businessdate"]` | confirmed |
| 4 | `prodcentercode` | 生产/加工中心编码 | 中心编码、高炉编码、工序编码、prodcentercode | 查一下昨天的铁水化验索引的生产/加工中心编码，返回实际字段prodcentercode，并带上businessdate、heatno。 | `variables=["prodcentercode"]` | structural |
| 5 | `prodcentername` | 生产/加工中心名称 | 中心名称、高炉名称、工序名称、prodcentername | 查一下昨天的铁水化验索引的生产/加工中心名称，返回实际字段prodcentername，并带上businessdate、heatno。 | `variables=["prodcentername"]` | structural |
| 6 | `sources` | 样品/任务来源 | 检验来源、样品来源、sources | 查一下昨天的铁水化验索引的样品/任务来源，返回实际字段sources，并带上businessdate、heatno。 | `variables=["sources"]` | structural |
| 7 | `materialcode` | 物料编码 | 物料代码、材料编码、materialcode | 查一下昨天的铁水化验索引的物料编码，返回实际字段materialcode，并带上businessdate、heatno。 | `variables=["materialcode"]` | structural |
| 8 | `materialname` | 物料名称 | 物料、材料名称、materialname | 查一下昨天的铁水化验索引的物料名称，返回实际字段materialname，并带上businessdate、heatno。 | `variables=["materialname"]` | structural |
| 9 | `inspplancode` | 检验计划编码 | 检验方案代码、化验计划号、inspplancode | 查一下昨天的铁水化验索引的检验计划编码，返回实际字段inspplancode，并带上businessdate、heatno。 | `variables=["inspplancode"]` | structural |
| 10 | `inspplanname` | 检验计划名称 | 检验方案、化验计划、inspplanname | 查一下昨天的铁水化验索引的检验计划名称，返回实际字段inspplanname，并带上businessdate、heatno。 | `variables=["inspplanname"]` | structural |
| 11 | `takesamplesite` | 取样地点 | 采样位置、取样点、takesamplesite | 查一下昨天的铁水化验索引的取样地点，返回实际字段takesamplesite，并带上businessdate、heatno。 | `variables=["takesamplesite"]` | confirmed |
| 12 | `takesamplestaff` | 取样人员 | 采样人、取样人、takesamplestaff | 查一下昨天的铁水化验索引的取样人员，返回实际字段takesamplestaff，并带上businessdate、heatno。 | `variables=["takesamplestaff"]` | structural；人员信息，限制使用 |
| 13 | `takesampletime` | 取样时间 | 采样时间、取铁水样时间、takesampletime | 查一下昨天的铁水化验索引的取样时间，返回实际字段takesampletime，并带上businessdate、heatno。 | `variables=["takesampletime"]` | confirmed |
| 14 | `takesampleshift` | 取样班次 | 采样班次、取样白夜班、takesampleshift | 查一下昨天的铁水化验索引的取样班次，返回实际字段takesampleshift，并带上businessdate、heatno。 | `variables=["takesampleshift"]` | structural |
| 15 | `takesampleclass` | 取样班组 | 采样班组、取样甲乙丙班、takesampleclass | 查一下昨天的铁水化验索引的取样班组，返回实际字段takesampleclass，并带上businessdate、heatno。 | `variables=["takesampleclass"]` | structural |
| 16 | `judgeresult` | 判定结果 | 化验结论、是否合格、judgeresult | 查一下昨天的铁水化验索引的判定结果，返回实际字段judgeresult，并带上businessdate、heatno。 | `variables=["judgeresult"]` | structural |
| 17 | `judgestaff` | 判定/审核人员 | 审核人、判定人、judgestaff | 查一下昨天的铁水化验索引的判定/审核人员，返回实际字段judgestaff，并带上businessdate、heatno。 | `variables=["judgestaff"]` | structural；人员信息，限制使用 |
| 18 | `judgetime` | 结果判定时间 | 判定时间、审核时间、化验完成时间、judgetime | 查一下昨天的铁水化验索引的结果判定时间，返回实际字段judgetime，并带上businessdate、heatno。 | `variables=["judgetime"]` | confirmed |
| 19 | `judgeshift` | 判定班次 | 审核班次、判定白夜班、judgeshift | 查一下昨天的铁水化验索引的判定班次，返回实际字段judgeshift，并带上businessdate、heatno。 | `variables=["judgeshift"]` | structural |
| 20 | `judgeclass` | 判定班组 | 审核班组、判定甲乙丙班、judgeclass | 查一下昨天的铁水化验索引的判定班组，返回实际字段judgeclass，并带上businessdate、heatno。 | `variables=["judgeclass"]` | structural |
| 21 | `teststatus` | 检验状态 | 化验状态、是否已检、teststatus | 查一下昨天的铁水化验索引的检验状态，返回实际字段teststatus，并带上businessdate、heatno。 | `variables=["teststatus"]` | confirmed |
| 22 | `remark` | 备注 | 说明、备注信息、remark | 查一下昨天的铁水化验索引的备注，返回实际字段remark，并带上businessdate、heatno。 | `variables=["remark"]` | structural |
| 23 | `status` | 记录状态 | 状态、有效状态、记录状态、status | 查一下昨天的铁水化验索引的记录状态，返回实际字段status，并带上businessdate、heatno。 | `variables=["status"]` | structural |
| 24 | `creatorid` | 创建人ID | 录入人账号、创建账号、creatorid | 查一下昨天的铁水化验索引的创建人ID，返回实际字段creatorid，并带上businessdate、heatno。 | `variables=["creatorid"]` | structural；账号信息，限制使用 |
| 25 | `creator` | 创建人 | 录入人、创建人员、creator | 查一下昨天的铁水化验索引的创建人，返回实际字段creator，并带上businessdate、heatno。 | `variables=["creator"]` | structural；人员信息，限制使用 |
| 26 | `createtime` | 记录创建时间 | 创建时间、录入时间、createtime | 查一下昨天的铁水化验索引的记录创建时间，返回实际字段createtime，并带上businessdate、heatno。 | `variables=["createtime"]` | structural |
| 27 | `updaterid` | 更新人ID | 修改账号、更新账号、updaterid | 查一下昨天的铁水化验索引的更新人ID，返回实际字段updaterid，并带上businessdate、heatno。 | `variables=["updaterid"]` | structural；账号信息，限制使用 |
| 28 | `updater` | 更新人 | 修改人、更新人员、updater | 查一下昨天的铁水化验索引的更新人，返回实际字段updater，并带上businessdate、heatno。 | `variables=["updater"]` | structural；人员信息，限制使用 |
| 29 | `updatetime` | 记录更新时间 | 更新时间、最后修改时间、updatetime | 查一下昨天的铁水化验索引的记录更新时间，返回实际字段updatetime，并带上businessdate、heatno。 | `variables=["updatetime"]` | structural |
| 30 | `steelgrade` | 钢种/牌号 | 钢种、牌号、steelgrade | 查一下昨天的铁水化验索引的钢种/牌号，返回实际字段steelgrade，并带上businessdate、heatno。 | `variables=["steelgrade"]` | structural |
| 31 | `heatno` | 对应炉次号 | 炉次、化验对应哪一炉、heatno | 查一下昨天的铁水化验索引的对应炉次号，返回实际字段heatno，并带上businessdate、heatno。 | `variables=["heatno"]` | confirmed |
| 32 | `inspphyclass` | 检验物理分类/检验类别 | 检验类别、物检分类、inspphyclass | 查一下昨天的铁水化验索引的检验物理分类/检验类别，返回实际字段inspphyclass，并带上businessdate、heatno。 | `variables=["inspphyclass"]` | uncertain；正式中文名称待MES字典确认 |
| 33 | `inspstaff` | 检验人员 | 化验人、检验人、inspstaff | 查一下昨天的铁水化验索引的检验人员，返回实际字段inspstaff，并带上businessdate、heatno。 | `variables=["inspstaff"]` | structural；人员信息，限制使用 |
| 34 | `inspshift` | 检验班次 | 化验班次、检验白夜班、inspshift | 查一下昨天的铁水化验索引的检验班次，返回实际字段inspshift，并带上businessdate、heatno。 | `variables=["inspshift"]` | structural |

### 6.7 `public.v_qpes_inner_batch_insp_final_sample`：高炉铁水完整化验视图

- 账号：`laboratory`
- 用途：铁水试样、人员、班次和C/Si/Mn/P/S等最终结果
- 推荐时间字段：`发布时间`
- 推荐主标识：`试样号 / 发布时间 / 发布日期`
- 典型精确条件：`{"高炉": "2"}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "laboratory",
    "object_name": "public.v_qpes_inner_batch_insp_final_sample",
    "variables": [
      "试样号",
      "发布时间",
      "发布日期",
      "id"
    ],
    "time_column": "发布时间",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {
      "高炉": "2"
    },
    "order_by": "发布时间",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `id` | 内部记录ID | 记录号、内部ID、主键、id | 查一下2号高炉昨天的最终铁水化验的内部记录ID，返回实际字段id，并带上试样号、发布时间。 | `variables=["id"]` | structural |
| 2 | `试样号` | 铁水试样/检验批号 | 试样号、化验批号 | 查一下2号高炉昨天的最终铁水化验的铁水试样/检验批号，返回实际字段试样号，并带上试样号、发布时间。 | `variables=["试样号"]` | confirmed |
| 3 | `发布时间` | 结果判定或审核完成时间 | 判定时间、化验完成时间、发布时间 | 查一下2号高炉昨天的最终铁水化验的结果判定或审核完成时间，返回实际字段发布时间，并带上试样号、发布时间。 | `variables=["发布时间"]` | confirmed |
| 4 | `发布日期` | 结果发布日期 | 发布日期、发布业务日 | 查一下2号高炉昨天的最终铁水化验的结果发布日期，返回实际字段发布日期，并带上试样号、发布时间。 | `variables=["发布日期"]` | confirmed |
| 5 | `高炉` | 高炉编号 | 几号高炉、高炉号、高炉 | 查一下2号高炉昨天的最终铁水化验的高炉编号，返回实际字段高炉，并带上试样号、发布时间。 | `variables=["高炉"]` | confirmed |
| 6 | `罐号` | 铁水罐号 | 铁水包号、罐号 | 查一下2号高炉昨天的最终铁水化验的铁水罐号，返回实际字段罐号，并带上试样号、发布时间。 | `variables=["罐号"]` | confirmed |
| 7 | `班次` | 化验判定班组 | 甲乙丙班、判定班次、班次 | 查一下2号高炉昨天的最终铁水化验的化验判定班组，返回实际字段班次，并带上试样号、发布时间。 | `variables=["班次"]` | confirmed |
| 8 | `检验人` | 执行检验人员 | 化验人、检验员、检验人 | 查一下2号高炉昨天的最终铁水化验的执行检验人员，返回实际字段检验人，并带上试样号、发布时间。 | `variables=["检验人"]` | confirmed；人员信息，限制使用 |
| 9 | `审核人` | 审核发布人员 | 审核员、发布人、审核人 | 查一下2号高炉昨天的最终铁水化验的审核发布人员，返回实际字段审核人，并带上试样号、发布时间。 | `variables=["审核人"]` | confirmed；人员信息，限制使用 |
| 10 | `cvalue` | 铁水碳C | 碳、C、碳含量、cvalue | 查一下2号高炉昨天的最终铁水化验的铁水碳C，返回实际字段cvalue，并带上试样号、发布时间。 | `variables=["cvalue"]` | confirmed |
| 11 | `sivalue` | 铁水硅Si | 硅、Si、硅含量、铁水硅、sivalue | 查一下2号高炉昨天的最终铁水化验的铁水硅Si，返回实际字段sivalue，并带上试样号、发布时间。 | `variables=["sivalue"]` | confirmed |
| 12 | `mnvalue` | 铁水锰Mn | 锰、Mn、锰含量、mnvalue | 查一下2号高炉昨天的最终铁水化验的铁水锰Mn，返回实际字段mnvalue，并带上试样号、发布时间。 | `variables=["mnvalue"]` | confirmed |
| 13 | `pvalue` | 铁水磷P | 磷、P、磷含量、pvalue | 查一下2号高炉昨天的最终铁水化验的铁水磷P，返回实际字段pvalue，并带上试样号、发布时间。 | `variables=["pvalue"]` | confirmed |
| 14 | `svalue` | 铁水硫S | 硫、S、硫含量、svalue | 查一下2号高炉昨天的最终铁水化验的铁水硫S，返回实际字段svalue，并带上试样号、发布时间。 | `variables=["svalue"]` | confirmed |
| 15 | `tivalue` | 铁水钛Ti | 钛、Ti、钛含量、tivalue | 查一下2号高炉昨天的最终铁水化验的铁水钛Ti，返回实际字段tivalue，并带上试样号、发布时间。 | `variables=["tivalue"]` | confirmed |
| 16 | `vvalue` | 铁水钒V | 钒、V、钒含量、vvalue | 查一下2号高炉昨天的最终铁水化验的铁水钒V，返回实际字段vvalue，并带上试样号、发布时间。 | `variables=["vvalue"]` | confirmed |
| 17 | `crvalue` | 铁水铬Cr | 铬、Cr、铬含量、crvalue | 查一下2号高炉昨天的最终铁水化验的铁水铬Cr，返回实际字段crvalue，并带上试样号、发布时间。 | `variables=["crvalue"]` | confirmed |
| 18 | `nivalue` | 铁水镍Ni | 镍、Ni、镍含量、nivalue | 查一下2号高炉昨天的最终铁水化验的铁水镍Ni，返回实际字段nivalue，并带上试样号、发布时间。 | `variables=["nivalue"]` | confirmed |
| 19 | `cuvalue` | 铁水铜Cu | 铜、Cu、铜含量、cuvalue | 查一下2号高炉昨天的最终铁水化验的铁水铜Cu，返回实际字段cuvalue，并带上试样号、发布时间。 | `variables=["cuvalue"]` | confirmed |
| 20 | `asvalue` | 铁水砷As | 砷、As、砷含量、asvalue | 查一下2号高炉昨天的最终铁水化验的铁水砷As，返回实际字段asvalue，并带上试样号、发布时间。 | `variables=["asvalue"]` | confirmed；asvalue历史覆盖较低，空值不是0 |

### 6.8 `public.v_qpes_mat_final`：高炉铁水精简化验视图

- 账号：`laboratory`
- 用途：铁水试样及元素结果；与完整铁水视图同源，不能重复累计
- 推荐时间字段：`publishtime`
- 推荐主标识：`batchno / publishtime`
- 典型精确条件：`{"prodcentercode": "2"}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "laboratory",
    "object_name": "public.v_qpes_mat_final",
    "variables": [
      "batchno",
      "publishtime",
      "id"
    ],
    "time_column": "publishtime",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {
      "prodcentercode": "2"
    },
    "order_by": "publishtime",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `id` | 内部记录ID | 记录号、内部ID、主键、id | 查一下2号高炉昨天的精简铁水化验的内部记录ID，返回实际字段id，并带上batchno、publishtime。 | `variables=["id"]` | structural |
| 2 | `batchno` | 检验批号/试样批号 | 化验批号、检验批号、样品批号、batchno | 查一下2号高炉昨天的精简铁水化验的检验批号/试样批号，返回实际字段batchno，并带上batchno、publishtime。 | `variables=["batchno"]` | confirmed |
| 3 | `publishtime` | 结果发布时间 | 发布时间、发布日期、结果发布时刻、publishtime | 查一下2号高炉昨天的精简铁水化验的结果发布时间，返回实际字段publishtime，并带上batchno、publishtime。 | `variables=["publishtime"]` | confirmed |
| 4 | `prodcentercode` | 生产/加工中心编码 | 中心编码、高炉编码、工序编码、prodcentercode | 查一下2号高炉昨天的精简铁水化验的生产/加工中心编码，返回实际字段prodcentercode，并带上batchno、publishtime。 | `variables=["prodcentercode"]` | structural |
| 5 | `thankno` | 铁水罐号 | 罐号、铁水包号、thankno | 查一下2号高炉昨天的精简铁水化验的铁水罐号，返回实际字段thankno，并带上batchno、publishtime。 | `variables=["thankno"]` | confirmed |
| 6 | `cvalue` | 铁水碳C | 碳、C、碳含量、cvalue | 查一下2号高炉昨天的精简铁水化验的铁水碳C，返回实际字段cvalue，并带上batchno、publishtime。 | `variables=["cvalue"]` | confirmed |
| 7 | `sivalue` | 铁水硅Si | 硅、Si、硅含量、铁水硅、sivalue | 查一下2号高炉昨天的精简铁水化验的铁水硅Si，返回实际字段sivalue，并带上batchno、publishtime。 | `variables=["sivalue"]` | confirmed |
| 8 | `mnvalue` | 铁水锰Mn | 锰、Mn、锰含量、mnvalue | 查一下2号高炉昨天的精简铁水化验的铁水锰Mn，返回实际字段mnvalue，并带上batchno、publishtime。 | `variables=["mnvalue"]` | confirmed |
| 9 | `pvalue` | 铁水磷P | 磷、P、磷含量、pvalue | 查一下2号高炉昨天的精简铁水化验的铁水磷P，返回实际字段pvalue，并带上batchno、publishtime。 | `variables=["pvalue"]` | confirmed |
| 10 | `svalue` | 铁水硫S | 硫、S、硫含量、svalue | 查一下2号高炉昨天的精简铁水化验的铁水硫S，返回实际字段svalue，并带上batchno、publishtime。 | `variables=["svalue"]` | confirmed |
| 11 | `tivalue` | 铁水钛Ti | 钛、Ti、钛含量、tivalue | 查一下2号高炉昨天的精简铁水化验的铁水钛Ti，返回实际字段tivalue，并带上batchno、publishtime。 | `variables=["tivalue"]` | confirmed |
| 12 | `vvalue` | 铁水钒V | 钒、V、钒含量、vvalue | 查一下2号高炉昨天的精简铁水化验的铁水钒V，返回实际字段vvalue，并带上batchno、publishtime。 | `variables=["vvalue"]` | confirmed |
| 13 | `crvalue` | 铁水铬Cr | 铬、Cr、铬含量、crvalue | 查一下2号高炉昨天的精简铁水化验的铁水铬Cr，返回实际字段crvalue，并带上batchno、publishtime。 | `variables=["crvalue"]` | confirmed |
| 14 | `nivalue` | 铁水镍Ni | 镍、Ni、镍含量、nivalue | 查一下2号高炉昨天的精简铁水化验的铁水镍Ni，返回实际字段nivalue，并带上batchno、publishtime。 | `variables=["nivalue"]` | confirmed |
| 15 | `cuvalue` | 铁水铜Cu | 铜、Cu、铜含量、cuvalue | 查一下2号高炉昨天的精简铁水化验的铁水铜Cu，返回实际字段cuvalue，并带上batchno、publishtime。 | `variables=["cuvalue"]` | confirmed |
| 16 | `asvalue` | 铁水砷As | 砷、As、砷含量、asvalue | 查一下2号高炉昨天的精简铁水化验的铁水砷As，返回实际字段asvalue，并带上batchno、publishtime。 | `variables=["asvalue"]` | confirmed；asvalue历史覆盖较低，空值不是0 |

### 6.9 `public.v_qpes_sinter_machine_sample_insp_final`：烧结矿最终化验视图

- 账号：`laboratory`
- 用途：烧结机试样流程、TFe、FeO、CaO、SiO2、R2等
- 推荐时间字段：`业务日期`
- 推荐主标识：`试样单号 / 业务日期 / 检验批号`
- 典型精确条件：`{"加工中心编码": "JS2"}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "laboratory",
    "object_name": "public.v_qpes_sinter_machine_sample_insp_final",
    "variables": [
      "试样单号",
      "业务日期",
      "检验批号",
      "试样单id"
    ],
    "time_column": "业务日期",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {
      "加工中心编码": "JS2"
    },
    "order_by": "业务日期",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `试样单id` | 烧结试样单内部ID | 试样记录ID、试样单id | 查一下2号烧结机昨天的烧结矿化验的烧结试样单内部ID，返回实际字段试样单id，并带上试样单号、业务日期。 | `variables=["试样单id"]` | structural |
| 2 | `试样单号` | 烧结试样单编号 | 试样号、烧结样号、试样单号 | 查一下2号烧结机昨天的烧结矿化验的烧结试样单编号，返回实际字段试样单号，并带上试样单号、业务日期。 | `variables=["试样单号"]` | confirmed |
| 3 | `业务日期` | 样品生产业务日 | 生产日期、样品日期、业务日期 | 查一下2号烧结机昨天的烧结矿化验的样品生产业务日，返回实际字段业务日期，并带上试样单号、业务日期。 | `variables=["业务日期"]` | confirmed |
| 4 | `检验批号` | 烧结化验检验批号 | 化验批号、检验批次、检验批号 | 查一下2号烧结机昨天的烧结矿化验的烧结化验检验批号，返回实际字段检验批号，并带上试样单号、业务日期。 | `variables=["检验批号"]` | confirmed |
| 5 | `加工中心编码` | 烧结机/加工中心编码 | 烧结机代码、JS1或JS2、加工中心编码 | 查一下2号烧结机昨天的烧结矿化验的烧结机/加工中心编码，返回实际字段加工中心编码，并带上试样单号、业务日期。 | `variables=["加工中心编码"]` | confirmed |
| 6 | `加工中心名称` | 烧结机名称 | 1号烧结机、2号烧结机、加工中心名称 | 查一下2号烧结机昨天的烧结矿化验的烧结机名称，返回实际字段加工中心名称，并带上试样单号、业务日期。 | `variables=["加工中心名称"]` | confirmed |
| 7 | `制样时间` | 样品制备时间 | 制样时刻、样品制备时间、制样时间 | 查一下2号烧结机昨天的烧结矿化验的样品制备时间，返回实际字段制样时间，并带上试样单号、业务日期。 | `variables=["制样时间"]` | confirmed |
| 8 | `接样人` | 接收样品人员/账号 | 接样人、收样人 | 查一下2号烧结机昨天的烧结矿化验的接收样品人员/账号，返回实际字段接样人，并带上试样单号、业务日期。 | `variables=["接样人"]` | confirmed；人员信息，限制使用 |
| 9 | `接样时间` | 化验室接样时间 | 收样时间、样品到实验室时间、接样时间 | 查一下2号烧结机昨天的烧结矿化验的化验室接样时间，返回实际字段接样时间，并带上试样单号、业务日期。 | `variables=["接样时间"]` | confirmed |
| 10 | `接样班次` | 接样白班/夜班 | 接样班次、白班夜班 | 查一下2号烧结机昨天的烧结矿化验的接样白班/夜班，返回实际字段接样班次，并带上试样单号、业务日期。 | `variables=["接样班次"]` | confirmed |
| 11 | `接样班别` | 接样甲/乙/丙班组 | 接样班组、甲乙丙班、接样班别 | 查一下2号烧结机昨天的烧结矿化验的接样甲/乙/丙班组，返回实际字段接样班别，并带上试样单号、业务日期。 | `variables=["接样班别"]` | confirmed |
| 12 | `发布人` | 化验结果发布人员 | 发布人、结果审核人 | 查一下2号烧结机昨天的烧结矿化验的化验结果发布人员，返回实际字段发布人，并带上试样单号、业务日期。 | `variables=["发布人"]` | confirmed；人员信息，限制使用 |
| 13 | `发布时间` | 化验结果正式发布时间 | 结果发布时间、化验完成时间、发布时间 | 查一下2号烧结机昨天的烧结矿化验的化验结果正式发布时间，返回实际字段发布时间，并带上试样单号、业务日期。 | `variables=["发布时间"]` | confirmed |
| 14 | `tfevalue` | 烧结矿全铁TFe | 全铁、TFe、总铁、tfevalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿全铁TFe，返回实际字段tfevalue，并带上试样单号、业务日期。 | `variables=["tfevalue"]` | confirmed |
| 15 | `caovalue` | 烧结矿氧化钙CaO | 氧化钙、CaO、caovalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿氧化钙CaO，返回实际字段caovalue，并带上试样单号、业务日期。 | `variables=["caovalue"]` | confirmed |
| 16 | `mgovalue` | 烧结矿氧化镁MgO | 氧化镁、MgO、mgovalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿氧化镁MgO，返回实际字段mgovalue，并带上试样单号、业务日期。 | `variables=["mgovalue"]` | confirmed |
| 17 | `sio2value` | 烧结矿二氧化硅SiO2 | 二氧化硅、SiO2、sio2value | 查一下2号烧结机昨天的烧结矿化验的烧结矿二氧化硅SiO2，返回实际字段sio2value，并带上试样单号、业务日期。 | `variables=["sio2value"]` | confirmed |
| 18 | `al2o3value` | 烧结矿三氧化二铝Al2O3 | 三氧化二铝、Al2O3、al2o3value | 查一下2号烧结机昨天的烧结矿化验的烧结矿三氧化二铝Al2O3，返回实际字段al2o3value，并带上试样单号、业务日期。 | `variables=["al2o3value"]` | confirmed |
| 19 | `pvalue` | 烧结矿磷P | 磷、P、pvalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿磷P，返回实际字段pvalue，并带上试样单号、业务日期。 | `variables=["pvalue"]` | confirmed |
| 20 | `tio2value` | 烧结矿二氧化钛TiO2 | 二氧化钛、TiO2、tio2value | 查一下2号烧结机昨天的烧结矿化验的烧结矿二氧化钛TiO2，返回实际字段tio2value，并带上试样单号、业务日期。 | `variables=["tio2value"]` | confirmed |
| 21 | `mnovalue` | 烧结矿氧化锰MnO | 氧化锰、MnO、mnovalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿氧化锰MnO，返回实际字段mnovalue，并带上试样单号、业务日期。 | `variables=["mnovalue"]` | confirmed |
| 22 | `znvalue` | 烧结矿锌Zn | 锌、Zn、znvalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿锌Zn，返回实际字段znvalue，并带上试样单号、业务日期。 | `variables=["znvalue"]` | confirmed |
| 23 | `crvalue` | 烧结矿铬Cr | 铬、Cr、crvalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿铬Cr，返回实际字段crvalue，并带上试样单号、业务日期。 | `variables=["crvalue"]` | confirmed |
| 24 | `r2value` | 烧结矿二元碱度R2 | 碱度、二元碱度、R2、r2value | 查一下2号烧结机昨天的烧结矿化验的烧结矿二元碱度R2，返回实际字段r2value，并带上试样单号、业务日期。 | `variables=["r2value"]` | confirmed |
| 25 | `feovalue` | 烧结矿氧化亚铁FeO | 氧化亚铁、FeO、feovalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿氧化亚铁FeO，返回实际字段feovalue，并带上试样单号、业务日期。 | `variables=["feovalue"]` | confirmed |
| 26 | `svalue` | 烧结矿硫S | 硫、S、svalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿硫S，返回实际字段svalue，并带上试样单号、业务日期。 | `variables=["svalue"]` | confirmed |
| 27 | `mgalvalue` | 烧结矿镁铝比MgO/Al2O3 | 镁铝比、mgalvalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿镁铝比MgO/Al2O3，返回实际字段mgalvalue，并带上试样单号、业务日期。 | `variables=["mgalvalue"]` | confirmed |
| 28 | `alsivalue` | 烧结矿铝硅比Al2O3/SiO2 | 铝硅比、alsivalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿铝硅比Al2O3/SiO2，返回实际字段alsivalue，并带上试样单号、业务日期。 | `variables=["alsivalue"]` | confirmed |
| 29 | `qdvalue` | 烧结矿QD强度类指标 | QD、强度指标、qdvalue | 查一下2号烧结机昨天的烧结矿化验的烧结矿QD强度类指标，返回实际字段qdvalue，并带上试样单号、业务日期。 | `variables=["qdvalue"]` | uncertain；确切试验名、算法和单位待字典确认 |

### 6.10 `public.v_qpes_slag_insoection_final`：高炉炉渣命名化验视图

- 账号：`laboratory`
- 用途：渣样、炉次、命名氧化物和R2/R3/R4
- 推荐时间字段：`publishtime`
- 推荐主标识：`sampleno / meltno / publishtime`
- 典型精确条件：`{"prodcentercode": "JLZ2"}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "laboratory",
    "object_name": "public.v_qpes_slag_insoection_final",
    "variables": [
      "sampleno",
      "meltno",
      "publishtime"
    ],
    "time_column": "publishtime",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {
      "prodcentercode": "JLZ2"
    },
    "order_by": "publishtime",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `sampleno` | 炉渣试样号 | 渣样号、炉渣样品号、sampleno | 查一下2号炉昨天发布的炉渣化验的炉渣试样号，返回实际字段sampleno，并带上sampleno、meltno。 | `variables=["sampleno"]` | confirmed |
| 2 | `meltno` | 对应高炉炉次号 | 炉次、这份渣是哪一炉、meltno | 查一下2号炉昨天发布的炉渣化验的对应高炉炉次号，返回实际字段meltno，并带上sampleno、meltno。 | `variables=["meltno"]` | confirmed |
| 3 | `prodcentercode` | 炉渣加工中心/高炉编码 | JLZ1、JLZ2、炉渣中心编码、prodcentercode | 查一下2号炉昨天发布的炉渣化验的炉渣加工中心/高炉编码，返回实际字段prodcentercode，并带上sampleno、meltno。 | `variables=["prodcentercode"]` | confirmed |
| 4 | `publishtime` | 炉渣化验发布时间 | 渣样发布时间、炉渣结果时间、publishtime | 查一下2号炉昨天发布的炉渣化验的炉渣化验发布时间，返回实际字段publishtime，并带上sampleno、meltno。 | `variables=["publishtime"]` | confirmed |
| 5 | `tfe` | 炉渣全铁TFe | 全铁、渣中TFe、tfe | 查一下2号炉昨天发布的炉渣化验的炉渣全铁TFe，返回实际字段tfe，并带上sampleno、meltno。 | `variables=["tfe"]` | confirmed；历史覆盖较低 |
| 6 | `feo` | 炉渣氧化亚铁FeO | 氧化亚铁、渣中FeO、feo | 查一下2号炉昨天发布的炉渣化验的炉渣氧化亚铁FeO，返回实际字段feo，并带上sampleno、meltno。 | `variables=["feo"]` | confirmed |
| 7 | `cao` | 炉渣氧化钙CaO | 氧化钙、渣中CaO、cao | 查一下2号炉昨天发布的炉渣化验的炉渣氧化钙CaO，返回实际字段cao，并带上sampleno、meltno。 | `variables=["cao"]` | confirmed |
| 8 | `mgo` | 炉渣氧化镁MgO | 氧化镁、渣中MgO、mgo | 查一下2号炉昨天发布的炉渣化验的炉渣氧化镁MgO，返回实际字段mgo，并带上sampleno、meltno。 | `variables=["mgo"]` | confirmed |
| 9 | `sio2` | 炉渣二氧化硅SiO2 | 二氧化硅、渣中SiO2、sio2 | 查一下2号炉昨天发布的炉渣化验的炉渣二氧化硅SiO2，返回实际字段sio2，并带上sampleno、meltno。 | `variables=["sio2"]` | confirmed |
| 10 | `al2o3` | 炉渣三氧化二铝Al2O3 | 三氧化二铝、渣中Al2O3、al2o3 | 查一下2号炉昨天发布的炉渣化验的炉渣三氧化二铝Al2O3，返回实际字段al2o3，并带上sampleno、meltno。 | `variables=["al2o3"]` | confirmed |
| 11 | `tio2` | 炉渣二氧化钛TiO2 | 二氧化钛、渣中TiO2、tio2 | 查一下2号炉昨天发布的炉渣化验的炉渣二氧化钛TiO2，返回实际字段tio2，并带上sampleno、meltno。 | `variables=["tio2"]` | confirmed |
| 12 | `r2` | 炉渣二元碱度R2 | 二元碱度、R2、炉渣碱度、r2 | 查一下2号炉昨天发布的炉渣化验的炉渣二元碱度R2，返回实际字段r2，并带上sampleno、meltno。 | `variables=["r2"]` | confirmed |
| 13 | `r3` | 炉渣三元碱度R3 | 三元碱度、R3、r3 | 查一下2号炉昨天发布的炉渣化验的炉渣三元碱度R3，返回实际字段r3，并带上sampleno、meltno。 | `variables=["r3"]` | structural；正式公式待确认 |
| 14 | `r4` | 炉渣四元碱度R4 | 四元碱度、R4、r4 | 查一下2号炉昨天发布的炉渣化验的炉渣四元碱度R4，返回实际字段r4，并带上sampleno、meltno。 | `variables=["r4"]` | structural；正式公式待确认 |
| 15 | `mgo_al2o3` | 炉渣镁铝比MgO/Al2O3 | 镁铝比、mgo_al2o3 | 查一下2号炉昨天发布的炉渣化验的炉渣镁铝比MgO/Al2O3，返回实际字段mgo_al2o3，并带上sampleno、meltno。 | `variables=["mgo_al2o3"]` | confirmed |
| 16 | `sio2_al2o3` | 炉渣硅铝比SiO2/Al2O3 | 硅铝比、sio2_al2o3 | 查一下2号炉昨天发布的炉渣化验的炉渣硅铝比SiO2/Al2O3，返回实际字段sio2_al2o3，并带上sampleno、meltno。 | `variables=["sio2_al2o3"]` | confirmed；当前核查样本全空 |

### 6.11 `public.v_qpes_steel_final`：炼钢最终化验视图

- 账号：`laboratory`
- 用途：炼钢试样、钢种、工序和合金/残余元素；不是高炉铁水
- 推荐时间字段：`businessdate`
- 推荐主标识：`sampleno / businessdate / furnacenumber`
- 典型精确条件：`{}`

单变量程序调用：把下面示例 `variables` 中最后一个字段替换为本节任意实际字段。

```json
{
  "tool": "query_imes_variables",
  "arguments": {
    "account_profile": "laboratory",
    "object_name": "public.v_qpes_steel_final",
    "variables": [
      "sampleno",
      "businessdate",
      "furnacenumber",
      "id"
    ],
    "time_column": "businessdate",
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-28 00:00:00",
    "exact_filters": {},
    "order_by": "businessdate",
    "descending": true,
    "row_limit": 100
  }
}
```

| 序号 | 实际变量 | 业务解释 | 口语别名 | 可直接对模型说 | MCP变量参数 | 可信度/边界 |
|---:|---|---|---|---|---|---|
| 1 | `id` | 内部记录ID | 记录号、内部ID、主键、id | 查一下昨天的炼钢最终试样的内部记录ID，返回实际字段id，并带上sampleno、businessdate。 | `variables=["id"]` | structural |
| 2 | `sampleno` | 炼钢试样号 | 钢样号、试样号、sampleno | 查一下昨天的炼钢最终试样的炼钢试样号，返回实际字段sampleno，并带上sampleno、businessdate。 | `variables=["sampleno"]` | confirmed |
| 3 | `femdvalue` | 钢样铁Fe | 铁、Fe、femdvalue | 查一下昨天的炼钢最终试样的钢样铁Fe，返回实际字段femdvalue，并带上sampleno、businessdate。 | `variables=["femdvalue"]` | confirmed；部分样品不发布 |
| 4 | `cmdvalue` | 钢样碳C | 碳、C、cmdvalue | 查一下昨天的炼钢最终试样的钢样碳C，返回实际字段cmdvalue，并带上sampleno、businessdate。 | `variables=["cmdvalue"]` | confirmed |
| 5 | `simdvalue` | 钢样硅Si | 硅、Si、simdvalue | 查一下昨天的炼钢最终试样的钢样硅Si，返回实际字段simdvalue，并带上sampleno、businessdate。 | `variables=["simdvalue"]` | confirmed |
| 6 | `mnmdvalue` | 钢样锰Mn | 锰、Mn、mnmdvalue | 查一下昨天的炼钢最终试样的钢样锰Mn，返回实际字段mnmdvalue，并带上sampleno、businessdate。 | `variables=["mnmdvalue"]` | confirmed |
| 7 | `pmdvalue` | 钢样磷P | 磷、P、pmdvalue | 查一下昨天的炼钢最终试样的钢样磷P，返回实际字段pmdvalue，并带上sampleno、businessdate。 | `variables=["pmdvalue"]` | confirmed |
| 8 | `nimdvalue` | 钢样镍Ni | 镍、Ni、nimdvalue | 查一下昨天的炼钢最终试样的钢样镍Ni，返回实际字段nimdvalue，并带上sampleno、businessdate。 | `variables=["nimdvalue"]` | confirmed |
| 9 | `momdvalue` | 钢样钼Mo | 钼、Mo、momdvalue | 查一下昨天的炼钢最终试样的钢样钼Mo，返回实际字段momdvalue，并带上sampleno、businessdate。 | `variables=["momdvalue"]` | confirmed |
| 10 | `cumdvalue` | 钢样铜Cu | 铜、Cu、cumdvalue | 查一下昨天的炼钢最终试样的钢样铜Cu，返回实际字段cumdvalue，并带上sampleno、businessdate。 | `variables=["cumdvalue"]` | confirmed |
| 11 | `almdvalue` | 钢样总铝Al | 总铝、铝、Al、almdvalue | 查一下昨天的炼钢最终试样的钢样总铝Al，返回实际字段almdvalue，并带上sampleno、businessdate。 | `variables=["almdvalue"]` | structural；正式名称待化验室确认 |
| 12 | `alsmdvalue` | 钢样酸溶铝Als | 酸溶铝、Als、alsmdvalue | 查一下昨天的炼钢最终试样的钢样酸溶铝Als，返回实际字段alsmdvalue，并带上sampleno、businessdate。 | `variables=["alsmdvalue"]` | uncertain；口径待化验室确认 |
| 13 | `timdvalue` | 钢样钛Ti | 钛、Ti、timdvalue | 查一下昨天的炼钢最终试样的钢样钛Ti，返回实际字段timdvalue，并带上sampleno、businessdate。 | `variables=["timdvalue"]` | confirmed |
| 14 | `vmdvalue` | 钢样钒V | 钒、V、vmdvalue | 查一下昨天的炼钢最终试样的钢样钒V，返回实际字段vmdvalue，并带上sampleno、businessdate。 | `variables=["vmdvalue"]` | confirmed |
| 15 | `nbmdvalue` | 钢样铌Nb | 铌、Nb、nbmdvalue | 查一下昨天的炼钢最终试样的钢样铌Nb，返回实际字段nbmdvalue，并带上sampleno、businessdate。 | `variables=["nbmdvalue"]` | confirmed |
| 16 | `wmdvalue` | 钢样钨W | 钨、W、wmdvalue | 查一下昨天的炼钢最终试样的钢样钨W，返回实际字段wmdvalue，并带上sampleno、businessdate。 | `variables=["wmdvalue"]` | confirmed |
| 17 | `comdvalue` | 钢样钴Co | 钴、Co、comdvalue | 查一下昨天的炼钢最终试样的钢样钴Co，返回实际字段comdvalue，并带上sampleno、businessdate。 | `variables=["comdvalue"]` | confirmed |
| 18 | `bmdvalue` | 钢样硼B | 硼、B、bmdvalue | 查一下昨天的炼钢最终试样的钢样硼B，返回实际字段bmdvalue，并带上sampleno、businessdate。 | `variables=["bmdvalue"]` | confirmed |
| 19 | `camdvalue` | 钢样钙Ca | 钙、Ca、camdvalue | 查一下昨天的炼钢最终试样的钢样钙Ca，返回实际字段camdvalue，并带上sampleno、businessdate。 | `variables=["camdvalue"]` | confirmed |
| 20 | `sbmdvalue` | 钢样锑Sb | 锑、Sb、sbmdvalue | 查一下昨天的炼钢最终试样的钢样锑Sb，返回实际字段sbmdvalue，并带上sampleno、businessdate。 | `variables=["sbmdvalue"]` | confirmed |
| 21 | `asmdvalue` | 钢样砷As | 砷、As、asmdvalue | 查一下昨天的炼钢最终试样的钢样砷As，返回实际字段asmdvalue，并带上sampleno、businessdate。 | `variables=["asmdvalue"]` | confirmed |
| 22 | `snmdvalue` | 钢样锡Sn | 锡、Sn、snmdvalue | 查一下昨天的炼钢最终试样的钢样锡Sn，返回实际字段snmdvalue，并带上sampleno、businessdate。 | `variables=["snmdvalue"]` | confirmed |
| 23 | `pbmdvalue` | 钢样铅Pb | 铅、Pb、pbmdvalue | 查一下昨天的炼钢最终试样的钢样铅Pb，返回实际字段pbmdvalue，并带上sampleno、businessdate。 | `variables=["pbmdvalue"]` | confirmed |
| 24 | `bimdvalue` | 钢样铋Bi | 铋、Bi、bimdvalue | 查一下昨天的炼钢最终试样的钢样铋Bi，返回实际字段bimdvalue，并带上sampleno、businessdate。 | `variables=["bimdvalue"]` | confirmed |
| 25 | `znmdvalue` | 钢样锌Zn | 锌、Zn、znmdvalue | 查一下昨天的炼钢最终试样的钢样锌Zn，返回实际字段znmdvalue，并带上sampleno、businessdate。 | `variables=["znmdvalue"]` | confirmed |
| 26 | `insptime` | 钢样检验完成时间 | 检验时间、化验完成时间、insptime | 查一下昨天的炼钢最终试样的钢样检验完成时间，返回实际字段insptime，并带上sampleno、businessdate。 | `variables=["insptime"]` | confirmed |
| 27 | `smdvalue` | 钢样硫S | 硫、S、smdvalue | 查一下昨天的炼钢最终试样的钢样硫S，返回实际字段smdvalue，并带上sampleno、businessdate。 | `variables=["smdvalue"]` | confirmed |
| 28 | `crmdvalue` | 钢样铬Cr | 铬、Cr、crmdvalue | 查一下昨天的炼钢最终试样的钢样铬Cr，返回实际字段crmdvalue，并带上sampleno、businessdate。 | `variables=["crmdvalue"]` | confirmed |
| 29 | `alismdvalue` | 钢样不溶铝结果 | 不溶铝、alismdvalue | 查一下昨天的炼钢最终试样的钢样不溶铝结果，返回实际字段alismdvalue，并带上sampleno、businessdate。 | `variables=["alismdvalue"]` | uncertain；由字段与样本关系推断 |
| 30 | `alisinvalue` | 钢样不溶铝高精度结果 | 不溶铝原始值、不溶铝高精度值、alisinvalue | 查一下昨天的炼钢最终试样的钢样不溶铝高精度结果，返回实际字段alisinvalue，并带上sampleno、businessdate。 | `variables=["alisinvalue"]` | uncertain；仪器/计算口径待确认 |
| 31 | `nmdvalue` | 钢样氮N | 氮、N、nmdvalue | 查一下昨天的炼钢最终试样的钢样氮N，返回实际字段nmdvalue，并带上sampleno、businessdate。 | `variables=["nmdvalue"]` | confirmed |
| 32 | `ceq` | 钢样碳当量CEQ | 碳当量、CEQ、ceq | 查一下昨天的炼钢最终试样的钢样碳当量CEQ，返回实际字段ceq，并带上sampleno、businessdate。 | `variables=["ceq"]` | structural；公式可能随钢种标准变化 |
| 33 | `businessdate` | 炼钢生产业务日期 | 生产日期、业务日、businessdate | 查一下昨天的炼钢最终试样的炼钢生产业务日期，返回实际字段businessdate，并带上sampleno、businessdate。 | `variables=["businessdate"]` | confirmed |
| 34 | `steelgrade` | 计划/申报钢种 | 钢种、牌号、steelgrade | 查一下昨天的炼钢最终试样的计划/申报钢种，返回实际字段steelgrade，并带上sampleno、businessdate。 | `variables=["steelgrade"]` | structural |
| 35 | `judgingsteelgrade` | 化验判定钢种 | 判定钢种、最终钢种、judgingsteelgrade | 查一下昨天的炼钢最终试样的化验判定钢种，返回实际字段judgingsteelgrade，并带上sampleno、businessdate。 | `variables=["judgingsteelgrade"]` | structural |
| 36 | `heatno` | 炼钢炉位/工序代码字段 | 炉位代码、工序代码、heatno | 查一下昨天的炼钢最终试样的炼钢炉位/工序代码字段，返回实际字段heatno，并带上sampleno、businessdate。 | `variables=["heatno"]` | uncertain；不是唯一炉号 |
| 37 | `prodcentercode` | 炼钢工序/加工中心编码 | 工序编码、加工中心、prodcentercode | 查一下昨天的炼钢最终试样的炼钢工序/加工中心编码，返回实际字段prodcentercode，并带上sampleno、businessdate。 | `variables=["prodcentercode"]` | structural；精确中文映射待字典确认 |
| 38 | `publishtime` | 炼钢结果发布时间 | 发布时间、结果时间、publishtime | 查一下昨天的炼钢最终试样的炼钢结果发布时间，返回实际字段publishtime，并带上sampleno、businessdate。 | `variables=["publishtime"]` | confirmed |
| 39 | `receivesampleclass` | 炼钢接样班组 | 接样班组、甲乙丙班、receivesampleclass | 查一下昨天的炼钢最终试样的炼钢接样班组，返回实际字段receivesampleclass，并带上sampleno、businessdate。 | `variables=["receivesampleclass"]` | confirmed |
| 40 | `furnacenumber` | 炼钢实际炉号/生产炉次号 | 实际炉号、炼钢炉次、furnacenumber | 查一下昨天的炼钢最终试样的炼钢实际炉号/生产炉次号，返回实际字段furnacenumber，并带上sampleno、businessdate。 | `variables=["furnacenumber"]` | structural；需与生产系统主键对账 |
| 41 | `receivesampletime` | 炼钢接样时间 | 接样时间、样品到达时间、receivesampletime | 查一下昨天的炼钢最终试样的炼钢接样时间，返回实际字段receivesampletime，并带上sampleno、businessdate。 | `variables=["receivesampletime"]` | confirmed |
| 42 | `prodname` | 产品/产线名称代码 | 产品代码、产线代码、prodname | 查一下昨天的炼钢最终试样的产品/产线名称代码，返回实际字段prodname，并带上sampleno、businessdate。 | `variables=["prodname"]` | uncertain；确切中文含义待字典确认 |

## 7. 完整覆盖验收

- 实际可读对象：`11`
- 实际“对象×字段”：`315`
- 已登记业务解释与口语模板：`315`
- 未登记项：`0`
- 机器可读覆盖证据：`logs/imes_mcp_full_variable_coverage_20260727.json`。

<!-- AUTO:IMES-FULL-VARIABLES:END -->

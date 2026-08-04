# 220.12 IMES 跳板转发与 MCP

> 2026-07-20 默认策略：用户本机访问 Vastbase 和 pSpace 均默认经过
> `10.30.220.12` 跳板，并优先使用本页登记的转发脚本、只读脚本和 MCP。
> 本机目标地址偶发可达不构成自动直连授权。只有程序本身运行在 220.12，
> 或用户明确要求专项直连对照时，才允许使用固定目标直连；例外必须记录实际链路。

## 1. 已验证链路

```text
本机 -> SSH 10.30.220.12 -> IMES Web / Vastbase / pSpace
```

2026-07-16 已在 220.12 实测：

| 本机回环端口 | 220.12 目标 | 用途 | 验证 |
| --- | --- | --- | --- |
| `127.0.0.1:15433` | `10.10.181.195:5432` | Vastbase | SSH direct-tcpip 成功 |
| `127.0.0.1:18080` | `10.10.181.209:8080` | IMES Web | 本机经转发 HTTP 200 |
| `127.0.0.1:18889` | `10.22.181.243:8889` | pSpace | SSH direct-tcpip 成功 |

转发器只能绑定回环地址，不能作为局域网代理或生产控制通道。

## 2. 启动与检查

### 2.1 本机一键启动 Vastbase 专用转发

连接 SSLVPN 后，双击 [start_imes_vastbase_relay_local.cmd](../tools/start_imes_vastbase_relay_local.cmd)，或在 PowerShell 中执行：

```powershell
.\tools\start_imes_vastbase_relay_local.cmd
```

该入口只建立：

```text
127.0.0.1:15433 -> SSH 10.30.220.12 -> 10.10.181.195:5432
```

如果当前进程已有 `BF_22012_SSH_PASSWORD`，脚本直接使用；否则安全地提示输入 220.12 SSH 密码，不把密码写入命令行、文档或日志。转发窗口必须保持打开，按 `Ctrl+C` 或关闭窗口即停止。监听地址固定为 `127.0.0.1`，不会向局域网开放数据库端口。

转发建立后，数据库客户端连接参数为：

```text
host=127.0.0.1
port=15433
database=vastbase
user/password=使用已授权的 Vastbase 数据库账号
```

`5432` 是 Vastbase/PostgreSQL 协议端口，普通浏览器不能显示数据库内容。浏览器访问 IMES Web 时应另外启动完整 IMES profile，并打开 Web 转发地址：

```powershell
python .\tools\imes_22012_relay.py --prompt-password --profile imes
```

```text
http://127.0.0.1:18080/imes.web/
```

先检查三个 SSH 通道：

```powershell
python .\tools\imes_22012_relay.py --allow-agents-password --check `
  --status-file .\logs\imes_22012_relay_check.json
```

启动全部转发（前台运行，使用完 `Ctrl+C` 停止）：

```powershell
python .\tools\imes_22012_relay.py --allow-agents-password
```

只启动 IMES Web 与 Vastbase：

```powershell
python .\tools\imes_22012_relay.py --allow-agents-password --profile imes
```

转发运行后：

```powershell
Invoke-WebRequest http://127.0.0.1:18080/imes.web/
python .\tools\export_vastbase_local.py --host 127.0.0.1 --port 15433 --discover `
  --output-dir .\logs\imes_vastbase_catalog_via_22012
```

## 3. Vastbase 权限结果

2026-07-16 通过 220.12 转发发现260个可见对象，其中9个真实可 `SELECT`，MES业务对象6个：

- `public.t_ipes_out_put`：生产实绩；
- `public.batch_input`：批次投料；
- `public.t_ipes_cond`、`public.t_qpes_inner_batch`、`public.inner_batch_insp_bb`：炉次/铁水化验；
- `public.slag_inspection`：炉渣检验。

原料投入、配料方案、料仓和生产计划没有被这个直连账号验证为可读；需要另行申请数据库权限，或改走已授权的 IMES Web 查询接口。

### 3.1 受限样本实际读取复核（2026-07-16）

使用 `2026-05-01` 至 `2026-07-16`、每对象最多 100 行、单条语句 30 秒的只读导出复核。结果文件为 `logs/imes_vastbase_read_validation_20260716/vastbase_discovery_manifest.json`（含字段、行数和文件名，不含凭据）：

| 对象 | `SELECT` 权限 | 此时间窗实际读取行数 | 结论 |
| --- | --- | ---: | --- |
| `public.batch_input` | 是 | 100（达到样本上限） | 批次投料数据实际存在 |
| `public.inner_batch_insp_bb` | 是 | 100（达到样本上限） | 铁水化验数据实际存在；样本的 `value_02` 有实际数值 |
| `public.slag_inspection` | 是 | 100（达到样本上限） | 炉渣检验数据实际存在 |
| `public.t_ipes_cond` | 是 | 100（达到样本上限） | 炉次作业/批次范围数据实际存在 |
| `public.t_ipes_out_put` | 是 | 100（达到样本上限） | 生产实绩数据实际存在 |
| `public.t_qpes_inner_batch` | 是 | 0 | 表可读；本次日期窗内没有返回记录，不能据此判断全库无该类历史数据 |

“100”是保护生产库设置的上限，不是总记录数。若需要完整性审计，应按业务日分段统计，并在数据库低峰期执行。

### 3.2 完整性审计（2026-07-16）

只读聚合工具：[audit_imes_vastbase_completeness.py](../tools/audit_imes_vastbase_completeness.py)。它不会导出业务明细，只对已验证的 6 个 MES 对象执行按业务日 `COUNT(*)`、时间边界和 2# 覆盖率统计；2# 采用 `prodcentercode IN ('2','2D012')` 或炉次号以 `2#` 开头的保守识别规则。

实际审计窗口为 `2026-05-01` 至 `2026-07-16`，结果在 [审计报告](../logs/imes_vastbase_completeness_audit_20260501_20260716_v2/imes_vastbase_completeness_audit.md) 与 [逐日 CSV](../logs/imes_vastbase_completeness_audit_20260501_20260716_v2/imes_vastbase_daily_counts.csv)：

| 对象 | 总行数 | 2# 行数 | 2# 覆盖率 | 有数据天数 |
| --- | ---: | ---: | ---: | ---: |
| `public.batch_input` | 53,007 | 26,230 | 49.48% | 77 |
| `public.inner_batch_insp_bb` | 5,581 | 2,659 | 47.64% | 77 |
| `public.slag_inspection` | 2,167 | 1,043 | 48.13% | 77 |
| `public.t_ipes_cond` | 2,167 | 1,043 | 48.13% | 77 |
| `public.t_ipes_out_put` | 7,931 | 3,889 | 49.04% | 77 |
| `public.t_qpes_inner_batch` | 0 | 0 | 不适用 | 0 |

命令如下；每条 SQL 受 `--statement-timeout-ms` 限制，若发生超时，JSON 报告会记录失败对象，绝不能把失败当作 0 行：

```powershell
python .\tools\audit_imes_vastbase_completeness.py `
  --host 127.0.0.1 --port 15433 `
  --start-date 2026-05-01 --end-date 2026-07-16 `
  --statement-timeout-ms 60000 `
  --output-dir .\logs\imes_vastbase_completeness_audit_20260501_20260716
```

### 3.3 统计口径与六个对象查询指南

完整性审计的三项数值不是同一概念：

| 名称 | 计算方式 | 本次报告中的含义 |
| --- | --- | --- |
| 总行数 | 某对象在审计窗口中所有产线/高炉的记录数 | 例如 `batch_input=53,007` 是 77 天内 1#、2#等全部符合日期条件的投料批次记录，不是仅 2# |
| 2# 行数 | `prodcentercode IN ('2','2D012')` **或** `meltno/heatno LIKE '2#%'` 的记录数 | 例如 `batch_input=26,230` 是其中被保守识别为 2# 高炉的数据 |
| 2# 覆盖率 | `2# 行数 / 总行数 × 100%` | `26,230 / 53,007 × 100% = 49.48%`；它说明该表约一半记录属于 2#，**不是**数据缺失率、不是成功率，也不是“2# 数据只覆盖 49.48% 的日期” |

本次六个有数据对象均有 77 个有数据日，表示从 5 月 1 日到 7 月 16 日每天至少有一条记录；是否每个班次、每炉次都齐全，需在逐日 CSV 之外再按班次/炉次做专门稽核。

数据库手动查询前，先启动转发器并连接 `127.0.0.1:15433/vastbase`。以下 SQL 都是只读示例，日期范围采用左闭右开，避免遗漏当天含时分秒的记录；`2#` 条件按每张表实际可用字段选择。

| 对象 | 可查询的数据 | 2# 识别与常用关联 |
| --- | --- | --- |
| `public.batch_input` | 每批的矿批/焦批、料仓通道 `value_01...value_24`、总量 `value_sum`、矿/焦汇总 | `prodcentercode='2D012'`；以 `workdate`、`lot`、`charge` 与炉次表的批次范围关联 |
| `public.t_ipes_cond` | 炉次作业时间、出铁、批次起止、实际/理论铁量、渣比、班次 | `prodcentercode='2D012'` 或 `meltno LIKE '2#%'`；主键线索为 `meltno`、`sumbatchstart/sumbatchend/sumbatch` |
| `public.t_ipes_out_put` | 生产实绩、炉次、铁量、毛/皮重、班次、出库/计量状态 | `prodcentercode='2D012'` 或 `meltno LIKE '2#%'`；以 `meltno` 对齐炉次作业表 |
| `public.t_qpes_inner_batch` | 炉次与化验批号、取样/判定状态、采样时间 | `prodcentercode='2D012'` 或 `heatno LIKE '2#%'`；用 `heatno -> batchno` 衔接化验值 |
| `public.inner_batch_insp_bb` | 化验批号、判定/发布时间、元素值 `value_01...value_11`；已确认 `value_02=Si` | `prodcentercode='2'`；用 `batchno` 与 `t_qpes_inner_batch.batchno` 衔接炉次 |
| `public.slag_inspection` | 炉渣炉次、试样、工作/发布时间、`value_01...value_12` 化验值 | `prodcentercode='2D012'` 或 `meltno LIKE '2#%'`；用 `meltno` 对齐炉次作业/实绩 |

常用只读查询示例：

```sql
-- 1) 2# 高炉某天的炉次作业与批次范围
SELECT workdate, meltno, sumbatchstart, sumbatchend, sumbatch,
       opentime, closetime, tappingtime, ironquan, theoryquan, slagrate, workshift
FROM public.t_ipes_cond
WHERE workdate >= DATE '2026-07-01' AND workdate < DATE '2026-07-02'
  AND (prodcentercode = '2D012' OR meltno LIKE '2#%')
ORDER BY workdate, meltno;

-- 2) 2# 高炉同天的批次投料量（不是原料化学成分）
SELECT workdate, lot, charge, value_01, value_02, value_03, value_04,
       value_sum, mining_batch_sum, coke_charge_sum
FROM public.batch_input
WHERE workdate >= DATE '2026-07-01' AND workdate < DATE '2026-07-02'
  AND prodcentercode = '2D012'
ORDER BY workdate, lot, charge;

-- 3) 已发布的 2# 铁水 Si：先由炉次找化验批号，再取 value_02
SELECT q.heatno, q.businessdate, q.batchno, b.judgetime, b.publishtime,
       b.value_01 AS c, b.value_02 AS si, b.value_03 AS mn,
       b.value_04 AS p, b.value_05 AS s
FROM public.t_qpes_inner_batch q
JOIN public.inner_batch_insp_bb b ON b.batchno = q.batchno
WHERE q.businessdate >= DATE '2026-07-01' AND q.businessdate < DATE '2026-07-02'
  AND (q.prodcentercode = '2D012' OR q.heatno LIKE '2#%')
ORDER BY q.businessdate, q.heatno, b.judgetime;

-- 4) 2# 炉渣检验
SELECT workdate, meltno, sampleno, publishtime,
       value_01, value_02, value_03, value_04, value_05
FROM public.slag_inspection
WHERE workdate >= DATE '2026-07-01' AND workdate < DATE '2026-07-02'
  AND (prodcentercode = '2D012' OR meltno LIKE '2#%')
ORDER BY workdate, meltno, sampleno;
```

`t_qpes_inner_batch` 在本次 77 天窗口没有记录，故示例 3 的关联 SQL 已提供但需要在它实际有数据的日期执行；不能因当前窗口为 0 行而将化验数据误判为不存在。MCP 可安全查询受限对象和铁水 Si；需要上述跨表关联时，使用受控数据库客户端并保持只读事务。

## 4. IMES Relay MCP

服务入口：[imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)。它使用 stdio，不监听 HTTP 端口。启动前必须先启动 Vastbase 转发。

```powershell
$env:IMES_RELAY_DB_HOST = '127.0.0.1'
$env:IMES_RELAY_DB_PORT = '15433'
python .\高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py
```

工具契约：

| 工具 | 能力 | 强制边界 |
| --- | --- | --- |
| `imes_relay_status` | 读取本机回环端口和数据库身份 | 不返回密码或 SSH 信息 |
| `list_imes_database_profiles` | 返回 `operations/laboratory` 两个账号用途与配置状态 | 不返回密码 |
| `list_imes_business_objects` | 按 `account_profile` 返回该账号实际可读对象与字段 | 默认发现 `public` schema |
| `query_imes_object` | 指定账号、对象并按业务日查询 | 本机兼容旧93天/500行接口 |
| `query_imes_variables` | 指定账号、对象、列、时间字段、左闭右开时间窗和精确条件 | 列名和条件字段必须属于已发现对象 |
| `query_hot_metal_silicon` | 查询2#炉次/批次化验及 Si | 只读、最多93天、500行 |
| `search_imes_variables` | 按中文含义、口语别名或字段名检索变量 | 返回含义、单位、可信度和注意事项 |
| `explain_imes_variable` | 解释指定对象字段 | 未确认的炉渣编号指标明确标为 unknown，不猜成分 |
| `resolve_imes_natural_language` | 将口语问题解析为对象、字段、2#过滤和推荐工具 | 相对日期由调用方换算成明确日期 |
| `query_imes_readonly_sql` | 按账号执行带 `%s` 参数的任意单条只读 SQL | 本机 relay 与220.12 direct均可用；禁止写入、DDL、事务控制和多语句；单次响应默认500、最大5000行 |

### 4.1 220.12 / 8093 项目内运行

220.12 已能直接访问 Vastbase，因此同步到 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW` 的 MCP 不需要再 SSH 回跳到自己。远端启动入口为 `高炉前端数据\智能助手\mcp\run_imes_mcp_22012.cmd`：它显式设为 `IMES_MCP_CONNECTION_MODE=direct_22012`，只允许固定的 `10.10.181.195:5432` 目标，使用 stdio，不新开 HTTP 监听端口。

2026-07-27 MCP 已升级为两个命名只读账号：`operations` 与
`laboratory`。本机 relay 和 220.12 direct 均可通过
`query_imes_readonly_sql` 查询所选账号有权读取的任意数据，也可通过
`query_imes_variables` 安全构造列与时间范围查询。结构化对象目录不再使用
业务类别白名单，而是列出账号在 `IMES_MCP_DISCOVERY_SCHEMAS`（默认
`public`）中实际具有 `SELECT` 的全部对象。仍保留数据库
`SET TRANSACTION READ ONLY`、单语句校验、参数化查询、响应行数上限以及
对写入/DDL/事务控制的拒绝。

2026-07-27 本机语义层已由“主要变量子集”升级为机器可读的完整目录
[imes_full_variable_catalog.json](../高炉前端数据/智能助手/mcp/imes_full_variable_catalog.json)：
覆盖两个账号当前真实可读的11个对象、315个“对象×字段”。每项登记实际
字段名、业务解释、口语别名、可信度/边界、账号、时间字段、主标识、
可直接提问的句子和推荐工具。`search_imes_variables`、
`explain_imes_variable`和`resolve_imes_natural_language`均加载同一目录；
具体变量默认推荐`query_imes_variables`并返回账号、对象、字段和时间字段。
料仓编号使用数字边界匹配，避免“24号料仓”误命中“4号料仓”。无法从现有
证据确认的旧炉渣编号指标仍标为`unknown`，不会猜成分。2026-07-16
远端旧版冒烟中，“查一下2号炉昨天每炉出了多少铁”已解析为
`public.t_ipes_out_put.ironquan`；完整逐变量口语模板见
[PT/IMES Vastbase MCP 指令模板全集](../PT/IMES_Vastbase_MCP指令模板全集.md)。

2026-07-16 已同步下列文件到该远端项目：`高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py`、`高炉前端数据\智能助手\mcp\run_imes_mcp_22012.cmd`、`tools\export_vastbase_local.py`。远端冒烟脚本以 `direct_22012` 模式成功发现可读对象，并从 `public.t_ipes_out_put` 实际读取数据和执行只读聚合；未启动常驻 MCP 进程，因为 stdio MCP 应由其调用方按需启动。

2026-07-27 多账号增强已在本机完成并通过真实数据库与stdio契约冒烟，但
当日向220.12同步时新建SSH连接持续在22端口超时，因此远端项目文件尚未
替换，不能把本次表述为220.12已部署。恢复SSLVPN/SSH后，先运行
`tools/remote_probe_22012_imes_multi_mcp.ps1` 确认远端根目录、旧文件、
Python和本机凭据文件，再上传本机MCP文件、保留旧文件备份并执行远端
`py_compile`和两个账号只读冒烟。

MCP 查询样例已经实测返回炉次 `2#20260508-120` 的铁水 `Si=0.27`。

## 5. 安全与恢复

- 凭据由 `BF_22012_SSH_PASSWORD` 和数据库环境变量/项目批准的历史本机特例提供，绝不写入新文档、MCP响应或日志。
- 转发进程断开时，MCP 返回“relay unavailable”；不能自动改为公网或直接生产网访问。
- 关闭转发使用前台 `Ctrl+C`；若以后台进程启动，按 PID 精确停止，不要使用模糊进程匹配。
- pSpace 原始 TCP 转发只解决网络路径；读取 pSpace 数据仍优先复用现有 SDK/MCP 的只读调用和业务账号，不把 Windows/SSH账号当 pSpace 账号。

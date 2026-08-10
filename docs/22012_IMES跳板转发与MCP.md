# 220.12 IMES 跳板转发与 MCP

## 0. 2026-08-05：220.12 VPN 直达入口已经上线

用户已明确把目标拓扑调整为“VPN 客户端只访问 220.12，再由 220.12 转发到数据源”，
而不是每次在客户端启动 SSH 回环转发器。当前入口如下：

| VPN 客户端入口 | 220.12 转发目标 | 协议与用途 |
| --- | --- | --- |
| `http://10.30.220.12:18080/` | `10.10.181.209:8080` | Nginx 根地址跳转到 `/imes.web/`，用于 IMES Web 登录 |
| `10.30.220.12:15433` | `10.10.181.195:5432` | Vastbase/PostgreSQL 协议，只能由数据库驱动和只读账号使用 |
| `10.30.220.12:18889` | `10.22.181.243:8889` | pSpace TCP 协议，只能由既有 SDK/MCP 与业务账号使用 |

18080 原有 `g13.html` 没有删除，仍可直接访问
`http://10.30.220.12:18080/g13.html`。Nginx 配置使用标记
`OPS-22012-IMES-WEB-PROXY-20260805`；15433/18889 使用 Windows
`portproxy`。三个入站规则只允许部署时核实的 VPN 客户端地址
`10.30.200.18`，不得改成任意来源。

部署入口为 [受控部署器](../tools/remote_deploy_22012_direct_source_relays.ps1)，
配置补丁为 [Nginx补丁器](../tools/patch_22012_nginx_imes_web.py)，只读复核为
[直接转发探针](../tools/remote_probe_22012_direct_relays.ps1)。部署会备份 Nginx、
portproxy 和受保护端口 PID；失败自动回滚，只重载 Nginx，不停止
8093/8768/8094/8770。

2026-08-05 实际验收：IMES Web 返回 `HTTP 200 text/html;charset=UTF-8`；用户在
浏览器提交验证码后，220.12 Nginx 日志确认登录成功并访问
`/imes.web/mes/desktop.do`、`/imes.web/mes/main.do`、炉次化验、生产实绩和炉渣检验
业务接口，相关请求均通过 `10.30.220.12:18080` 返回。15433 不仅 TCP 成功，还完成
Vastbase 认证和 `BEGIN READ ONLY` 验收，服务端身份为
`10.10.181.195:5432/vastbase`、`transaction_read_only=on`；18889 也已通过现有 pSpace
SDK/业务账号读取真实静压力点，质量为 `Good`。部署结果证明 8093/8768/8094/8770 PID
前后完全一致。备份与结果位于远端
`logs\deploy_backups\22012_direct_source_relays_20260805_151949`。

本页后续“本机回环转发”章节继续保留，作为兼容和应急方案；它不再代表唯一的
VPN 访问方式。

### 0.1 2026-08-07：冀南新区高炉作业日志的报表源站核验

使用授权 Web 账号登录 IMES 后，菜单“报表管理 → 冀南高炉报表 → 冀南新区高炉作业日志”
本身可见，说明菜单权限正常；但浏览器点击后加载的是独立报表地址
`http://10.10.181.205:8080/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht`，
不是 `/imes.web/` 下的 IMES 请求。

2026-08-07 从 220.12 本机核验：

- `10.30.220.12 -> 10.10.181.205:8080` TCP 连接成功；
- 同一报表 URL 从 220.12 直接请求返回 `HTTP 200 OK`，响应约 631 KB，页面标题为
  `Raqsoft Fill Report`；
- 220.12 的 18080 Nginx 仅配置 `location ^~ /imes.web/` 转发到
  `10.10.181.209:8080`，其余 `/demo/...` 路径落到本地静态根目录；
- 因此 `http://10.30.220.12:18080/demo/reportJsp/showInput.jsp?...` 当前返回
  `HTTP 404`，而从本机浏览器直接访问 `10.10.181.205:8080` 会因 VPN/路由不可达而超时。

结论：报表源站和数据页面在 220.12 网络侧是可用的，原失败点是“报表源站没有纳入
220.12 的 Web 转发”，不是 IMES 账号权限或报表页面本身无数据。现已新增独立受控端口
`18084` 转发到 `10.10.181.205:8080`，并对 HTML 中的绝对源站 URL 做同端口重写。本机浏览器
可使用：

```text
http://10.30.220.12:18084/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht
```

注意：`18081` 是其他既有转发/服务端口，不承载该 Raqsoft 报表；访问
`18081/demo/reportJsp/showInput.jsp?...` 会返回 404。该报表必须使用 `18084`，不要把
18081 当作报表入口。

部署标记为 `OPS-22012-IMES-REPORT-PROXY-20260808`，部署脚本为
`tools/remote_deploy_22012_imes_report_proxy.ps1`，未改变 8093/8768/8094/8770 PID。
该端口只允许已核实的 VPN 客户端地址访问；18080 原有 IMES Web 转发保持不变。

### 0.2 2026-08-08：2# 高炉报表数据落库

报表不是普通 IMES `*Data.do` JSON 接口，程序入口为
`数据库同步和存取/sync_bf2_operation_log_report.py`，解析器为
`数据库同步和存取/src/imes_report_client.py`。它按报表日期读取全部返回网格，保留每个单元格的
`raw_value/display_text/col_no`，并写入 220.12 PostgreSQL `bf_trend.bf_imes`：

- 数据集：`bf2_operation_log_report`；统一明细：`bf_imes.raw_rows`；宽表：`bf_imes.imes_bf2_operation_log_report`；视图：`bf_imes.v_bf2_operation_log_report`。
- D 列登记为 `report_batch_count`（批数），M 列登记为 `report_fuel_ratio`（按 Raqsoft 页面公式重算）；`material_rate` 为空并返回 `semantic_unconfirmed`，不把批数冒充料速。
- 2026-02-09 至 2026-08-08 已回填 180 天、4320 行、180 个业务日；最近日期 24 行，重复 `(workdate, report_row_number)` 键 0。
- 计划任务 `IMESBF2OperationLogReport5m` 已在 220.12 注册，当前 `LastTaskResult=0`，每 5 分钟只同步当天报表并幂等更新。
- 采集清单已更新为 `数据库同步和存取/config/IMES可读数据清单.tsv`，数据字典和用法同步见 `数据库同步和存取/IMES只读采集说明.md`。

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

如果希望 Web 与 Vastbase 同时可用，推荐使用项目内的组合入口
[start_imes_web_vastbase_relay_local.cmd](../tools/start_imes_web_vastbase_relay_local.cmd)，
或直接运行：

```powershell
python .\tools\imes_22012_relay.py --prompt-password --profile imes
```

组合 profile 固定建立两个本机回环端口：

```text
127.0.0.1:15433 -> 220.12 -> 10.10.181.195:5432 (Vastbase)
127.0.0.1:18080 -> 220.12 -> 10.10.181.209:8080 (IMES Web)
```

此前 GUI 的问题是把 `--profile all` 与单个 `--forward imes_web:...` 同时传给转发器。
转发器约定是显式 `--forward` 会替换 profile 默认列表，因此 GUI 实际只启动了 Web，
没有启动 Vastbase。现已修复 [imes_web_launcher.py](../tools/imes_web_launcher.py)：
改用 `--profile imes`，并在显示“运行中”前同时检查 Web HTTP 与 Vastbase TCP；
GUI 的“打开 IMES 页面”仍只打开 Web 地址，不会把数据库协议误当作浏览器页面。

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

### 2.2 SSLVPN 与 220.12 跳板关系

SSLVPN 只表示本机可能获得到生产网段的路由；是否能直接访问
`10.10.181.195:5432` 仍取决于 VPN 路由、ACL、防火墙和 Vastbase 监听策略。
当前项目已验证、可复现且默认采用的链路是“本机 → 220.12 → Vastbase”，不是把
SSLVPN 视为自动直连授权。本机专项探针曾返回 Windows `10013`/连接超时，故目前
不能宣称直连已打通，也不会在 MCP 失败时静默切换直连。若以后要启用直连，必须单独
完成 TCP、账号、`current_user=lg_fq`、`current_database=vastbase` 和只读事务验收，
并另行记录链路；在此之前请使用 `127.0.0.1:15433`。

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

本机 MCP Host 的扩展 Web 服务入口为
[imes_web_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_web_mcp_server.py)。它同样
使用 stdio，服务 ID 为 `imes-web-readonly`，只调用 IMES Web 白名单接口；默认地址是
`http://127.0.0.1:18080/imes.web/`。验证码登录需要进程环境中的
`IMES_WEB_CAPTCHA` 或受控 `IMES_WEB_SESSION_COOKIE`，不共享浏览器 Cookie；缺少凭据时
返回 `IMES_WEB_CAPTCHA_REQUIRED`，不会伪造查询结果。三服务注册表及按需路由见
[mcp/README.md](../高炉前端数据/智能助手/mcp/README.md#本机三服务-mcp-注册表扩展-imes-web)。

### 4.1 2026-08-05 炉次化验可见性核查

用户截图证明 IMES Web 页面已经读取到 2026-08-05 的炉次化验索引：最新显示到
`2#20260805-069`，`069`～`066` 暂无元素值，`2#20260805-065` 已有
`C=4.99、Si=0.23、Mn=0.22、P=0.157、S=0.04`。因此“Web 有数据”事实成立。

MCP 未返回该数据有两个独立原因：

1. **Web 会话隔离**：浏览器页面持有自己的 `JSESSIONID`，不会自动提供给 stdio
   MCP。`imes-web-readonly` 没有验证码或受控 `IMES_WEB_SESSION_COOKIE` 时会返回
   `IMES_WEB_CAPTCHA_REQUIRED`，不会读取浏览器 Cookie。
2. **当前/上一炉排序错误**：远端只读复核已经证明 `operations` profile 的
   `gl2#dmx` 可以读取 `2#20260805-065` 的 3 条正式化验记录（Si 为
   `0.20、0.25、0.24`，均值 `0.23%`）。真正的问题是旧查询先把
   `closetime IS NULL` 的历史 `2#20240805-056` 排到最前，复合工具随后查询
   `055`，所以返回 `NO_SI_SAMPLES`。现在已改为先按正式 `meltno/opentime` 最新排序，
   再判断活动状态；化验账号默认保持已实测可读的 `operations`，并支持显式配置。

另外，问题“当前/上一炉铁水 Si”只会查询当前时点的最近两炉。截图中最近炉次是
`069`、`068`，两炉元素值都是横杠；它不会自动跳过空值去寻找 `065`。要查 `065`，
必须使用正式炉次号 `2#20260805-065`，并走已验证的 operations 化验查询或 Web `heat_lab`。

本机核查时 `127.0.0.1:15433` 与 `127.0.0.1:18080` 当前未监听，因此尚未进行新的
在线查询；截图是此前已登录 Web 会话的有效证据。Web MCP 仍需要受控验证码或
`IMES_WEB_SESSION_COOKIE`，不能自动读取浏览器 `JSESSIONID`；但这与 Vastbase
operations 化验查询是两条独立链路，不能把 Web 会话缺失解释成数据库无数据。

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

### 2026-08-05：8093 生产四服务目录已同步

此前“220.12 文件尚未替换”的 2026-07-27 状态已经结束。2026-08-05 已通过
受控部署把 8093 的生产 MCP 注册表扩为 `gl02-data`、`gl02-extended`、
`imes-readonly`、`imes-web-readonly`，同步 315 项 MES 字段目录和当前炉次 72 小时
新鲜度修复。生产数据库 MCP 使用 `direct_22012` 访问厂内 Vastbase，不依赖客户端
SSH 回环或本机 `15433`。

真实自动路由验收返回当前炉次 `2#20260805-072`、上一炉次 `071`、上一炉 3 个
Si 试样平均 `0.273%`；炉身温度自动路由返回 `T_body_L13_C=89.37`，时间
`2026-08-05 22:06:00`。本次只重启 8093，8768/8094/8770 PID 未变化。部署备份、
哈希、回滚和验证命令见
[生产同步交接](handoffs/2026-08-05-22012-imes-mcp-production-sync.md)。

Web 适配器仍遵守登录边界：没有有效验证码/会话时必须明确返回需要登录，不能因为
数据库 MCP 已通过就宣称 IMES Web 登录态也已通过。

## 5. 安全与恢复

- 凭据由 `BF_22012_SSH_PASSWORD` 和数据库环境变量/项目批准的历史本机特例提供，绝不写入新文档、MCP响应或日志。
- 转发进程断开时，MCP 返回“relay unavailable”；不能自动改为公网或直接生产网访问。
- 关闭转发使用前台 `Ctrl+C`；若以后台进程启动，按 PID 精确停止，不要使用模糊进程匹配。
- pSpace 原始 TCP 转发只解决网络路径；读取 pSpace 数据仍优先复用现有 SDK/MCP 的只读调用和业务账号，不把 Windows/SSH账号当 pSpace 账号。

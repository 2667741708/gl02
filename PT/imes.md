# IMES / Vastbase 交接说明

更新时间：2026-08-05

## 当前结论

- IMES Web：`http://10.10.181.209:8080/imes.web/`，账号 `2gldmx`。
- 2026-08-05 起，VPN 客户端优先直接打开 `http://10.30.220.12:18080/`；220.12
  会转发到 IMES Web。Vastbase 使用 `10.30.220.12:15433`，pSpace 使用
  `10.30.220.12:18889`。这三个入口只对核实的 VPN 客户端放行；旧本机
  `127.0.0.1` SSH 回环脚本继续作为应急兼容入口，不再是默认的唯一方式。
- 口令由用户授权保存在 Git 忽略的本机专用配置 `PT/imes_web.local.env`；使用时只通过当前进程环境变量注入，不复制到普通文档、脚本、前端、日志或接口响应。
- 登录接口为 `POST /imes.web/login.do`，成功后进入 `/imes.web/mes/desktop.do`，会话使用 `JSESSIONID`；登录页有 4 位数字验证码。2026-07-15 已实际登录成功；2026-08-05 又通过 `10.30.220.12:18080` 完成验证码登录，并访问炉次化验、生产实绩和炉渣检验真实业务页，代理日志均为 HTTP 200。
- Vastbase 正式库目标为 `10.10.181.195:5432/vastbase`，业务只读角色为 `lg_fq`。完整凭据只保存在 Git 忽略的 `PT/imes_vastbase.local.env`，不在本说明重复记录。
- 该账号可见 10 个业务菜单，覆盖料仓、变料、生产计划、配料、原料投入、批次投料、生产实绩、炉次化验和炉渣检验；已验证 12 个白名单查询数据集。
- 截图显示目标业务画面为“23488高炉炉身中部静压力检测”，包含 `PE424022A` 至 `PE424022F` 等压力测点；当前账号的 10 个菜单没有该入口，需另提供实际页面 URL 或现场网络取证。

## 程序入口

- [IMES Web 只读导出](../tools/export_imes_web_readonly.py)：用 `IMES_WEB_USER/IMES_WEB_PASSWORD/IMES_WEB_CAPTCHA` 登录，只调用已核实查询接口；支持 `--list-datasets`、`--all-datasets`、任意支持日期范围、批次业务日自动逐日展开、分页、JSON Lines 和 manifest。12 个数据集完整说明见 [MES 数据集说明](../docs/mes数据集.md)。
- [IMES Web 本地 GUI 启动器](../tools/imes_web_launcher.py)：点击“启动转发”后建立仅绑定 `127.0.0.1:15433`（Vastbase）和 `127.0.0.1:18080`（IMES Web）的 220.12 跳板，再点击“打开 IMES 页面”访问 `http://127.0.0.1:18080/imes.web/`；SSH 密码只从当前进程环境变量或 GUI 临时输入读取，不写入文件、命令行、日志或页面。GUI 会同时检查 Web HTTP 与 Vastbase TCP，关闭窗口会停止本次转发。Windows 可直接双击 [start_imes_web_gui.cmd](../tools/start_imes_web_gui.cmd)；无 GUI 时使用 [start_imes_web_vastbase_relay_local.cmd](../tools/start_imes_web_vastbase_relay_local.cmd)。
- [本机 MCP 注册表与 Web 适配器](../高炉前端数据/智能助手/backend/mcp_host/server_registry.json)：统一加载 `gl02-data`、`imes-readonly`、`imes-web-readonly` 三个只读服务，共 35 个 Host 可见工具；Web 查询仅走白名单接口，验证码/受控会话缺失时明确返回 `IMES_WEB_CAPTCHA_REQUIRED`。
- [安全版 Vastbase 直连导出](../tools/export_vastbase_direct.py)：使用 `IMES_DB_*` 环境变量，当前覆盖生产实绩、炉次条件、铁水元素和炉渣检验。
- [历史本机特例导出](../tools/export_vastbase_local.py)：按用户明确授权保留历史凭据硬编码，不得把该模式扩散到新脚本或文档。
- [IMES 镜像表导出](../tools/export_imes_to_excel.py)：从 `bf_imes.raw_rows` 展开导出，不使用 Web 账号。
- [连接前置检查](../tools/check_vastbase.ps1)：只显示环境变量是否设置和 TCP 是否可达，不显示口令。

完整的数据路径、验证命令、源码边界和待办见 [docs/imes.md](../docs/imes.md)。

## 一期 MES 正式库 Vastbase 连接方式（2026-07-16）

本机默认连接策略已于 2026-07-20 收紧：Vastbase 查询默认先启动 220.12
回环转发，再使用 `-Relay` 加载 `127.0.0.1:15433`，并通过只读脚本或
IMES MCP 的 `relay` 模式查询。pSpace 查询同样默认由 220.12 本机
PythonSDK/MCP 完成，或使用 `127.0.0.1:18889` 回环转发；不得因目标地址
临时可达而静默改成本机直连。

### 连接参数与账号边界

| 项目 | 配置 | 说明 |
| --- | --- | --- |
| Navicat 连接名 | `一期MES正式库` | 仅是本机连接显示名 |
| 直连主机 | `10.10.181.195` | 需要当前网络/VPN具备 `10.10.181.*` 路由 |
| 直连端口 | `5432` | Vastbase PostgreSQL 兼容端口 |
| 初始数据库 | `vastbase` | 登录时的数据库名 |
| 截图所示管理账号 | `vbadmin` | 高权限运维账号，不用于日常查询、前端、MCP 或自动值守 |
| 业务只读角色 | `lg_fq` | 首字符是小写字母 `l`；本机专用配置已保存该角色，历史只读登录证据见下文 |
| 完整本机凭据 | `PT/imes_vastbase.local.env` | 用户明确授权本机保存；已由根目录 `.gitignore` 排除，不得提交或外发 |

业务只读口令已按用户明确授权保存到本机专用配置 `PT/imes_vastbase.local.env`，但不重复写入本说明、`AGENTS.md`、脚本或日志。该配置不得提交 Git 或对外发送。截图字体容易把 `lg_fq` 的小写字母 `l` 误读成数字 `1`；本机配置已按合法角色名 `lg_fq` 保存。新建业务账号和授权仍应由数据库管理员按最小权限原则执行，本项目不会自动执行 `CREATE ROLE` 或 `GRANT`。

### 2026-08-05 凭据与连通性复核

- 用户提供的业务只读口令与本机受控配置 `PT/imes_vastbase.local.env` 中的 `IMES_DB_PASSWORD` 完全匹配；本说明不记录口令明文。
- 目标合同为 `host=10.10.181.195`、`port=5432`、`database=vastbase`、`user=lg_fq`。因此“账号是 `lg_fq`、端口是 `5432`”可以确认。
- 当前工作区的受限网络探针返回 Windows `10013`/连接超时，未能在本轮再次取得服务器端 `current_user`；不能把本轮结果表述为新的在线认证验收。此前 2026-07-16 只读证据已确认 `current_user=lg_fq`、会话只读且授权视图可查询。
- 恢复 VPN/路由后，使用下方 `psql` 只读验证命令重新执行；只要返回 `current_user=lg_fq`、`current_database=vastbase` 和 `transaction_read_only=on`，即可完成本次在线复核。

### 2026-08-05 化验账号与当前炉次选择修复

- 远端只读复核已经证明 `operations/gl2#dmx` 可以读取 `2#20260805-065` 的 3 条正式铁水化验，Si 为 `0.20、0.25、0.24`，算术平均为 `0.23%`；此前把 `operations` 判定为错误账号是不准确的。
- 本机 MCP 的统一受控账号仍由 `PT/imes_vastbase.local.env` 的 `IMES_DB_USER/IMES_DB_PASSWORD` 提供，默认同时覆盖 `operations` 和 `laboratory`；只有完成独立授权后才通过 `IMES_OPS_DB_*` 或 `IMES_LAB_DB_*` 显式覆盖，模型不得自行猜测账号。
- 化验工具默认 `IMES_CHEMISTRY_ACCOUNT_PROFILE=operations`，精确查询必须传正式 MES `meltno`，例如 `2#20260805-065`。当前/上一炉工具已改为按 `COALESCE(opentime, workdate) DESC, meltno DESC` 选择，再单独判断活动状态；超过 72 小时的未关口历史记录只标记为 `latest_known`，不会抢占当前炉次。
- 该修复不改变 Vastbase 数据、不把缺失 Si 填成 0；`NO_SI_SAMPLES` 仅表示被选中的正式炉次没有已发布的有效 Si 样本。Web MCP 的验证码/会话 Cookie 仍需受控注入，不能自动读取浏览器会话。

### 方式一：Navicat 直接连接

在“常规”页填写：

```text
连接名=一期MES正式库
主机=10.10.181.195
端口=5432
初始数据库=vastbase
用户名=<获批账号；管理维护才使用 vbadmin>
密码=<从本机密码管理器输入，不保存到仓库>
```

先点“测试连接”。若 TCP 不通，先检查 VPN 路由；不要反复尝试不同账号或密码。若只需要查数，优先使用已授予 `CONNECT`、目标 schema `USAGE` 和目标表 `SELECT` 的只读账号。

### 方式二：本机经 220.12 回环转发连接

本机没有 `10.10.181.*` 路由时，在项目根目录以前台方式启动转发：

```powershell
python .\tools\imes_22012_relay.py --allow-agents-password --profile imes
```

只需要 Vastbase 数据库端口时，可直接运行一键入口：

```powershell
.\tools\start_imes_vastbase_relay_local.cmd
```

它只建立 `127.0.0.1:15433 -> 220.12 -> 10.10.181.195:5432`，窗口保持打开期间有效。`15433` 应由 Navicat、DBeaver、psql 或 Python 数据库驱动连接；浏览器不能直接打开 Vastbase 数据库协议。

转发存活期间，Navicat 改填：

```text
连接名=一期MES正式库（220.12转发）
主机=127.0.0.1
端口=15433
初始数据库=vastbase
用户名=<获批账号>
密码=<从本机密码管理器输入>
```

这里的 `127.0.0.1:15433` 只监听本机回环，链路为 `本机 -> 10.30.220.12 -> 10.10.181.195:5432`。使用完在转发器窗口按 `Ctrl+C` 停止；不得改成 `0.0.0.0` 或开放防火墙入站端口。完整转发说明见 [220.12 IMES 跳板转发与 MCP](../docs/22012_IMES跳板转发与MCP.md)。

### PowerShell 临时环境变量

直接连接时，在项目根目录点源加载本机配置，使变量保留在当前 PowerShell：

```powershell
. .\PT\load_imes_vastbase_local.ps1
python .\tools\export_vastbase_local.py --host $env:IMES_DB_HOST --port ([int]$env:IMES_DB_PORT) --tcp-check
```

经 220.12 转发时使用 `-Relay`，加载器只在当前进程内把目标覆盖为回环地址，不改动配置文件：

```powershell
. .\PT\load_imes_vastbase_local.ps1 -Relay
python .\tools\export_vastbase_local.py --host $env:IMES_DB_HOST --port ([int]$env:IMES_DB_PORT) --tcp-check
```

`--tcp-check` 只验证网络端口，不代表账号认证、角色存在或 `SELECT` 权限已经通过。获批做只读登录验证时，再使用现有安全客户端和有界查询；不得用管理账号直接跑全库发现或无限制导出。完成后清理当前终端凭据：

```powershell
Remove-Item Env:IMES_DB_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:IMES_DB_USER -ErrorAction SilentlyContinue
```

本机配置文件包含真实凭据；查看、复制或备份它都按敏感数据处理。若密码变更，只修改 `PT/imes_vastbase.local.env` 中的 `IMES_DB_PASSWORD`，不要把新密码同步到普通 Markdown 文档。

本配置的长期安全边界同步记录在 [数据库账号配置说明](../docs/数据库账号配置说明.md#一期-mes-正式库-vastbase)。

## `lg_fq` 已授权查询视图（2026-07-16 实测，2026-08-05 仍为当前合同）

2026-07-16 15:08 使用本机专用凭据直连 `10.10.181.195:5432/vastbase`，数据库实际返回 `current_user=lg_fq`、`transaction_read_only=on`。下列五个对象均为 `public` schema 下的视图，五个视图全部存在且 `has_table_privilege(..., 'SELECT')=true`，因此可以明确使用该账号读取对应数据：

| 授权视图 | 可读取的数据 | 实测行数 | 实测时间覆盖 |
| --- | --- | ---: | --- |
| `public.v_qpes_inner_batch_insp_final_sample` | 高炉铁水试样、罐号、班次、检验/审核人与 C、Si、Mn、P、S、Ti、V、Cr、Ni、Cu、As | 49,356 | `2024-08-19 10:34:16` 至 `2026-07-16 14:59:28` |
| `public.v_qpes_mat_final` | 上述铁水化验源的精简字段投影；不是原料化学成分表 | 49,356 | `2024-08-19` 至 `2026-07-16` |
| `public.v_qpes_sinter_machine_sample_insp_final` | 1、2号烧结机试样、制样/接样/发布流程及烧结矿成分、碱度、比值和 QD 指标 | 10,179 | `2025-04-21` 至 `2026-07-16 14:43:56` |
| `public.v_qpes_slag_insoection_final` | 1、2号高炉炉渣的 TFe、FeO、CaO、MgO、SiO2、Al2O3、TiO2、R2/R3/R4 等 | 4,939 | `2024-08-30 02:36:26` 至 `2026-07-16 04:02:08` |
| `public.v_qpes_steel_final` | 炼钢各工序试样的钢液成分、钢种、工序/炉位、炉号、取样检验及发布时间 | 212,136 | `2024-10-10 11:02:25` 至 `2026-07-16 15:01:08` |

注意：`v_qpes_slag_insoection_final` 中的 `insoection` 是数据库当前真实拼写，不得擅自改成 `inspection`；若后续数据库新增正确拼写别名，再同步程序和文档。行数与最大时间是 2026-07-16 核查时点快照，会随源系统继续写入而变化。

只读复核命令：

```powershell
. .\PT\load_imes_vastbase_local.ps1
python .\tools\audit_imes_granted_views.py `
  --sample-limit 50 `
  --statement-timeout-ms 60000 `
  --output .\logs\imes_granted_views_audit_20260716.json
```

审计程序强制 `default_transaction_read_only=on`，只执行目录查询、`SELECT`、有超时保护的 `count(*)`、字段非空统计和最多 50 行样本摘要，不记录密码。完整 123 个字段的逐项解释、非空情况和使用边界见 [MES 数据集说明：五个授权视图](../docs/mes数据集.md#9-lg_fq-五个授权视图与逐变量字典2026-07-16)，原始只读证据为 [审计 JSON](../logs/imes_granted_views_audit_20260716.json)。

## 源码边界

## MCP 炉次化验、炉渣与烧结矿成分（2026-07-16）

新增只读工具位于 [imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py)：

- `query_hot_metal_chemistry_by_heat(heat_no)`：精确炉次查询铁水 C/Si/Mn/P/S/Ti/V/Cr/Cu/Ni/As；
- `query_blast_furnace_slag_by_heat(heat_no)`：精确炉次查询全部渣样及命名氧化物、R2/R3/R4；
- `query_sinter_feed_chemistry(start_date,end_date,machine?,sample_no?,limit?)`：查询烧结矿化验；
- `resolve_imes_natural_language(question)`：把炉次成分、炉渣和进料成分口语解析到专用工具。

完整口语模板、歧义处理、多轮追问和验收 Prompt 见 [MCP可执行功能及口语调用模板第15节](MCP可执行功能及口语调用模板.md#15-imes-炉次化验炉渣与进料成分口语模板2026-07-16)。本轮真实连接复测时目标数据库在认证后关闭连接，因此只完成代码编译和 12 项单元测试；不能把本轮表述为生产 MCP 现网验收通过。此前 15:08 的五视图只读权限证据仍保存在审计 JSON 中。

数据读取客户端源码可以继续维护或新增；仅凭 Web 账号只能审计浏览器端资源和已授权接口，不能取得 IMES Java 服务端源码。服务端源码需要系统所有方提供源码仓库，或在明确授权下提供部署包/构建产物。

2026-07-15 验证：新 Web 客户端单元测试 9/9 通过；真实只读冒烟导出 `output` 数据集 22 行、22 字段；批次多日范围自动拆为两个 `workdate` 窗口并返回 334 行。临时原始数据验证后已删除。

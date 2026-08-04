# IMES / Vastbase 数据访问说明

更新时间：2026-07-16  
追踪编号：`OPS-IMES-VASTBASE-20260715`、`Q-IMES-DATA-SOURCE-20260715`

## 1. 系统边界

| 对象 | 当前已确认信息 | 说明 |
|---|---|---|
| IMES Web | `http://10.10.181.209:8080/imes.web/` | 2026-07-15 本机 GET 返回 HTTP 200；登录成功后目标页为 `/imes.web/mes/desktop.do` |
| Web 账号 | `2gldmx` | 2026-07-15 已成功登录；仅登记账号名，口令由授权人线下保管，不写入仓库、日志、截图或前端 |
| Web 登录接口 | `POST /imes.web/login.do` | 参数来自登录表单 `username/password/captchaInput`；成功响应文本为 `success`，使用 `JSESSIONID` 会话 |
| Vastbase 直连目标 | `10.10.181.195:5432/vastbase` | 来自仓库现有直连脚本；与 8080 Web 服务不是同一地址 |
| 数据库类型 | Vastbase（PostgreSQL 兼容协议） | 现有程序使用 `psycopg`/`psycopg2` 连接；具体服务端版本应在数据库账号验证成功后用 `SELECT version()` 确认 |

未登录访问 `/imes.web/mes/desktop.do` 会返回 HTTP 302 并跳转到 `/imes.web/index.jsp`。登录页验证码由浏览器端生成；自动化登录必须按授权流程处理验证码，不得绕过认证。

## 2. 账号与权限结论

2026-07-15 至 2026-07-16 的结论应区分网络路径与身份体系：

- Web 账号 `2gldmx` 已验证可登录 IMES Web；Web 凭据能否用于 Vastbase 不能仅凭 Web 登录推断。
- 2026-07-15 本机直接访问 Vastbase 时，使用该 Web 账号返回 `Invalid username/password, login denied`；当时没有到目标网段的有效 VPN 路由。
- 2026-07-16 经 `220.12` 跳板使用项目已批准的本机历史直连配置，成功连接 Vastbase，并发现 260 个可见对象、9 个可读对象、6 个 MES 业务对象。该直连身份的具体凭据不记录在文档中，也不能反推它与 Web 密码相同。
- 因而手动 Web 登录使用 Web 账号；手动数据库登录须使用受控的数据库连接配置。两种访问方式应分别验证权限，不能互换猜测。
- 该账号登录后可见 10 个业务入口：2#高炉料仓维护、料仓变料、生产计划、配料方案、原料投入、批次投料详情、生产实绩、炉次化验、炉渣检验和炉次化验全量。
- 截图所示“23488高炉炉身中部静压力检测”及 `PE424022A-F` 实时压力画面不在这 10 个菜单中。仅凭当前菜单不能确认它是否属于另一个 HMI/SCADA 系统、隐藏路由或另一个 IMES 权限；需要提供该画面的实际 URL 或从现场浏览器网络面板取证。

## 3. 可行的数据获取路径

### 3.1 通过 IMES Web 会话读取

适用于只有 `2gldmx` Web 账号的情况。推荐流程：

1. 在浏览器中完成验证码和登录，取得同一会话的 `JSESSIONID`。
2. 从菜单进入目标业务页面，记录页面 URL、查询表单字段和实际 XHR/Fetch 请求。
3. 对每个接口记录方法、参数、分页、日期格式、响应字段和权限错误。
4. 在用户已有读取权限范围内编写客户端；默认只做 GET/查询类 POST，不调用新增、修改、删除、审核、发布接口。
5. 先用一天、小页数做 dry-run，再扩大时间范围；输出中保留来源 URL、查询参数、抓取时间和行数。

2026-07-15 已在授权会话内验证：表格查询使用 `POST application/x-www-form-urlencoded`，分页参数为 `_size` 和 `_index`，常见响应为 `{total, rows}`；非分页表返回 JSON 数组。

| 数据集 | 已验证只读接口 | 主要过滤参数 | 响应 |
|---|---|---|---|
| 料仓 | `/mes/ipes/pesBin/listPageData.do` | `prodCenterCode=2D012` | 分页 |
| 料仓变料 | `/mes/ipes/pesBinMaterial/listPageData.do` | `startDate/endDate/prodCenterCode` | 分页 |
| 生产月计划 | `/mes/cpes/productionPlanMonth/listMonthData.do` | `sinteringMachineCode=2D012` | 数组 |
| 配料方案 | `/mes/ipes/dosingScheme/listPageData.do` | `startDate/endDate/prodCenterCode` | 分页 |
| 原料投入 | `/mes/ipes/input/listPageData.do` | `startDate/endDate/prodCenterCode` | 分页 |
| 批次投料合并 | `/mes/ipes/input/listPageData2.do` | `workdate/lot/prodCenterCode`；服务端已验证日期参数有效 | 分页 |
| 批次投料矿批/焦批 | `/mes/ipes/input/listPageData3/4.do` | `workdate/lot/prodCenterCode` | 分页 |
| 生产实绩 | `/mes/ipes/outputM/listCondData.do` | `startDate/endDate/prodCenterCode/meltNo` | 分页 |
| 炉次化验 | `/mes/ipes/outputM/listCondDataAvg2.do` | 同上 | 分页 |
| 炉渣检验 | `/mes/qpes/productManage/listInspData3.do` | `startDate/endDate/prodCenterCode/meltNo` | 分页 |
| 炉次化验全量 | `/mes/ipes/outputM/listCondDataAvg2New.do` | `startDate/endDate/prodCenterCode/meltNo` | 数组 |

页面源码同时包含编辑、删除、下发、审核等接口，但本项目只读客户端没有收录这些接口，也不得调用。

### 3.2 直连 Vastbase

适用于另有数据库只读账号的情况。现有安全入口为 [tools/export_vastbase_direct.py](../tools/export_vastbase_direct.py)，通过下列环境变量注入连接参数：

```text
IMES_DB_HOST=10.10.181.195
IMES_DB_PORT=5432
IMES_DB_NAME=vastbase
IMES_DB_USER=<数据库只读账号>
IMES_DB_PASSWORD=<仅在本机进程环境中设置>
IMES_START_DATE=<YYYY-MM-DD>
IMES_END_DATE=<YYYY-MM-DD>
IMES_EXPORT_DIR=<导出目录>
```

该脚本当前读取：

- `public.t_ipes_out_put`：生产实绩；
- `public.t_ipes_cond`：炉次条件；
- `public.t_qpes_inner_batch` + `public.inner_batch_insp_bb`：铁水元素；
- `public.slag_inspection`：炉渣检验。

[tools/export_vastbase_local.py](../tools/export_vastbase_local.py) 是经用户明确批准保留硬编码历史凭据的本机特例；不得复制其凭据到新脚本、文档、日志或前端。新开发继续优先使用环境变量版 `export_vastbase_direct.py`。

### 3.3 从已有 PostgreSQL 镜像表导出

如果数据已经同步到 `220.12` 的 `bf_imes.raw_rows`，可使用 [tools/export_imes_to_excel.py](../tools/export_imes_to_excel.py) 导出。该路径读取 `GL02_PGUSER/GL02_PGPASSWORD`，不会使用 `2gldmx` Web 账号。脚本已识别生产实绩、批次投料、炉次化验、炉渣检验、原料投入、配料方案、料仓和计划等数据集键。

### 3.4 使用新增只读 Web 客户端

[白名单数据集 tools/export_imes_web_readonly.py:L41-L137](../tools/export_imes_web_readonly.py#L41-L137) 固定列出 12 个已验证查询数据集；[登录会话:L151-L171](../tools/export_imes_web_readonly.py#L151-L171) 使用环境变量建立 `JSESSIONID`；[时间窗口生成:L200-L211](../tools/export_imes_web_readonly.py#L200-L211) 将批次日期范围拆成逐日查询；[统一查询接口:L244-L269](../tools/export_imes_web_readonly.py#L244-L269) 只向白名单接口提交查询参数；[导出与 manifest:L272-L316](../tools/export_imes_web_readonly.py#L272-L316) 输出 JSON Lines 和字段清单。12 个数据集字段、时间能力和使用示例见 [MES 数据集说明](mes数据集.md)。

先在登录页人工读取当前 4 位验证码，再在同一授权操作窗口设置：

```powershell
$env:IMES_WEB_USER = '2gldmx'
$env:IMES_WEB_PASSWORD = '<在当前终端输入，不写文档>'
$env:IMES_WEB_CAPTCHA = '<当前4位验证码>'

python .\tools\export_imes_web_readonly.py --list-datasets
python .\tools\export_imes_web_readonly.py `
  --dataset output `
  --start-date 2026-07-14 `
  --end-date 2026-07-15 `
  --output-dir .\exports\imes_output_20260715

Remove-Item Env:IMES_WEB_PASSWORD
Remove-Item Env:IMES_WEB_CAPTCHA
```

需要多个数据集时重复 `--dataset`。程序把单页限制在 50 行，保留接口、查询条件、行数和字段到 `manifest.json`，不打印密码、Cookie 或原始响应到控制台。

## 4. 对应程序源码是否可获得

需要区分两类“源码”：

- **数据读取客户端源码：可以。** 仓库已有 Vastbase 直连导出和 PostgreSQL 镜像导出源码；Web 账号登录并完成接口审计后，也可以在本仓库新增一个只读 Web 客户端。
- **IMES 服务端源码：仅凭 Web 账号不能获得。** 浏览器只能看到服务端返回的 HTML/CSS/JavaScript、静态资源和接口契约，看不到服务器中的 Java 源码、数据库访问层或部署配置。完整服务端源码需要由系统所有方提供源码仓库，或在得到服务器文件读取授权后提供部署包/构建产物；不得通过猜路径、目录遍历或认证绕过获取。

现有程序索引：

| 程序 | 数据路径 | 主要用途 |
|---|---|---|
| [tools/export_imes_web_readonly.py:L41-L485](../tools/export_imes_web_readonly.py#L41-L485) | IMES Web 白名单查询 | 使用 `2gldmx` 会话按任意支持日期范围导出 12 个已验证数据集 |
| [tools/check_vastbase.ps1](../tools/check_vastbase.ps1) | TCP / 环境变量状态 | 不显示口令地检查连接前置条件 |
| [tools/export_vastbase_direct.py](../tools/export_vastbase_direct.py) | Vastbase 直连 | 按日期导出 4 类已知业务数据 |
| [tools/export_vastbase_local.py](../tools/export_vastbase_local.py) | Vastbase 直连 | 历史本机特例脚本，不作为新开发模板 |
| [tools/export_imes_to_excel.py](../tools/export_imes_to_excel.py) | PostgreSQL `bf_imes.raw_rows` | 将已同步的原始 JSON 数据集展开为 Excel/CSV |

`tools/export_vastbase_local.py` 已于 2026-07-16 扩展为 Vastbase 权限发现与安全导出工具。它先从 `information_schema` 枚举账号可见的非系统表/视图，再对每个对象执行零行 `SELECT` 验证真实读取权限，最后按对象名和字段归类为生产实绩、批次投料、炉次化验、炉渣检验、原料投入、配料方案、料仓、生产计划或其他。默认导出只包含 MES 候选对象、每对象最多 1000 行；未分类对象、全量导出都需要显式参数，避免误扫生产库。批次投料历史专用入口仍保留 `tools/export_batch_input.py`；Web 数据读取见 `tools/export_imes_web_readonly.py`。

### Vastbase 全对象权限发现与导出

只检查 TCP：

```powershell
python .\tools\export_vastbase_local.py --tcp-check
```

发现账号能读取的全部表/视图并生成目录，不导出业务行：

```powershell
python .\tools\export_vastbase_local.py --discover `
  --output-dir .\exports\imes_vastbase_catalog
```

目录文件 `vastbase_accessible_catalog.json` 会记录对象类型、分类、字段、时间字段、是否可 `SELECT` 和失败原因，不记录密码。

按日期导出全部已识别 MES 候选，每个对象最多 1000 行：

```powershell
python .\tools\export_vastbase_local.py --export `
  --start-date 2026-07-01 --end-date 2026-07-15 `
  --max-rows-per-object 1000 `
  --output-dir .\exports\imes_vastbase_sample
```

只导出一个分类或明确对象：

```powershell
python .\tools\export_vastbase_local.py --export --category 炉次化验 `
  --start-date 2026-07-01 --end-date 2026-07-15

python .\tools\export_vastbase_local.py --export `
  --object public.t_ipes_out_put `
  --start-date 2026-07-01 --end-date 2026-07-15 `
  --max-rows-per-object 5000
```

只有明确接受大查询风险时才能使用 `--max-rows-per-object 0 --allow-unlimited`。不得对全部未分类对象执行无限制导出。

### 2026-07-16 网络诊断结论

只读诊断脚本：

```powershell
.\tools\diagnose_imes_network.ps1 `
  -OutFile .\logs\imes_network_diagnosis_20260716.json
```

实测 `10.10.181.209:8080` 与 `10.10.181.195:5432` 均不可达，最佳路由均为 `WLAN -> 192.168.43.1 -> 0.0.0.0/0`，没有目标专用 VPN 路由。`Sangfor aTrust VNIC` 存在但状态为 `Disconnected`，没有检测到 SSL VPN 进程。Clash Verge 系统代理为 `127.0.0.1:7897`，但 `ProxyOverride` 明确包含 `10.*`，所以浏览器访问该私网地址会绕过 Clash 代理。当前主因是 aTrust 数据隧道未建立或未下发 `10.10.181.0/24` 路由，不是 Clash 节点代理。

### 2026-07-19 网页空响应复核

当前 `10.10.181.209:8080` 和 `10.10.181.195:5432` 已改为经
`Meta` 的 `10.10.0.0/16` 路由，TCP 均成功；但 Chrome 访问
`/imes.web/` 返回 `ERR_EMPTY_RESPONSE`，`curl --noproxy "*"`
同样得到 `Empty reply from server`。这证明本次不是浏览器缓存、URL、
HTTP 404 或登录失败，而是 TCP 建连后没有收到 HTTP 响应。

同时 `10.30.220.12:22/5432` 不可达，导致备用
`127.0.0.1:18080 -> 220.12 -> 10.10.181.209:8080` 转发未建立，
浏览器对本地转发口返回 `ERR_CONNECTION_REFUSED`。当前应先恢复正式
SSLVPN 或 220.12 跳板，再用第二来源复测 HTTP：第二来源正常则检查
Meta 路径；第二来源也为空响应则由 IMES 运维检查 `.209` 的 Web
服务、访问策略和日志。完整分层证据见
[IMES 网络与 Vastbase 直连排障](IMES网络与Vastbase直连排障.md)。

## 5. 只读验证命令

连通性检查：

```powershell
Test-NetConnection -ComputerName '10.10.181.209' -Port 8080
Test-NetConnection -ComputerName '10.10.181.195' -Port 5432
```

检查数据库环境变量是否已经配置（不输出值）：

```powershell
& '.\tools\check_vastbase.ps1'
```

数据库账号取得后，先使用只读事务验证身份、版本和可见表；不要直接运行大时间窗导出。验证通过后再运行：

```powershell
$env:IMES_DB_USER = '<数据库只读账号>'
$env:IMES_DB_PASSWORD = '<仅在当前终端输入>'
$env:IMES_START_DATE = '2026-07-14'
$env:IMES_END_DATE = '2026-07-15'
python .\tools\export_vastbase_direct.py
Remove-Item Env:IMES_DB_PASSWORD
```

新 Web 客户端的静态与单元验证：

```powershell
python -m py_compile .\tools\export_imes_web_readonly.py .\tests\test_export_imes_web_readonly.py
python .\tools\export_imes_web_readonly.py --help
python .\tools\export_imes_web_readonly.py --list-datasets
python -m unittest .\tests\test_export_imes_web_readonly.py -v
```

2026-07-15 实际冒烟：只读导出 `output` 数据集在 `2026-07-14` 至 `2026-07-15` 返回 22 行、22 个字段；多日批次冒烟把 `2026-07-13` 至 `2026-07-14` 自动拆成 2 个查询窗口并返回矿批 334 行（165+169）。原始测试数据写入系统临时目录后均已删除。单元测试 9/9 通过，覆盖响应归一化、分页 `_size/_index`、日期范围逐日展开、白名单无明显写接口和 manifest 序列化。

## 6. 当前待办

- 登录与 12 个只读查询接口已经核实；后续按实际需要选择数据集和时间窗导出，不默认抓取全库。
- 确认截图所示“23488高炉炉身中部静压力检测”页面对应的实际 URL、数据接口、测点字段、采样周期和历史范围；当前账号菜单没有该入口。
- 若需要直连，向 IMES/Vastbase 管理方申请独立只读数据库账号；不要把 Web 口令当数据库口令反复尝试。
- 若要同步到 `bf_imes.raw_rows`，下一步应在新增 Web 客户端外再做可追踪的入库适配器、幂等键、断点续传和审计表；本次只提供文件导出，不写数据库。

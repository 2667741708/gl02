# IMES 只读采集说明

本模块用于通过 IMES Web 系统的已登录页面接口读取数据，并保存为 JSON、CSV 或本地 SQLite。程序只允许登录、菜单、页面发现、列表/查询类接口和本地 `SELECT` 查询；会拒绝 `save/update/delete/remove/import/upload` 等疑似修改类接口。

## 凭证配置

不要把 IMES 密码写入仓库文件。推荐在本机临时设置环境变量：

```powershell
$env:IMES_BASE_URL = "http://10.10.181.209:8080/imes.web/"
$env:IMES_USERNAME = "<IMES用户名>"
$env:IMES_PASSWORD = "<IMES密码>"
```

也可以在项目根目录创建 `.env.imes.local`，该文件已加入 `.gitignore`：

```text
IMES_BASE_URL=http://10.10.181.209:8080/imes.web/
IMES_USERNAME=<IMES用户名>
IMES_PASSWORD=<IMES密码>
```

## 已确认数据集

当前已确认并内置的 2#高炉页面数据集：

- `bf2_batch_all_rows`：2#高炉批次投料详情，矿批和焦批合并明细。
- `bf2_batch_mining`：2#高炉批次投料详情，矿批表。
- `bf2_batch_coke`：2#高炉批次投料详情，焦批表。
- `bf2_batch_input_detail`：分组读取矿批表和焦批表。
- `bf2_operation_log_report`：2# 高炉“冀南新区高炉作业日志”Raqsoft 报表；保留全部报表单元格，燃料比按报表公式重算，D 列仅登记为批数。

查看数据集和页面清单：

```powershell
python 数据库同步和存取\src\imes_readonly_client.py list-datasets
```

## 常用命令

检查登录：

```powershell
python 数据库同步和存取\src\imes_readonly_client.py login-check
```

发现页面里的表格接口：

```powershell
python 数据库同步和存取\src\imes_readonly_client.py discover-page `
  --page-key bf2_batch_input_detail `
  --out 数据库同步和存取\imes_exports\bf2_batch_input_detail_discovery.json
```

读取某天批次投料详情并保存 JSON、CSV 和 SQLite：

```powershell
python 数据库同步和存取\src\imes_readonly_client.py fetch `
  --dataset bf2_batch_input_detail `
  --date 2026-05-10 `
  --page-size 100 `
  --out-dir 数据库同步和存取\imes_exports `
  --sqlite-db 数据库同步和存取\data\imes_readonly.db
```

只读查询本地 SQLite：

```powershell
python 数据库同步和存取\src\imes_readonly_client.py sqlite-query `
  --db 数据库同步和存取\data\imes_readonly.db `
  --sql "SELECT workdate2,value_01,value_04,mining_batch_sum FROM imes_bf2_batch_mining ORDER BY workdate2 DESC LIMIT 20"
```

## 手工接口读取

如果先用 `discover-page` 找到了新的列表类接口，可以用 `fetch-endpoint` 只读采集。表名只允许英文、数字和下划线：

```powershell
python 数据库同步和存取\src\imes_readonly_client.py fetch-endpoint `
  --endpoint mes/ipes/input/listPageData2.do `
  --table-name imes_bf2_batch_all_rows_manual `
  --param prodCenterCode=2D012 `
  --param workdate=2026-05-10 `
  --param lot= `
  --formats json,csv,sqlite
```

安全限制仍然生效：程序只允许 `GET/POST`，并拒绝疑似新增、修改、删除、上传、导入等接口；本地 `sqlite-query` 也只允许 `SELECT` 或 `WITH`。

## 同步到 220.12 PostgreSQL

`从IMES数据库同步.py` 用于把 IMES 只读接口数据写入 220.12 PostgreSQL 的 `bf_trend` 数据库，schema 为 `bf_imes`。它会写入：

- `bf_imes.dataset_catalog`：数据集目录。
- `bf_imes.fetch_runs`：每次同步运行记录。
- `bf_imes.raw_rows`：统一 JSONB 明细表，按 `dataset_key + row_key` 幂等更新。
- `bf_imes.imes_bf2_batch_mining`、`bf_imes.imes_bf2_batch_coke`、`bf_imes.imes_bf2_batch_all_rows`：便于直接查询的宽表。
- `bf_imes.v_bf2_batch_input_detail`：批次投料详情统一视图。

当前 IMES 读取日期会自动与 GL02 PostgreSQL 传感器库 `bf_sensor.one_minute_values` 的时间范围对齐；早于传感器库最早 `ts` 所在日期的数据不再读取或写入。可读页面/接口清单见 `config/IMES可读数据清单.tsv`，存储位置和时间范围说明见 `IMES数据存储位置与时间范围.md`。

单日同步：

```powershell
python 数据库同步和存取\从IMES数据库同步.py `
  --dataset bf2_batch_input_detail `
  --date 2026-05-10 `
  --page-size 200
```

多日同步：

```powershell
python 数据库同步和存取\从IMES数据库同步.py `
  --dataset bf2_batch_input_detail `
  --start-date 2026-05-01 `
  --end-date 2026-05-10
```

220.12 上可使用启动脚本同步当天数据：

```powershell
powershell -ExecutionPolicy Bypass -File 数据库同步和存取\run_22012_从IMES数据库同步.ps1
```

同步 10 个 2#高炉页面的所有动态发现只读表格接口：

```powershell
python 数据库同步和存取\从IMES数据库同步.py `
  --dataset imes_10_pages `
  --date 2026-05-10 `
  --page-size 200
```

该模式会先读取左侧 10 个页面，动态发现 `*Data.do` 只读表格接口，再按页面默认参数叠加日期参数同步到 `bf_imes.raw_rows` 和对应 `bf_imes.imes_*` 宽表。

## 作业日志报表同步

报表源站通过 220.12 的受控代理访问，不在本机直连生产源：

```text
http://10.30.220.12:18084/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht
```

单日只读解析/写入：

```powershell
python 数据库同步和存取\sync_bf2_operation_log_report.py `
  --date 2026-08-08 `
  --report-base-url http://127.0.0.1:18084/
```

先验收不写库：

```powershell
python 数据库同步和存取\sync_bf2_operation_log_report.py `
  --date 2026-08-08 `
  --report-base-url http://127.0.0.1:18084/ `
  --dry-run
```

报表解析不会把 D 列“批数”强行命名为料速；只有现场确认批次窗口、单位和算法后，才允许补充 `material_rate` 派生字段。

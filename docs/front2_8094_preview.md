# front2 8094 工业工作台预览

## REQ-FRONT2-20260713

### 需求与边界

- 在不替换 8093 原页面、不改变总体后端入口和既有数据契约的前提下，建立独立的 `front2` 前端样式与布局分支。
- 以参数优化建议页的钢灰、低饱和青绿和紧凑工业工作台风格为基准，重构总览、炉况诊断、趋势分析和智能问答的视觉层级。
- 五个 hash 路由、WebSocket 消息、Chronos 请求、同源 API、SSE 流式问答、正式品牌头部和现有交互必须保持不变。
- `front2` 只在本机 `127.0.0.1:8094` 预览，不替换 8093，不新增生产控制写入。

### 基线与实现位置

原页面基线为 [高炉前端数据/frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html)，固定 SHA256：

```text
BB42228F73C281965CC4B2D2FEB65472A5926764B8820F33B5D1E1BAB762B7BC
```

| 类型 | 位置 | 作用 |
|---|---|---|
| front2 页面 | [frontend_dashboard_front2.server.html:L664](../高炉前端数据/front2/frontend_dashboard_front2.server.html#L664) | 保留原五页功能契约，并用 `front2-app` 限定新主题作用域 |
| 工业主题 | [front2-industrial.css:L1-L26](../高炉前端数据/front2/front2-industrial.css#L1-L26) | 钢灰表面、低饱和青绿主操作色、宋体与全局密度变量 |
| 响应式规则 | [front2-industrial.css:L617](../高炉前端数据/front2/front2-industrial.css#L617) | 1280 桌面与 1279 以下平板/窄屏边界 |
| 本机启动 | [start_front2.py:L17-L18](../高炉前端数据/front2/start_front2.py#L17-L18) | 选择 front2 入口并记录本机进程状态 |
| 后端环境 | [start_front2.py:L106-L111](../高炉前端数据/front2/start_front2.py#L106-L111) | 复用原后端入口，绑定 8094，并默认连接本机原生 PostgreSQL 5443 |
| 静态契约 | [verify_front2_static.py:L13-L44](../高炉前端数据/front2/verify_front2_static.py#L13-L44) | 校验原页哈希、五路由、实时/问答契约、品牌头部和主题标记 |
| 原后端入口 | [ollama_proxy_server.py:L50-L58](../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L50-L58) | 静态页面、登录、问答、报表和模型代理的既有入口 |

### 运行链

```text
浏览器 http://127.0.0.1:8094/
  -> 原 ollama_proxy_server.py
     -> BF_INDEX_FILE=front2/frontend_dashboard_front2.server.html
     -> 同源 /api/* 与 /v1/*
  -> ws://127.0.0.1:8767
     -> 既有 PostgreSQL WebSocket 实时流
```

关键约束：

- `BF_FRONTEND_DIR` 继续固定为 `高炉前端数据/`，避免 `.env`、项目、报表、静态资源和允许目录随 front2 漂移。
- 只把 `BF_INDEX_FILE` 切到 `front2/frontend_dashboard_front2.server.html`；原 HTML 和原后端文件不修改。
- 数据库账号、登录口令和模型地址只从已有环境变量读取，本文档和 front2 文件均不保存敏感值。
- 预览地址必须使用服务根路径；不要直接把嵌套 HTML 当作独立静态页打开。

## 启动与预览

在项目根目录执行前台启动：

```powershell
Set-Location -LiteralPath 'D:\文件\冀南钢铁运行中第二版本'
python '.\高炉前端数据\front2\start_front2.py' --host 127.0.0.1 --port 8094 --ws-port 8767 --strictPort
```

需要让预览在后台保持运行时：

```powershell
python '.\高炉前端数据\front2\start_front2.py' --host 127.0.0.1 --port 8094 --ws-port 8767 --strictPort --detached
```

预览入口：

```text
http://127.0.0.1:8094/?ws_port=8767#overview
```

`--strictPort` 用于在 8094 被占用时直接失败，禁止静默切换到其它端口。后台模式会把状态与日志写入 `logs/front2_8094.state.json`、`logs/front2_8094.out.log` 和 `logs/front2_8094.err.log`；停止进程前必须先确认状态文件中的 PID 仍属于本次 front2 进程。

若当前 Python 缺少后端依赖，可在项目根目录按已维护的依赖清单安装：

```powershell
python -m pip install -r '.\requirements-local.txt'
```

## 验证命令

### 静态契约

```powershell
python '.\高炉前端数据\front2\verify_front2_static.py'
```

合格信号：`ok=true`，并且 `original_sha256_unchanged`、`front2_only_allowed_html_changes`、`five_routes`、`websocket_contract`、`qa_sse_contract`、`trend_history_marker`、`automation_marker` 和 `industrial_tokens` 全部为 `true`。`front2_only_allowed_html_changes` 会把 body 作用域和主题 link 两处允许差异归一化后，再断言 front2 HTML 与原页面全文一致，防止后续误改 JS 或功能契约。

### 端口、HTTP 与实时流

```powershell
netstat.exe -ano | Select-String -Pattern ':8094 ',':8767 '
curl.exe --max-time 20 --silent --output NUL --write-out '%{http_code}' 'http://127.0.0.1:8094/?ws_port=8767'
curl.exe --max-time 20 --silent 'http://127.0.0.1:8094/api/ollama/status'
python '.\tools\check_v3_ws_bridge_python.py' --url 'ws://127.0.0.1:8767' --timeout 20
```

HTTP 合格信号为 `200`；模型状态必须区分“8094 代理可达”和“所配置模型端点可用”，不能把模型未配置的错误态记成完整功能通过。

### 浏览器与视口矩阵

静态契约通过不等于响应式或跨浏览器验收完成。提交前必须覆盖五页：`#overview`、`#diagnosis`、`#optimization`、`#trend`、`#qa`。

- Chromium：`1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`、`1024×768`、`768×1024`、`390×844`、`375×667`。
- Firefox 与 WebKit：至少覆盖 `1920×1080`、`1366×768`、`768×1024`、`390×844`。
- Edge：在现场主用稳定版上对五页做一次冒烟。
- 每个组合记录浏览器引擎、CSS viewport、页面 URL、数据状态、截图、失败项、页面错误和控制台错误；同时检查横向溢出、关键内容裁切、正式头部、核心路由、按钮可点击、底部导航遮挡以及 loading/empty/error 状态。
- 必须使用 `1546×864`，不得以历史脚本中的 `1536×864` 代替。

### 2026-07-13 本次预览验收记录

- Chromium 已完成 5 个路由 × 9 个规定 viewport，共 45 个页面组合；结果为 `45/45` 通过、页面控制台错误 `0`。
- 结果清单：[manifest.json](../logs/front2_iab_matrix_20260713_final/manifest.json)。同目录保存各路由和 viewport 的截图，命名为 `<route>_<width>x<height>.png`。
- 实际检查包括：CSS viewport 精确匹配、主题与正式头部、五个导航入口、活动路由、横向溢出、核心区域横向裁切、面板越界和页面控制台错误。
- 路由导航均实际点击；参数优化动作卡选择状态、跳转趋势、以及 `375×667` 下可达且可用的问答输入框均已验证。
- Product Design 同视口对照证据：`logs/front2_design/source_optimization_1366x768.png`、`logs/front2_design/front2_optimization_1366x768.png`、`logs/front2_design/optimization_side_by_side.png`；结论见 [design-qa.md](../design-qa.md)。
- 诊断结论区的高饱和火焰 SVG 已在 front2 渲染态替换为低饱和钢灰高炉剖面资产 `assets/blast-furnace-cutaway-industrial-v1.png`；诊断数据与交互未改变。`1366×768` 和 `390×844` 均确认资产加载、结论文字完整且无横向溢出，证据位于 `logs/front2_design/diagnosis_industrial_furnace_*.png`。
- Firefox、WebKit 和现场 Edge 冒烟未纳入本次“仅供查看”的预览回合，生产提交前仍必须按上节矩阵补齐，不得把本次结果表述为完整跨浏览器验收。

### 2026-07-14 参数优化驾驶舱重构

- `#optimization` 已改为四层阅读顺序：左侧“当前炉况”，中部“AI 决策中心”，右侧“实时监测 / 风险监控”，下方“风险趋势 / 调剂候选”。原有诊断、实时变量、候选建议和趋势接口均继续复用，不改 8093 或后端入口。
- 实际入口：`http://127.0.0.1:8094/?ws_port=8767#optimization`。若 8767 没有有效测点历史，页面必须显示“等待实时数据”和 `--`，不把空数据伪装为建议或趋势。
- 专项检查入口：`python .\tools\verify_front2_optimization_cockpit.py --browser chromium --matrix all`；代表视口的 Firefox/WebKit 用同一脚本的 `--matrix representative`。验收记录位于 `logs/front2_optimization_cockpit_qa/`。
- 视觉对照：用户参考与实现并排图位于 `logs/front2_design/optimization_cockpit_comparison.png`；说明与结论见 [design-qa.md](../design-qa.md)。

## 已知边界与风险

- `start_front2.py` 只启动 8094 页面/API 进程，不启动、停止或重启 8767、8093、8768、数据库或模型服务。
- 8767 不可达时页面应显示真实断连/等待状态；不得用静态数值伪装实时数据已经接入。
- 本机模型端点或登录/数据库环境变量未配置时，问答与授权功能应显示明确错误态；这不影响样式预览，但不能据此宣称五页功能全部通过。
- 当前 front2 HTML 已包含趋势历史和自动值守标记，静态校验会持续防止后续复制时丢失它们。
- 本机验证时 `/api/automation/status` 与 `/api/qa/projects` 返回 `200`；`/api/trend/history?hours=8` 返回 `502`，错误明确指向当前工作区缺少 `趋势分析/trend_backend/pspace_history.py`。这是原后端运行依赖缺口，不是 front2 样式分支引入；补齐该原模块前不得宣称本机趋势历史接口完整通过。
- `start_front2.py` 会在 `front2/.python_packages` 存在时把它加入后端子进程 `PYTHONPATH`。本次本机为恢复 PostgreSQL 接口，将 `psycopg[binary]` 安装在该隔离目录；不写入账号或口令。
- front2 复用原 `libs`、`logo`、`models` 与同源后端资源；不要在 front2 中复制或分叉后端主体。
- 本页是本机预览运行手册，不构成 8093 或生产服务器部署授权。

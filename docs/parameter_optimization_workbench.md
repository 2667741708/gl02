# 参数优化建议工作台

## REQ-OPT-20260710-WORKBENCH

### 用户目标

将“参数优化建议”从高密度、同权重的工业大屏改为当班可执行的决策工作台：先看到当前状态与处置路径，再核对变量证据和风险边界，最后选择一项建议查看依据、作用和现场确认要求。

### 实现边界

- 数据来源保持为页面已有的 `buildDynamicOptimization(buf, diagnosis)`；数据来自 WebSocket 缓冲区和炉况规则引擎，不新增生产写入或调控接口。
- 当实时流尚未到达时，页面必须明确显示“等待实时数据”，仅展示规则框架，不能伪装为已形成实时建议。
- “查看趋势”和“进入研判”分别跳转到现有 `#trend`、`#diagnosis` 路由；建议卡仅用于切换详情，不执行生产控制。

### 实现位置

| 类型 | 说明 | 位置 |
|---|---|---|
| 页面交互 | 趋势、研判路由跳转 | [optWorkbenchNavigate 高炉前端数据/frontend_dashboard_v3.server.html:L1974-L1978](../高炉前端数据/frontend_dashboard_v3.server.html#L1974-L1978) |
| 页面组件 | 当班处置、当班决策、变量证据、风险边界和建议队列 | [BFOptimizationWorkbenchV10 高炉前端数据/frontend_dashboard_v3.server.html:L1979-L2062](../高炉前端数据/frontend_dashboard_v3.server.html#L1979-L2062) |
| 样式与响应式 | 钢灰/青绿工业配色、1366 桌面布局及 390 宽单列布局 | [v3-optimization-workbench-v10-style 高炉前端数据/frontend_dashboard_v3.server.html:L2065-L2102](../高炉前端数据/frontend_dashboard_v3.server.html#L2065-L2102) |
| 浏览器验收 | 溢出、裁切、建议卡选择与趋势路由检查 | [verify_optimization_layout_polish.py:L27-L115](../tools/verify_optimization_layout_polish.py#L27-L115) |

### 状态模型

| 状态 | 页面表现 | 数据边界 |
|---|---|---|
| 实时数据接入中 | 显示“等待实时数据”，变量值不作为生产判断 | 只呈现规则框架 |
| 正常顺行 | “默认运行”，突出维持当前制度、观察项和复查间隔 | 建议来自当前诊断与变量窗口 |
| 异常炉况 | “需要现场确认”，最多突出三条优先动作 | 调剂动作需由现场确认 |

### 验收命令

```powershell
python tools\verify_optimization_layout_polish.py --width 1366 --height 768 --screenshot logs\optimization_workbench_v10_1366x768_verified.png
python tools\verify_optimization_layout_polish.py --width 1920 --height 1080 --screenshot logs\optimization_workbench_v10_1920x1080.png
python tools\verify_optimization_layout_polish.py --width 390 --height 844 --screenshot logs\optimization_workbench_v10_390x844.png
```

2026-07-10 静态浏览器验收结果：三种尺寸均无横向溢出或隐藏裁切；建议卡选择状态可更新；“查看趋势”可到达 `#trend`。静态文件模式未连接 WebSocket，因此截图会显示“等待实时数据”；这是空数据状态验证，不代表生产连接状态。

## OPS-OPT-20260711-8093-DEPLOY：8093 部署与视口矩阵

- 2026-07-11 已停止独立服务 `BFV4PreviewProxy8093`，备份原页面后替换新版，再恢复该服务；`BFV4PreviewWs8768` 数据桥全程保持监听。
- 远端备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html.bak_optimization_workbench_20260711_114146`。
- 部署后 `BFV4PreviewProxy8093=Running`、8093 与 8768 均监听、HTTP 200，并包含 `optimization-workbench-v10` 和正式品牌头部标记。
- 多视口验收暴露 `768×1024` 平板下旧 `1180px` 主内容宽度溢出，已通过 `v3-optimization-tablet-width-fix` 释放 1280px 以下工作台宽度；修复后真实 8093 的 `1920×1080`、`1536×864`、`1440×900`、`1366×768`、`1280×720`、`1024×768`、`768×1024`、`390×844`、`375×667` 全部为 `failed: 0`。
- 上述 Chromium 验收均确认：横向溢出 0、隐藏裁切 0、建议卡选择成功、趋势路由可达、页面错误 0、控制台错误 0。截图位于 `logs/8093_optimization_*_final.png`。
- Firefox 与 WebKit 也已在 `1920×1080`、`768×1024`、`390×844` 三个代表视口验证，均为 `failed: 0`；截图为 `logs/8093_optimization_firefox_*_final.png` 与 `logs/8093_optimization_webkit_*_final.png`。WebKit 是 Windows 自动化兼容信号，不替代最终 macOS/iOS 真实 Safari 冒烟。
- 平板修复重新部署时新增远端备份 `frontend_dashboard_v3.server.html.bak_optimization_workbench_20260711_120349`；最终文件 SHA256 为 `11040816BB3B8307123AF28778F26C9DA71C1D67551AB10832B3701B98262F85`。
- 部署脚本：[remote_deploy_8093_optimization_workbench.ps1:TODO-LINES](../tools/remote_deploy_8093_optimization_workbench.ps1)。浏览器验收脚本：[verify_optimization_layout_polish.py:TODO-LINES](../tools/verify_optimization_layout_polish.py)。

## REQ-OPT-20260711-1280-DESKTOP：1280×720 桌面断点修复

- 根因：多个 `@media(max-width:1280px)` 在恰好 1280px 时同时触发，将参数优化工作台切成平板单列，并把 `.app` 攑成自动高度；结果是页面纵向拉长、正式品牌区被简化、底部导航与主内容重叠。
- 修复：主页面相关断点统一改为 `max-width:1279px`，让 `1280×720` 保持三栏桌面工作台；1279px 以下才进入平板/窄屏布局。自动值守浮层自身的 1280px 隐藏规则不参与主页面排版，继续保留。
- 固定桌面验收矩阵按用户指定写入 `AGENTS.md`：`1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`，每次覆盖五个生产页面共 25 个组合。
- 本地与真实 8093 的 `1280×720` 参数优化页均为 `failed: 0`：三栏宽度约 `296.6 / 593.3 / 346.1px`，横向溢出 0、隐藏裁切 0、页面/控制台错误 0、建议选择和趋势路由正常。
- 远端备份：`frontend_dashboard_v3.server.html.bak_optimization_workbench_20260711_163355`；最终 HTML SHA256：`05CD7DE62A5C09B7A2254ABEDFC360A736D002F68B2BF131FD6F52623D070F9F`。
- 验收截图：[8093 1280×720 参数优化页](../logs/8093_optimization_1280x720_desktop_fix.png)。

## BUG-OPT-20260711-SELECTED-DETAIL-CLIP：当前查看正文裁切

- 现象：`当前查看` 的“判断依据／预期作用／现场确认”三张卡在 1280–1500 宽的紧凑桌面档发生底部文字裁切。
- 根因：该档字体被增强后，`.workbench-selected` 与父级 `.panel-body` 仍使用隐藏溢出；同时“本轮复查”占用了同一有限高度，挤压优先级更高的当前建议依据。
- 修复：新增 `v3-optimization-selected-detail-fix`；在 `1280px–1500px` 且高度至少 `650px` 时，依据卡最小高度设为 86px、正文使用 12px/1.32 行高、取消当前详情区裁切，并隐藏次级“本轮复查”。这保留完整的现场决策依据，不以缩小正文解决问题。
- 验收：真实 8093 `1280×720` 结果 `selected_detail_clipped_count=0`、横向溢出 0、隐藏裁切 0、页面/控制台错误 0；建议选择与趋势路由均正常。截图：[selected detail fix](../logs/8093_optimization_1280x720_selected_detail_fix.png)。
- 部署备份：`frontend_dashboard_v3.server.html.bak_optimization_workbench_20260711_164101`；最终 HTML SHA256：`5DAC47DD61A19235BD1B2ADFC316443CB2C497DD850A33AECCEE3C1327C15657`。

## 2026-07-10 远端 JSON 兼容性验证

### 端口与权限边界

- 对 `10.30.220.12:8193` 的只读 TCP/HTTP 探测均失败；同一主机的 `8093` TCP 和 HTTP 均正常。因此当前阻塞点是 **8193 尚未部署/未监听**，不是 VPN 或 8093 故障。
- 本次没有写入 8093 的文件、没有重启 8093/8768 服务，也没有写入数据库。为验证真实数据，只在自动化浏览器内把新版组件覆盖到 8093 的 HTTP 响应内存中；浏览器关闭后覆盖自动消失。

### 真实数据契约结果

`ws://10.30.220.12:8768` 返回的 `init` JSON 包含诊断、数据质量、479 个时间点，以及 `DP_total`、`P_top`、`PI`、`T_top`、`GasUtil`、`Q_blast` 六个页面关键序列。`GasUtil` 比共用时间轴多 2 个历史前导样本；前端窗口读取逻辑现按时间轴长度截取最新窗口，避免长趋势的起点错位。

| 验证项 | 结果 |
|---|---|
| `init` / 诊断 / 数据质量 | 通过，诊断为 `normal`，数据质量为 `ok` |
| 关键变量短窗口 | 通过，六个序列均可用于最近 60 分钟窗口 |
| 真实页面渲染 | 通过，显示“默认运行 / 正常顺行”，5 个实时变量均有数值 |
| 建议队列交互 | 通过，5 张卡片均已渲染，点击第二张后选择状态更新 |
| 桌面横向溢出和浏览器错误 | 通过，均为 0 |

### 实现与验证位置

- [JSON 窗口截齐 高炉前端数据/frontend_dashboard_v3.server.html:TODO-LINES](../高炉前端数据/frontend_dashboard_v3.server.html)：`OPS-OPT-JSON-ALIGN-V1`。
- [隔离预览 WebSocket 主机覆盖 高炉前端数据/frontend_dashboard_v3.server.html:TODO-LINES](../高炉前端数据/frontend_dashboard_v3.server.html)：`OPS-OPT-REMOTE-WS-HOST-V1`；仅在 URL 显式提供 `ws_host` 时启用。
- [真实 init JSON 合同验证 tools/verify_optimization_json_contract.py:TODO-LINES](../tools/verify_optimization_json_contract.py)。
- [同源浏览器内存覆盖渲染验证 tools/verify_remote_optimization_workbench_overlay.py:TODO-LINES](../tools/verify_remote_optimization_workbench_overlay.py)。

```powershell
python tools\verify_optimization_json_contract.py --out logs\optimization_json_contract_remote_8768.json
python tools\verify_remote_optimization_workbench_overlay.py --screenshot logs\optimization_workbench_remote_8093_live.png --out logs\optimization_workbench_remote_8093_live.json
```

结果文件：[JSON 合同](../logs/optimization_json_contract_remote_8768.json)、[同源渲染](../logs/optimization_workbench_remote_8093_live.json)、[真实数据截图](../logs/optimization_workbench_remote_8093_live.png)。

### 下一步

若要把该版本实际部署到 8193，需要先明确 8193 的独立测试服务目录、进程/计划任务名称及是否允许新建监听服务；这些信息当前不在项目运行文档中，不能套用 8093 的服务配置。

## REQ-OPT-20260711-TYPOGRAPHY：字体重构

- 页面新增 `v3-optimization-typography-v2` 样式层，中文统一使用 `SimSun / 宋体 / serif`。
- 1920 桌面状态与主结论为 28px，路径正文和变量行为 14px，建议标题/正文为 15px/13px；1366 桌面主标题为 25px；390 手机主标题为 23–24px，正文不低于 13px。
- `tools/verify_optimization_layout_polish.py` 同时校验计算字号、横向溢出、隐藏裁切、建议选择、趋势路由和控制台错误，并按桌面/手机视口设置字号门槛。
- 1920×1080、1366×768、390×844 均为 `failed: 0`，没有横向溢出、隐藏裁切或页面错误。
- 截图位于 `logs/optimization_workbench_typography_v2_1920x1080.png`、`logs/optimization_workbench_typography_v2_1366x768.png`、`logs/optimization_workbench_typography_v2_390x844.png`。
- 本次只修改本地新版页面和验证工具，没有替换或写入 8093 页面。

## REQ-FRONT2-20260713：front2 工业风格基准

`front2` 以本页现有参数优化工作台作为五个生产页面的视觉母版，并保持原 8093 页面不变。独立实现位于 [高炉前端数据/front2](../高炉前端数据/front2/)，完整运行边界与命令见 [front2 8094 工业工作台预览](front2_8094_preview.md)。

### 风格继承

- 沿用参数优化工作台的钢灰表面、低饱和青绿主操作色、琥珀警示色、短动词按钮、紧凑网格和低装饰信息层级。
- 总览、炉况诊断、趋势分析和智能问答仅调整样式、密度、布局比例和响应式规则；五个 hash 路由、实时数据、Chronos、问答 SSE、项目/报表和现有交互不得删改。
- front2 专属规则集中在 [front2-industrial.css:L1-L26](../高炉前端数据/front2/front2-industrial.css#L1-L26)，并由 [frontend_dashboard_front2.server.html:L2419](../高炉前端数据/front2/frontend_dashboard_front2.server.html#L2419) 引入；原 `frontend_dashboard_v3.server.html` 固定哈希由静态契约脚本保护。

### 固定验收口径

- 五个桌面视口固定为 `1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`，逐页覆盖总览、炉况诊断、参数优化建议、趋势分析和智能问答，共 25 个桌面组合。
- `1546×864` 是当前强制尺寸；历史记录和 [capture_8093_five_pages_matrix.py:L11](../tools/capture_8093_five_pages_matrix.py#L11) 中的 `1536×864` 只能作为旧证据，不能用于本次 front2 合格结论。
- Chromium 还必须覆盖 `1024×768`、`768×1024`、`390×844`、`375×667`；Firefox 与 WebKit 至少覆盖 `1920×1080`、`1366×768`、`768×1024`、`390×844`。
- 静态检查 `python 高炉前端数据\front2\verify_front2_static.py` 只证明原页保护与功能标记存在，不替代浏览器引擎、真实 CSS viewport、交互和错误检查。

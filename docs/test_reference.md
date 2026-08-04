# 测试参考

## TEST-8093-DIAGNOSIS-REVIEW-LOCAL-PROTOTYPE-20260803

```powershell
python -m pytest tests/test_diagnosis_review_api.py tests/test_diagnosis_review_contract.py -q
python tools/verify_diagnosis_review_local.py --base-url http://127.0.0.1:8096
```

- 模块/契约测试：14项通过。
- 浏览器矩阵：需先启动8096/8769；Chromium覆盖5页面×9视口，Firefox/WebKit各覆盖5页面×4视口。
- 数据库验收：查询 `bf_assistant.diagnosis_review_events`，确认真实/测试来源标记、八类分数和身份完整；220.12只做提交前后只读计数对比，不执行写入。

## TEST-BF3D-8093-BILLBOARD-EMPHASIS-20260802

```powershell
node --check "高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js"
python -m unittest tests.test_8093_stable_tooltip_hover
```

- 预期：6 项测试通过；运行时包含 `BILLBOARD_SCALE_MULTIPLIER = 1.22`，共享 adapter 不变。
- 页面信号：`.cad-furnace-viewer` 的 `data-status=loaded`、`data-billboard-count=121`、`data-point-policy=measured-121-8093`、`data-billboard-emphasis-scale=1.22`、`data-billboard-emphasis=moderate-8093`。
- 2026-08-02 Chrome 现场页通过上述信号并完成目视检查；独立冷启动专项仍受 8093 静态依赖偶发空响应阻断。

## TEST-BF3D-8093-STABLE-TOOLTIP-HOVER-20260802

```powershell
node --check "高炉前端数据/assets/bf3d-tooltip-stable-hover-8093.js"
python -m py_compile tools/remote_deploy_8093_stable_tooltip_hover.py tests/test_8093_stable_tooltip_hover.py
python -m unittest tests.test_8093_stable_tooltip_hover
python tools/verify_8093_stable_tooltip_hover.py --headed --ready-timeout-ms 120000
```

- 结果：JavaScript/Python 语法通过，6 项 unittest 通过；远端守卫停—改—启、8093/8768 监听、HTTP 200 和资源标记通过。
- 覆盖：单一写入者、视口固定坐标、迟滞参数、无周期位置写入、冷启动安装重试、无 `viewer.THREE` 依赖、页面补丁幂等、8094/共享文件保护。
- 专项输出：`logs/8093_tooltip_hover_acceptance_20260802.json` 与同名 PNG；2026-08-02 最新两次冷启动均因 8093 多个静态依赖出现 `ERR_EMPTY_RESPONSE/ERR_CONNECTION_RESET`，viewer 未初始化，故专项当前是失败诊断证据而非通过证据。Chromium 专项不替代全跨浏览器/视口矩阵。

## TEST-IMES-MCP-FULL-VARIABLE-TEMPLATES-20260727

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-IMES-MCP-FULL-VARIABLE-TEMPLATES-20260727` |
| 最终模板 | [IMES_Vastbase_MCP指令模板全集.md](../PT/IMES_Vastbase_MCP指令模板全集.md) |
| 自动生成 | [update_imes_mcp_full_variable_templates.py](../tools/update_imes_mcp_full_variable_templates.py) |
| 机器目录 | [imes_full_variable_catalog.json](../高炉前端数据/智能助手/mcp/imes_full_variable_catalog.json) |
| 覆盖测试 | [test_imes_mcp_full_variable_templates.py](../tests/test_imes_mcp_full_variable_templates.py) |
| MCP检索测试 | [test_imes_relay_mcp_server.py](../tests/test_imes_relay_mcp_server.py) |
| 覆盖证据 | [imes_mcp_full_variable_coverage_20260727.json](../logs/imes_mcp_full_variable_coverage_20260727.json) |

验证命令：

```powershell
python .\tools\update_imes_mcp_full_variable_templates.py --check
python -m py_compile `
  .\tools\update_imes_mcp_full_variable_templates.py `
  .\高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py
python -m unittest `
  tests.test_imes_mcp_full_variable_templates `
  tests.test_imes_relay_mcp_server -v
```

2026-07-27 实测：真实目录包含11个可读对象和315个“对象×字段”，
模板与机器目录均覆盖315/315，无缺失对象、额外对象或未登记字段。
5项模板覆盖测试和19项MCP测试共24项通过。口语检索已验证
“24号料仓投料”→`public.batch_input.value_24`、
“烧结矿QD强度”→`public.v_qpes_sinter_machine_sample_insp_final.qdvalue`、
“炼钢钨”→`public.v_qpes_steel_final.wmdvalue`、
“铁口深度”→`public.t_ipes_cond.depth`。数字边界测试防止24号料仓
串命中4号料仓。

## TEST-IMES-MULTI-ACCOUNT-ANY-READ-MCP-20260727

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-IMES-MULTI-ACCOUNT-ANY-READ-MCP-20260727` |
| MCP实现 | [imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py) |
| 单元测试 | [test_imes_relay_mcp_server.py](../tests/test_imes_relay_mcp_server.py) |
| 真实冒烟 | [smoke_test_imes_multi_account_mcp.py](../tools/smoke_test_imes_multi_account_mcp.py) |
| stdio契约冒烟 | [smoke_test_imes_mcp_stdio.py](../tools/smoke_test_imes_mcp_stdio.py) |
| 证据 | `logs/imes_multi_account_mcp_smoke_20260727.json`、`logs/imes_mcp_stdio_schema_smoke_20260727.json` |

验证命令：

```powershell
python -m py_compile .\高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py
python -m unittest tests.test_imes_relay_mcp_server -v
python .\tools\smoke_test_imes_multi_account_mcp.py
python .\tools\smoke_test_imes_mcp_stdio.py
```

2026-07-27 实测：原16项多账号与只读边界测试通过；随后逐变量语义目录
增强新增3项检索测试，当前本文件共19项测试通过。真实Vastbase只读冒烟发现
`operations=6`、`laboratory=5`个可读对象；结构化变量查询分别返回
10和7行；任意参数化只读SQL分别返回5和1行；写SQL被拒绝；所有成功
结果均声明`read_policy=readonly`。stdio实际列出13个工具，新增四个核心工具
及其账号、时间窗、参数和行数Schema完整。MCP账号目录和状态接口不返回密码。

## TEST-HEAT-SI-DISTRIBUTION-20260726

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-HEAT-SI-DISTRIBUTION-20260726` |
| 后端统计 | [summarize_hot_metal_si](../db_dashboard/heat_service.py) |
| 页面实现 | [heat.html](../db_dashboard/heat.html) |
| 单元/契约测试 | [test_heat_service.py](../tests/test_heat_service.py)、[test_heat_dashboard_si_distribution.py](../tests/test_heat_dashboard_si_distribution.py) |
| 真实样例 | `2#20260725-329`，Si=`0.21/0.19/0.59` |

验证命令：

```powershell
python -m py_compile db_dashboard\heat_service.py tools\build_heat_centric_docx.py
python -m pytest tests\test_heat_service.py tests\test_heat_dashboard_si_distribution.py -q
Invoke-RestMethod "http://127.0.0.1:8890/api/heat-detail?meltno=2%2320260725-329&window=pre_tap&group=core"
curl.exe -I "http://127.0.0.1:8890/api/heats?limit=24&format=xlsx"
```

2026-07-26 实测：pytest `8 passed`。API 返回 `sample_count=3`、
`valid_count=3`、`median=0.21`、`min=0.19`、`max=0.59`、
`spread≈0.40`；XLSX HTTP 200。页面图表包含 55 个全部 Si 样本点、
24 个中位点和 24 组最小—最大范围。Chromium 九个规定视口、
Firefox/WebKit 各四个代表视口、Edge `1366×768` 均无横向溢出，
正式标题、刷新、导出、详情和四条图表 series 可见，控制台与页面错误为 0。
初始详情未完成时立即点选 `329` 的竞态反例保持标题和选中行均为 `329`。

## TEST-HEAT-CENTRIC-DASHBOARD-20260725

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-HEAT-CENTRIC-DASHBOARD-20260725` |
| 聚合服务 | [heat_service.py](../db_dashboard/heat_service.py) |
| 页面与 API | [heat.html](../db_dashboard/heat.html)、[server.py](../db_dashboard/server.py) |
| DOCX 构建器 | [build_heat_centric_docx.py](../tools/build_heat_centric_docx.py) |
| 单元测试 | [test_heat_service.py](../tests/test_heat_service.py) |

验证命令：

```powershell
python -m py_compile `
  db_dashboard\server.py `
  db_dashboard\heat_service.py `
  tools\start_db_dashboard_python.py `
  tools\build_heat_centric_docx.py
python -m pytest tests\test_heat_service.py -q
Invoke-RestMethod "http://127.0.0.1:8890/api/heats?limit=24"
Invoke-RestMethod "http://127.0.0.1:8890/api/heat-detail?meltno=2%2320260725-327&window=pre_tap&group=all"
```

2026-07-25 实测：炉次列表和明细均来自当前只读数据源；样例炉次
`2#20260725-327` 返回铁水 3 条、炉渣 1 条、开口前 12 小时烧结矿 7 条、
全部物理点 133 个。`core/static/body/all` 分组分别为 17/18/80/133 个点。
Chromium 在 9 个规定 CSS 视口无横向溢出，Edge `1366×768` 页面、按钮和
真实明细通过；2026-07-26 的 Si 分布升级已补齐 Firefox/WebKit 代表视口。
DOCX 已验证为可解压的 Office Open XML 包，包含 62 个段落、11 张表格和
1 张真实页面截图；本机 Word COM 类型库异常，未生成分页 PDF 作为视觉审查件。

## TEST-DB-RELAY-DASHBOARD-20260725

| 项目 | 内容 |
|---|---|
| 对应需求 | `OPS-DB-RELAY-DASHBOARD-20260725` |
| 回环转发 | [imes_22012_relay.py](../tools/imes_22012_relay.py) |
| 炉况页启动器 | [start_db_dashboard_python.py](../tools/start_db_dashboard_python.py) |
| 页面与 API | [db_dashboard](../db_dashboard/) |
| 运行手册 | [本机数据库转发与炉况汇总页面](本机数据库转发与炉况汇总页面_20260725.md) |

验证命令：

```powershell
python -m py_compile `
  tools\imes_22012_relay.py `
  tools\start_db_dashboard_python.py `
  db_dashboard\server.py
Invoke-WebRequest http://127.0.0.1:18080/imes.web/
Invoke-RestMethod http://127.0.0.1:8890/api/overview
Invoke-RestMethod "http://127.0.0.1:8890/api/diagnosis?hours=24"
Invoke-RestMethod "http://127.0.0.1:8890/api/summaries?limit=5"
```

2026-07-25 实测：三条 SSH direct-tcpip 目标探测成功；IMES Web HTTP 200；
Vastbase 业务角色登录成功，数据库/schema CREATE 权限均为 false，两个目标
化验视图 SELECT 为 true；pSpace 243 经 18889 的 PythonSDK 认证返回 0。
8890 总览、24 小时诊断和近期总结 API 成功。Chromium `1440×900` 和
`390×844` 无横向溢出。分钟值总行数来自 PostgreSQL 统计估算并以 `≈`
显示，不作为审计精确计数；本轮未完成 Firefox、WebKit 与全部规定视口。

## TEST-HOT-METAL-SI-DATASET-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-HOT-METAL-SI-DATASET-20260719` |
| 构建程序 | [build_hot_metal_si_dataset.py](../tools/build_hot_metal_si_dataset.py) |
| 离线验证 | [validate_hot_metal_si_dataset.py](../tools/validate_hot_metal_si_dataset.py) |
| 单元测试 | [test_build_hot_metal_si_dataset.py](../tests/test_build_hot_metal_si_dataset.py) |
| 数据口径 | [铁水硅炉况传感器数据集](铁水硅炉况传感器数据集.md) |
| 产物目录 | [铁水硅炉况传感器数据集_20260719](../reports/铁水硅炉况传感器数据集_20260719) |

运行命令：

```powershell
python -m py_compile `
  tools\build_hot_metal_si_dataset.py `
  tools\validate_hot_metal_si_dataset.py
python -m pytest tests\test_build_hot_metal_si_dataset.py -q
python tools\validate_hot_metal_si_dataset.py `
  --dataset-dir reports\铁水硅炉况传感器数据集_20260719
```

2026-07-19 结果：单元测试 `3 passed`，离线产物验证 `PASS`。完整集
5,699 行、312 列，严格训练版 4,090 行；主键重复、特征截止越界、
炉况未来匹配、传感器年龄超限、`cold/hot` 展示映射错误均为 0，
manifest 内文件大小和 SHA-256 全部匹配。该测试验证数据对齐和产物完整性，
不批准生产 Si 预测模型；取样/出铁时间仍需现场链路补齐。

## TEST-BF3D-VISUAL-BIBLE-BUNDLE-20260718

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-VISUAL-BIBLE-001` |
| 规范入口 | [工业级高炉数字孪生视觉规范](../PT/高炉3D模型/工业级高炉数字孪生视觉规范（Visual%20Bible）.md) |
| 验证程序 | [validate_visual_bible_bundle.py](../PT/高炉3D模型/validate_visual_bible_bundle.py) |
| 受控参数 | [lookdev_camera_v1.json](../PT/高炉3D模型/web/presets/lookdev_camera_v1.json) |
| 数据附件 | [GL02数据映射附件.md](../PT/高炉3D模型/docs/GL02数据映射附件.md) |
| 合规证据 | [Visual_Bible当前实现合规矩阵.md](../PT/高炉3D模型/validation/Visual_Bible当前实现合规矩阵.md) |

运行命令：

```powershell
python -m py_compile PT\高炉3D模型\validate_visual_bible_bundle.py
python -B PT\高炉3D模型\validate_visual_bible_bundle.py
python -B PT\高炉3D模型\validate_visual_bible_bundle.py --json
```

验收信号：

- `RESULT: PASS`；
- Visual Bible 为 v1.1，且包含 `REQ-BF3D-VISUAL-BIBLE-001` 和七个受控附件编号；
- 小 FOV=窄视角、大 FOV=广角的语义正确；
- LookDev 与 Golden View JSON 可解析；
- P40 七个固定相机齐全，LookDev 引用文件存在，CC0 HDRI SHA-256 与本地文件一致；
- Golden View 共 16 个唯一 ID，14 张 P40 证据图路径与 SHA-256 一致，且没有误标为已批准 Golden；
- 材质卡恰好 18 张且 ID 唯一；
- 合规机器镜像恰好 45 个唯一 ID，状态计数和批准边界与 Markdown 矩阵一致；
- 数据附件包含 115 点、L7～L16、18 个静压力点、三轴来源/派生/质量和七类时间；
- 合规矩阵保留 P50 pending、P60 preflight only 的批准边界；
- 所有受控 Markdown 相对链接均存在。

2026-07-18 当前结果：22 项检查全部 `PASS`，最终 `RESULT: PASS`。

## TEST-BF3D-PROCESS-DOCX-20260717

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-PROCESS-DOCX-20260717` |
| 生成器 | [tools/build_bf3d_process_docx.py](../tools/build_bf3d_process_docx.py) |
| 分页验证器 | [tools/verify_bf3d_process_docx_render.py](../tools/verify_bf3d_process_docx_render.py) |
| 隔离预览 | [tools/serve_bf3d_preview.py](../tools/serve_bf3d_preview.py) |
| Word 产物 | [高炉3D模型制作过程与内切面验收记录_20260717.docx](../PT/高炉3D模型/高炉3D模型制作过程与内切面验收记录_20260717.docx) |
| 图像清单 | [高炉3D模型制作过程图片清单_20260717.csv](../PT/高炉3D模型/高炉3D模型制作过程图片清单_20260717.csv) |
| 生成报告 | [高炉3D模型制作过程文档生成报告_20260717.json](../PT/高炉3D模型/高炉3D模型制作过程文档生成报告_20260717.json) |

运行命令：

```powershell
C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe `
  -m py_compile tools\build_bf3d_process_docx.py tools\serve_bf3d_preview.py
C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe `
  tools\build_bf3d_process_docx.py
python -m py_compile tools\verify_bf3d_process_docx_render.py
python tools\verify_bf3d_process_docx_render.py
```

验收信号：

- 源图数量固定为 308，PNG=307、GIF=1；
- P35=6、P36=6、P40=106、P50=170、浏览器 QA=20；
- 266 个唯一 SHA-256，42 个迭代副本仍分别编入附录；
- DOCX ZIP `testzip()` 返回空，308 个 `图 A-NNN` 编号全部存在；
- Word 重分页为 70 页；封面、目录、正文、附录中段和末页抽查无裁切、重叠或缺图；
- `webkit_390x844_FAIL.png` 图注明确为历史失败取证，最终 WebKit 390×844 仍以通过截图和 manifest 为准；
- 8094 预览模型路由映射到 P60 隔离候选，正式 GLB 文件和 SHA-256 不变。

## TEST-BF3D-SKILL-PACK-20260716

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-SKILL-PACK-20260716` |
| 校验程序 | [PT/高炉3D模型/validate_skill_pack.py](../PT/高炉3D模型/validate_skill_pack.py) |
| Skill 清单 | [bundle-manifest.json](../PT/高炉3D模型/skills/bundle-manifest.json) |
| 版本与哈希 | [sources.lock.json](../PT/高炉3D模型/skills/sources.lock.json) |
| 设计与门禁 | [总设计详细规划.md](../PT/高炉3D模型/总设计详细规划.md) |

运行命令：

```powershell
python -m py_compile PT/高炉3D模型/validate_skill_pack.py
python -B PT/高炉3D模型/validate_skill_pack.py
$validator='C:\Users\hmw20\.codex\skills\.system\skill-creator\scripts\quick_validate.py'
Get-ChildItem -LiteralPath 'PT\高炉3D模型\skills' -Directory | Where-Object Name -Like 'bf3d-*' | ForEach-Object { python $validator $_.FullName }
```

可选上游复核：

```powershell
python -B PT/高炉3D模型/validate_skill_pack.py --upstream-repo "cc-blender-skill=C:\path\to\cc-blender-skill"
```

预期结果：七个 Skill 的 frontmatter 仅含 `name/description`，名称与目录一致，`agents/openai.yaml` 的默认提示包含对应 `$skill-name`；锁文件包含六个仓库的 40 位 commit/tree 和选定文件 64 位 SHA-256；本地 PythonCAD、GLB、manifest 哈希无漂移。验证只检查 Skill Pack 和源基线，不代表 Blender 材质或浏览器视觉已经完成。

独立前向测试（2026-07-16）：使用 `$bf3d-orchestrate` 处理“真实哑光风化钢、保留 115 点、导出 Three.js GLB”请求时，正确路由至第一阶段 `$bf3d-geometry-audit`，要求 P00/P10、世界矩阵基线和五视图证据；未跳过 UV/PBR/浏览器门禁，也未修改模型。

## TEST-BF3D-P35-P40-LAYER-CONTRACT-20260717

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-P35-P40-LAYERS-20260717` |
| P35 检查点 | [P35_DETAIL_GEOMETRY_APPROVED.blend](../PT/高炉3D模型/work/P35_DETAIL_GEOMETRY_20260717_135927/P35_DETAIL_GEOMETRY_APPROVED.blend) |
| P36 检查点 | [P36_LAYER_SEGMENTATION_APPROVED.blend](../PT/高炉3D模型/work/P36_LAYER_SEGMENTATION_20260717_P35_INTEGRATED/P36_LAYER_SEGMENTATION_APPROVED.blend) |
| P40 检查点 | [P40_LOOKDEV_APPROVED.blend](../PT/高炉3D模型/work/P40_FIXED_LOOKDEV_20260717_P36_FINAL/P40_LOOKDEV_APPROVED.blend) |
| 追踪说明 | [十层运行时与 P50 法线修复追踪](../PT/3D模型构建显示.md#116-2026-07-17-十层运行时与-p50-法线修复追踪) |

验收信号：P35、P36、P40 各自具有批准文件及独立视觉复核；P36 包含 L7～L16 共 10 个独立网格和 10 个独立材质，每层关联 A～H 8 个点；模型仍为 115 个传感器和 80 个炉体温度点。该检查不代表 P50、P60 或 P70 已批准。

正式 GLB 防覆盖复核：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '高炉前端数据\models\gl02_blast_furnace.glb'
```

预期 SHA-256：`808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`。

## TEST-BF3D-LAYERED-UI-EDGE-20260717

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-THREE-RUNTIME-20260717` |
| 页面实现 | [frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html) |
| 专项脚本 | [verify_gl02_layered_model_ui.py](../tools/verify_gl02_layered_model_ui.py) |
| 已测浏览器/视口 | 本机 Edge，`1366×768` |
| 数据边界 | 静态数据源；使用 `--allow-offline-data-source` |

运行命令：

```powershell
python -m py_compile tools/verify_gl02_layered_model_ui.py
python tools/verify_gl02_layered_model_ui.py `
  --base-url http://127.0.0.1:18092 `
  --page-path /frontend_dashboard_v3.server.html `
  --ws-port 8767 `
  --allow-offline-data-source
```

断言范围：L7～L16 每层只显示对应 A～H 8 点；高亮进入、回弹、呼吸、切层和清除状态正确；正常/关注/严重/无数据状态色正确；哑光材质参数与纹理存在；同层重复选择不重启动画；连续切层 100 次后对象和 GPU 资源不持续增长；页面错误和非预期控制台错误为 0。

边界：该结果只证明静态页面、模型、动画与资源合同。未连接 8767 实时流和生产数据库，因此不覆盖生产实时值、实时状态色或完整数据链路；生产验收时不得使用 `--allow-offline-data-source`。

## TEST-BF3D-LAYER-MATRIX-20260717

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-THREE-RUNTIME-20260717` |
| Chromium 报告 | [manifest.json](../logs/bf3d_layer_matrix_20260717/manifest.json) |
| Firefox/WebKit 报告 | [manifest.json](../logs/bf3d_layer_cross_engine_20260717/manifest.json) |
| Edge 专项 | [verify_gl02_layered_model_ui.py](../tools/verify_gl02_layered_model_ui.py) |
| 数据边界 | 三组均为静态数据源 |

结果：Chromium 九个规定视口为 9/9；Firefox 四个代表视口和 WebKit 四个代表视口合计 8/8；Edge `1366×768` 专项通过。各视口均验证十层按钮、L7/L10/L13/L16 单层八点、115 点模型合同、无横向溢出、控制栏不被底栏遮挡，以及除已声明离线项外无页面、控制台和资源错误。

边界：manifest 只允许把 `127.0.0.1:8767` WebSocket 和静态服务器 `/api/*` 失败记录为 expected offline。8767 实时流、生产数据库、实时值与实时状态色均未验证；该矩阵不是 P70 或生产实时链路批准。

## TEST-BF3D-P50-NORMAL-FIX-SMOKE-20260717

| 项目 | 内容 |
|---|---|
| 对应问题 | `BUG-BF3D-P50-FLAT-NORMAL-20260717` |
| 烘焙程序 | [p50_full_furnace_bake_candidate.py](../PT/高炉3D模型/skills/bf3d-uv-bake/scripts/p50_full_furnace_bake_candidate.py) |
| 旧 1K 复核 | [p50_1k_visual_review.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_20260717_153648_R2/p50_1k_visual_review.json) |
| 256px 修复报告 | [p50_full_furnace_bake_candidate.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_20260717_NORMAL_FIX_SMOKE256_R2/p50_full_furnace_bake_candidate.json) |
| 256px 独立复核 | [p50_normal_fix_smoke_review.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_20260717_NORMAL_FIX_SMOKE256_R2/p50_normal_fix_smoke_review.json) |

旧 1K 候选的独立结论为 `ITERATE`：NormalGL 有效像素为恒定 `(0.5019608, 0.5019608, 1.0)`，图集有效占比 `21.743%`，并缺少背部接缝和分区边界视觉证据。它不是 P50 批准文件。

修复后的 256px R2 采用 `4×` 法线编码放大和 `0.25` 运行时法线强度，新增 `normal_contains_quantization_safe_microdetail` 门禁；结果为 `26/26`、重复纹理哈希一致，115 点、80 个炉体温度点和 L7～L16 十层保持不变。

复现命令：

```powershell
python PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py `
  --output-dir PT/高炉3D模型/work/P50_NORMAL_FIX_SMOKE256_REPRO `
  --texture-size 256 `
  --margin 4 `
  --samples 8 `
  --skip-render
```

预期信号：报告新增且通过 `normal_contains_quantization_safe_microdetail`，总断言为 `26/26`，`normal_policy.encoding_amplification=4.0`，运行时强度为 `0.25`。该测试只批准法线修复 smoke；后续三列 1K 已补做高分辨率、图集占比与背缝/边界证据，但局部接触 AO、旋转 shimmer 和 P60/P70 仍未批准。

## TEST-BF3D-P50-3COL-1K-SMOKE-20260717

| 项目 | 内容 |
|---|---|
| 对应问题 | `BUG-BF3D-P50-FLAT-NORMAL-20260717` |
| 1K 机器报告 | [p50_full_furnace_bake_candidate.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/p50_full_furnace_bake_candidate.json) |
| 独立复核 | [p50_3col_visual_review.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/p50_3col_visual_review.json) |
| 八机位生成脚本 | [render_p50_multiview_review.py](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/review/render_p50_multiview_review.py) |
| P50 运行入口 | [run_p50_full_furnace_bake_candidate.py](../PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py) |

实测信号：机器断言 32/32；三列图集有效像素占比 `57.297%`；有效纹素密度 `25.580 texel/m`；NormalGL 通过非平坦与 8 位量化安全微细节门禁；115 个传感器、80 个炉体温度点、L7～L16 十层及每层 A～H 八点保持不变。

独立结论仅为 `APPROVE_SMOKE`，且 `p50_stage_approval=false`。这证明三列布局和非平坦 Normal 可继续迭代，不表示 P50 已批准。

复现机器候选：

```powershell
python PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py `
  --output-dir PT/高炉3D模型/work/P50_3COL_1K_REPRO `
  --texture-size 1024 `
  --margin 4 `
  --samples 16 `
  --skip-render
```

## TEST-BF3D-P50-METALLIC-R2-20260717

| 项目 | 内容 |
|---|---|
| 对应问题 | `BUG-BF3D-P50-METALLIC-SHIMMER-20260717` |
| R2 机器报告 | [p50_full_furnace_bake_candidate.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/p50_full_furnace_bake_candidate.json) |
| 八机位证据 | [p50_multiview_review_evidence.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/review/p50_multiview_review_evidence.json) |
| R1/R2 量化 | [p50_r1_r2_boundary_metrics.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/review/p50_r1_r2_boundary_metrics.json) |
| 比较脚本 | [compare_r1_r2_boundary.py](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_METALLIC_FIX_20260717_R2/review/compare_r1_r2_boundary.py) |

实测信号：R2 机器断言 35/35；按同一阈值统计，Metallic 近二值比例从 R1 的 `79.87%` 降到 `0.043%`；R2 相邻像素差 P95 为 `0.0667`，大跳变比例为 `0`，局部脉冲比例为 `0`。八机位覆盖前、后、左、右、背缝、工艺段边界、近距离 mip 和远距离 mip。

当前结论是 `approval=not_granted_comparison_only`：静态机位已经证明盐粒与局部突刺改善，但尚未完成 Three.js 旋转 shimmer 验证。

## TEST-BF3D-BOSH-BELLY-KNUCKLE-20260717

| 项目 | 内容 |
|---|---|
| 对应追踪 | `Q-BF3D-BOSH-BELLY-KNUCKLE-20260717` |
| 诊断结论 | [p50_boundary_diagnosis_conclusion.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/review/diagnosis/p50_boundary_diagnosis_conclusion.json) |
| 像素与通道报告 | [p50_boundary_diagnosis.json](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/review/diagnosis/p50_boundary_diagnosis.json) |
| 复跑脚本 | [p50_boundary_diagnosis.py](../PT/高炉3D模型/work/P50_FULL_FURNACE_BAKE_1024_3COL_20260717_R1/review/diagnosis/p50_boundary_diagnosis.py) |

预期信号：炉腹—炉腰 `z=-1.4` 的平均几何法线夹角保持 `7.5°～7.9°`，实测 `7.67°`；炉腰—炉身对照不高于 `0.1°`，实测 `0.004°`。BaseColor、NormalGL、Metallic、几何法线及无 Normal 统一材质分通道证据共同支持“合法炉型折角，非贴图断裂”。不得为消除该高光而改动批准顶点。

以上三个测试是 P50 的历史中间证据，本身都不批准 P50、P60 或 P70。后续局部接触 AO 人工观察、4K 母版、24 帧旋转审查和 P60 内部预检已经完成，见下文对应测试；Khronos Validator 与 P50/P60/P70 阶段批准仍未完成。正式 GLB SHA-256 继续为 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`，115 点、80 个炉体温度点和 L7～L16 十层合同不变。

## TEST-BF3D-P50-LOCAL-AO-R3-20260717

| 项目 | 内容 |
|---|---|
| 对应追踪 | `TEST-BF3D-P50-LOCAL-AO-R3-20260717` |
| 候选报告 | [p50_full_furnace_bake_candidate.json](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/p50_full_furnace_bake_candidate.json) |
| 八视角证据 | [p50_multiview_review_evidence.json](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/review/p50_multiview_review_evidence.json) |
| 人工观察 | [p50_multiview_manual_observations.json](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/review/p50_multiview_manual_observations.json) |
| R2/R3 比较脚本 | [compare_r2_r3_ao.py](../PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_20260717_1702_R3/review/compare_r2_r3_ao.py) |
| P50 运行入口 | [run_p50_full_furnace_bake_candidate.py](../PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py) |

白名单合同：`local_contact_whitelist_v1` 仅允许炉壳焊缝、加强圈、风口法兰本体和风口螺栓参与局部接触 AO；平台、结构塔架、内部构件、`SENSOR_` 节点及 L7～L16 诊断覆盖层必须排除，且烘焙结束后对象隐藏/渲染状态必须完全恢复。

参数与机器信号：

- `distance=0.12m`、`strength=0.28`、`floor=0.78`、`samples=32`；
- 41/41 断言通过；
- AO min `0.780392`、mean `0.996459`、std `0.022720`；
- 非纯白占比 `5.197%`、`<0.98` 占比 `2.852%`、`<0.82` 占比 `0.723%`；
- 五段炉壳几何、对象矩阵、隐藏态、115 个传感器、80 个炉体温度点和 L7～L16 十层均不变。

固定哈希：

| 产物 | SHA-256 |
|---|---|
| 候选 `.blend` | `1b6e9e5ec2257787c5859615c10e9d5c06244654f36fdc641b45e656d2b89977` |
| AO 1K | `a2686f4355e430dd06288178ed4d8356dcfb37a83dd3fc19f0f85412dd8ac358` |
| NormalGL 1K | `15b1dea80a2ab1edb5f1e62f5c1b2df1d6c1a21cebf827fef8dc4647ce33583b` |
| 候选报告 | `5744b6585d036852c3c0756f9d14d46d7b361ea1659404e19db4d73b1892c179` |

复现机器候选：

```powershell
python PT/高炉3D模型/run_p50_full_furnace_bake_candidate.py `
  --output-dir PT/高炉3D模型/work/P50_LOCAL_CONTACT_AO_1K_REPRO `
  --texture-size 1024 `
  --margin 4 `
  --samples 32 `
  --skip-render
```

人工观察已完成，结论为 `AO_MAP_LOCALIZED_VISUAL_CONSUMPTION_PENDING_P60`、`approval=not_granted`：八机位未出现平台黑带或整体压暗，但 Blender EEVEE 当时没有消费 ORM R 通道，所以该报告只证明 AO 数据范围受控，不能单独证明浏览器最终 AO 强度。后续 4K 母版、24 帧旋转审查和 P60 内部预检已经完成，见以下测试；P50/P60 仍未批准，正式 GLB 未覆盖。

## TEST-BF3D-P50-4K-ROTATION-20260717

| 项目 | 内容 |
|---|---|
| 对应追踪 | `TEST-BF3D-P50-4K-ROTATION-20260717` |
| 4K 机器报告 | [p50_full_furnace_bake_candidate.json](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/p50_full_furnace_bake_candidate.json) |
| 贴图清单 | [p50_texture_manifest.json](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/p50_texture_manifest.json) |
| 24 帧联系表 | [P50_ROTATION_CONTACT_SHEET_24.png](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/review/P50_ROTATION_CONTACT_SHEET_24.png) |
| 旋转指标 | [p50_rotation_contact_sheet_metrics.json](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/review/p50_rotation_contact_sheet_metrics.json) |
| 人工观察 | [p50_master_4k_manual_observations.json](../PT/高炉3D模型/work/P50_MASTER_4K_20260717_R1/review/p50_master_4k_manual_observations.json) |

实测信号：4K 母版机器断言 41/41；BaseColor、Roughness、Metallic、NormalGL、AO 与 ORM 全部存在；115 个传感器、80 个炉体温度点和 L7～L16 十层合同保持不变。24 帧整圈旋转审查未发现明显背缝、盐粒噪点、UV 方向翻转或静态摩尔纹。

停止线：人工观察的决定为 `KEEP_P50_PENDING_NOT_APPROVED`，`approval=not_granted`。41/41 与 24 帧审查是候选证据，不得命名为 `P50_BAKE_APPROVED`。

## TEST-BF3D-P60-PREFLIGHT-20260717

| 项目 | 内容 |
|---|---|
| 对应追踪 | `TEST-BF3D-P60-PREFLIGHT-20260717` |
| 隔离 GLB | [P60_PREFLIGHT_4K_UNCOMPRESSED.glb](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/P60_PREFLIGHT_4K_UNCOMPRESSED.glb) |
| 预检报告 | [p60_preflight_report.json](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_report.json) |
| manifest | [p60_preflight_manifest.json](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_manifest.json) |
| 文件哈希 | [p60_preflight_sha256.json](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/p60_preflight_sha256.json) |
| Validator 状态 | [gltf_validator_status.json](../PT/高炉3D模型/work/P60_PREFLIGHT_4K_20260717_R1/gltf_validator_status.json) |

实测信号：20/20 内部检查及 Blender 回读通过；炉壳为 `OPAQUE`、BaseColor alpha 为 `1`；BaseColor、Normal 和 ORM 全部嵌入，ORM 同时供 Metallic-Roughness 与 Occlusion 使用；无外部 URI、无 Draco/Meshopt 依赖；115 个传感器、80 个炉体温度点、L7～L16 十层和 45 个内部工艺示意对象保持不变。

停止线：本机 Khronos glTF Validator 不可用，因此状态是 `internal_preflight_passed`、`approval=not_granted_preflight_only`。该 GLB 只用于隔离预览和浏览器预检，不得替换正式生产 GLB。

## TEST-BF3D-CUTAWAY-RUNTIME-20260717

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-CUTAWAY-20260717` |
| 页面实现 | [frontend_dashboard_v3.server.html](../高炉前端数据/frontend_dashboard_v3.server.html) |
| 专项脚本 | [verify_gl02_cutaway_runtime.cjs](../tools/verify_gl02_cutaway_runtime.cjs) |
| 正式模型边界 | 默认正式 GLB 只读；可用 `--model` 指向 P60 隔离候选 |

运行命令：

```powershell
node --check tools\verify_gl02_cutaway_runtime.cjs
node tools\verify_gl02_cutaway_runtime.cjs
node tools\verify_gl02_cutaway_runtime.cjs `
  --model="PT\高炉3D模型\work\P60_PREFLIGHT_4K_20260717_R1\P60_PREFLIGHT_4K_UNCOMPRESSED.glb"
```

断言合同：

- 默认“外观”模式精确识别 45 个内部对象且可见数为 0；
- “内切面”启用局部裁剪平面，按料柱、软熔带和气流/炉缸流体分阶段显现；
- 内切面临时隐藏 5 组外部遮挡附件，开启两盏炉内补光和两条炉型剖切边缘；复位后全部恢复/关闭；
- 状态文字包含“工艺示意，非实时断面测量”；
- L7～L16 每层仍只显示 A～H 八点；
- 炉壳外观保持 `transparent=false`、`opacity=1`、`depthWrite=true`，并保留已有 BaseColor、Roughness、Metallic、Normal 和 AO 通道；
- 连续切换模式后对象、材质和几何资源数量不增长，复位恢复 OrbitControls 位置/目标并隐藏内部对象；
- “总览→炉况诊断→总览”后新查看器重新挂载完整 API/状态，旧 RAF 停止且资源释放。

运行接口为 `setCutawayMode()`、`playCutaway()`、`pauseCutaway()`、`resetCutaway()` 和 `getCutawayState()`；DOM 状态为 `data-cutaway-mode`、`data-cutaway-phase`、`data-internal-count` 和 `data-internal-visible-count`。

实测：正式 GLB 与 P60 4K 隔离候选两轮运行均 `ok=true`，意外页面、控制台和 HTTP 错误均为 0；Chromium 九个规定视口已复跑为 9/9；[Firefox/WebKit 专项报告](../logs/bf3d_cutaway_cross_engine_20260717/report.md)为 8/8。边界：这仍不提前声明 P70，现场 Edge、性能、8767 和数据库实时链路按正式交付门禁继续补齐。

## TEST-IMES-GRANTED-VIEWS-AUDIT-20260716

| 项目 | 内容 |
|---|---|
| 对应运维项 | `OPS-IMES-GRANTED-VIEWS-20260716` |
| 审计程序 | [tools/audit_imes_granted_views.py](../tools/audit_imes_granted_views.py) |
| 单元测试 | [tests/test_audit_imes_granted_views.py](../tests/test_audit_imes_granted_views.py) |
| 真实报告 | [logs/imes_granted_views_audit_20260716.json](../logs/imes_granted_views_audit_20260716.json) |

运行命令：

```powershell
python -m py_compile .\tools\audit_imes_granted_views.py .\tests\test_audit_imes_granted_views.py
python -m unittest .\tests\test_audit_imes_granted_views.py -v
. .\PT\load_imes_vastbase_local.ps1
python .\tools\audit_imes_granted_views.py --sample-limit 50 --statement-timeout-ms 60000
```

预期信号：单元测试通过；真实会话显示 `current_user=lg_fq`、`read_only=on`、`Found views: 5; missing: 0`，五个视图均为 `select=True`。报告不得包含 `IMES_DB_PASSWORD` 的值。

## TEST-8093-OVERVIEW-ADAPTIVE-20260716

| 项目 | 内容 |
|---|---|
| 对应问题 | `BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716` |
| 测试文件 | [tools/verify_overview_adaptive_layout.py](../tools/verify_overview_adaptive_layout.py) |
| 页面实现 | [最终响应式覆盖](../高炉前端数据/frontend_dashboard_v3.server.html#L10656) |
| Chromium 报告 | [45/45 manifest](../logs/overview_adaptive_qa_20260716/manifest.json) |
| 跨引擎报告 | [45/45 manifest](../logs/overview_adaptive_qa_20260716_cross_engine/manifest.json) |

运行命令：

```powershell
python -m py_compile .\tools\verify_overview_adaptive_layout.py
python .\tools\verify_overview_adaptive_layout.py --static-only --url "http://127.0.0.1:18093/frontend_dashboard_v3.server.html?ws_port=8767#overview"
python .\tools\verify_overview_adaptive_layout.py --url "http://127.0.0.1:18093/frontend_dashboard_v3.server.html?ws_port=8767#overview" --engines chromium --out-dir .\logs\overview_adaptive_qa_20260716
python .\tools\verify_overview_adaptive_layout.py --url "http://127.0.0.1:18093/frontend_dashboard_v3.server.html?ws_port=8767#overview" --engines firefox,webkit,msedge --out-dir .\logs\overview_adaptive_qa_20260716_cross_engine
```

断言范围：正式头部和底部导航位于视口内；5 个核心路由可渲染；页面及主内容区横向溢出为 0；总览核心变量两页各 14 行名称、数值、页签和趋势入口不裁切；变量详情弹层可打开和关闭；桌面保持三栏，平板/手机按核心变量、炉体、右栏顺序纵向可达。静态服务器未启动 8767 与后端 API，因此脚本只忽略明确的连接拒绝/404，其他页面与控制台错误仍判失败。

## TEST-IMES-WEB-READONLY-20260715

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-IMES-UNIFIED-TIME-QUERY-20260715`、`OPS-IMES-VASTBASE-20260715` |
| 测试文件 | [tests/test_export_imes_web_readonly.py:L42-L163](../tests/test_export_imes_web_readonly.py#L42-L163) |
| 被测白名单 | [DATASETS:L41-L137](../tools/export_imes_web_readonly.py#L41-L137) |
| 被测时间窗口 | [build_query_windows:L200-L211](../tools/export_imes_web_readonly.py#L200-L211) |
| 被测统一接口 | [query_dataset:L244-L269](../tools/export_imes_web_readonly.py#L244-L269) |

运行命令：

```powershell
python -m py_compile .\tools\export_imes_web_readonly.py .\tests\test_export_imes_web_readonly.py
python .\tools\export_imes_web_readonly.py --help
python .\tools\export_imes_web_readonly.py --list-datasets
python -m unittest .\tests\test_export_imes_web_readonly.py -v
```

预期结果：9 个单元测试全部通过；帮助文本包含 `--dataset`、`--all-datasets`、`--start-date`、`--end-date`、`--workdate`。

真实只读冒烟：`batch_mining` 在 `2026-07-13~2026-07-14` 生成 2 个查询窗口，返回 334 行，其中 7月13日 165 行、7月14日 169 行。测试数据仅写系统临时目录并在核对后删除。

失败排查：

- 登录失败：检查 `IMES_WEB_USER/IMES_WEB_PASSWORD/IMES_WEB_CAPTCHA`，不得打印变量值。

## TEST-IMES-VASTBASE-DISCOVERY-20260716

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-IMES-VASTBASE-DISCOVERY-20260716` |
| 测试文件 | [tests/test_export_vastbase_local.py](../tests/test_export_vastbase_local.py) |
| 被测程序 | [tools/export_vastbase_local.py](../tools/export_vastbase_local.py) |
| 网络诊断 | [tools/diagnose_imes_network.ps1](../tools/diagnose_imes_network.ps1) |

```powershell
python -m py_compile .\tools\export_vastbase_local.py .\tests\test_export_vastbase_local.py
python .\tools\export_vastbase_local.py --help
python -m unittest .\tests\test_export_vastbase_local.py -v
python .\tools\export_vastbase_local.py --tcp-check --connect-timeout 3
.\tools\diagnose_imes_network.ps1 -OutFile .\logs\imes_network_diagnosis_20260716.json
```

预期：7 个离线单元测试通过；无 VPN 路由时 TCP 检查以退出码2返回结构化超时，不泄露账号密码；网络诊断 JSON 应包含目标路由、端口、系统代理绕过、VPN 网卡和诊断摘要。

## TEST-IMES-22012-RELAY-MCP-20260716

| 项目 | 内容 |
| --- | --- |
| 对应需求 | `REQ-IMES-22012-RELAY-MCP-20260716` |
| 转发器 | [tools/imes_22012_relay.py](../tools/imes_22012_relay.py) |
| Vastbase 本机一键入口 | [tools/start_imes_vastbase_relay_local.cmd](../tools/start_imes_vastbase_relay_local.cmd) |
| MCP 服务 | [imes_relay_mcp_server.py](../高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py) |
| 完整性审计 | [audit_imes_vastbase_completeness.py](../tools/audit_imes_vastbase_completeness.py) |
| 单元测试 | [tests/test_imes_22012_relay.py](../tests/test_imes_22012_relay.py)、[tests/test_imes_relay_mcp_server.py](../tests/test_imes_relay_mcp_server.py) |
| 审计测试 | [tests/test_audit_imes_vastbase_completeness.py](../tests/test_audit_imes_vastbase_completeness.py) |

```powershell
python -m py_compile .\tools\imes_22012_relay.py .\高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py
python -m unittest .\tests\test_imes_22012_relay.py .\tests\test_imes_relay_mcp_server.py -v
python .\tools\imes_22012_relay.py --allow-agents-password --check
.\tools\start_imes_vastbase_relay_local.cmd
python -m unittest .\tests\test_audit_imes_vastbase_completeness.py -v
```

实际验收：2026-07-16 三条 SSH direct-tcpip 通道均成功；本机 `http://127.0.0.1:18080/imes.web/` 返回 HTTP 200；Vastbase目录发现为260可见对象、9个可读、6个MES对象；MCP `query_hot_metal_silicon` 返回真实炉次 `2#20260508-120` 与 `Si=0.27`。2026-07-19 新增的 Vastbase 一键入口固定只启动 `127.0.0.1:15433 -> 10.30.220.12 -> 10.10.181.195:5432`，未保存密码；窗口关闭或按 `Ctrl+C` 即停止。同轮离线转发测试 4/4 通过，自定义映射解析通过，真实 `--check` 返回 `all_ok=true`、目标连通耗时 79ms。完整性审计在 2026-05-01 至 2026-07-16 成功聚合 6 个业务对象并生成逐日计数；审计单元测试 3/3 通过。详情见 [跳板转发与MCP](22012_IMES跳板转发与MCP.md)。

远端验收：同日已同步到 220.12 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW`；按用户授权扩展后的 `direct_22012` 冒烟返回 `status_ok=true`、`catalog_objects=9`，从 `public.t_ipes_out_put` 返回 3 行，并用 `query_imes_readonly_sql` 成功执行只读总行数聚合。语义增强后，“查一下2号炉昨天每炉出了多少铁”实际解析为 `public.t_ipes_out_put.ironquan`；MCP 单元测试 10/10。冒烟入口为 [tools/smoke_22012_imes_mcp.py](../tools/smoke_22012_imes_mcp.py)。
- HTTP 超时：先检查 `10.10.181.209:8080` 连通性，再缩小日期范围。
- 超过最大页数：缩小日期范围或明确提高 `--max-pages`。
- 字段变化：对照 [MES 数据集说明](mes数据集.md) 与实际 `manifest.json.fields`，更新白名单、测试和文档。

## TEST-8093-MCP-GENERIC-SENSOR-005 通用传感器查询与绘图

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-8093-MCP-GENERIC-SENSOR-005` |
| MCP 测试 | `test_batch_sensor_tool_supports_multiple_history_series`、`test_batch_sensor_tool_keeps_partial_latest_failures` |
| 路由测试 | `test_layer_body_temperature_colloquialism_expands_to_a_through_h`、`test_arbitrary_catalog_sensor_description_and_id_are_resolved` |
| 绘图测试 | `test_layer_body_temperature_chart_routes_all_eight_sensors`、`test_auto_trend_uses_small_multiples_for_large_scale_gap_even_without_units` |

运行命令：

```powershell
python -X utf8 -m unittest "高炉前端数据.智能助手.tests.test_mcp_chart_expansion" "高炉前端数据.智能助手.tests.test_qa_latency_optimizations"
python -X utf8 tools\test_8093_colloquial_prompts.py --url "http://10.30.220.12:8093/api/qa/chat" --case mcp_body_temperature_layer7_all --case mcp_generic_multi_sensor_latest --case mcp_generic_multi_sensor_chart
```

预期结果：本地 38 项全部通过；现网三条均 `auto_pass=true`，整层预取八个 `T_body_L7_A-H`，绘图工具为 `plot_gl02_trends` 且最终 `image_url` 返回 `200 image/png`。

## TEST-BF3D-INTERNAL-RUNTIME-6X-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-INTERNAL-RUNTIME-6X-20260719` |
| 运行时 | [bf3d-internal-simulation.js](../高炉前端数据/assets/bf3d-internal-simulation.js) |
| 配置 | [bf3d_internal_simulation.v1.json](../高炉前端数据/config/bf3d_internal_simulation.v1.json) |
| 旧内切面回归 | [verify_gl02_cutaway_runtime.cjs](../tools/verify_gl02_cutaway_runtime.cjs) |
| 专项合同 | [verify_bf3d_internal_simulation.cjs](../tools/verify_bf3d_internal_simulation.cjs) |
| 浏览器矩阵 | [verify_bf3d_internal_simulation_matrix.cjs](../tools/verify_bf3d_internal_simulation_matrix.cjs) |
| 完整说明 | [WEB-60 炉内仿真运行时说明](../PT/高炉3D模型/docs/WEB-60_炉内仿真运行时说明.md) |

```powershell
node --check .\tools\verify_bf3d_internal_simulation.cjs
node --check .\tools\verify_bf3d_internal_simulation_matrix.cjs
node .\tools\verify_gl02_cutaway_runtime.cjs
node .\tools\verify_bf3d_internal_simulation.cjs
node .\tools\verify_bf3d_internal_simulation_matrix.cjs
```

断言范围：

- 正式 GLB 115 点、L7～L16 每层八点、旧内切面相机/裁剪/资源生命周期不回归；
- 数据态在门禁和输入不足时隐藏料面形变、软熔带、18 点、滴落和炉缸液面；
- 教学态固定种子、明确 `illustrative`，软熔带为闭合参数化壳并带估计置信区间；
- 26 风口统一强度，不从总量随机制造圆周差异；喷煤使用 `Points`；
- 18 点、三条插值带和 `−12～+12kPa` 固定色标；压力箭头不命名为真实流线；
- 上料事件必须 `mass_balance_valid=true`，铁口事件只开/关等宽流束；
- 50 次模式切换后场景根、层池、实例、Points 容量、面板和控制器不增长；
- Chromium 九视口、Firefox/WebKit 各四代表视口，每个走五个核心页面，共 85 个页面组合，无横向溢出、核心路由不可达或意外错误。

结果：

- [专项合同报告](../logs/bf3d_internal_simulation_20260719/runtime_contract_report.json)：`ok=true`；
- [跨引擎矩阵](../logs/bf3d_internal_simulation_20260719/matrix/cross_engine_viewport_report.json)：17 个视口运行、85 个页面组合；
- 静态验收只忽略明确的 8767 连接拒绝和后端 API 404，不能替代现场 Edge、生产数据库和实时快照链路验收。

## TEST-BF3D-STRUCTURAL-REVIEW-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-STRUCTURAL-REVIEW-20260719` |
| GLB 构建 | [export_bf3d_structural_review_glb.py](../tools/export_bf3d_structural_review_glb.py) |
| 资产清单 | [gl02_blast_furnace_structural_review.v1.manifest.json](../高炉前端数据/models/gl02_blast_furnace_structural_review.v1.manifest.json) |
| 模式专项 | [verify_bf3d_structural_review.cjs](../tools/verify_bf3d_structural_review.cjs) |
| 旧内切面回归 | [verify_gl02_cutaway_runtime.cjs](../tools/verify_gl02_cutaway_runtime.cjs) |
| 五页跨引擎回归 | [verify_bf3d_internal_simulation_matrix.cjs](../tools/verify_bf3d_internal_simulation_matrix.cjs) |

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python '.\tools\export_bf3d_structural_review_glb.py'
node --check .\高炉前端数据\assets\bf3d-structural-review.js
node .\tools\verify_bf3d_structural_review.cjs
node .\tools\verify_bf3d_structural_review.cjs --matrix
node .\tools\verify_gl02_cutaway_runtime.cjs
node .\tools\verify_bf3d_internal_simulation_matrix.cjs
```

关键断言：

- 受控 GLB SHA 为 `859819f415feee0533018daf3290c65c69b607352d8e8e34735e952d8f3772fd`，正式回滚 GLB SHA 不变；
- 五个 R5 外壳、五个 R2J 实体、R2K 背衬/铜与铸铁冷却壁/热面/残余耐火层齐全，结瘤层按 missing 隐藏；
- 纯材质审查只剩五个可见炉壳，传感器、拾取体、引线、黄色剖面和工艺运行时全部隐藏；
- 结构剖面显示 10 个有效逻辑结构对象、25 个多材质渲染 primitive，并显示 E/illustrative 图例；
- 30 次模式往返后逻辑对象数、材质克隆数和传感器数不增长，返回运行视图后 115 点恢复；
- Chromium 九视口、Firefox/WebKit 各四代表视口共 17/17；五业务页回归 85/85，无横向溢出、核心按钮遮挡或意外页面/控制台错误。

证据：[专项报告](../logs/bf3d_structural_review_20260719/report.json)、[模式矩阵](../logs/bf3d_structural_review_20260719/matrix_report.json)、[材质审查截图](../logs/bf3d_structural_review_20260719/material_review_1440x900.png)、[结构剖面截图](../logs/bf3d_structural_review_20260719/structural_section_1440x900.png)。

## TEST-BF3D-R2Q-V3-MATERIAL-STRUCTURE-EDGE-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-R2Q-INTERNAL-MATERIAL-LOOKDEV-V3-20260719`、`REQ-BF3D-R2R-LOCAL-EDGE-SMOKE-20260719` |
| 受控资产 | [V3 主 GLB](../高炉前端数据/models/gl02_blast_furnace_review.v3.glb)、[V3 纯材质 GLB](../高炉前端数据/models/gl02_blast_furnace_material_review.v3.glb)、[V3 结构 GLB](../高炉前端数据/models/gl02_blast_furnace_structural_review.v3.glb)、[直开 Blend](../高炉前端数据/models/gl02_blast_furnace_review.v3.blend) |
| 运行时 | [bf3d-structural-review.js](../高炉前端数据/assets/bf3d-structural-review.js) |
| 验证器 | [verify_bf3d_structural_review.cjs](../tools/verify_bf3d_structural_review.cjs) |
| 跨引擎报告 | [17/17 matrix](../logs/bf3d_structural_review_v3_20260719/matrix_report.json) |
| 本机 Edge 报告 | [4/4 edge smoke](../logs/bf3d_structural_review_v3_20260719/edge_smoke_report.json) |

```powershell
node .\tools\verify_bf3d_structural_review.cjs
node .\tools\verify_bf3d_structural_review.cjs --matrix
node .\tools\verify_bf3d_structural_review.cjs --edge-smoke
```

关键断言：

- V3 主/材质/结构 GLB SHA 分别固定为 `7e4b3b95...574b`、`87c2bbe6...4c09`、`8490f56b...f41a`；直开 Blend 为 `9da11f58...f32`；正式生产 GLB 保持 `808960f1...b62af6`；
- 纯材质审查使用 10 个物理半剖对象和层材质近景相机，使钢壳、背衬、铜/铸铁冷却、热面与耐火层可见；结构剖面使用同一 10 个对象和整炉相机；
- 两种审查模式均隐藏传感器、拾取体、数据引线、黄色轮廓、工艺粒子和旧环线；返回运行视图恢复 115 点；
- Chromium 九视口、Firefox/WebKit 各四代表视口共 `17/17`；
- 本机真实 Microsoft Edge `150.0.4078.83` 以严格 `channel=msedge` 在 `1920×1080`、`1366×768`、`768×1024`、`390×844` 完成 `4/4` 模式切换，意外页面/控制台/HTTP 错误为 `0`。

Edge 报告的 `scope` 固定为 `local Microsoft Edge stable smoke; not on-site Edge acceptance`。它是本机 localhost、headless、静态数据源验证；现场主机、实际交付 URL、真实 8767 数据、现场 GPU/驱动/组策略和人工 headed 冒烟仍未验收，禁止用本机报告关闭 `field_edge_smoke`。

严格 Cycles/Eevee 和 Three.js/Eevee 数值 A/B 另由 `WEB-60 R2R` 失败关闭门管理；17/17 浏览器功能矩阵及 Edge 冒烟都不能替代相机、四灯、色彩与逐图数值合同。

## TEST-BF3D-INT40-R0-TRUTH-INPUT-GATE-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-INT40-R0-TRUTH-BACKTEST-INPUT-GATE-20260719` |
| 输入锁 | [input_lock.json](../PT/高炉3D模型/work/INT_40_20260719_R0_TRUTH_BACKTEST_INPUT_GATE/input_lock.json) |
| 参考合同 | [label_contract.md](../PT/高炉3D模型/work/INT_40_20260719_R0_TRUTH_BACKTEST_INPUT_GATE/label_contract.md) |
| 阻断报告 | [blocked_no_accepted_reference.json](../PT/高炉3D模型/work/INT_40_20260719_R0_TRUTH_BACKTEST_INPUT_GATE/blocked_no_accepted_reference.json) |
| 阶段状态 | `blocked_no_accepted_reference`；INT-40 未完成，INT-50 未开始 |

当前可验证的只是：

- 输入工件、测试、报告和正式 GLB 的字节数/SHA 已锁定；
- 当前根部估计器继续为 `uncalibrated/control_use=prohibited/confidence<=0.45`；
- 浏览器 `12/12` 只证明字段和渲染合同；
- 数据源审计证明可读输入，不证明真实软熔带位置、厚度或偏心。

没有签署的独立参考时，不执行或伪造封存集准确率、经验置信区间与适用范围。解除门后必须验证输入 SHA、字段/单位/时区/方位、知识时间无未来泄漏、切分隔离、同输入确定性、缺失/陈旧/错位降级，以及高度/厚度误差、方向识别、区间覆盖率、可用率、漂移和基线比较。

## TEST-BF3D-CLEAN-STRUCTURAL-REVIEW-20260719

- 对应需求：`REQ-BF3D-CLEAN-STRUCTURAL-REVIEW-20260719`
- 被测程序：[V2 导出器](../tools/export_bf3d_structural_review_v2.py)、[Blender 复开/GLB 直导验证](../tools/verify_bf3d_structural_review_v2_blender.py)
- 资产清单：[V2 manifest](../高炉前端数据/models/gl02_blast_furnace_structural_review.v2.manifest.json)
- 预期：
  - 纯材质 GLB 仅 5 个 `steel_shell` 节点；
  - 结构 GLB 仅 10 个节点，角色为 5 钢壳、1 背衬、1 热面、1 耐火、2 冷却壁；
  - `SENSOR/PRESSURE/FLOW/STREAMLINE/BURDEN/TEMP_LAYER/PARTICLE/GUIDE/RING` 等禁止对象为 0；
  - 直接打开 Blend 后结构剖面集合默认可见、完整材质集合默认隐藏、27 张图像已打包；
  - Blender 的 Layout/实体着色不作为材质缺失判断；复开时以已打包图像、材质 ID 和 `Z → M` 材质预览为检查口径；
  - 正式 GLB 与 V1 GLB 哈希不变。
- 验证命令：

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background `
  'D:\文件\冀南钢铁运行中第二版本\高炉前端数据\models\gl02_blast_furnace_structural_review.v2.blend' `
  --python-exit-code 1 `
  --python 'D:\文件\冀南钢铁运行中第二版本\tools\verify_bf3d_structural_review_v2_blender.py'

& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background `
  --factory-startup --python-exit-code 1 `
  --python 'D:\文件\冀南钢铁运行中第二版本\tools\verify_bf3d_structural_review_v2_blender.py' `
  -- --glb-import
```

- 结果：[复开报告](../PT/高炉3D模型/work/WEB_60_20260719_R2P_CLEAN_STRUCTURAL_REVIEW/reopen_validation.json) 与 [GLB 导入报告](../PT/高炉3D模型/work/WEB_60_20260719_R2P_CLEAN_STRUCTURAL_REVIEW/glb_import_validation.json) 均 `ok=true`。

## TEST-BF3D-C2-ROOT-MOTION-20260719

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-C2-ROOT-MOTION-20260719` |
| 实现记录 | [软熔带移动预测趋势.md](../PT/软熔带移动预测趋势.md) |
| 估计器 | [cohesive_zone_estimator.py](../炉况规则引擎/features/cohesive_zone_estimator.py) |
| 参数 | [cohesive_zone_estimator.yaml](../炉况规则引擎/config/cohesive_zone_estimator.yaml) |
| 8767 适配 | [local_pg_ws_bridge.py](../自动诊断服务/local_pg_ws_bridge.py) |
| Three.js 运行时 | [bf3d-internal-simulation.js](../高炉前端数据/assets/bf3d-internal-simulation.js) |

```powershell
python -m pytest `
  .\tests\test_cohesive_zone_estimator.py `
  .\tests\test_local_pg_ws_bridge_cohesive_zone.py -q

python -m py_compile `
  .\炉况规则引擎\features\cohesive_zone_estimator.py `
  .\自动诊断服务\local_pg_ws_bridge.py `
  .\tools\check_v3_ws_bridge_python.py

node --check .\高炉前端数据\assets\bf3d-internal-simulation.js
node --check .\tools\verify_bf3d_internal_simulation.cjs
node --check .\tools\verify_bf3d_c2_cross_engine.cjs
node .\tools\verify_bf3d_internal_simulation.cjs
node .\tools\verify_bf3d_c2_cross_engine.cjs
node .\tools\verify_bf3d_internal_simulation_matrix.cjs
node .\tools\verify_gl02_cutaway_runtime.cjs
```

关键断言：

- 当前窗口与参考窗口只使用共同的 L7～L13 层和共同方位，避免缺层造成伪上移/下移；
- 温度和静压力均先在同一标高去除周向均值，再计算共同方位偏心；
- 压力数据必须在五分钟新鲜度门内，静压力至少两个标高才参与纵向梯度；
- 热风、富氧、喷煤等热力修正逐概念执行五分钟新鲜度门；陈旧项只被忽略，
  不阻断主估计，也不能制造虚假上移；
- 禁止读取 `evaluation_time` 之后的数据，缓存按数据源和单调知识时间隔离；
- 可用输出必须在 8767 和浏览器两侧分别满足有限值、几何范围、形状、
  运动、外推和安全元数据合同；
- 固定 `evidence=estimated`、`calibration_status=uncalibrated`、
  `control_use=prohibited`、`confidence<=0.45`；
- 陈旧或失效输出保留明确状态后隐藏，不以 fixture 冒充当前在线炉况。

结果：

- 后端估计器与 8767 桥接：`34 passed`；
- [Three.js 专项报告](../logs/bf3d_internal_simulation_20260719/runtime_contract_report.json)：`ok=true`；
- [C2 三引擎专项](../logs/bf3d_c2_cross_engine_20260719/report.json)：Chromium、Firefox、WebKit 各四个代表视口，`12/12`；
- [跨引擎/视口矩阵](../logs/bf3d_internal_simulation_20260719/matrix/cross_engine_viewport_report.json)：17 个视口运行、85 个页面组合全部通过；
- [旧内切面回归](../logs/bf3d_cutaway_runtime_20260717/formal_report.json)：`ok=true`；
- [确定性验收截图](../logs/bf3d_internal_simulation_20260719/chromium_1440x900_c2_root_prediction.png)只证明前端运行合同，不代表当前生产炉况；
- 本机 `bf_trend` 当前缺少 `bf_sensor`，220.12 本轮直连超时，因此现场只读在线值验证尚未执行。

## TEST-TAPHOLE-HEAT-ALIGNMENT-20260719

对应问题：
[Q-TAPHOLE-HEAT-INFERENCE-20260719](question_traceability.md#q-taphole-heat-inference-20260719)。

测试入口：

- [纯函数测试](../tests/test_analyze_taphole_heat_alignment.py)
- [只读对齐程序](../tools/analyze_taphole_heat_alignment.py)

运行命令：

```powershell
python -m unittest tests.test_analyze_taphole_heat_alignment -v

python tools\analyze_taphole_heat_alignment.py `
  --start "2026-07-12 00:00:00" `
  --end "2026-07-19 00:00:00" `
  --statement-timeout-ms 180000 `
  --out-dir "reports\出铁口温度炉次对齐_20260712_20260718"
```

成功信号：

- 纯函数测试 `3/3 OK`；
- 两个温度变量均从 `bf_sensor.sensor_registry` 解析到唯一物理点；
- 两个点各返回 10,080 个分钟值；
- IMES 返回 89 个 2# 正式炉次；
- `summary.json` 明确记录
  `can_infer_official_heat_number_from_temperatures_alone=false`；
- 数据库事务只读，报告和 CSV 仅写本地 `reports/`。

## TEST-BF3D-R2R-RENDERER-NUMERIC-AB-20260719

- 对应需求：`REQ-BF3D-R2R-RENDERER-NUMERIC-AB-20260719`
- 预注册合同：[capture_contract.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/capture_contract.json)
- Blender 捕获：[render_bf3d_r2q_ab_blender.py](../tools/render_bf3d_r2q_ab_blender.py)
- 数值比较：[compare_bf3d_r2q_ab.py](../tools/compare_bf3d_r2q_ab.py)
- Three.js 预检：[capture_bf3d_r2q_ab_three.cjs](../tools/capture_bf3d_r2q_ab_three.cjs)
- 阶段状态：[pipeline_status.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/pipeline_status.json)

静态检查：

```powershell
python -m py_compile `
  tools\render_bf3d_r2q_ab_blender.py `
  tools\compare_bf3d_r2q_ab.py

node --check tools\capture_bf3d_r2q_ab_three.cjs
```

Blender 捕获和比较入口：

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background `
  --python-exit-code 1 `
  --python tools\render_bf3d_r2q_ab_blender.py

python tools\compare_bf3d_r2q_ab.py
```

Three.js 合同预检：

```powershell
node tools\capture_bf3d_r2q_ab_three.cjs
```

当前结果不是成功门：

- Blender 捕获完成 `12/12`，严格 OptiX、无 CPU/CUDA 回退；
- 数值比较进程应因真实失败返回非零，[comparison_report.md](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/comparison_report.md)必须为 `80 required / 68 pass / 12 fail / 0 not-evaluated`；
- Three.js 进程应因合同不匹配返回非零，[three_contract_preflight.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reports/three_contract_preflight.json)必须为 `blocked_contract_mismatch`、`13 pass / 8 fail / 2 blocked`；
- [three_capture_manifest.json](../PT/高炉3D模型/work/WEB_60_20260719_R2R_RENDERER_NUMERIC_AB_GATE/reports/three_capture_manifest.json)必须保持 `capture_attempted=false`、beauty/mask `0`、`ab_pass_claimed=false`；
- 输入锁 before/after/current、正式 GLB 和 R2Q 候选 SHA 必须一致；
- 任何阈值捕获后放宽、`not_evaluated` 视为通过、平均两个 repeat 掩盖单项失败或伪造 Three.js 截图，都应使门禁失败。

R2S 的成功信号必须是同一冻结阈值下 Blender `80/80`，且 Three.js 预检全通过后再执行并通过 Three.js/Eevee 数值 A/B；浏览器页面矩阵或人工观感不能替代这两个数值门。

## TEST-BF3D-R2S-RENDERER-CONTRACT-ALIGNMENT-20260720

- 对应需求：`REQ-BF3D-R2S-RENDERER-CONTRACT-ALIGNMENT-20260720`
- 状态：[pipeline_status.json](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/pipeline_status.json)
- 增量清单：[implementation_delta_manifest.json](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/implementation_delta_manifest.json)
- 专项验证器：[verify_bf3d_r2s_audit_contract.cjs](../tools/verify_bf3d_r2s_audit_contract.cjs)
- 结果记录：[r2s_audit_contract_verification.json](../PT/高炉3D模型/work/WEB_60_20260719_R2S_RENDERER_CONTRACT_ALIGNMENT/r2s_audit_contract_verification.json)

执行：

```powershell
node --check 高炉前端数据\assets\bf3d-structural-review.js
node --check tools\verify_bf3d_r2s_audit_contract.cjs
node tools\verify_bf3d_r2s_audit_contract.cjs
node tools\verify_bf3d_structural_review.cjs
node tools\verify_bf3d_structural_review.cjs --matrix
node tools\verify_bf3d_structural_review.cjs --edge-smoke
node tools\verify_gl02_cutaway_runtime.cjs
```

成功信号：

- 真实生产 HTML 和合成 harness 各 `9` 组负向门均禁用，精确双门只开放冻结数值 manifest；
- instrumentation 在应用脚本前建立，两个独立 full-ready 上下文完成 ready、API、4 RAF 和 `450ms` 延迟核查；
- `input_lock.json` 根文件与 `22/22` 锁项前后匹配；R2R 合同/捕获清单 SHA 固定；
- `12` 个 engine × repeat × shot 记录、三个正交 shot、P40 四灯、TOP/world 和原 `13` 项阈值匹配；
- capability/manifest 的递归冻结对象为 `124/40`，`12/12` 次突变以 `TypeError` 拒绝；
- `colorState=pending_preapproval`、`captureEligible=false`、beauty/mask 不可用；
- API 前后生产 Viewer、PerspectiveCamera、OrbitControls、renderer、scene、灯光、资源、viewport/scissor/render target、RAF 和 ACES `1.05` 引用/状态不变，审计副作用为 `0`；
- 硬化验证器为 `112147` bytes、SHA `53b27a0e…5b20a9f`；根代理在最终状态字符串锁定后独立复跑 `2/2 PASS`；
- 原专项 PASS，矩阵 `17/17 PASS`，本机真实 Edge `4/4 PASS`，旧切面错误为 `0`；
- 正式 GLB SHA 仍为 `808960f1…62af6`。

失败信号：

- 单门即可启用、迟注入令牌可绕过模块加载门，或普通生产 URL暴露 capture；
- 缺任一 shot、P40 TOP/方向或原阈值；
- 未批准色彩/光度时生成 beauty/mask；
- 生产相机、控制器、renderer、ACES、页面或 GLB 被修改；
- 将数值合同 PASS 写成跨渲染器图像 PASS。

## TEST-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720

- 对应需求：`REQ-BF3D-R2T-OCIO-PHOTOMETRIC-EQUIVALENCE-20260720`
- 状态：[pipeline_status.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/pipeline_status.json)
- 输入锁：[input_lock.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/input_lock.json)
- 色彩候选：[color_management_candidate.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/color_management_candidate.json)
- 光度合同：[photometric_calibration_contract.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/photometric_calibration_contract.json)
- 生成器：[generate_bf3d_r2t_ocio_assets.py](../tools/generate_bf3d_r2t_ocio_assets.py)
- OCIO 验证器：[verify_bf3d_r2t_ocio_assets.py](../tools/verify_bf3d_r2t_ocio_assets.py)
- 阶段验证器：[verify_bf3d_r2t_stage.py](../tools/verify_bf3d_r2t_stage.py)
- WebGL oracle 验证器：[verify_bf3d_r2t_ocio_webgl.cjs](../tools/verify_bf3d_r2t_ocio_webgl.cjs)
- WebGL oracle 报告：[ocio_webgl_oracle_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/ocio_webgl_oracle_report.json)
- LTC runtime oracle 验证器：[verify_bf3d_r2t_ltc_runtime.cjs](../tools/verify_bf3d_r2t_ltc_runtime.cjs)
- LTC runtime oracle 报告：[ltc_runtime_oracle_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/ltc_runtime_oracle_report.json)
- 光度 fixture 构建/验证：[build_bf3d_r2t_photometric_fixture.py](../tools/build_bf3d_r2t_photometric_fixture.py)、[verify_bf3d_r2t_photometric_fixture.py](../tools/verify_bf3d_r2t_photometric_fixture.py)
- 光度 fixture 证据：[冻结定义](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/photometric_fixture/fixture_definition.json)、[fit/held-out 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/photometric_fit_held_out_report.json)、[独立验证报告](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/reports/photometric_verification_report.json)
- 隔离审查验证：[verify_bf3d_review_preview.cjs](../tools/verify_bf3d_review_preview.cjs)、[arrayBuffer ×2 稳定性主日志](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/root_arraybuffer_stability_x2.stdout.log)、[第 1 轮明细](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/bf3d_review_stability_run_1.json)、[第 2 轮明细](../PT/高炉3D模型/work/WEB_60_20260720_R2T_OCIO_PHOTOMETRIC_EQUIVALENCE/preview/bf3d_review_stability_run_2.json)

执行：

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' `
  'tools\generate_bf3d_r2t_ocio_assets.py'

& 'D:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' `
  'tools\verify_bf3d_r2t_ocio_assets.py'

python -m py_compile `
  tools\generate_bf3d_r2t_ocio_assets.py `
  tools\verify_bf3d_r2t_ocio_assets.py `
  tools\vendor_three_r160_rect_area_ltc.py `
  tools\verify_bf3d_r2t_stage.py

python tools\vendor_three_r160_rect_area_ltc.py --verify-only
python tools\verify_bf3d_r2t_stage.py
node tools\verify_bf3d_r2t_ocio_webgl.cjs
node tools/verify_bf3d_r2t_ltc_runtime.cjs
python tools\build_bf3d_r2t_photometric_fixture.py
python tools\verify_bf3d_r2t_photometric_fixture.py
python tools\serve_bf3d_review.py --check-only
node tools\verify_bf3d_review_preview.cjs
```

OCIO WebGL oracle 命令当前预期退出码为 `1`：exact generated shader 是 release hard gate，
Firefox 黑点 float 失败；该退出码是当前可复现的失败证据，不应改写为脚本异常或整体 PASS。
独立的 LTC runtime oracle 命令当前为 PASS；它只验证 runtime prerequisite，不能覆盖前一条
exact OCIO 硬门失败。

当前成功信号：

- 19 个 R2S/R2R/R2Q/Three/Blender/OCIO 输入 bytes/SHA 全匹配；
- PyOpenColorIO `2.5.0`，processor cache 为 `cb6dc6defbf01d33b84718a55c277f0a`；
- GLSL ES3 为 `14155` bytes、SHA `8e90dd51…494ac`；
- 37³/57³ RGB32F 与 RGBA32F 资源 SHA 匹配；
- `235846` 个 texel 的 RGB 位序和 alpha `0x3f800000` 全量通过；
- 黑、中灰、白、HDR、红、绿、蓝共 8 个 CPU oracle 均通过，最大绝对误差 `4.886817894789175e-10`；
- Three r160 内建 AgX 只记录静态负向事实，不宣称与 Blender Medium Low 等价；
- SUN/TOP/world 只登记 family-level `k=1` 解析候选；TOP `I(k=1)=1.3275510357953`；
- Three r160 官方 LTC addon 为 `313854` bytes、SHA `08085bc9…214`，Three MIT、selfshadow LTC 许可证和 `vendor.lock.json` 全部 verify-only 通过；
- 阶段保持 `capture_eligible=false`、`approval_granted=false`、`next_stage_allowed=false`。
- fixture 定义在 renderer 前冻结为 `103102` bytes、SHA-256 `8d43067c8875c4e677330e830eda079b841d5d8a6fad05f13b26200f349bbcfd`；Blender Cycles `67/67`、Eevee WORLD held-out `8/8`，Three Chromium/Firefox/WebKit 各两次合计 `6/6`，错误 `0`；
- WLS 为 `k_sun=0.9414175269608743`、`k_area=0.9450029255130412`、`k_env=0.9299202953495894`，分母分别为 `0.055471528149193094`、`0.0910057735916505`、`0.0019578534604496323`，均非零；
- fit/held-out 已执行且 held-out 未参与 refit；因未预注册线性接受阈值，只能验证 candidate evidence 完整性，状态为 `candidate_evidence_verified_not_approved`，`photometric_equivalence_approved=false`、`capture_eligible=false`、`production_integration_allowed=false`；
- 隔离审查只请求 SHA-256 `7e4b3b95343103784500aba354a124262ecf593fe89a3f0aa98348692152574b` 的 `review.v3`，以 `response.arrayBuffer()` 完整消费 GLB，使用独立 Scene/Renderer/Camera/RAF，并检查纯材质审查、内部层近景、结构剖面；V3 为 `13` 个 PBR 材质、`39` 个 texture、`21` 个 image、forbidden 对象 `0`；
- arrayBuffer 稳定性门连续执行两轮，每轮 `17/17`、`51` 图，合计 `34/34` viewport runs、`102` captures；`34/34` review GLB 均 `requestfinished=1`、`request_failed=0`，console/page/HTTP/external/request_failed 五类错误累计 `0`；
- 可解释性检查必须确认：外表面横向变化为 R2J 五区实体交界/原始纹理，不是数据圆环/引线；底部深色楔为现有 V3 GLB 十个 Section 封口面共面叠合/遮挡，不是内腔，且 Web 没有修复或改写该几何。

最新 WebGL oracle 结果：

- exact generated shader：Chromium、WebKit 通过，Firefox 失败，即 `2 PASS / 1 FAIL`，exact 硬门整体 FAIL；Firefox 黑点 RGBA32F 为 `0`，CPU oracle 约为 `0.0002386`，最大误差 `0.000238734 > 2e-5`；
- exact 的其余 7 点、三引擎全部默认 framebuffer RGBA8、两次重复，以及页面/控制台/HTTP/外部请求隔离检查均通过；
- literal-nextafter 候选仍是 `2 PASS / 1 FAIL`，候选整体 FAIL；
- 共享 highp uniform `0x00800001` 候选为 `3/3 PASS`，非黑点副作用门也通过，但其审批状态为 `candidate_not_approved`，不能满足或覆盖 exact release hard gate；
- oracle 隔离页未加载或改动生产页面、生产控制器或正式 GLB，也没有执行生产集成。

最新 LTC runtime oracle 结果：

- `node tools/verify_bf3d_r2t_ltc_runtime.cjs` PASS；Chromium、Firefox、WebKit 各执行 `2` 次新鲜运行，结果 `6/6 PASS`；
- oracle 与 `RectAreaLightUniformsLib` 解析到同一 Three r160 ESM；每次只有 `1` 次有效 addon init，显式重复探针均在调用 addon 前被拒绝；
- 四张 `64×64` DataTexture 的类型、payload 与 SHA 通过：`LTC_FLOAT_1=cf5cf21e5c112d2095c7e2418cb0a1ac54636e275d73e42f3453646c67f26814`、`LTC_FLOAT_2=3b1b09080b26104498db277c14fc1733786465c6958e7a8403d688b1e24c2ff5`、`LTC_HALF_1=a391de32f868fd4aa8774917b793174b7be804c08e2fb8924c30f31d7aa8dcd7`、`LTC_HALF_2=fa1ecbc6deb3c85ddf603cdf1e98e30279444f905eb1cebb849d761b570dd696`；六次运行实际选择均为 `float` 分支；
- 单 RectAreaLight + `metalness=1` MeshStandardMaterial 平面在无 environment、无 AmbientLight、无 emissive 时读回非黑；零强度控制为黑；同一引擎的页内重复和两次独立运行字节一致；
- console/page/HTTP/external 四类错误均为 `0`；
- 报告只批准隔离 LTC runtime prerequisite；审批状态仍为 `candidate_not_approved`（顶层 `status=runtime_prerequisite_verified_candidate_not_approved`），不证明 Blender/Three 光度等价，不证明 RectAreaLight 阴影，也不解除 capture、production integration 或 next stage。

当前失败/停止信号：

- exact generated shader 在 Firefox 黑点超过 float `2e-5` 阈值；即使 uniform candidate 为 `3/3 PASS`，exact 硬门仍必须保持 FAIL；
- 3D LUT 轴序、filter、wrap、颜色空间或最后 OETF 与合同不同；
- 浏览器路径对 OCIO 输出再执行一次 sRGB OETF；
- 后续若 `RectAreaLightUniformsLib` 与 renderer 不再解析到同一 Three ESM、有效 init 不为 `1`、重复探针未在 addon 前拒绝、四张 `64×64` LTC texture/扩展分支任一不成立，则 LTC runtime prerequisite 必须 fail closed；
- 按灯、材质、shot、engine 或 browser 分别拟合光强；
- 把 SUN 8°角、RectArea 阴影、DISK/square 或 PMREM/path tracing 写成原生解析等价；
- 把已执行但无预注册接受阈值的 fit/held-out 写成 photometric equivalence PASS，或把 DISK→equal-area square 的 known non-equivalence 写成等价；
- 把 `E/illustrative`、`REF-PENDING` 的隔离审查矩阵 PASS 写成生产页、正式 GLB、Blender/Three 数值 A/B 或阶段批准；
- 许可取证未完成却把 LUT payload 复制到生产 Web 资产；
- 在色彩和光度门通过前生成炉体 beauty/mask 或替换生产 ACES/GLB。

因此 capture、生产接入和 next stage 继续阻断；LTC runtime prerequisite 的 PASS 不改变
exact OCIO 硬门整体 FAIL。独立 V3 页面已解决 `E/illustrative`、`REF-PENDING` 的只读
材质/结构可见性，但光度 fit/held-out、LTC 与 OCIO 均未批准 photometric equivalence 或
production；仍需 OCIO LUT 专属许可、炉体 A/B 和发布门，不能把候选结果写成阶段完成。
正式 GLB SHA-256 仍为 `808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6`，
8092 生产默认 V1 仍未修复或替换；十阶段统计仍为 `5` 完成、`2` 部分完成、`3` 未开始。

## TEST-BF3D-R2U-V4-SECTION-CAP-WEB-20260720

| 项目 | 内容 |
|---|---|
| 对应需求 | `REQ-BF3D-R2U-SECTION-CAP-CONTROLLED-V4-20260720` |
| 阶段目录 | [WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/) |
| 根审查 | [WEB-60_R2U_根审查结论.md](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/WEB-60_R2U_根审查结论.md) |
| 几何报告 | [section_topology_validation.json](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/section_topology_validation.json)、[section_cap_overlap_validation.json](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/section_cap_overlap_validation.json) |
| 独立验证 | [root_independent_verifier_v4.json](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/root_independent_verifier_v4.json) |
| Khronos | [khronos_gltf_validator_v4.json](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/khronos_gltf_validator_v4.json) |
| Web 报告 | [bf3d_review_v4_preview_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4/reports/bf3d_review_v4_preview_report.json) |

固定复验命令：

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background `
  --python tools\export_bf3d_structural_review_v4.py `
  -- `
  --verify `
  --blend '高炉前端数据\models\gl02_blast_furnace_review.v4.blend' `
  --output 'PT\高炉3D模型\work\WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4\reports\root_independent_verifier_v4.json' `
  --expected-input-sha256 '86bce712181ac0771ed460806f54b072659fd8f854334bd0a1ddf73b4e15c9c1'

node tools\verify_bf3d_review_v4_preview.cjs
```

预期信号：

- 独立 Blender 验证 `passed=true`，10 个 Section 全部闭合正体积，boundary/non-manifold
  均为 `0`，跨对象封口重叠为 `0`；
- 三份 GLB factory import PASS；Khronos errors 均为 `0`；
- Web `overall_status=full_matrix_passed_illustrative_only`，连续两轮 `34/34`
  viewport runs、`102` captures，五类错误为 `0`，`protected_files_unchanged=true`；
- 独立视觉 PASS；规范只批准 R2U 结构候选，不批准 P60/生产；前端资产隔离加载和
  资源释放 PASS，但统一/纯材质/结构纹理解码估算约 `264/192/264 MiB`。

已知非通过项：主 GLB 与结构 GLB 各有 21 条 generated tangent-space warning；每份
GLB 各有四条本机绝对路径 extras；解码内存/真机性能、R1/R5 AO、生产 8092、现场
Edge、P50/P60/P70/QA-70、长稳和 Blender/Three 数值光度等价仍待。不得把本测试的 isolated illustrative
PASS 写成正式 GLB、生产页或阶段批准。

## TEST-BF3D-R2V-V5-PORTABILITY-WEB-20260720

| 项目 | 受控值 |
|---|---|
| 对应需求 | `REQ-BF3D-R2V-GLTF-PORTABILITY-TANGENT-BUDGET-20260720` |
| 阶段目录 | [WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/) |
| V5 manifest | [gl02_blast_furnace_review.v5.manifest.json](../高炉前端数据/models/gl02_blast_furnace_review.v5.manifest.json) |
| 可移植性 | [v5_portability_audit.json](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/v5_portability_audit.json) |
| 切线最小修复 | [glb_tangent_vector_sanitization.json](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/glb_tangent_vector_sanitization.json) |
| Khronos | [khronos_gltf_validator_v5.json](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/khronos_gltf_validator_v5.json) |
| Web 矩阵 | [bf3d_review_v5_preview_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/bf3d_review_v5_preview_report.json) |
| 独立审查 | [independent_review_decisions.json](../PT/高炉3D模型/work/WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET/reports/independent_review_decisions.json) |

固定复验命令：

```powershell
python tools\audit_bf3d_glb_portability.py `
  --asset '高炉前端数据\models\gl02_blast_furnace_review.v5.glb' `
  --asset '高炉前端数据\models\gl02_blast_furnace_material_review.v5.glb' `
  --asset '高炉前端数据\models\gl02_blast_furnace_structural_review.v5.glb' `
  --output 'PT\高炉3D模型\work\WEB_60_20260720_R2V_GLTF_PORTABILITY_TANGENT_BUDGET\reports\v5_portability_audit.json' `
  --require-release-ready

python tools\serve_bf3d_review_v5.py --check-only
node tools\verify_bf3d_review_v5_preview.cjs
python tools\finalize_bf3d_review_v5.py
```

预期信号：

- 三 GLB 绝对路径 `0`、normal-map 缺失切线风险 `0`、无效显式切线 accessor `0`；
- 10 个 Section 顶点/边界/材质槽/UV 合同保持，10/10 闭合正体积，封口重叠 `0`；
- 3 个未定义几何切线顶点只在统一/结构 GLB 各回退一次，有效非零切线改写数 `0`；
- Khronos 三资产均 `0 errors / 0 warnings`；
- Web 两轮 `34/34` viewport runs、`102` captures，五类错误 `0`；
- 收口器输出 `r2v_scope_passed=true`、`next_release_stage_allowed=false`。

已知非通过项：默认外表面全景材质对比偏弱；内部两实体层之间的窄黑缝可能被误读为
竖线；`EXT_texture_webp` 为必需扩展；三资产同时解码约 `720 MiB`，完整 mip 约
`960 MiB`。现场 Edge、移动端/现场性能、R5 AO、P50/P60/P70/QA-70、生产接入和
Blender/Three 数值光度等价继续待办。

## TEST-BF3D-R2W-CAMERA-AO-INTERFACE-20260720

| 项目 | 受控值 |
|---|---|
| 对应需求 | `REQ-BF3D-R2W-MATERIAL-READABILITY-CAMERA-20260720` |
| 阶段目录 | [WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/) |
| 预注册 | [WEB-60_R2W_阶段预注册合同.md](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_阶段预注册合同.md) |
| Web 构建 | [web_candidate_build_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/web_candidate_build_report.json) |
| Web 矩阵 | [bf3d_review_r2w_preview_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/bf3d_review_r2w_preview_report.json) |
| AO 审计 | [ao_consumption_audit.json](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/ao_consumption_audit.json) |
| 相邻层审计 | [interface_gap_audit.json](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/interface_gap_audit.json) |
| 独立视觉复核 | [independent_review_decisions.json](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/reports/independent_review_decisions.json) |
| 根结论 | [WEB-60_R2W_根审查结论.md](../PT/高炉3D模型/work/WEB_60_20260720_R2W_MATERIAL_READABILITY_AO_EDGE/WEB-60_R2W_根审查结论.md) |

固定复验命令：

```powershell
python tools\audit_bf3d_r2w_ao_consumption.py

& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background '高炉前端数据\models\gl02_blast_furnace_review.v5.blend' `
  --python 'tools\audit_bf3d_r2w_interface_gap.py'

python tools\build_bf3d_review_r2w_web.py
python tools\serve_bf3d_review_r2w.py --check-only
node tools\verify_bf3d_review_r2w_preview.cjs
```

预期信号：

- Web 构建范围为 `camera_only=true`；GLB、材质、灯光、曝光、环境、Tone Mapping
  和 AO 均未改变；
- 双轮矩阵为 `34/34` runs、`136` captures，五类错误 `0`，受保护文件不变，
  PBR 改写、禁止对象与黄色轮廓均为 `0`；
- 独立视觉复核只返回
  `conditional_pass_r2w_camera_readability_candidate_only`；
- ORM.R 为全 `255`，glTF `occlusionTexture` 和 Blend ORM.R 消费均不存在；
  `audit_passed=true`，但 `ao_consumption_ready=false`；
- 旧 P50 R3 的 UV 名称和对象身份与 V5 R2J 不兼容，
  `reuse_old_p50_atlas_allowed=false`；
- L03/L04 高度范围不重叠，覆盖率为 `0`，
  `adjacent_layer_continuity_passed=false`、`design_reference_required=true`；
- L03→L05 的 `14.816–49.456 mm` 必须标为非相邻诊断；`z=-1.2 m` 只标为
  冷却壁拼缝/端面剖切诊断。

失败关闭解释：相机可读性 PASS 只说明同一 V5 PBR 在受控近景中更容易看清，不表示
新增或消费了 AO，也不表示相邻层结构连续、P50/P60/P70/QA-70 或生产通过。受控收口器
`python tools\finalize_bf3d_r2w_stage.py` 会写阶段/根状态 JSON 和清单，只能由阶段
所有者在上述文档和证据锁定后执行，不属于只读复验命令。

## TEST-BF3D-R2X-R2J-AO-SMOKE1K-20260720

| 项目 | 受控值 |
|---|---|
| 对应需求 | `REQ-BF3D-R2X-R2J-AO-REBAKE-CONSUMPTION-20260720` |
| 阶段状态 | `r2x_machine_passed_three_visual_failed_closed` |
| 阶段目录 | [WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/) |
| 预注册 | [WEB-60_R2X_阶段预注册合同.md](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_阶段预注册合同.md) |
| 最终候选 | [gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/glb/gl02_blast_furnace_material_review.r2x-ao-smoke1k.v5payload.glb) |
| 重打包 / 独审 | [r2x_ao_v5_payload_repack_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_ao_v5_payload_repack_report.json)、[r2x_ao_smoke1k_v5payload_audit.json](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_ao_smoke1k_v5payload_audit.json) |
| Khronos | [khronos_gltf_validator_r2x_ao_v5payload.json](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/khronos_gltf_validator_r2x_ao_v5payload.json) |
| Three / pixel diff | [bf3d_review_r2x_representative_report.json](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/bf3d_review_r2x_representative_report.json) |
| 独立视觉 | [r2x_independent_visual_review.json](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/reports/r2x_independent_visual_review.json) |
| 根结论 | [WEB-60_R2X_根审查结论.md](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/WEB-60_R2X_根审查结论.md) |

受控复验命令：

```powershell
python tools\finalize_bf3d_r2x_stage.py --preflight
python tools\repack_bf3d_r2x_ao_v5_payload.py
python tools\audit_bf3d_r2x_ao_candidate.py
python tools\build_bf3d_review_r2x_web.py
python tools\serve_bf3d_review_r2x.py --check-only
node tools\verify_bf3d_review_r2x_preview.cjs
```

机器通过信号：

- 最终候选为 `1,115,216` bytes，SHA-256
  `bd074c23c237fe7ff3abac0f823bd9aef978021e4e829963b3f979e9b58f1c00`；
  五壳具有 `TEXCOORD_2/uv2`，AO texture 绑定 channel `2`，BaseColor、Normal、
  Roughness、Metalness channel 继续为 `0`。
- 非 AO V5 payload 保持，sampler 数量 `1→1`；Khronos `0 errors / 0 warnings`，
  独立审计 `audit_passed=true`。
- Chromium `1440×900` 代表测试共四张截图、两组 off/on pair；运行时只有
  `aoMapIntensity: 0→1` 改变，五类
  `console/page/http/external/request_failed`
  错误均为 `0`，受保护 V5、formal 与生产文件不变。

必须保留的失败证据：

- 首版候选 SHA
  `c8b748ef03b516a78de658a3b25a5f2265fef9bd34cea334a3490fba1fbab139`
  因越权新增第二个 clamp sampler 触发
  `UNAUTHORIZED_EXTRA_AO_CLAMP_SAMPLER`，结果为 `fail_closed`。
- 最终候选的全景和近景两组 `changed_pixels` 均为 `0`，每组 off/on PNG SHA
  完全相同；AO PNG `99.6763%` 为纯白，非白像素仅 `0.3237%`。因此
  `machine_three_passed=true` 但 `visual_gate_passed=false`，独立视觉结论必须是
  `fail_closed_ao_visual_signal_absent`。

四张代表截图：

- [global off](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/preview/screenshots/r2x_chromium_1440x900_global-off.png)
- [global on](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/preview/screenshots/r2x_chromium_1440x900_global-on.png)
- [detail off](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/preview/screenshots/r2x_chromium_1440x900_detail-off.png)
- [detail on](../PT/高炉3D模型/work/WEB_60_20260720_R2X_R2J_AO_REBAKE_CANDIDATE/preview/screenshots/r2x_chromium_1440x900_detail-on.png)

失败关闭边界：`full_matrix_executed=false`。本测试不得触发 2K，不批准
P50/P60、正式 GLB、生产 8092 或下一发布阶段，也不能把 AO 机器绑定通过描述为“具体
材质已经可见”。后续验证应针对可见几何接触源、材质检视照明、近景模式和权威结构参考，
禁止用黑圆环或 BaseColor 改色伪造视觉通过。

## TEST-BF3D-R2Y-MATERIAL-SIGNAL-DIAGNOSTIC-20260720

用途：分离验证 R2Y 的输入哈希、PBR raw signal、AO UV/相机命中、Three.js 代表
fixture 与最终视觉边界；仅为 `E/diagnostic`。

```powershell
python tools\verify_bf3d_r2y_input_gate.py
python tools\audit_bf3d_r2y_ao_uv_hit.py
python tools\audit_bf3d_r2y_pbr_texture_signal.py
python tools\build_bf3d_review_r2y_web.py
python tools\serve_bf3d_review_r2y.py --check-only
node tools\verify_bf3d_review_r2y_preview.cjs
```

预期结果：

- 前五个入口必须成功；输入和受保护资产前后哈希不变；
- CPU UV/AO 门通过，全景/近景 mip 非白可见像素分别为 `785 / 6483`；
- 代表 verifier 捕获 Chromium `1440×900` 下的 13 个状态，五类错误为 `0`；
- 最后一个命令当前预期退出 `1`，因为 macro `0.962958 < 1`、anisotropy
  `1.021708 < 1.03`、environment changed ratio/mean diff 均为 `0`。这是预注册
  fail-closed，不是基础设施运行失败；
- AO WebGL liveness 必须保持 `NOT_EXECUTED`；不得把 CPU 命中或 raw-signal PASS
  合并写成阶段 PASS。

权威输出：

- [CPU AO/UV 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_ao_uv_hit_raster_audit.json)
- [PBR raw signal 报告](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_pbr_texture_signal_audit.json)
- [代表报告](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/bf3d_review_r2y_representative_report.json)
- [独立审查](../PT/高炉3D模型/work/WEB_60_20260720_R2Y_MATERIAL_SIGNAL_VISIBILITY_DIAGNOSTIC/reports/r2y_independent_review_decisions.json)

失败关闭边界：完整浏览器/视口矩阵未执行；不批准 beauty、Golden、2K、P50/P60、
正式 GLB 或生产替换。

## TEST-BF3D-ASSET-CONTROLLED-MASTER-R1-20260721

对应需求：`REQ-BF3D-ASSET-CONTROLLED-MASTER-R1-20260721`。

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\build_controlled_master_r1.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\verify_controlled_master_r1.py'
node tools\validate_bf3d_glb_khronos.cjs --module-dir 'PT\高炉3D模型\work\WEB_60_20260720_R2U_SECTION_CAP_CONTROLLED_V4\vendor\gltf-validator-runtime' --asset 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\glb\bf3d_base.r1.glb' --asset 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\glb\bf3d_sensors.r1.glb' --asset 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\glb\bf3d_combined_review.r1.glb' --asset 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\glb\bf3d_structural_section.r1.glb' --output 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\reports\khronos_gltf_validator_r1.json'
```

预期：输入哈希门通过；母版十个模块集合齐全；静压力点18个；四个GLB网格计数为 `5/18/23/10`；禁用对象为0；Khronos四资产均为0错误、0警告；正式GLB哈希不变。

浏览器运行态补充：打开 `http://127.0.0.1:8095/高炉前端数据/bf3d_controlled_master_r1.server.html`，依次点击组合审查、基础炉体、18点传感器、结构剖面。预期Three.js网格数分别为 `23 / 5 / 18 / 25`，其中结构剖面的25个Web网格来自10个源对象按材质primitive拆分；四项状态均为“可用”，控制台错误和警告为0，页面无横向溢出。证据见[浏览器组件复核报告](../PT/高炉3D模型/work/ASSET_10_20260721_R1_CONTROLLED_MASTER/reports/browser_component_review.json)。

完整总装补充：`bf3d_full_assembly.r1.glb`必须在Blender工厂导入为33个对象，其中5个外壳、10个R2J/R2K结构对象、18个静压力点；Khronos必须为0错误、0警告。浏览器“整体高炉”和“整体剖切”必须加载同一总装GLB并显示 `48/48` Web网格；前者可见23个网格，后者可见43个网格，二者静压力均为18/18，控制台错误/警告为0。

Blender 直接打开工程补充：

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\create_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\verify_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\render_direct_open_internal_default_preview.py'
```

预期：输出 `.blend` 可由 Blender 5.2 原生复开，并同时存在 `内部工艺_默认 / 完整外观 / 墙体分层` 三个视图层。默认帧为 `432`，活动视图层必须为 `内部工艺_默认`；可见网格总数 `113`，其中矿焦料柱/料面 `11`、内部剖面 `10`、黄色静压力 `18`、布料溜槽 `9`、受控模拟内部模块 `54`。内部模拟模块固定为软熔带 `1`、统一响应回旋区 `26`、死料柱 `1`、滴落液滴 `24`、铁水/炉渣液面 `2`，必须带 `illustrative/simulated` 与 `control_use=prohibited` 标签。默认层可见辅助线为 `0`；`完整外观` 只显示整壳与静压力，`墙体分层` 只显示 R2J/R2K 与静压力。复开报告和视觉门均必须 `passed=true`。

Web 边界：现有 `bf3d_full_assembly.r1.glb` 仍只验证结构总装，文件头保持 `glTF/version 2` 且哈希锁定；上述新增工艺仿真模块尚未纳入该 GLB。GLB 必须通过“文件→导入→glTF 2.0”加载，不得使用“文件→打开”。

## TEST-BF3D-COMPLETE-EXTERIOR-COHESIVE-DRIP-ANIMATION-R2-20260721

对应需求：`REQ-BF3D-COMPLETE-EXTERIOR-COHESIVE-DRIP-ANIMATION-R2-20260721`。

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\create_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\verify_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\render_direct_open_exterior_preview.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_FULL_ASSEMBLY_R1_DIRECT_OPEN.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\render_direct_open_animation_keyframes.py'
```

成功信号：

- 源审查壳圆周覆盖审计为 `301.5°`，新 `BF3D_R2_COMPLETE_EXTERIOR` 固定为 5 个 `360°` 闭合区段；
- `完整外观` 可见网格为 `23`：闭合外壳 `5`、静压力 `18`、Section `0`、SIM `0`；
- 时间轴为 `1–480`、`24 fps`；软熔带五个高度样本总变化不小于 `0.75 m`；
- 液滴 01 在帧 `1/49/96/97` 的 Z 位置约为 `+4.35/-5.15/-16.85/+4.35 m`，完整落距大于 `20 m`，循环重生有效；
- 复开、完整外观视觉门、动画双关键帧视觉门全部 `passed=true`。

失败边界：不得用换相机视角掩盖 58.5° 开口；不得把 R2 旋转重建外壳解释为施工几何；不得把时间轴示意动画解释为 C2、CFD、实测液滴或生产控制输出。现有 Web GLB 未同步 R2 对象。

## TEST-BF3D-COMPLETE-EQUIPMENT-PRESENCE-AUDIT-20260721

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_CONTROLLED_MASTER_R3_EQUIPMENT_MERGED.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\audit_complete_equipment_presence.py'
```

当前预期（R3 完成门）：炉顶设备网格 `2`、炉缸底部临时闭合网格 `1`、两个铁口相关网格 `3`、风口/围管可见总成网格 `3`、逐风口位置锚点 `26`；回旋区模拟仍单独为 `26`，报告必须保持 `tuyere_hardware_must_not_be_inferred_from_raceway_simulation=true`，并令 `complete_equipment_assembly_present=true`、缺失设备列表为空。炉缸底部详细建模必须保持 `deferred_after_interim_visible_closure`。

## TEST-BF3D-CONTROLLED-EQUIPMENT-MERGE-R3-20260721

对应需求：`REQ-BF3D-CONTROLLED-EQUIPMENT-MERGE-R3-20260721`。

```powershell
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\create_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_CONTROLLED_MASTER_R3_EQUIPMENT_MERGED.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\verify_full_assembly_direct_open_blend.py'
& 'D:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\blends\BF3D_CONTROLLED_MASTER_R3_EQUIPMENT_MERGED.blend' --python-exit-code 1 --python 'PT\高炉3D模型\work\ASSET_10_20260721_R1_CONTROLLED_MASTER\scripts\render_controlled_equipment_details.py'
```

成功信号：

- P40 输入 SHA-256 必须为 `d268759a0e923cf9412da91400cee85e7b94e3418c1c41363053a15c372dd478`，仅允许附加登记白名单中的对象；
- R3 母版与兼容直开副本字节一致，SHA-256 为 `5e5298d014e61be8ec0949367e2b40fb3f7d82f8cc544e5c0ecf9956e96d5640`；
- `完整外观` 可见网格 `32 = 5闭合炉壳 + 18静压力 + 9设备`，Section/SIM 均为 `0`；`内部工艺_默认` 可见设备网格 `9`；`墙体分层` 设备网格 `0`；
- 26个风口锚点编号连续、同高 `Z=-11.8 m`、圆周半径约 `2.8886 m`；不得从26个回旋区模拟反推风口设备；
- 炉顶、风口/围管、铁口三个设备近景视觉门均 `passed=true`；复开失败项和可见辅助线均为 `0`。

边界：R3 是 Blender 受控母版，不覆盖 R1 基线，不同步现有 Web GLB；炉缸底部仅为可见闭合占位，冷却、砖衬、基础和施工结构必须等待后续单独建模。

## TEST-BF3D-IMG2THREEJS-PROTOTYPE-20260724

对应需求：`REQ-BF3D-IMG2THREEJS-PROTOTYPE-20260724`。

启动页面：

```powershell
python -m http.server 8096 --bind 127.0.0.1
```

规格门：

```powershell
python <img2threejs>\forge\stage1_intake\probe_image.py 'PT\高炉3D模型\work\WEB_60_IMG2THREEJS_20260724_R1\reference\gl02_blast_furnace_exterior_layered_reference.png'
python <img2threejs>\forge\stage1_intake\check_reference_admission.py 'PT\高炉3D模型\work\WEB_60_IMG2THREEJS_20260724_R1\reference\gl02_blast_furnace_exterior_layered_reference.png' --viewpoint three-quarter-front --json
python <img2threejs>\forge\stage2_spec\validate_sculpt_spec.py 'PT\高炉3D模型\work\WEB_60_IMG2THREEJS_20260724_R1\spec\object_sculpt_spec.json' --strict-quality --json
```

本机浏览器矩阵：

```powershell
$env:BF_PLAYWRIGHT_CORE_URL='file:///C:/Users/hmw20/.codex/playwright-runtime/node_modules/playwright/node_modules/playwright-core/index.mjs'
node tools\verify_bf3d_img2threejs_preview.mjs
```

成功信号：

- 参考图 `1024×1536`，准入通过，最大连通主体比例 `0.9513`；
- PBR 五通道提取 `confidence=0.86`；
- 严格规格 `ok=true`、25 构件、4 材质；
- 页面为 `ready`，合同通过，八层均可恢复显示；
- 分层隐藏/恢复、45% 展开/复位、灰模、风口聚焦和参考图折叠全部闭环；
- 页面统计为 `239` 网格、`424` 实例构件、`134,720` 三角面；
- Chromium 九视口、Firefox/WebKit 各四个代表视口，共 `17/17` 通过、失败项 `0`。

权威报告：

- [浏览器矩阵 JSON](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.json)
- [浏览器矩阵 Markdown](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.md)
- [img2threejs 管线报告](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/img2threejs_pipeline_report.md)

失败边界：不得把生成图的附属结构解释为现场实测、BIM 或施工几何；不得覆盖正式 GLB 或切换 8092 生产路由。

## TEST-BF3D-IMG2THREEJS-SEMANTIC-DETAIL-R2-20260724

对应需求：`REQ-BF3D-IMG2THREEJS-SEMANTIC-DETAIL-R2-20260724`。

本机浏览器矩阵：

```powershell
$env:BF_PLAYWRIGHT_CORE_URL='file:///C:/Users/hmw20/.codex/playwright-runtime/node_modules/playwright/node_modules/playwright-core/index.mjs'
node tools\verify_bf3d_img2threejs_preview.mjs
```

成功信号：

- 页面为 `ready`，运行合同为“合同通过”；
- 工艺大区 `8`，L7～L16 `10` 层，炉体测温 `80` 点；
- 正式传感器 `115`，新增静压力 `18`，风口 `26`，出铁口 `2`；
- 方位状态固定为 `relative_only`，页面不得显示东南西北结论；
- 工艺区、L10、80 点总开关和出铁口设备可隐藏并由“全部显示”恢复；
- 80 点总开关关闭时，L7～L16 单层开关禁用；恢复后重新启用；
- 展开滑块 `45% → 0%` 反馈正确，灰模开关可逆；
- 风口、出铁口、进料口近景和参考图折叠可执行；
- 页面统计为 `284` 网格、`599` 实例构件、`198,456` 三角面；
- Chromium 九视口、Firefox/WebKit 各四个代表视口，共 `17/17` 通过、失败项 `0`；
- 页面错误、控制台错误、资源失败和页面横向溢出均为 `0`。

权威证据：

- [R2 需求追踪](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/REQ-BF3D-IMG2THREEJS-SEMANTIC-DETAIL-R2-20260724_追踪.md)
- [浏览器矩阵 JSON](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.json)
- [浏览器矩阵 Markdown](../PT/高炉3D模型/work/WEB_60_IMG2THREEJS_20260724_R1/reports/browser_matrix.md)

失败边界：不得把正式 115 点与新增 18 点混为一组；不得把 3 个旧静压力节点复制成 18 个实测值；不得伪造单风口差异；不得把诊断覆盖层解释为断开的机械炉壳。

## TEST-BF3D-FURNACE-BODY-BILLBOARD-R1-20260725

对应需求：`REQ-BF3D-FURNACE-BODY-BILLBOARD-R1-20260725`。

本机验证：

```powershell
$env:BF_PLAYWRIGHT_CORE_URL='file:///C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core/index.mjs'
node tools\export_bf3d_furnace_body_billboard_asset.mjs
node tools\verify_bf3d_furnace_body_billboards.mjs
node tools\capture_bf3d_asset_catalog_previews.mjs
node tools\verify_bf3d_asset_catalog.mjs
```

成功信号：

- 本体 GLB 中正式传感器、静压力、非实体数据环和上料/外部除尘节点均为 `0`；
- 点位清单为正式传感器 `115`、静压力 `18`、总计 `133`；
- 网页创建 `133` 个 `THREE.Sprite`，图层切换、查找、点选和数据适配器通过；
- Chromium 1440×900 与 390×844 无横向溢出、控制台错误或页面错误；
- Khronos glTF Validator 错误 `0`，GLB 可移植性 `release_ready=true`；
- 分布式资产库共 `9/9` 加载与完整性验证通过。

证据：

- [本体与 Billboard 需求追踪](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard/REQ-BF3D-FURNACE-BODY-BILLBOARD-R1-20260725_追踪.md)
- [网页运行时报告](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard/billboard_validation_report.json)
- [点位清单](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard/sensor_billboards.v1.json)
- [资产库完整性报告](../PT/高炉3D模型/模型资产库/asset_catalog_validation.json)

失败边界：Billboard 是网页运行时数据层，默认数值为空；不得把测试值写入资产、
不得把坐标清单解释为新增实测数据，也不得切换 8092 生产路由。

## TEST-BF3D-FURNACE-BODY-BILLBOARD-CN-R1-20260725

对应需求：`REQ-BF3D-FURNACE-BODY-BILLBOARD-CN-R1-20260725`。

本机验证：

```powershell
node tools\build_bf3d_furnace_body_billboard_cn_variant.mjs
$env:BF_PLAYWRIGHT_CORE_URL='file:///C:/Users/hmw20/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core/index.mjs'
node tools\verify_bf3d_furnace_body_billboards_cn.mjs
node tools\capture_bf3d_asset_catalog_previews.mjs
node tools\verify_bf3d_asset_catalog.mjs
```

成功信号：

- 中文点位清单为 `133` 项，且 `133/133` 个缩写均含中文；
- 中文版与原 09 资产的原始 ID 集合完全相同，唯一 ID 为 `133`；
- `SENSOR_T_taphole_1/2` 分别显示“南铁口温/北铁口温”；
- `SENSOR_T_body_L10_A` 显示“身下温·L10A”；
- `GL02_INT30_PRESSURE_MIDDLE_B` 显示“身中静压·B”；
- 运行时 locale 为 `zh-CN`，`THREE.Sprite` 为 `133`；
- Chromium 1440×900 与 390×844 通过，资产总库 `10/10` 通过。

证据：

- [中文版本需求追踪](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard_cn/REQ-BF3D-FURNACE-BODY-BILLBOARD-CN-R1-20260725_追踪.md)
- [中文逐点映射](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard_cn/cn_label_mapping.v1.json)
- [中文版本验证报告](../PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard_cn/cn_variant_validation_report.json)

失败边界：不得改写点位 ID、坐标、类别或实时数据绑定键；中文缩写只属于显示层。
# REQ-BF3D-BILLBOARD-PSPACE-LIVE-20260726

- 合同测试：
  `python -m pytest tests\test_pspace_billboard_realtime_bridge.py -q`。
  成功信号为 140 个兼容流字段、133 个 Billboard `point_meta`、
  `billboard_mapped=133`、缺失为 0。
- 浏览器测试：
  `node tools\verify_bf3d_furnace_body_billboards_cn.mjs`。
  测试在页面加载前安装 pSpace WebSocket 合同桩，向 133 个
  `canonical_id` 下发真实帧形状的值、时间和 `Good` 质量码；桌面与手机均需
  通过，控制台/页面错误为 0。
- 生产验收：
  [受控远端发布脚本](../tools/remote_deploy_8094_billboard_pspace_live.ps1)
  新建并启动独立 `V4BillboardPspace8770`，不重启 8768；随后运行
  `python tools\verify_billboard_pspace_8770.py` 读取真实 WebSocket tick；必须返回
  `stream_value_count=140`、`billboard_meta_count=133`、
  `numeric_billboard_values=133`、`quality_metadata_count=133`、
  `billboard_missing_count=0` 和 `required_keys_present=true`。
- 背景验收：8094 与独立预览均应默认 `soft-light/#eef2f1`，背景控件必须包含
  护眼浅灰、纯白、钢灰、深色和自定义；切换背景不得重启或改动 8768/8770。

## 8093/8094 炉顶压力“如何”趋势回归（2026-07-26）

- 精确提示词：`最近半小时炉顶压力如何？`
- 路由断言：`mcp_prefetch_used=true`、`mcp_prefetch_kind=statistics`、
  `mcp_prefetch_variables=["P_top"]`。
- 内容断言：回答必须包含半小时时间范围、数值范围、平均值、起止变化和
  上升/下降/平稳趋势；不得出现“未提供连续数据”或“无法判断”。
- 单元与图表回归：
  `python -m pytest 高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py
  高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py -q`，应为 `41 passed`。
- 2026-07-26 现网结果：8093、8094 均 HTTP 200、自动验收通过，并各产生一次
  MCP statistics 工具结果。

## TEST-MCP-AGENT-ORCHESTRATION-20260726

- 对应需求：`REQ-MCP-AGENT-ORCHESTRATION-20260726`。
- 测试文件：
  [test_mcp_agent_orchestration.py](../高炉前端数据/智能助手/tests/test_mcp_agent_orchestration.py#L28)。
- 覆盖内容：合法调用、未知工具、Schema 外 SQL 参数、缺少必填参数、错误枚举、
  数组/载荷上限、多步分析路由、纯知识问题不误触发，以及流式入口保持多轮工具
  执行。
- 回归命令：
  `python -m pytest 高炉前端数据/智能助手/tests/test_mcp_agent_orchestration.py
  高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py
  高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py -q`。
- 预期与实测：`49 passed`。
- 现网测试：8093/8094 对半小时顶压与总压差相关性问题均执行
  `find_gl02_variables × 2 + plot_gl02_analysis × 1`，HTTP 200、自动验收通过；
  [结果 JSON](../logs/8093_8094_mcp_agent_orchestration_acceptance_20260726.json)。

## TEST-MCP-AGENT-LATENCY-20260726

- 对应需求：`REQ-MCP-AGENT-LATENCY-20260726`。
- 测试文件：
  [test_mcp_latency_optimization.py](../高炉前端数据/智能助手/tests/test_mcp_latency_optimization.py)。
- 覆盖：相关性复合单工具计划、规划上下文排除完整炉况/RAG、低温度和小输出
  默认值、成功结果缓存、失败结果不缓存、规划预算和工具超时接线。
- 基线保护测试：
  `python tools/restore_mcp_route_baseline.py --verify`，必须显示3个文件全部
  `ok=true`；不得在常规测试中运行`--restore`。
- 全量相关回归结果：`54 passed`。
- 现网性能验收：同题工具调用由3次降至1次；8093优化后样本15.43/25.94秒，
  8094优化后16.32秒；固定统计路由仍为HTTP 200和自动通过。
- 证据：
  [性能验收JSON](../logs/8093_8094_mcp_latency_optimization_acceptance_20260726.json)。

## TEST-MCP-BUSINESS-OBJECT-CATALOG-20260726

- 对应需求：`REQ-MCP-BUSINESS-OBJECT-CATALOG-20260726`。
- 测试文件：
  [test_business_object_catalog.py](../高炉前端数据/智能助手/tests/test_business_object_catalog.py)。
- 覆盖：
  - 7个catalog JSON文件存在且可解析；
  - 9种业务对象类型齐全；
  - 每个对象满足统一必填合同；
  - 18个静压力点全部进入sensor目录；
  - 炉顶压力、铁水硅、炉渣、进料、日报和相关图表可搜索；
  - list/get/search工具合同和未知对象错误。
- 回归命令：
  `python -m pytest 高炉前端数据/智能助手/tests/test_business_object_catalog.py
  高炉前端数据/智能助手/tests/test_mcp_latency_optimization.py
  高炉前端数据/智能助手/tests/test_mcp_agent_orchestration.py
  高炉前端数据/智能助手/tests/test_qa_latency_optimizations.py
  高炉前端数据/智能助手/tests/test_mcp_chart_expansion.py -q`。
- 结果：`61 passed`；8093/8094统一目录口语2/2自动通过。
- 证据：
  [目录验收JSON](../logs/8093_8094_business_object_catalog_acceptance_20260726.json)。

## TEST-MCP-CONVERSATION-CONTEXT-20260726

- 测试文件：
  [test_mcp_conversation_context.py](../高炉前端数据/智能助手/tests/test_mcp_conversation_context.py)、
  [test_business_object_catalog.py](../高炉前端数据/智能助手/tests/test_business_object_catalog.py)。
- 覆盖：首轮对象/时间记录、低信息追问继承、时间替换、对象合并与替换、图表
  切换、相关矩阵优先级、latest不误触发图表、确定性事实回答、未知变量ID禁止
  模糊匹配。
- 相关回归：
  `python -m pytest test_mcp_conversation_context.py test_business_object_catalog.py
  test_mcp_latency_optimization.py test_mcp_agent_orchestration.py
  test_qa_latency_optimizations.py test_mcp_chart_expansion.py -q`。
- 结果：`76 passed`。
- 现网多轮：
  `python tools/test_8093_mcp_context_followups.py
  --output logs/8093_mcp_context_followups_20260726.json`，结果`7/7`。
- 关键四问：
  `python tools/test_8093_colloquial_prompts.py --groups mcp
  --case mcp_latest_probe_pair --case mcp_latest_top_gas_pressure_abcd
  --case mcp_latest_cold_blast_pressure --case mcp_latest_oxygen_pair`，
  结果`4/4`自动通过，中位总耗时`1117.6ms`，回答包含正式中文名和单位。
- 无Prompt直连：
  `python tools/test_mcp_direct_no_prompt.py
  --output logs/mcp_direct_no_prompt_20260726.json`，结果4/4，总耗时
  `3730.5ms`；报告明确`llm_used=false/qa_router_used=false/rag_used=false`。
## TEST-PT-SIX-PRODUCTION-ANALYTICS-20260726

- 对应需求：`REQ-PT-SIX-PRODUCTION-ANALYTICS-20260726`
- 测试文件：[tests/test_pt_six_analysis_modules.py](../tests/test_pt_six_analysis_modules.py)
- 命令：

  ```powershell
  python -m pytest -q tests/test_pt_six_analysis_modules.py --basetemp .tmp/pytest_pt_six
  ```

- 验证范围：六个入口均能读取标准CSV并生成各自结果；测试样本贯通炉次、Si、
  炉况质量、矿焦批次、分钟传感器和烧结矿背景。
- 2026-07-26 实际结果：`1 passed`。默认系统临时目录曾返回 WinError 5，改用
  工作区内受控 `--basetemp` 后通过，该错误与模块逻辑无关。
## TEST-HEAT-MULTISOURCE-EXPLORER-20260727

- 需求：`REQ-HEAT-MULTISOURCE-EXPLORER-20260727`
- 本地契约：`tests/test_heat_service.py`、`tests/test_external_sources.py`、
  `tests/test_heat_data_explorer_contract.py`、
  `tests/test_heat_dashboard_si_distribution.py`。功能改造后首次完整回归为
  `17 passed`；移动端 CSS 定点修复后，JavaScript `node --check` 与 4 个前端
  直接契约断言再次通过。
- 远端 API：31 项目录；Vastbase 双账号、PostgreSQL、pSpace ready；
  IMES Web `authorization_required`；正式炉次 `2#20260726-345` 以
  `heatno+batchno` 双键精确返回；CSV/XLSX 文件头通过。
- 远端页面：真实 pSpace UI 查询返回 2 行；Chromium 固定视口
  `1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`、
  `1024×768`、`768×1024`、`390×844`、`375×667` 为 9/9；无页面横向
  溢出、核心查询按钮可达、表格内部可滚动、宋体生效、浏览器错误 0。
- 证据：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8891_multisource_20260727\8891_multisource_acceptance.json`
  及同目录截图。Firefox、WebKit、现场 Edge 本次未执行，不能写成完整跨浏览器通过。

## TEST-BF3D-8094-SURFACE-CAMERA-GUARD-20260801

- 对应需求：`REQ-BF3D-8094-SURFACE-CAMERA-GUARD-20260801`。
- 本地静态验证：

  ```powershell
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8094.js
  python -m py_compile tools/patch_8094_surface_camera_guard.py tools/verify_remote_8094_surface_camera_guard.py
  python tests/test_8094_surface_camera_guard_contract.py
  ```

- 契约结果：`2 tests OK`。补丁器幂等且会备份；守卫必须替换旧炉心滚轮处理器、
  设置炉壳表面 target 并在向内移动前执行壳体 Raycast。
- 远端交互：Chrome/CDP 打开真实 8094 页面，确认 133 个 Billboard；连续 54 次
  向内滚轮最多在首次碰撞时即停止，真实炉壳法向间距为 `1.200m`，target 保持
  同一炉壳表面点；点击“全景”后仍为 `shell-raycast` 表面 target。
- Chromium 视口：`1280×720`、`1366×768`、`1440×900`、`1546×864`、
  `1920×1080`、`1024×768`、`768×1024`、`390×844`、`375×667` 全部通过；
  无页面横向溢出、3D 视口可见、守卫就绪、target 模式为 `furnace-surface`。
- 证据：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8094_surface_camera_guard_20260801_r1`。
  Firefox、WebKit、现场 Edge 未执行。

## TEST-BF3D-8093-NEAR-CLIP-20260801

- 对应缺陷：`BUG-BF3D-8093-NEAR-CLIP-20260801`。
- 本地验证：

  ```powershell
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8094.js
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8093.js
  python -m py_compile tools/verify_remote_8093_furnace_body_no_simulation.py tools/run_remote_22012_with_local_deps.py
  python -m unittest tests.test_8093_furnace_body_no_simulation_contract
  ```

- 结果：语法检查通过，`2 tests OK`。契约覆盖 8093 缓存版本、`0.05m`
  端口专属近裁剪面、滚轮纠偏、周期纠偏和运行时纠偏计数；8094 默认端口分支
  不启用该锁定。
- 部署探针：远端磁盘和 8093 HTTP 返回同时包含新标记；入口哈希
  `01231424...D462F9`，共享守卫哈希 `0C331DE1...AB929`，主页面哈希
  `8DF482B7...01B9D6`；外层入口和模块内部均使用 `near-plane-r4`；资源回滚目录
  包含 2 文件，主页面另有独立回滚备份。
- 真实 Chrome 核心回归：10 次标准 `WheelEvent` 后停止在炉壳外 `1.2m`；
  `cameraNear=0.05m < signedShellGap=1.2m`；模型、133 点、端口作用域、无仿真
  面板、无仿真运行时和浏览器错误 0 均通过，共 10/10 核心断言。
- 核心报告：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8093_near_plane_fix_20260801_r8\8093_furnace_body_no_simulation_acceptance.json`。
- 本轮没有生成新截图或重跑 45 组合：服务器无界面 Chrome 的截图和尺寸切换
  超过单次 5 秒等待限制。布局仍引用
  `8093_furnace_body_no_simulation_20260801_r1` 的 45/45 基线；Firefox、WebKit、
  现场 Edge 与用户端视觉复核待补。

## TEST-BF3D-8093-FURNACE-BODY-NO-SIM-20260801

- 对应需求：`REQ-BF3D-8093-FURNACE-BODY-NO-SIM-20260801`。
- 本地契约与语法：

  ```powershell
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8094.js
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8093.js
  python -m py_compile tools/patch_8093_furnace_body_no_simulation.py tools/verify_remote_8093_furnace_body_no_simulation.py
  python tests/test_8093_furnace_body_no_simulation_contract.py
  ```

- 契约结果：`2 tests OK`。验证 21 个静压兼容点、两处 viewer 句柄合同、133 点
  适配器、8093 端口作用域相机、内联 favicon，以及内部仿真 JS/CSS 均未加载。
- 远端资产：`models/gl02_blast_furnace.glb` 为 `8,229,120` bytes，SHA-256
  `150DF18B68F0410B9A168F80C2DF34EFDA86384FC51D37226F81C2ACD244ED53`。
- Chrome 真实交互：133 点；schema 为
  `bf3d.surface-camera-shell-guard.8093.v1`；连续滚轮触发炉壳碰撞并停在 `1.2m`；
  仿真面板数量 0，仿真运行时不存在。
- Chromium 完整矩阵：总览、炉况诊断、参数优化建议、趋势分析、智能问答 ×
  `1280×720`、`1366×768`、`1440×900`、`1546×864`、`1920×1080`、
  `1024×768`、`768×1024`、`390×844`、`375×667`，共 45/45 通过；无页面
  横向溢出、正式头部可见、浏览器错误 0。
- 证据：
  `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\acceptance\8093_furnace_body_no_simulation_20260801_r1`。
  Firefox、WebKit、现场 Edge 未执行。

## TEST-BF3D-8093-DUAL-CAMERA-MODES-20260801

- 对应需求：`REQ-BF3D-8093-DUAL-CAMERA-MODES-20260801`；本节取代上文 v1
  固定表面 target 的相机交互口径，但不推翻 45/45 页面布局基线。
- 本地语法与契约：

  ```powershell
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8093.js
  python -m py_compile tools/patch_8093_furnace_body_no_simulation.py tools/remote_deploy_8093_dual_camera_modes.py tools/deploy_8093_dual_camera_modes_smb.py tools/verify_remote_8093_furnace_body_no_simulation.py
  python -m unittest tests.test_8093_furnace_body_no_simulation_contract tests.test_8093_dual_camera_deploy
  ```

- 结果：JavaScript、4 个 Python 文件均通过语法检查；模型纠错后 `4 tests OK`。契约覆盖
  `bf3d.camera.dual-mode.8093.v2`、炉心 target、全模型包围半径、无限方位角、
  累计方位行程、Billboard 聚焦、动态方位 Raycast、退出复位和 8094 隔离；临时
  根目录部署测试还验证备份存在、8093 原子替换成功、8094 页面及运行时哈希不变；
  新增契约固定专项页只能加载 `GL02_FURNACE_BODY_R1.glb`、`8,229,120` bytes 和
  受控 SHA-256，不得退回本机 `4,314,736` bytes 的同名旧模型。
- 模型纠错：首次记录的累计 `650.8°`、动态更新 `8→125` 和碰撞结果来自错误的
  本机旧模型，只保留为算法原型历史，不属于正式模型验收。
- 正确资产浏览器冒烟：`GL02_FURNACE_BODY_R1` 实际/预期字节数均为 `8229120`，
  `assetVerified=true`，133 点、`overview/furnace-center`、near `0.050m`、包围半径
  `25.769`，浏览器 error/warning 为 0。完整旋转、点位聚焦与碰撞交互待按正确
  资产重新执行。
- 未完成项：截至记录时远端 8093 未部署，故不能把本机专项结果表述为 220.12
  验收。远端恢复后运行
  `tools/remote_deploy_8093_dual_camera_modes.py` 与
  `tools/verify_remote_8093_furnace_body_no_simulation.py`，再补远端 Edge、Firefox、
  WebKit 及规定视口矩阵。

## TEST-BF3D-8093-MEASURED-121-OVERVIEW-20260801

- 对应需求：`REQ-BF3D-8093-MEASURED-121-OVERVIEW-20260801`；本节取代上文双相机/点位聚焦运行口径，不推翻既有页面布局基线。
- 验证命令：

  ```powershell
  node --check 高炉前端数据/assets/bf3d-physical-point-filter-8093.js
  node --check 高炉前端数据/assets/bf3d-surface-camera-guard-8093.js
  python -m py_compile tools/remote_deploy_8093_physical_points_overview.py tests/test_8093_physical_points_overview.py
  python -m unittest tests.test_8093_physical_points_overview tests.test_8093_furnace_body_no_simulation_contract
  ```

- 结果：JavaScript 与 Python 语法通过；`Ran 7 tests / OK`。测试固定 121 个可见点、12 个排除点、100 个炉壳物理点、21 个设备实测点、左侧变量面板零改动、点位聚焦缺失、炉心 target、全模型半径、无限方位角和 8094 三项资源哈希隔离。
- 远端静态验收：8093 页面、筛选器和相机资源均为 HTTP 200；页面版本为 `20260801-measured121-r2` 与 `20260801-overview-only-r6`。部署备份为 `F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_measured121_overview_20260801\20260801_202127`。
- 浏览器边界：正式页加载超过用户限定的单次 5 秒操作窗口，本轮没有通过延长等待补做全量视觉矩阵；不得把静态/契约验收写成 Firefox、WebKit 或现场 Edge 已通过。

## TEST-BF3D-8094-CAD-BOTTOM-BAND-20260804

- 对应故障：`BUG-BF3D-CAD-BOTTOM-BAND-20260804`。
- 验证命令：

  ```powershell
  python -m unittest -v tests.test_8094_cad_bottom_band_fix
  python -m py_compile tools/patch_8094_cad_bottom_band.py
  ```

- 结果：3 项合同测试通过，补丁器语法通过；覆盖首次插入、`bottom:0` 及紧凑断点、幂等重复执行和无关页面拒绝。
- 远端结果：8094 HTML 备份后更新并 HTTP 200；页面标记存在；8094 任务 Running；8093、8094、8768、8770 进程未变化；8093 返回内容前后一致。
- 浏览器结果：Chrome 现场页在 `1552×816` 读取到补丁运行时样式，stage/viewer 底部差值约 `1px`，横向溢出为 0。实时数据等待态下未宣称完成全量跨浏览器矩阵。

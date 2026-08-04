# front2：8094 工业工作台预览

`front2` 是 8093 五个生产页面的独立样式与布局分支。原始页面 `../frontend_dashboard_v3.server.html` 不被替换；实时数据、诊断、Chronos、问答、项目/报表和自动值守仍沿用既有后端契约。

## 设计边界

- 参数优化建议页是视觉母版：钢灰面板、低饱和青绿主操作色、琥珀警示色、7px 以内圆角和 12px 桌面间距。
- 总览、炉况诊断、趋势分析和智能问答只调整表面、密度、布局比例和响应式规则。
- 诊断类别色及安全/关注/高风险语义色保持不变。
- 正式品牌头部、五个 hash 路由、WebSocket 消息、同源 API、SSE 流式问答和所有现有交互保持不变。

## 本机预览

从本目录运行：

```powershell
python start_front2.py --host 127.0.0.1 --port 8094 --ws-port 8767 --strictPort
```

入口：`http://127.0.0.1:8094/?ws_port=8767#overview`

启动脚本继续调用原后端 `../智能助手/backend/ollama_proxy_server.py`，并保持 `BF_FRONTEND_DIR=高炉前端数据`；仅把 `BF_INDEX_FILE` 指向 front2。数据库账号、登录配置和模型地址只从既有环境读取，不写入本目录。

## 静态契约检查

```powershell
python verify_front2_static.py
```

检查包括：原 8093 基线哈希未变化、五个路由、WebSocket/Chronos、问答 SSE、正式头部、趋势历史/自动值守标记、front2 主题入口，以及诊断结论工业高炉资产覆盖。

诊断结论区使用 `assets/blast-furnace-cutaway-industrial-v1.png` 替换 front2 渲染态中的高饱和火焰 SVG。该覆盖只改变视觉资产和布局，不改诊断数据、阈值、文案或交互；8093 原页面保持不变。

本机 Python 无法读取系统级 `psycopg` 时，可把驱动隔离安装到本目录；启动脚本会自动加入该目录，不影响原后端入口：

```powershell
python -m pip install --target '.\.python_packages' 'psycopg[binary]'
```

Chromium 5 路由 × 9 个 viewport 的本次结果位于 `../../logs/front2_iab_matrix_20260713_final/manifest.json`；Firefox、WebKit 和现场 Edge 冒烟仍是生产交付前置项。

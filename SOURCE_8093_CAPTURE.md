# 8093 运行源码捕获记录

捕获时间：2026-07-06 20:23 左右（Asia/Shanghai）

## 已复制内容

- 8093 当前返回入口：`高炉前端数据/frontend_dashboard_v3.server.html`
- 前端运行资源：`高炉前端数据/libs`、`logo`、`models`、`config`、`智能助手`
- 运行服务源码：`自动诊断服务`
- WebSocket/诊断依赖：`炉况规则引擎/features`、`炉况规则引擎/config`
- 同步和值守脚本：`tools`、`db_dashboard`、`db_sync_storage`
- 启动/安装文件：`start_v3_full.ps1`、`install_22012_autoguard.ps1`、`install_local_autoguard_tasks.ps1`、`docker-compose.local-postgres.yml`、`requirements-local.txt`

## 8093 入口校验

- URL：`http://10.30.220.12:8093/#diagnosis`
- 本地保存：`高炉前端数据/frontend_dashboard_v3.server.html`
- SHA256：`866AEAEB1278128D93921DB8D9464EC6505F1F0E0C60E8A358FD7946A55111A3`

## Git 版本匹配结论

在 `D:\文件\服务器实际运行版V4` 的 `高炉前端数据/frontend_dashboard_v3.server.html` 历史提交中未找到与 8093 当前入口字节级完全一致的提交。

最接近的提交是：

- `0ec8e2f`，2026-06-04，`feat: optimize frontend style for modern visual depth and grand UI`
- `a6e4855`，2026-05-18，`anchor CAD tooltip and stream body temperature points`

因此 8093 当前入口更像是某次提交基础上的未提交工作区版本，或来自另一个预览目录。

## 数据库未连接根因

8093 页面源码中：

```js
const WS_PORT = window.BF_WS_PORT || new URLSearchParams(window.location.search).get('ws_port') || '8768';
const WS_URL = `ws://${WS_HOST}:${WS_PORT}`;
```

而当前可用的实时数据桥是 `ws://10.30.220.12:8767`：

- `ws://10.30.220.12:8767` 可连接，返回 `type=init`
- `data_quality.status=ok`
- `latest_data_ts=2026-07-06 20:20:00`
- `source_lag_seconds=60`
- 数据源：`local_postgresql`，`127.0.0.1:5432/bf_trend`

所以不带参数打开 `http://10.30.220.12:8093/#diagnosis` 时，页面默认去连 `8768`，WebSocket 失败后头部显示“数据状态：未连接”。这不是 PostgreSQL 数据本身不可用；8767 桥已经能读到本地 PostgreSQL 数据。

临时访问方式：

```text
http://10.30.220.12:8093/?ws_port=8767#diagnosis
```

长期修复方式二选一：

- 把 8093 HTML 默认 WebSocket 端口从 `8768` 改回 `8767`
- 或者在服务器上启动一个真正可用的 `8768` WebSocket 桥

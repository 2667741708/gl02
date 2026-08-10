# A9/B13/C11 33项炉况规则本机实现交接

需求编号：`REQ-ABC33-FURNACE-RULES-20260807`

## 已完成

- 33项规则目录：A1–A9、B1–B13、C1–C11。
- 服务端特征、评分、置信度、缺数/陈旧门禁和生产/后台字段白名单。
- JSON数值配置、校验、fsync原子发布与SHA-256。
- `bf_sensor` 计算批次/明细、配置版本、告警生命周期DDL；调度器并行计算并写入审计。
- 8768桥接安全序列化；8092代理生产详情、趋势、管理员内部详情和配置发布接口。
- 生产页面增加A/B/C规则入口；C红色、B黄色/琥珀分级提示；后台页面 `/furnace-rule-admin.html`。

## 本机验证

```powershell
& 'D:\ProgramData\anaconda3\python.exe' -m pytest -q tests/test_abc_rule_engine.py
node tools/check_frontend_babel_syntax.cjs '高炉前端数据/frontend_dashboard_v3.server.html'
node --check '高炉前端数据/assets/abc-furnace-rules-production.js'
```

结果：规则合同 `11 passed`，Babel语法通过，生产资源语法通过；服务端模块 `py_compile` 通过。

## 尚未执行

- 未执行本机或220.12数据库DDL迁移、影子运行、远端上传、8093/8094/8768重启。
- 现场浏览器多引擎矩阵和真实数据库接口验收需要在迁移后执行。
- 现有8类页面中的历史 `RULE_KNOWLEDGE` 仅保留兼容展示；新33项数据来自服务端安全合同，不把ABC内部公式复制到前端。

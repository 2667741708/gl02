# QA MCP 图表与推荐问题实施交接

> 状态：本机已实现，尚未部署 220.12。最后核对：2026-08-14。
>
> 需求：`REQ-QA-MCP-VISUAL-RECOMMENDATIONS-20260814`。

## 1. 用户可见结果

智能助手现在支持以下完整链路：

```text
中文矩阵热度图问题
  → 确定性解析层号和方位
  → 单次 plot_gl02_body_temperature_matrix
  → 数据库批量读取并生成 PNG/JSON 旁车
  → 答案内显示同源矩阵热力图
```

可直接使用：

> 绘制最近一小时第7层到第13层A到H炉体温度矩阵热度图，每格显示当前温度和变化趋势。

左侧推荐区可滚动，固定展示常用 MCP 模板；每次成功收到回答的 final 后，按刚才问题的主题刷新
3–4 条相关追问。点击推荐项只填入输入框，不自动发送。星标可以固定/取消固定；用户也可以输入
最多 240 字的自定义问题，自定义项添加后默认固定，并可删除。

## 2. 安全与持久化边界

- 图表渲染只接受 `/data/mcp_charts/<ASCII安全文件名>.png`；不接受外部域名、`data:`、`javascript:`
  或任意 HTML。
- 推荐问题不会触发后台请求，只有用户再次点击发送才调用 `/api/qa/chat`。
- 固定与自定义偏好保存在当前浏览器 `localStorage`，键为 `bf_qa_prompt_preferences_v1`；共享匿名
  会话仍共享消息，但不会让某个局域网访客修改所有浏览器的推荐偏好。
- 本轮不新增数据库表、环境变量或 API；没有连接生产数据库，也没有修改 220.12。

## 3. 实现位置

- [矩阵图中文路由](../../高炉前端数据/智能助手/backend/ollama_proxy_server.py#L4662-L4712)
- [安全图表解析与渲染](../../高炉前端数据/frontend_dashboard_v3.server.html#L8881-L8882)
- [回答完成后相关问题事件](../../高炉前端数据/frontend_dashboard_v3.server.html#L8921-L8929)
- [常用模板与相关问题分类](../../高炉前端数据/frontend_dashboard_v3.server.html#L9223-L9241)
- [滚动、固定与自定义推荐区](../../高炉前端数据/frontend_dashboard_v3.server.html#L9242-L9252)
- [自动化合同](../../tests/test_qa_mcp_visual_recommendations.py#L23-L81)

## 4. 验证结果

- 聚焦回归：`24 passed`；
- 生产前端构建：`ok=true`、`contractMatch=true`、像素差为 0；
- Chromium `1366×768` 单视口交互：`1/1 passed`，同源 PNG 实际渲染可见；
- 图表路由为一个复合工具；视口验证真实模型请求数为 0；
- 页面无横向溢出、无底栏遮挡、中文可读、页面错误为 0。

单视口报告：
`logs/qa_mcp_visual_recommendations_1366x768_final2/report.json`。

## 5. 后续部署边界

如果需要上线 8093，必须先重新审查 220.12 的最新 Git 更新，再使用
`deploy-8093-guarded-update`。发布包至少包含代理后端与生产前端；上线验收只允许一次真实热度图
问题，必须证明一个绘图工具调用、PNG 可访问、回答内图片可见、推荐问题不会自动发送，且保护 PID
保持不变。
# 2026-08-14 补充：保留原有常用问题

- 追踪编号：`REQ-QA-LOCAL-RECOMMENDATION-PRESERVATION-20260814`。
- 原有随炉况动态生成的问题没有删除；此前因排在 12 条 MCP 模板之后并共用一个标题而难以发现。
- 当前推荐区固定为“已固定 → 原有常用问题 → 常用 MCP 模板 → 本轮相关追问 → 自定义”，原有问题
  与 MCP 模板分别传递，不再合并成无来源数组。
- 滚动容器继续使用独立 `overflow-y:auto`，增加键盘焦点和可访问名称。用户可自行滚动，点击仍只填入
  输入框，不自动发送。
- 聚焦测试 `15 passed`；Chromium `1366×768` 报告
  `logs/qa_local_recommendations_1366x768_final/report.json` 为 `1/1 passed`，两个分区、实际滚动、
  键盘可访问性均通过，真实模型请求为 0；生产前端构建合同通过。
- 2026-08-14 已随生产 HTML 受控部署至 `10.30.220.12:8093`：执行 ID
  `qa-copy-recommendations-20260814-222600`，8093 PID `4928 → 14396`，保护 PID 全部不变。
- 生产轻量冒烟确认“原有常用问题”和“常用 MCP 模板”同时可见、推荐区可手动滚动、固定与自定义
  提示词可用；报告 `logs/qa_copy_recommendations_8093_smoke_r2/report.json` 为 `1/1 passed`，
  `real_sent=0`。
- 远端 Git 提交为 `949d3dde6fc2451a4a28c753c651053d218b9353`，生产标签为
  `prod-8093/20260814-qa-copy-recommendations-949d3dde6fc2`。

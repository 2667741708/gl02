# 2026-08-06 8093/8094 建议可视工作台交接

## 范围

- 恢复建议驾驶舱的数字、主证据迷你曲线、实时监测、风险、得分演化、基线偏离和建议队列。
- 增加8炉况紧凑切换、完整动作/模型抽屉和可展开19项核心证据中心。
- 不修改 `multi_condition_recommendation.v1`、规则分数、动作合同、数据库或8768服务逻辑。

## 关键入口

- 页面：[frontend_dashboard_v3.server.html:L10530](../../高炉前端数据/frontend_dashboard_v3.server.html#L10530)
- 构建：[build_8093_8094_recommendation_visual_frontend.py:L30](../../tools/build_8093_8094_recommendation_visual_frontend.py#L30)
- 部署：[remote_deploy_8093_8094_recommendation_visual_frontend.ps1:L109](../../tools/remote_deploy_8093_8094_recommendation_visual_frontend.ps1#L109)
- 浏览器验收：[verify_remote_recommendation_pages.cjs](../../tools/verify_remote_recommendation_pages.cjs)

## 本地验收

- Babel语法通过。
- 8种炉况逐一切换，每种均返回4项对应主证据。
- 展开后19项唯一变量齐全；单变量详情、时点表、相关性和四点顶温对比曲线可打开。
- 动作抽屉包含 `eligible/blocked/needs_data/manual_confirm` 与全部9类审计字段。
- 相关代码合同 `36 passed`。
- 对8093候选源页与从8094生产基线生成的候选页分别执行 Chromium 9视口、Firefox 4视口、WebKit 4视口，共 `34 checks / PASS`；无横向溢出，页面错误为0。
- 首轮按远端8094原样文件复验时发现 `useCoreMetricRealtime8093 is not defined`；R2把证据中心当前值适配器、4项主证据曲线和详情降级边界纳入可移植功能块。R2补丁页本地SHA-256与远端8094最终SHA-256一致。

## 部署与回滚

发布包只含页面源码和8094补丁器。部署器先原子更新8094并HTTP验收，再更新8093；正常路径不停止服务。任一页面失败都会从本轮备份恢复已安装页面，并要求8093/8094/8768/8770/11434 PID全部保持不变。

R2构建包SHA-256为 `37016D8666A68D9D49D09A5548ACB10735CEC4BD424EA83BE828361785A72212`，8093源页SHA-256为 `4C552CBA92D70379E3CBFD6447195F6B1105403009D3C6B39512BF5EF5D31262`。

远端备份目录：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_8094_recommendation_visual_20260806\20260806_095324`。

R2远端调用超过本机300秒控制器上限后，先只读取证确认两页已完成原子替换；外部普通TCP探测一度显示8093/8768不可达，因此按最小范围分别恢复 `BFV4PreviewProxy8093` 和 `BFV4PreviewWs8768`。服务器本机最终口径如下：

- `BFV4PreviewProxy8093=Running`，8093监听PID `14740`，HTTP 200；
- `BFV4PreviewWs8768=Running`，8768监听PID `3296`；
- 8094/8770/11434监听PID分别为 `10384/2096/12456`，8094 HTTP 200；
- 8093页面SHA-256：`4C552CBA92D70379E3CBFD6447195F6B1105403009D3C6B39512BF5EF5D31262`；
- 8094页面SHA-256：`876C14DF1F5620D3333C0F4AAC6D202FACE508E5C4C82E707F4E4D939A187C69`；
- 两页均包含 `REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806`、活动入口 `OptimizationVisualWorkbenchLayout`，并使用共享8768。

浏览器自动化所在通道直接访问220.12私网时出现 `ERR_EMPTY_RESPONSE`；远端响应体与服务器本机HTTP检查均正常。最终浏览器矩阵使用从远端下载/按同一补丁器生成并以SHA-256对齐的原样页面执行，不把私网通道问题冒充为生产页面错误。

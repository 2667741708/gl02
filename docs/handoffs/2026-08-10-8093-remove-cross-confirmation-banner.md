# 8093“严重事件交叉确认”提示移除上线记录

需求编号：`REQ-8093-REMOVE-CROSS-CONFIRMATION-BANNER-20260810`

## 结果

- 8093炉况复核详情不再创建“严重事件交叉确认”黄色提示条。
- 8094仍保留原显示条件；33项评分、详情接口和8768规则服务未修改。
- 实现采用端口级渲染条件，不使用CSS隐藏。

## 修改与验证

- 页面资源：[abc-furnace-rules-production.js](../../高炉前端数据/assets/abc-furnace-rules-production.js)
- 缓存版本：`abc33-20260810-hide-cross-confirmation-8093-r1`
- 专项测试：`pytest tests/test_abc_production_ui.py -q`，`6 passed`
- JavaScript：`node --check`通过
- 生产入口：`http://10.30.220.12:8093/?cb=abc33-20260810-hide-cross-confirmation-8093-r1#optimization`

## 受控部署证据

- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\remove_8093_cross_confirmation_20260810_142743`
- `BFV4PreviewProxy8093`：守卫已暂停并恢复，PID `15224 -> 7400`
- 8093：HTTP 200
- 8094 PID：`2988 -> 2988`
- 8768 PID：`18436 -> 18436`
- 8770 PID：`3732 -> 3732`
- 11434 PID：`5968 -> 5968`
- 8094页面文件：部署前后SHA-256一致
- 生产资源SHA-256：`0C33D8210C18CF1702D3951EAAE11477AA322C0103CA39C248345CDED5D51CF6`
- 8093页面SHA-256：`3A7C33BDD73C0F94AE6D5E20ABFB9EB771BCD3C68AD42878EE2973E9D94C990A`

## 回滚

如需回滚，只恢复上述备份目录中的`abc-furnace-rules-production.js`和`frontend_dashboard_v3.server.html`，并再次通过同一8093守卫停—改—启闭环验证；不得停止8768、8094、8770或11434。

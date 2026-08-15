# 8093 ABC33炉况总览入口交接

需求ID：`BUG-8093-ABC33-OVERVIEW-ENTRY-20260811`

## 交付结果

- “查看A/B/C 33项炉况”已从固定悬浮层移入“炉况总览”面板标题栏。
- 点击后打开独立33项总览，展示A类9项、B类13项、C类11项；关闭后回到原总览，不遮挡其他内容。
- 总览入口使用普通静态布局，生产页面横向溢出为0。

## 生产证据

- 8093 HTTP：200。
- 8093 PID：3704 → 16428。
- 页面SHA-256：`2F92DC7A914E9D29153A137624E3044012B3F8687CC03B5696DCFA04B5968664`。
- 资源SHA-256：`C8C05A118C4B0A9BC023ACF258080DE1766A565CBCB3DB4074CA888F0B1A0CE1`。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_overview_entry_8093_20260811_114520`。
- `BFV4PreviewProxy8093`守卫已恢复，未触发回滚；8094、8768、8770、5432、11434 PID均保持不变。

## 验收

- Python相关回归：39 passed。
- 标准浏览器矩阵：17/17 passed。
- 生产Chromium冒烟：入口位于炉况总览标题栏，点击后33张卡，关闭按钮为“关闭总览”，横向溢出0，页面错误0。
- 截图：`logs/abc33_overview_entry_standard/production-8093-overview-entry.png`。

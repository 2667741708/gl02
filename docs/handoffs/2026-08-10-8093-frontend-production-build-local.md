# 8093前端生产构建优化（生产交接）

## 结果

2026-08-10 23:59 已通过`deploy-8093-guarded-update`部署到220.12:8093。Vite/esbuild生产构建、React生产版、总览3D路由延迟加载、gzip/Brotli、哈希资源缓存、共享页面调度器和8770 WebSocket复用均已切换生效。没有修改GLB、CSS主题或Billboard CanvasTexture绘制样式。

## 构建与本地证据

- 构建以部署前下载的生产HTML为源，避免覆盖220.12上比本机更新的业务功能。
- 生产HTML：221810 bytes；gzip 40462；Brotli 31323。
- 诊断页源页面传输：8984926；生产构建：3921971，下降约56.3%。
- 生产诊断页未加载Three.js、GLB、Billboard适配器、相机守卫或tooltip运行时。
- Chromium 1366x768核心冒烟通过：121点合同一致、广告牌纹理/位置/缩放与工艺标注样式签名一致、炉体结构像素差0。
- 部署前定向测试15项通过。

## 生产部署证据

- 受控部署总耗时：66872ms，其中本地验证29354ms、会话确认272ms、上传9255ms、停服/替换/恢复/远端验收27718ms、同会话复核264ms。
- SSH复用：`session_id=e23e3e9d681d42d489b7b607787ecdac`、`connection_id=f928ec393b5f4b4a9722937a159ed871`，请求计数17→19，重连0次。
- 8093守卫：`guard_paused=true`、`guard_restored=true`、`rollback_applied=false`；监听PID由14436切换为18820，HTTP 200。
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8093_frontend_perf_r1_20260810_235914`。
- 受保护PID前后不变：8094=18628、8768=9148、8770=3732、5432=12372、8892=5496、11434=5968。
- 压缩协商：哈希主包返回Brotli；版本化资源返回gzip。两类静态资源均返回`public, max-age=31536000, immutable`。
- 生产HTML SHA-256：`742945363CC45D662559824D1C319B91ADA32A6FED9B273A3FE2E049D9120C38`。
- 完整结构化日志：`.tmp/deploy-8093-frontend-perf.stdout.log`（本机临时证据，不作为长期运行依赖）。

## 验收边界

本轮按用户要求未运行85项跨引擎/视口矩阵。Chrome已打开生产诊断路由并显示正确系统标题，但浏览器扩展在读取DOM、网络资源和控制台状态时连续超时，因此生产视觉/控制台项不宣称通过；本地针对生产基线的1366x768像素与资源合同仍已通过。后续最终兼容验收再运行完整矩阵。

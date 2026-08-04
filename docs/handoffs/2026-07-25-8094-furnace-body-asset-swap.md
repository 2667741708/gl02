# 8094 高炉本体资产热替换记录

## 范围

- 目标：V4 预览页 `http://10.30.220.12:8094/#overview`。
- 维护程序：计划任务 `\BlastFurnaceServices\V3AutoPreviewProxy8094`，入口为远端 V4 预览目录中的 `tools\run_22012_8094_preview.ps1`，由 `ollama_proxy_server.py` 提供静态页/API。
- 生产边界：未修改 8093 页面、8093 监听进程、数据库、模型服务和计划任务。

## 变更

- 用 `PT/高炉3D模型/模型资产库/09_高炉本体133点Billboard_cn/GL02_FURNACE_BODY_R1.glb` 替换远端 8094 页面使用的 `models/gl02_blast_furnace.glb`。
- 上传 `sensor_billboards.v1.json` 为 `models/gl02_furnace_body_billboards.v1.json`，按 `canonical_id/data_binding_key` 恢复 115 个正式传感器和 18 个静压力点的运行时 Billboard 与透明拾取对象。
- 页面补丁通过 `getBuffer`、`scene`、`model` 暴露 CAD viewer 运行时句柄，并加入版本化适配器脚本与 `bf3d-internal-simulation.js`，使新本体继续承载内部负荷、煤气流线和风口流动层。
- 适配器增加单实例挂载锁，避免 GLB/manifest 首次加载期间的并发探测重复创建点位。

## 备份与回滚

- 远端备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\8094_furnace_body_swap_20260726_001347`。
- 备份内容：原 8094 HTML 和原 `gl02_blast_furnace.glb`。
- 回滚方式：停止 `V3AutoPreviewProxy8094`，从上述备份恢复 HTML/GLB，再启动同一任务；不要操作 8093。

## 验收证据

- 新 GLB SHA-256：`150DF18B68F0410B9A168F80C2DF34EFDA86384FC51D37226F81C2ACD244ED53`。
- 点位清单：schema `bf3d.sensor_billboards.v1`，115 + 18 = 133，SHA-256：`59E17A569CDE94ED52B35F09ABAFF33257B293B6329C3D78457116A8943EC024`。
- 8094 HTML SHA-256：`564A7C529E9F2EA219BDBE407279F36A907B5062874CF32A28FF2C90EF0A668C`。
- 远端 Python HTTP 探针：页面 200、点位清单 200。
- 远端一致性脚本：任务 Running、8094 listener PID `13772`、HTML 缓存破坏参数/scene-model viewer contract/flow runtime 均存在、manifest total `133`。
- 本地中文 Billboard 资产报告已记录模型无内嵌传感器节点、133 个 `THREE.Sprite` 运行时点位和桌面/移动端预览通过；本次远端浏览器最终计数受既有用户标签主线程解析和缓存状态影响，需刷新 8094 标签后观察新模型加载完成。


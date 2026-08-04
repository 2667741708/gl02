---
name: bf3d-orchestrate
description: 编排 GL02 高炉 3D 模型从源资产审计、非破坏几何优化、UV 与 PBR 烘焙、工业材质、灯光渲染、GLB 导出到 Three.js 浏览器验收的完整闭环。用于涉及高炉 Blender、贴图、渲染、模型拆分、材质升级或 Web 交付的任务，必须保护 115 个传感器与分层节点。
---

# 高炉 3D 制作总编排

## 开始前

1. 完整读取 [project-contract.md](references/project-contract.md) 和 [mcp-capability-map.md](references/mcp-capability-map.md)。
2. 读取 `../bundle-manifest.json` 与 `../sources.lock.json`，确认 Skill 集合和上游版本未漂移。
3. 将唯一原始模型视为只读；创建带阶段号的 `.blend` 副本后才能修改。
4. 明确本轮只改一个质量维度；禁止在同一轮同时重建几何、换材质、换灯光和改相机。
5. 缺少参考照片、尺寸依据或 Blender 运行能力时，先输出审计与待确认项，不得声称已经完成真实渲染。

## 工作流

按顺序调用下列项目 Skill；任何门禁失败都停止进入下一阶段：

1. `$bf3d-geometry-audit`：建立 P00 源资产和 P10 几何检查点。
2. `$bf3d-uv-bake`：建立 P20 UV、P21 烘焙测试和贴图报告。
3. `$bf3d-industrial-materials`：建立 P30 风化钢材质与通道检查。
4. `$bf3d-light-render`：建立 P40 中性 LookDev 和固定机位渲染。
5. `$bf3d-gltf-handoff`：建立 P50 烘焙、P60 GLB 和浏览器候选版本。
6. `$bf3d-visual-qa`：建立 P70 Blender/Three.js 对照证据和验收结论。

## 每阶段交付契约

每个阶段都输出：

- 输入模型路径、输入 SHA-256、Blender 版本和渲染设备；
- 新 `.blend` 检查点，禁止覆盖前一阶段；
- 实际执行的命令或 MCP 能力、参数和错误；
- 节点数量、传感器数量、包围盒和坐标审计结果；
- 固定机位截图或明确说明为何无法截图；
- 本轮差异、失败项、回滚点和下一步；
- 机器可读报告，不能只给“看起来更真实”的主观结论。

## 不可破坏约束

- 保留 115 个 `SENSOR_` 节点及其 ID、世界坐标和层级语义。
- 保留 `GL02_SENSOR_LAYER_L7`～`GL02_SENSOR_LAYER_L16`；当前 UI 只开放 L7～L13 不等于可删除 L14～L16。
- 保留五个 `APPROX_GL02_FURNACE_*` 工艺段节点、模型原点、Y-up 前端坐标和米制尺度。
- 将 `APPROX_` 资产继续标注为工艺可视化近似模型，不得写成施工级数字孪生。
- 将传感器、自发光点、动态高亮环带排除在炉壳贴图合并与烘焙对象之外。
- 程序化材质必须烘焙为 glTF 可识别的 PBR 贴图后才能交付。

## 停止条件

发生以下任一情况时停止写入并回到最近检查点：

- 任一 `SENSOR_` 节点丢失、重命名或世界坐标漂移；
- 工艺段或 L7～L16 分组丢失；
- 模型尺度、轴向或原点无法解释；
- UV 存在未批准重叠、零面积岛或贴图覆盖缺失；
- glTF Validator 出现错误；
- Three.js 中材质、传感器或 L7～L13 交互回归；
- 只有 Blender 漂亮截图，没有浏览器候选资产和对照证据。

## 来源说明

本 Skill 是面向本项目的中文适配编排，不是上游文件逐字副本。具体上游 commit、文件路径和 SHA-256 见 `../sources.lock.json`。

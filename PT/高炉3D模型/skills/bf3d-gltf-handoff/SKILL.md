---
name: bf3d-gltf-handoff
description: 将通过 Blender 审核的 GL02 高炉安全导出为浏览器 GLB，验证 glTF PBR、节点层级、115 个传感器、L7～L16 分层、贴图色彩空间、ORM、压缩和 Three.js 性能。用于正式导出、KTX2 或 Meshopt 优化、manifest 生成和 Web 交付回归。
---

# 高炉 GLB 与 Three.js 交付

## 导出前

1. 从批准检查点复制 `EXPORT_GL02` 集合，不直接破坏 LookDev 主场景。
2. 只导出交付集合，排除参考图、测试灯、烘焙 cage、隐藏备份和高模。
3. 将程序材质烘焙并接回标准 Principled BSDF；检查 BaseColor、Normal、Occlusion、Roughness、Metallic 和 Emissive 连接。
4. 保留对象名称、节点层级、extras、模型原点、米制尺度和 Y-up 语义。
5. 在导出前再次锁定 115 个传感器世界矩阵和十个层组清单。

## 导出与优化

1. 使用 Blender 官方 glTF 2.0 导出器生成未压缩基线 GLB。
2. 先让未压缩基线通过结构和视觉验收，再生成 Meshopt、Draco 或 KTX2 候选；不要同时引入多个变量。
3. KTX2 可将 BaseColor 优先使用 ETC1S，法线和 ORM 优先使用 UASTC；最终格式必须按目标浏览器实测。
4. 生成 4K 高档、2K 中档和 1K 低档贴图变体；材质和节点名称保持一致。
5. 生成 manifest，记录文件 SHA-256、字节数、节点、网格、材质、贴图、传感器、工艺段、层组、包围盒和生成时间。

## 必验合同

- glTF 2.0 Validator 错误为 0；警告必须逐项解释。
- `SENSOR_` 节点恰好 115 个，炉体温度点恰好 80 个。
- `GL02_SENSOR_LAYER_L7`～`L16` 各有 A～H 八点。
- 五个 `APPROX_GL02_FURNACE_*` 工艺段节点完整。
- 传感器坐标相对基线在确认容差内，默认要求无漂移。
- BaseColor 为 sRGB；Normal/ORM 为 Non-Color；Normal 为 OpenGL `+Y`；ORM 通道为 R/G/B。
- GLB 不包含外部绝对路径、生产密码、Token 或内部凭据。

## 浏览器交付

1. 在 Three.js 正式查看器加载候选 GLB，不以 Blender 截图代替交付验证。
2. 检查炉体轮廓、材质、透明排序、自发光点、工艺段显隐和 L7～L16 动态高亮。
3. 执行高、中、低性能档，记录加载时间、首帧、平均 FPS、显存近似和纹理尺寸。
4. 连续切换图层 100 次，确认场景对象、材质和 GPU 资源不持续增长。
5. 通过后保存 `P60_GLTF_APPROVED.glb`、validator 报告、manifest 和浏览器截图。

## 来源

依据 RobLe3 导出、dcc-mcp export/validation 与 BlendOps Web handoff/性能规则进行适配；精确来源见 `../sources.lock.json`。

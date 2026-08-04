---
name: bf3d-uv-bake
description: 为 GL02 高炉建立可审计的工业设备 UV、纹素密度和 PBR 通道烘焙流程，输出 BaseColor、OpenGL Normal、AO、Roughness、Metallic 与 ORM，并验证封闭曲面侧壁和背面覆盖。用于现有无 TEXCOORD_0 的 GLB 贴图化、图集制作和 Web 贴图降级。
---

# 高炉 UV 与贴图烘焙

## 先决条件

1. 只接受通过 `$bf3d-geometry-audit` P10 门禁的模型。
2. 确认当前生成器只含 `POSITION` 与 `NORMAL`，不得假定已有可用 UV。
3. 从一个代表性炉壳段做 P21 小样；未通过小样前不展开整炉。

## UV 策略

1. 炉壳锥台采用环向展开，并把主纵缝放在默认相机背侧或真实检修缝位置。
2. 环板、法兰、平台、管道、支撑和出铁口按几何类型独立设缝；禁止只用一次 Smart UV 代替设计。
3. 检查正面、背面、侧壁、内壁和端盖，避免只在当前相机可见面有贴图。
4. 默认使用一个或两个 4K 图集作为高档源，派生 2K 和 1K；浏览器版本不使用 UDIM。
5. 同一视觉等级内纹素密度偏差目标不超过 ±15%；近景重点对象可单独图集并记录理由。
6. 4K 图集默认保留不少于 16 px 岛间距；不允许零面积岛、越界岛或未经批准的重叠。
7. 不镜像需要方向性水痕、热变色、编号或不对称锈蚀的区域。

## 烘焙契约

输出并记录：

- `BaseColor`：sRGB；不得烘入灯光和镜面高光。
- `Normal`：Non-Color，OpenGL `+Y`；在 Three.js 中检查方向。
- `AO`：Non-Color，只表达局部遮蔽，不能把大面压黑。
- `Roughness`：Non-Color，保留钢、漆、锈、尘的差异。
- `Metallic`：Non-Color；裸钢接近 1，漆、锈、尘接近 0。
- `ORM`：R=AO、G=Roughness、B=Metallic；打包前验证每个源通道。

使用 Cycles 烘焙时先校准 cage/ray distance，确保焊缝和锐角不穿帮。每次烘焙输出分辨率、采样、边距、色彩空间、法线制式和耗时。

## 门禁

- UV 覆盖率完整，侧壁与背面没有空白；
- 棋盘格密度一致，无明显拉伸和接缝跳变；
- 切线法线在 Blender 与 Three.js 方向一致；
- 贴图名称、尺寸、色彩空间和 ORM 通道均通过机器检查；
- 传感器、动态高亮和自发光点未被合并进炉壳图集；
- 保存 `P20_UV_APPROVED.blend`、`P21_BAKE_TEST.blend`、UV 报告和贴图清单。

## 来源

依据 RobLe3 UV/封闭曲面规则与 dcc-mcp 结构化 UV/烘焙能力进行适配；精确来源见 `../sources.lock.json`。

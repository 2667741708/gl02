---
name: bf3d-light-render
description: 为 GL02 高炉建立可重复的中性 LookDev、工业展示灯光、固定相机、Cycles GPU 草稿与终稿渲染，并校准 AgX、曝光、降噪和 Three.js 实时表现。用于判断材质是否真实、生成固定机位证据或优化浏览器环境光与轮廓光。
---

# 高炉灯光与渲染

## 分离两套灯光

1. 建立 `LOOKDEV_NEUTRAL`：中性 HDRI 或大面积柔光、灰色背景、无 Bloom，用于判断材质本身。
2. 建立 `PRESENTATION_INDUSTRIAL`：柔和暖主光、冷色轮廓光和克制环境光，用于展示结构层次。
3. 禁止用强色光、重雾、眩光或高对比调色掩盖材质、法线和几何错误。
4. 两套灯光使用相同固定相机，方便逐像素或并排比较。

## 固定机位

至少创建并锁定：

- `CAM_GLOBAL_FRONT`：默认前侧全景；
- `CAM_GLOBAL_BACK`：背面纵缝和管线；
- `CAM_GLOBAL_LEFT`、`CAM_GLOBAL_RIGHT`：左右结构；
- `CAM_DETAIL_SHELL`：炉壳板缝、焊缝和粗糙度；
- `CAM_DETAIL_TUYERE`：风口与围管；
- `CAM_DETAIL_TAPHOLE`：出铁口和热影响区。

记录镜头焦距、位置、旋转、分辨率和裁切面。不得在每轮修改后凭感觉重新摆相机。

## 渲染基线

1. 使用 AgX 或当前 Blender 对应的场景参考视图变换，锁定曝光和对比度。
2. 草稿使用较低采样和降噪，只用于发现问题；终稿提高采样并保留相同色彩管理。
3. 有可用 NVIDIA GPU 时优先验证 Cycles GPU/OptiX，但先记录 Blender 实际识别的设备；不能仅凭显卡型号声称已启用 GPU。
4. 同时输出一个 EEVEE 或材质预览版本，提前暴露实时渲染差异。
5. 灯光尺寸随炉体包围盒缩放，避免把高炉当小型产品用近距离硬光照明。

## Three.js 对齐

- 浏览器使用 sRGB 输出、ACES tone mapping 和环境贴图时，记录曝光与 Blender 对照值。
- 不把 Blender 合成器后期效果当作 GLB 材质的一部分。
- 在浏览器相同机位检查粗糙度、金属度、法线方向、透明排序和传感器亮度。
- 若 Blender 与 Three.js 不一致，先排查色彩空间、环境强度、法线制式和 ORM 通道，而不是继续叠加灯光。

## 门禁

- 中性灯光下材质仍可信；
- 四个全景和三个细节机位均无遮挡、无裁切、无明显噪点；
- 曝光、色彩管理、渲染引擎、设备与采样已记录；
- 传感器和层高亮在展示灯光下仍清晰；
- 保存 `P40_LOOKDEV_APPROVED.blend` 和固定机位渲染矩阵。

## 来源

依据 RobLe3 灯光/渲染、ra100 场景渲染与 BlendOps 色彩和灯光检查规则进行适配；精确来源见 `../sources.lock.json`。

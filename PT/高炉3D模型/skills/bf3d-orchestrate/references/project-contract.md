# GL02 高炉项目契约

## 当前事实

- 浏览器模型：`高炉前端数据/models/gl02_blast_furnace.glb`。
- 模型清单：`高炉前端数据/models/gl02_blast_furnace.manifest.json`。
- 参数化生成器：`D:/文件/pythonCAD/src/geometry/visual_glb.py`。
- 炉型参数：`D:/文件/pythonCAD/input/furnace_profile.gl02.yaml`。
- 前端查看器：`高炉前端数据/frontend_dashboard_v3.server.html` 中 `CadFurnaceViewer`。
- 现模型为 190 节点、29 网格、23 材质、115 传感器，其中炉体温度点 80 个。
- 生成器目前只输出 `POSITION` 与 `NORMAL`，没有 `TEXCOORD_0`；专业图片贴图前必须补 UV。

## 坐标和命名

- CAD：Z-up、毫米；浏览器：Y-up、米；前端高度换算为 `Y = height_m - 20`。
- 五个工艺段：`APPROX_GL02_FURNACE_HEARTH/BOSH/BELLY/SHAFT/THROAT`。
- 十个层组：`GL02_SENSOR_LAYER_L7`～`GL02_SENSOR_LAYER_L16`。
- 每层 A～H 共 8 点；节点名为 `SENSOR_T_body_L<层>_<方位>`。
- 正式材质和几何改造不得把 `APPROX_` 改成暗示测绘精度的名称。

## 当前标高

| 层 | 标高 m | 当前区域 |
|---|---:|---|
| L7 | 16.860 | 炉腹下 |
| L8 | 18.335 | 炉腹上 |
| L9 | 20.125 | 炉腰 |
| L10 | 21.860 | 炉身下 |
| L11 | 23.711 | 炉身下 |
| L12 | 25.441 | 炉身下 |
| L13 | 27.171 | 炉身下 |
| L14 | 28.901 | 炉身中 |
| L15 | 30.631 | 炉身上 |
| L16 | 32.361 | 炉身上 |

## 当前 UI 交互

- 当前操作入口只开放 L7～L13，但模型必须保留 L14～L16。
- 选择一层后只显示对应 A～H 八点，并显示贴合炉壳的动态高亮环带。
- 颜色状态为正常、关注、严重、无数据；材质升级不得削弱传感器自发光可读性。
- Three.js 运行时已有 ACES 色调映射、哑光炉壳参数、粗糙纹理和性能分级；离线材质应逐步替代运行时伪纹理，而不是重复叠加。

## 基础验证

```powershell
python tools/build_gl02_layered_model.py --skip-generate --check-only
python tools/verify_gl02_layered_model_ui.py --base-url http://127.0.0.1:8092
```

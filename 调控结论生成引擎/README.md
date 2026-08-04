# 高炉调控结论生成引擎

本模块把标准炉况诊断转换为只读调控建议。输入包含主炉况、次炉况、诊断分数、8种炉况分数与特征快照；输出包含调控目标、立即动作、后续动作、禁止动作、复查周期、现场确认要求和安全门禁。

当前引擎覆盖 `normal`、`lowline`、`edge`、`center`、`channel`、`cold`、`hot`、`column` 八类炉况，并支持低料线+炉凉、边缘+炉凉组合修正。

运行示例：

```powershell
python 调控结论生成引擎\main.py diagnosis.json
python 调控结论生成引擎\main.py diagnosis.json --output recommendation.json
python tools\verify_8093_recommendation_engine_contract.py
```

安全边界：引擎只生成建议，不连接生产控制写接口；所有强动作仍需现场授权确认。

追踪文档：

- [docs 可追踪说明](../docs/调控结论生成引擎可追踪说明.md)
- [PT 交接说明](../PT/调控结论生成引擎可追踪说明.md)

# 铁水 Si 预测实验

对“一炉一行”宽表做时间顺序基线实验。目标默认
`target__hot_metal_Si_median`，只使用显式 `feature_columns`，防止把炉后化验、
炉况结果或未来字段泄漏给模型。

```powershell
python PT/02_铁水Si预测实验/analyze.py --input <model_feature_rows.csv>
```

第一版输出训练/测试切分、训练集中位数基线、MAE/RMSE和逐炉预测。后续模型必须
与此基线在相同时间切分上比较。

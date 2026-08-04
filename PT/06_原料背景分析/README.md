# 原料背景分析

将炉次开口前一定时间内的烧结矿化验汇总为“原料背景”，明确不冒充实际入炉
谱系。输入包括炉次CSV和烧结矿样本CSV。

```powershell
python PT/06_原料背景分析/analyze.py --heats <heats.csv> --sinter <sinter.csv>
```

炉次文件需要 `meltno,open_ts`；烧结文件需要 `sample_no,sample_ts`，可含
`TFe,FeO,CaO,MgO,SiO2,Al2O3,R2,Zn`。默认回看12小时。

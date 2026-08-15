# 19项时间序列统一排行榜修复

需求：`REQ-TS-LEADERBOARD-CORRECTION-20260811`

## 完成内容

- 新增`tools/timeseries_leaderboard.py`，从多个同切点评测明细生成统一JSON、CSV和Markdown排行榜。
- 新增8778只读接口`GET /api/timeseries/leaderboard`，排行榜文件按修改时间热加载。
- `GET /api/timeseries/status`增加排行榜可用性，不改变`default_model=last_value`。
- `tools/check_timeseries_sidecar_python.py`增加排行榜schema检查。

## 当前结果

- 公共切点8个，目标19项。
- 综合排名：Ridge target-only、Ridge expert-sparse、Chronos-2、IBM TTM R2、LastValue。
- 0–30分钟冠军：Chronos-2。
- 31–60分钟冠军：Ridge expert-sparse。
- 61–120分钟冠军：Ridge target-only。
- 结果只说明当前8切点；不得自动拼接三种预测曲线或切换生产模型。

## 本机复现

```powershell
python .\tools\timeseries_leaderboard.py `
  --detail '.\PT\时间序列预测评测\results\ttm_chronos2_zero_shot_detail_20260808_124916.csv' `
  --detail '.\PT\时间序列预测评测\results\ridge_fixed_cutoff_detail_20260808_131525.csv'
```

```powershell
python -m pytest .\tests\test_timeseries_leaderboard.py -q --basetemp '.tmp_pytest_timeseries_leaderboard'
```

## 生产更新边界

当前未执行生产部署。生产更新前先只读获取`\BlastFurnaceServices\TimeSeriesBenchmark8778`的Action、工作目录、当前服务脚本和排行榜目标哈希，不能依据历史安装脚本猜测实际根目录。

8778后端更新的最小产物为：

1. `tools/timeseries_sidecar_service.py`。
2. `PT/时间序列预测评测/results/timeseries_model_leaderboard_current.json`。

更新时只允许重启`TimeSeriesBenchmark8778`，并证明8777、8093、8768、8094、8770和数据库监听PID不变。验收必须包括8778状态、模型目录、排行榜HTTP 200/schema、默认模型仍为LastValue，以及失败时恢复服务脚本和排行榜文件。

`deploy-8093-guarded-update`不能用于8778任务本身，因为Skill明确限制为8093服务。如果后续要在8093趋势页展示排行榜，应另建只包含8093 HTML/静态资源的密封发布清单，再由该Skill执行8093备份、守卫停服、原子替换、恢复和页面验收；8778后端必须先独立完成部署和验收。

如果后续要让生产趋势页默认调用8778，还必须单独授权修改8768的`BF_CHRONOS_BASE_URL`并重启`BFV4PreviewWs8768`。这不是8093 Skill的权限范围，本次没有执行。

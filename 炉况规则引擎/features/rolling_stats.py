# -*- coding: utf-8 -*-
"""
核心模块功能说明：
1. 基础特征计算模块，提供时间序列滑动窗口统计功能，包含计算最近时间窗口平均值的rolling_mean、计算最近时间窗口标准差的rolling_std、计算最近时间窗口线性回归斜率的linear_slope、计算最近时间窗口最大值的rolling_max基础函数。
2. 支持15分钟、30分钟、60分钟这三种指定时间窗口维度的特征聚合，用于准确提取工况连续数据的波动性与趋势性特征。
3. 提供统一的高阶信号处理封装接口，包含负责统计顶压尖峰次数的count_spikes函数，为后续判断管道行程与中心过吹提供基础指标。
"""
import numpy as np
import pandas as pd

def rolling_mean(series, window):
    """计算滑动窗口的均值"""
    if series is None or len(series) == 0:
        return None
    return series.tail(window).mean()

def rolling_std(series, window):
    """计算滑动窗口的标准差"""
    if series is None or len(series) < 2:
        return 0.0
    return series.tail(window).std(ddof=1)

def rolling_max(series, window):
    """计算滑动窗口的最大值"""
    if series is None or len(series) == 0:
        return None
    return series.tail(window).max()

def linear_slope(series, window):
    """计算滑动窗口的线性回归斜率"""
    if series is None or len(series) < 2:
        return 0.0
    data = pd.to_numeric(series.tail(window), errors="coerce").dropna()
    if len(data) < 2:
        return 0.0
    y = data.values
    x = np.arange(len(y))
    # 避免除0
    if len(np.unique(x)) < 2:
        return 0.0
    try:
        slope, _ = np.polyfit(x, y, 1)
    except (np.linalg.LinAlgError, ValueError, FloatingPointError):
        return 0.0
    if not np.isfinite(slope):
        return 0.0
    return slope

def count_spikes(series, window, threshold=None, dynamic_multiplier=2.5):
    """
    统计滑动窗口内的尖峰次数。
    尖峰定义：某点的值大于均值 + dynamic_multiplier * 标准差，或者大于绝对 threshold。
    """
    if series is None or len(series) < 3:
        return 0
        
    data = series.tail(window)
    mean_val = data.mean()
    std_val = data.std(ddof=1)
    
    # 如果标准差为0，且没有绝对阈值，则没有尖峰
    if std_val == 0 and threshold is None:
        return 0
        
    # 如果标准差极小或者NaN，做个保护
    if pd.isna(std_val):
        std_val = 0
        
    limit = mean_val + dynamic_multiplier * std_val
    if threshold is not None:
        limit = max(limit, threshold)
        
    # 计算大于 limit 的点的个数，为了避免连续的高值算作多个尖峰，可以寻找局部极大值，
    # 但简单起见，按规范要求，可以统计超出阈值的点的数量（或连通域）。
    # 这里简单按超出阈值的次数统计：
    spikes = (data > limit).astype(int)
    
    # 如果要求是独立的尖峰，可以计算差分 > 0 的点
    # 这里采用差分方式，寻找突变点：
    # 如果前一个点没有超出，当前点超出了，算一个尖峰
    diff = spikes.diff().fillna(spikes.iloc[0])
    spike_count = int((diff == 1).sum())
    
    return spike_count

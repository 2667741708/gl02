# -*- coding: utf-8 -*-
"""
核心模块功能说明：
1. 历史基线映射模块，将风压、顶压、中心温度、边缘温度、顶温、风温、透气性指数、料线、炉喉温度、炉身静压力物理原始的绝对工程值转化为相对于正常生产期基线的无量纲Z-Score。
2. 读取并应用config目录下的baseline_meta.yaml配置文件中的正常样本中位数median_ref与正常样本四分位距IQR_ref两个统计参数。
3. 提供计算最近60分钟平均水平相对于历史正常水平偏离度z_level、计算最近30分钟趋势等同于跨越正常波动宽度数量z_trend、计算最近15分钟波动是否显著放大的标准差偏离度z_vol三个标准化函数计算接口，抹平物理特性的固有差异。
"""

import numpy as np

def z_level(current_mean, median_ref, iqr_ref):
    """
    计算绝对偏离度 (Z-Score of Level)
    :param current_mean: 当前滑动窗口的均值
    :param median_ref: 历史基准中位数
    :param iqr_ref: 历史基准四分位距
    """
    if current_mean is None or iqr_ref is None or iqr_ref == 0:
        return 0.0
    return (current_mean - median_ref) / iqr_ref

def z_trend(current_slope, window_size, iqr_ref):
    """
    计算趋势偏离度 (Z-Score of Trend)
    :param current_slope: 当前滑动窗口的线性回归斜率 (单位/分钟)
    :param window_size: 窗口大小(分钟)
    :param iqr_ref: 历史基准四分位距
    """
    if current_slope is None or iqr_ref is None or iqr_ref == 0:
        return 0.0
    # 趋势等同于跨越正常波动宽度数量
    return (current_slope * window_size) / iqr_ref

def z_vol(current_std, iqr_ref):
    """
    计算波动幅度偏离度 (Z-Score of Volatility)
    :param current_std: 当前滑动窗口的标准差
    :param iqr_ref: 历史基准四分位距
    """
    if current_std is None or iqr_ref is None or iqr_ref == 0:
        return 0.0
    # 由于标准差和IQR有关联，简单映射 (正态分布下 IQR ≈ 1.35 * std)
    # 此处粗略定义为当前 std 放大倍数
    return current_std / (iqr_ref / 1.35)

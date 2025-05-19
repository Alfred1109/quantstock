#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据提供程序模块的通用工具函数
"""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# 通用时间周期到不同API特定格式的映射
TIMEFRAME_MAPPING: Dict[str, Dict[str, str]] = {
    "tushare": {
        '1m': '1min',
        '5m': '5min',
        '15m': '15min',
        '30m': '30min',
        '1h': '60min',
        '1d': 'D',
        '1wk': 'W',
        '1mo': 'M'
    }
    # 可以根据需要添加其他API的映射
}

def map_timeframe(timeframe: str, api_name: str) -> Optional[str]:
    """
    将通用时间周期映射到指定API的特定格式。

    Args:
        timeframe: 通用时间周期 (e.g., '1m', '1d').
        api_name: API的名称 (e.g., 'tushare').

    Returns:
        映射后的API特定时间周期格式，如果找不到则返回None或默认值。
    """
    api_map = TIMEFRAME_MAPPING.get(api_name)
    if not api_map:
        logger.warning(f"No timeframe mapping found for API: {api_name}")
        return None 
    
    mapped_value = api_map.get(timeframe)
    if not mapped_value:
        logger.warning(f"Unsupported timeframe '{timeframe}' for {api_name}. Check TIMEFRAME_MAPPING.")
        return api_map.get('1d') 
    return mapped_value 
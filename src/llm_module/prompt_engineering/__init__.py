"""
提示工程模块，包含用于市场分析和交易策略的提示模板。
"""

# 导出市场分析提示模板
from .market_analysis_prompts import get_market_sentiment_prompt, get_trade_signal_prompt

# 导出金字塔交易策略提示模板
from .pyramid_trading_prompts import (
    get_market_trend_analysis_prompt,
    get_entry_point_prompt,
    get_position_sizing_prompt,
    get_exit_strategy_prompt
) 
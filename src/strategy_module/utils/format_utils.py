"""
数据格式化工具函数

用于将各类市场数据格式化为大模型易于理解的文本格式。
"""

import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

# 获取logger
logger = logging.getLogger('app')

def format_price_data(market_data: Dict[str, Any]) -> str:
    """
    将价格数据格式化为文本
    
    Args:
        market_data: 市场数据字典
        
    Returns:
        格式化后的价格数据文本
    """
    current = market_data.get('current', {})
    
    return f"""
    当前价格: {current.get('close', 'N/A')}
    今日开盘: {current.get('open', 'N/A')}
    今日最高: {current.get('high', 'N/A')}
    今日最低: {current.get('low', 'N/A')}
    """

def format_volume_data(market_data: Dict[str, Any]) -> str:
    """
    将成交量数据格式化为文本
    
    Args:
        market_data: 市场数据字典
        
    Returns:
        格式化后的成交量数据文本
    """
    current = market_data.get('current', {})
    history = market_data.get('history')
    
    # 计算今日成交量相对于近期平均值的变化，如果有历史数据
    volume_change = ""
    if history is not None and not history.empty and len(history) > 5:
        recent_volumes = [day.get('volume', 0) for day in history.tail(5).to_dict('records')]
        avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0
        current_volume = current.get('volume', 0)
        
        if avg_volume > 0:
            change_pct = (current_volume - avg_volume) / avg_volume * 100
            volume_change = f"较5日均量变化: {change_pct:.2f}%"
    
    return f"""
    今日成交量: {current.get('volume', 'N/A')}
    {volume_change}
    """

def format_technical_indicators(technical_analysis: Dict[str, Any], indicator_params: Dict[str, Any] = None) -> str:
    """
    将技术指标数据格式化为文本
    
    Args:
        technical_analysis: 技术分析结果字典
        indicator_params: 技术指标参数，用于显示指标周期
        
    Returns:
        格式化后的技术指标文本
    """
    indicators = technical_analysis.get('indicators', {})
    patterns = technical_analysis.get('patterns', [])
    
    # 默认参数
    if indicator_params is None:
        indicator_params = {
            'ma_short': 5,
            'ma_medium': 20,
            'ma_long': 50,
            'rsi_period': 14
        }
    
    # 格式化移动均线和RSI
    indicators_text = f"""
    短期均线(MA{indicator_params.get('ma_short', 5)}): {indicators.get('ma_short', 'N/A')}
    中期均线(MA{indicator_params.get('ma_medium', 20)}): {indicators.get('ma_medium', 'N/A')}
    长期均线(MA{indicator_params.get('ma_long', 50)}): {indicators.get('ma_long', 'N/A')}
    RSI({indicator_params.get('rsi_period', 14)}): {indicators.get('rsi', 'N/A')}
    """
    
    # 如果有MACD
    if 'macd' in indicators:
        indicators_text += f"MACD: {indicators.get('macd', 'N/A')}\n"
    
    # 如果有识别出的形态
    if patterns:
        patterns_text = "识别形态: " + ", ".join(patterns)
        indicators_text += f"\n{patterns_text}"
    
    return indicators_text

def format_trend_analysis(trend_analysis: Dict[str, Any]) -> str:
    """
    将趋势分析结果格式化为文本
    
    Args:
        trend_analysis: 趋势分析结果字典
        
    Returns:
        格式化后的趋势分析文本
    """
    trend = trend_analysis.get('trend', 'Unknown')
    strength = trend_analysis.get('strength', 'N/A')
    duration = trend_analysis.get('duration', 'Unknown')
    
    support = ", ".join(str(s) for s in trend_analysis.get('support_levels', []))
    resistance = ", ".join(str(r) for r in trend_analysis.get('resistance_levels', []))
    
    return f"""
    趋势方向: {trend}
    趋势强度: {strength}/10
    预计持续性: {duration}
    支撑位: {support if support else 'N/A'}
    阻力位: {resistance if resistance else 'N/A'}
    """

def format_recent_price_action(market_data: Dict[str, Any], days: int = 5) -> str:
    """
    将近期价格走势格式化为文本
    
    Args:
        market_data: 市场数据字典
        days: 显示的天数，默认为5天
        
    Returns:
        格式化后的近期价格走势文本
    """
    history = market_data.get('history')
    
    if history is None or history.empty:
        return "无近期价格数据"
        
    recent_df = history.tail(days)
    
    if recent_df.empty:
        return "无近期价格数据"
        
    result = f"近{len(recent_df)}个交易日价格:\n"
    for index, day in recent_df.iterrows():
        date = day.get('timestamp', 'N/A')
        if isinstance(date, datetime):
            date = date.strftime('%Y-%m-%d')
        open_price = day.get('open', 'N/A')
        high = day.get('high', 'N/A')
        low = day.get('low', 'N/A')
        close = day.get('close', 'N/A')
        volume = day.get('volume', 'N/A')
        
        # 计算日涨跌幅
        change_pct = ''
        if isinstance(open_price, (int, float)) and isinstance(close, (int, float)) and open_price > 0:
            change = ((close - open_price) / open_price) * 100
            change_pct = f" 涨跌幅: {change:.2f}%"
        
        result += f"日期: {date}, 开盘: {open_price}, 收盘: {close},{change_pct}\n"
        
    return result

def format_position_info(position: Dict[str, Any]) -> str:
    """
    将持仓信息格式化为文本
    
    Args:
        position: 持仓信息字典
        
    Returns:
        格式化后的持仓信息文本
    """
    quantity = position.get('quantity', 0)
    avg_price = position.get('avg_price', 0)
    last_update = position.get('last_update', '')
    
    # 尝试格式化更新时间
    update_time = ''
    if last_update:
        try:
            dt = datetime.fromisoformat(last_update)
            update_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            update_time = last_update
    
    trades = position.get('trades', [])
    
    # 计算持仓天数（如果有交易记录）
    holding_days = ''
    if trades and len(trades) > 0:
        first_trade = trades[0]
        first_timestamp = first_trade.get('timestamp', '')
        if first_timestamp:
            try:
                first_dt = datetime.fromisoformat(first_timestamp)
                days = (datetime.now() - first_dt).days
                holding_days = f"\n持仓天数: {days}天"
            except:
                pass
    
    return f"""
    持仓数量: {quantity}
    平均成本: {avg_price}
    最后更新: {update_time}{holding_days}
    """

def format_account_info(account_data: Dict[str, Any] = None) -> str:
    """
    将账户信息格式化为文本
    
    Args:
        account_data: 账户数据字典，如果为None则返回基本信息
        
    Returns:
        格式化后的账户信息文本
    """
    if account_data is None:
        return """
        总资产: 尚未获取
        可用资金: 尚未获取
        持仓市值: 尚未获取
        """
    
    total_assets = account_data.get('total_assets', 'N/A')
    available_cash = account_data.get('available_cash', 'N/A')
    positions_value = account_data.get('positions_value', 'N/A')
    
    # 计算持仓比例
    position_ratio = ''
    if isinstance(total_assets, (int, float)) and isinstance(positions_value, (int, float)) and total_assets > 0:
        ratio = (positions_value / total_assets) * 100
        position_ratio = f"\n当前持仓比例: {ratio:.2f}%"
    
    return f"""
    总资产: {total_assets}
    可用资金: {available_cash}
    持仓市值: {positions_value}{position_ratio}
    """

def calculate_price_volatility(market_data: Dict[str, Any], period: int = 20) -> str:
    """
    计算并格式化价格波动性信息
    
    Args:
        market_data: 市场数据字典
        period: 计算波动率的周期，默认为20天
        
    Returns:
        格式化后的价格波动性文本
    """
    history = market_data.get('history', [])
    
    if len(history) < period:
        return "价格波动性: 历史数据不足"
    
    # 获取最近period天的收盘价
    closes = [day.get('close', None) for day in history[-period:]]
    closes = [c for c in closes if c is not None]
    
    if len(closes) < period/2:  # 至少要有一半的数据
        return "价格波动性: 有效历史数据不足"
    
    # 计算日涨跌幅序列
    returns = []
    for i in range(1, len(closes)):
        if closes[i-1] > 0:
            daily_return = (closes[i] - closes[i-1]) / closes[i-1]
            returns.append(daily_return)
    
    if not returns:
        return "价格波动性: 无法计算"
    
    # 计算波动率 (标准差)
    import math
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    volatility = math.sqrt(variance)
    
    # 年化波动率 (假设252个交易日)
    annual_volatility = volatility * math.sqrt(252)
    
    # 简单分类波动性
    volatility_level = "低"
    if annual_volatility > 0.3:
        volatility_level = "非常高"
    elif annual_volatility > 0.2:
        volatility_level = "高"
    elif annual_volatility > 0.15:
        volatility_level = "中高"
    elif annual_volatility > 0.1:
        volatility_level = "中等"
    
    return f"""
    日波动率: {volatility:.4f}
    年化波动率: {annual_volatility:.4f}
    波动性水平: {volatility_level}
    """

def calculate_risk_metrics(symbol: str, position: Dict[str, Any], market_data: Dict[str, Any]) -> str:
    """
    计算并格式化风险指标
    
    Args:
        symbol: 资产代码
        position: 持仓信息
        market_data: 市场数据
        
    Returns:
        格式化后的风险指标文本
    """
    # 计算持仓盈亏
    current_price = market_data.get('current', {}).get('close')
    avg_price = position.get('avg_price')
    quantity = position.get('quantity')
    
    if not all([current_price, avg_price, quantity]):
        return "风险指标: 数据不足，无法计算"
    
    # 计算持仓盈亏
    absolute_pnl = (current_price - avg_price) * quantity
    percent_pnl = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0
    
    # 计算止损位置
    stop_loss = position.get('stop_loss', None)
    max_loss = "未设置止损"
    max_loss_percent = "未设置止损"
    
    if stop_loss and avg_price > 0:
        max_loss = (stop_loss - avg_price) * quantity
        max_loss_percent = ((stop_loss / avg_price) - 1) * 100
    
    return f"""
    当前盈亏: {absolute_pnl:.2f} ({percent_pnl:.2f}%)
    最大止损: {max_loss if isinstance(max_loss, str) else f"{max_loss:.2f}"} ({max_loss_percent if isinstance(max_loss_percent, str) else f"{max_loss_percent:.2f}%"})
    持仓市值: {current_price * quantity:.2f}
    """ 
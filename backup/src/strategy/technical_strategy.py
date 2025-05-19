#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
技术分析策略模块
实现基于技术指标的策略生成
作为LLM策略的备选方案
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Union, Any
from src.utils.logger import get_logger

logger = get_logger("tech_strategy")

class TechnicalStrategy:
    """
    技术分析策略类
    基于常见技术指标生成交易信号
    """
    def __init__(self):
        """初始化技术分析策略"""
        pass
    
    def analyze(self, symbol: str, kline_data: List[Dict]) -> Dict[str, Any]:
        """
        分析K线数据并生成策略建议
        
        Args:
            symbol: 交易标的代码
            kline_data: K线数据列表
            
        Returns:
            包含交易信号和分析结果的字典
        """
        logger.info(f"对{symbol}进行技术分析")
        
        if not kline_data or len(kline_data) < 20:
            logger.warning(f"{symbol}的K线数据不足，无法进行分析")
            return {
                "signal": "持有",
                "strength": "低",
                "reason": "数据不足，无法进行可靠分析",
                "position_size": 0
            }
        
        try:
            # 将K线数据转换为DataFrame
            df = pd.DataFrame(kline_data)
            
            # 确保数据类型正确
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 计算技术指标
            df = self._calculate_indicators(df)
            
            # 获取最新价格
            latest_close = float(df['close'].iloc[-1])
            
            # 分析多个技术指标
            macd_signal = self._analyze_macd(df)
            rsi_signal = self._analyze_rsi(df)
            ma_signal = self._analyze_moving_averages(df)
            
            # 汇总分析结果
            signals = [macd_signal, rsi_signal, ma_signal]
            buy_count = signals.count("买入")
            sell_count = signals.count("卖出")
            hold_count = signals.count("持有")
            
            # 确定最终信号
            if buy_count > sell_count and buy_count > hold_count:
                signal = "买入"
                strength = "高" if buy_count >= 2 else "中"
                reason = self._generate_buy_reason(df)
                stop_loss = round(latest_close * 0.95, 2)  # 简单的5%止损位
                take_profit = round(latest_close * 1.15, 2)  # 简单的15%止盈位
                position_size = 0.3 if buy_count >= 2 else 0.2
            elif sell_count > buy_count and sell_count > hold_count:
                signal = "卖出"
                strength = "高" if sell_count >= 2 else "中"
                reason = self._generate_sell_reason(df)
                stop_loss = None
                take_profit = None
                position_size = 0
            else:
                signal = "持有"
                strength = "中"
                reason = "技术指标显示混合信号，市场可能处于盘整阶段，建议持有观望。"
                stop_loss = round(latest_close * 0.93, 2) if 'stop_loss' in locals() else None
                take_profit = round(latest_close * 1.1, 2) if 'take_profit' in locals() else None
                position_size = 0.1
            
            return {
                "signal": signal,
                "strength": strength,
                "reason": reason,
                "entry_price": latest_close if signal == "买入" else None,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "position_size": position_size
            }
            
        except Exception as e:
            logger.error(f"技术分析过程中出错: {str(e)}")
            return {
                "signal": "持有",
                "strength": "低",
                "reason": f"分析过程中出错: {str(e)}",
                "position_size": 0
            }
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算常用技术指标"""
        # 确保按日期排序
        if 'date' in df.columns:
            df = df.sort_values('date')
        
        # 移动平均线
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma10'] = df['close'].rolling(window=10).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        
        # MACD
        df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = df['ema12'] - df['ema26']
        df['signal_line'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_histogram'] = df['macd'] - df['signal_line']
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 布林带
        df['sma20'] = df['close'].rolling(window=20).mean()
        df['stddev'] = df['close'].rolling(window=20).std()
        df['bollinger_upper'] = df['sma20'] + (df['stddev'] * 2)
        df['bollinger_lower'] = df['sma20'] - (df['stddev'] * 2)
        
        return df
    
    def _analyze_macd(self, df: pd.DataFrame) -> str:
        """分析MACD指标"""
        if len(df) < 2:
            return "持有"
        
        # 判断MACD金叉和死叉
        last_histogram = df['macd_histogram'].iloc[-1]
        prev_histogram = df['macd_histogram'].iloc[-2]
        
        if prev_histogram < 0 and last_histogram > 0:
            return "买入"  # MACD金叉
        elif prev_histogram > 0 and last_histogram < 0:
            return "卖出"  # MACD死叉
        elif last_histogram > 0 and last_histogram > prev_histogram:
            return "买入"  # MACD柱状图向上扩大
        elif last_histogram < 0 and last_histogram < prev_histogram:
            return "卖出"  # MACD柱状图向下扩大
        else:
            return "持有"
    
    def _analyze_rsi(self, df: pd.DataFrame) -> str:
        """分析RSI指标"""
        if 'rsi' not in df.columns or df['rsi'].isna().iloc[-1]:
            return "持有"
        
        last_rsi = df['rsi'].iloc[-1]
        
        if last_rsi < 30:
            return "买入"  # 超卖
        elif last_rsi > 70:
            return "卖出"  # 超买
        else:
            return "持有"
    
    def _analyze_moving_averages(self, df: pd.DataFrame) -> str:
        """分析移动平均线"""
        if len(df) < 20 or df['ma5'].isna().iloc[-1] or df['ma20'].isna().iloc[-1]:
            return "持有"
        
        ma5 = df['ma5'].iloc[-1]
        ma20 = df['ma20'].iloc[-1]
        
        if ma5 > ma20 and df['ma5'].iloc[-2] <= df['ma20'].iloc[-2]:
            return "买入"  # 短期均线上穿长期均线
        elif ma5 < ma20 and df['ma5'].iloc[-2] >= df['ma20'].iloc[-2]:
            return "卖出"  # 短期均线下穿长期均线
        elif ma5 > ma20:
            return "买入"  # 短期均线在长期均线上方
        elif ma5 < ma20:
            return "卖出"  # 短期均线在长期均线下方
        else:
            return "持有"
    
    def _generate_buy_reason(self, df: pd.DataFrame) -> str:
        """生成买入理由"""
        reasons = []
        
        # 检查MACD
        if df['macd_histogram'].iloc[-1] > 0 and df['macd_histogram'].iloc[-2] < 0:
            reasons.append("MACD指标形成金叉")
        elif df['macd_histogram'].iloc[-1] > 0:
            reasons.append("MACD指标处于上升趋势")
        
        # 检查RSI
        if 'rsi' in df.columns and not df['rsi'].isna().iloc[-1]:
            last_rsi = df['rsi'].iloc[-1]
            if last_rsi < 30:
                reasons.append("RSI指标显示市场超卖")
            elif 30 <= last_rsi <= 50:
                reasons.append("RSI指标从低位开始回升")
        
        # 检查移动平均线
        if 'ma5' in df.columns and 'ma20' in df.columns:
            if df['ma5'].iloc[-1] > df['ma20'].iloc[-1] and df['ma5'].iloc[-2] <= df['ma20'].iloc[-2]:
                reasons.append("短期均线上穿长期均线，形成黄金交叉")
            elif df['ma5'].iloc[-1] > df['ma20'].iloc[-1]:
                reasons.append("短期均线位于长期均线上方，保持上升趋势")
        
        # 检查布林带
        if 'bollinger_lower' in df.columns:
            if df['close'].iloc[-1] < df['bollinger_lower'].iloc[-1]:
                reasons.append("价格触及布林带下轨，存在反弹机会")
        
        # 检查成交量
        if 'volume' in df.columns and len(df) > 5:
            avg_volume = df['volume'].iloc[-6:-1].mean()
            if df['volume'].iloc[-1] > avg_volume * 1.5:
                reasons.append("成交量显著放大，市场兴趣增加")
        
        if not reasons:
            return "综合技术指标分析显示买入信号，可能存在上涨机会。"
        else:
            return "技术分析结果：" + "，".join(reasons) + "。建议买入并设置止损。"
    
    def _generate_sell_reason(self, df: pd.DataFrame) -> str:
        """生成卖出理由"""
        reasons = []
        
        # 检查MACD
        if df['macd_histogram'].iloc[-1] < 0 and df['macd_histogram'].iloc[-2] > 0:
            reasons.append("MACD指标形成死叉")
        elif df['macd_histogram'].iloc[-1] < 0:
            reasons.append("MACD指标处于下降趋势")
        
        # 检查RSI
        if 'rsi' in df.columns and not df['rsi'].isna().iloc[-1]:
            last_rsi = df['rsi'].iloc[-1]
            if last_rsi > 70:
                reasons.append("RSI指标显示市场超买")
            elif 70 >= last_rsi >= 50:
                reasons.append("RSI指标从高位开始回落")
        
        # 检查移动平均线
        if 'ma5' in df.columns and 'ma20' in df.columns:
            if df['ma5'].iloc[-1] < df['ma20'].iloc[-1] and df['ma5'].iloc[-2] >= df['ma20'].iloc[-2]:
                reasons.append("短期均线下穿长期均线，形成死亡交叉")
            elif df['ma5'].iloc[-1] < df['ma20'].iloc[-1]:
                reasons.append("短期均线位于长期均线下方，保持下降趋势")
        
        # 检查布林带
        if 'bollinger_upper' in df.columns:
            if df['close'].iloc[-1] > df['bollinger_upper'].iloc[-1]:
                reasons.append("价格触及布林带上轨，存在回调风险")
        
        # 检查成交量
        if 'volume' in df.columns and len(df) > 5:
            if df['close'].iloc[-1] > df['close'].iloc[-2] and df['volume'].iloc[-1] < df['volume'].iloc[-2]:
                reasons.append("价格上涨但成交量萎缩，上涨动能不足")
        
        if not reasons:
            return "综合技术指标分析显示卖出信号，可能面临下跌风险。"
        else:
            return "技术分析结果：" + "，".join(reasons) + "。建议卖出规避风险。" 
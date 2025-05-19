"""
金字塔交易法核心模块 - 实现金字塔交易法的核心算法和逻辑
"""
from enum import Enum
from typing import Dict, List, Tuple, Optional, Union
import numpy as np
import pandas as pd
from utils.logger import get_logger

logger = get_logger("pyramid")

class TrendDirection(Enum):
    """趋势方向枚举"""
    UP = 1      # 上升趋势
    DOWN = -1   # 下降趋势
    NEUTRAL = 0 # 盘整

class SignalType(Enum):
    """信号类型枚举"""
    ENTRY = 1       # 入场信号
    EXIT = 2        # 出场信号
    SCALE_IN = 3    # 加仓信号
    SCALE_OUT = 4   # 减仓信号
    STOP_LOSS = 5   # 止损信号

class TradeDirection(Enum):
    """交易方向枚举"""
    LONG = 1    # 做多
    SHORT = -1  # 做空
    NONE = 0    # 无交易

class PyramidStrategy:
    """
    金字塔交易法策略
    
    金字塔交易法是一种趋势跟踪策略，其核心理念是：
    1. 在趋势确认后入场
    2. 顺着趋势方向逐步加仓（金字塔式建仓）
    3. 在趋势反转或止损条件触发时退出
    """
    def __init__(
        self,
        ma_short_period: int = 20,
        ma_long_period: int = 60,
        atr_period: int = 14,
        breakout_periods: int = 20,
        volume_factor: float = 1.5,
        trail_stop_atr: float = 2.0,
        time_stop_bars: int = 10,
        profit_target_atr: float = 5.0,
        max_pyramids: int = 4,
        pyramid_factor: float = 0.5,
        allow_short: bool = True
    ):
        """
        初始化金字塔交易策略
        
        Args:
            ma_short_period: 短期均线周期
            ma_long_period: 长期均线周期
            atr_period: ATR周期
            breakout_periods: 突破周期数
            volume_factor: 成交量放大因子
            trail_stop_atr: 追踪止损ATR乘数
            time_stop_bars: 时间止损周期数
            profit_target_atr: 获利目标ATR乘数
            max_pyramids: 最大金字塔层数（最大加仓次数）
            pyramid_factor: 金字塔系数（每次加仓规模缩减比例）
            allow_short: 是否允许做空
        """
        self.ma_short_period = ma_short_period
        self.ma_long_period = ma_long_period
        self.atr_period = atr_period
        self.breakout_periods = breakout_periods
        self.volume_factor = volume_factor
        self.trail_stop_atr = trail_stop_atr
        self.time_stop_bars = time_stop_bars
        self.profit_target_atr = profit_target_atr
        self.max_pyramids = max_pyramids
        self.pyramid_factor = pyramid_factor
        self.allow_short = allow_short
        
        # 当前状态
        self.current_trend = TrendDirection.NEUTRAL
        self.current_position = 0  # 当前持仓数量
        self.pyramid_level = 0     # 当前金字塔层级
        self.entry_price = 0.0     # 入场价格
        self.highest_price = 0.0   # 持仓期间最高价
        self.lowest_price = 0.0    # 持仓期间最低价
        self.stop_loss_price = 0.0 # 止损价格
        self.last_signal_bar = 0   # 最后一次信号触发的bar序号
        self.position_direction = TradeDirection.NONE  # 持仓方向
        
        logger.info(f"金字塔交易策略初始化完成, 短期均线周期: {ma_short_period}, 长期均线周期: {ma_long_period}")
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标
        
        Args:
            df: 包含OHLCV数据的DataFrame
            
        Returns:
            添加了技术指标的DataFrame
        """
        # 确保数据包含所需列
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in df.columns:
                raise ValueError(f"数据缺少必要列: {col}")
        
        # 计算短期和长期移动平均线
        df['ma_short'] = df['close'].rolling(window=self.ma_short_period).mean()
        df['ma_long'] = df['close'].rolling(window=self.ma_long_period).mean()
        
        # 计算ATR (Average True Range)
        df['tr'] = np.maximum(
            np.maximum(
                df['high'] - df['low'],
                np.abs(df['high'] - df['close'].shift(1))
            ),
            np.abs(df['low'] - df['close'].shift(1))
        )
        df['atr'] = df['tr'].rolling(window=self.atr_period).mean()
        
        # 计算突破指标
        df['highest_high'] = df['high'].rolling(window=self.breakout_periods).max()
        df['lowest_low'] = df['low'].rolling(window=self.breakout_periods).min()
        
        # 计算成交量指标
        df['volume_avg'] = df['volume'].rolling(window=self.breakout_periods).mean()
        df['volume_ratio'] = df['volume'] / df['volume_avg']
        
        # 计算趋势指标
        df['trend'] = np.where(
            df['ma_short'] > df['ma_long'], 
            TrendDirection.UP.value, 
            np.where(
                df['ma_short'] < df['ma_long'],
                TrendDirection.DOWN.value,
                TrendDirection.NEUTRAL.value
            )
        )
        
        logger.info(f"计算完成技术指标, 数据长度: {len(df)}")
        return df
    
    def identify_trend(self, df: pd.DataFrame, index: int = -1) -> TrendDirection:
        """
        识别趋势方向
        
        Args:
            df: 包含技术指标的DataFrame
            index: 索引位置，默认为最后一行
            
        Returns:
            趋势方向
        """
        if 'trend' not in df.columns:
            raise ValueError("数据中缺少趋势指标")
        
        if index < 0:
            index = len(df) + index
        
        if index >= len(df) or index < 0:
            raise ValueError(f"索引超出范围: {index}")
        
        trend_value = df.iloc[index]['trend']
        return TrendDirection(trend_value)
    
    def generate_entry_signal(self, df: pd.DataFrame, index: int = -1) -> Tuple[bool, Optional[TradeDirection], Optional[float]]:
        """
        生成入场信号
        
        Args:
            df: 包含技术指标的DataFrame
            index: 索引位置，默认为最后一行
            
        Returns:
            (是否有信号, 信号方向, 入场价格)
        """
        if index < 0:
            index = len(df) + index
            
        if index < self.breakout_periods or index >= len(df):
            return False, None, None
        
        # 获取当前数据
        row = df.iloc[index]
        prev_row = df.iloc[index-1]
        close = row['close']
        high = row['high']
        low = row['low']
        volume_ratio = row['volume_ratio']
        highest_high = prev_row['highest_high']
        lowest_low = prev_row['lowest_low']
        trend = self.identify_trend(df, index)
        
        # 如果已有持仓，不生成入场信号
        if self.current_position != 0:
            return False, None, None
        
        # 多头入场条件：
        # 1. 上升趋势
        # 2. 价格突破前期高点
        # 3. 成交量放大
        if trend == TrendDirection.UP and high > highest_high and volume_ratio > self.volume_factor:
            logger.info(f"生成多头入场信号, 收盘价: {close}, 突破前期高点: {highest_high}")
            return True, TradeDirection.LONG, close
        
        # 空头入场条件（如果允许做空）：
        # 1. 下降趋势
        # 2. 价格跌破前期低点
        # 3. 成交量放大
        if self.allow_short and trend == TrendDirection.DOWN and low < lowest_low and volume_ratio > self.volume_factor:
            logger.info(f"生成空头入场信号, 收盘价: {close}, 跌破前期低点: {lowest_low}")
            return True, TradeDirection.SHORT, close
            
        return False, None, None
    
    def generate_scale_in_signal(self, df: pd.DataFrame, index: int = -1) -> Tuple[bool, Optional[float]]:
        """
        生成加仓信号
        
        Args:
            df: 包含技术指标的DataFrame
            index: 索引位置，默认为最后一行
            
        Returns:
            (是否有信号, 加仓价格)
        """
        if index < 0:
            index = len(df) + index
            
        if index >= len(df) or self.current_position == 0 or self.pyramid_level >= self.max_pyramids:
            return False, None
        
        # 获取当前数据
        row = df.iloc[index]
        close = row['close']
        high = row['high']
        low = row['low']
        atr = row['atr']
        
        # 多头加仓条件：
        # 1. 当前为多头持仓
        # 2. 价格比上次入场点上涨至少 1 个ATR
        # 3. 未达到最大金字塔层数
        if self.position_direction == TradeDirection.LONG:
            min_price_move = self.entry_price + atr
            if high > min_price_move and self.pyramid_level < self.max_pyramids:
                logger.info(f"生成多头加仓信号, 收盘价: {close}, 当前金字塔层级: {self.pyramid_level}")
                return True, close
        
        # 空头加仓条件：
        # 1. 当前为空头持仓
        # 2. 价格比上次入场点下跌至少 1 个ATR
        # 3. 未达到最大金字塔层数
        elif self.position_direction == TradeDirection.SHORT:
            max_price_move = self.entry_price - atr
            if low < max_price_move and self.pyramid_level < self.max_pyramids:
                logger.info(f"生成空头加仓信号, 收盘价: {close}, 当前金字塔层级: {self.pyramid_level}")
                return True, close
                
        return False, None
    
    def generate_exit_signal(self, df: pd.DataFrame, index: int = -1) -> Tuple[bool, SignalType, Optional[float]]:
        """
        生成出场信号，包括正常出场、止损和获利了结
        
        Args:
            df: 包含技术指标的DataFrame
            index: 索引位置，默认为最后一行
            
        Returns:
            (是否有信号, 信号类型, 出场价格)
        """
        if index < 0:
            index = len(df) + index
            
        if index >= len(df) or self.current_position == 0:
            return False, SignalType.EXIT, None
        
        # 获取当前数据
        row = df.iloc[index]
        close = row['close']
        high = row['high']
        low = row['low']
        atr = row['atr']
        trend = self.identify_trend(df, index)
        
        # 计算持仓时间
        bars_since_entry = index - self.last_signal_bar
        
        # 更新持仓期间的最高/最低价
        if self.position_direction == TradeDirection.LONG:
            self.highest_price = max(self.highest_price, high)
            
            # 止损条件（多头）：
            # 1. 价格低于追踪止损价格
            stop_price = self.highest_price - atr * self.trail_stop_atr
            if low < stop_price:
                logger.info(f"生成多头止损信号, 收盘价: {close}, 止损价: {stop_price}")
                return True, SignalType.STOP_LOSS, close
            
            # 获利了结条件（多头）：
            # 1. 价格高于入场价格 + ATR * 获利目标系数
            profit_target = self.entry_price + atr * self.profit_target_atr
            if high > profit_target:
                logger.info(f"生成多头获利了结信号, 收盘价: {close}, 获利目标: {profit_target}")
                return True, SignalType.EXIT, close
            
            # 趋势反转条件（多头）：
            # 1. 趋势由上升转为下降
            if trend == TrendDirection.DOWN and self.current_trend == TrendDirection.UP:
                logger.info(f"生成多头趋势反转出场信号, 收盘价: {close}")
                return True, SignalType.EXIT, close
                
        elif self.position_direction == TradeDirection.SHORT:
            self.lowest_price = min(self.lowest_price, low)
            
            # 止损条件（空头）：
            # 1. 价格高于追踪止损价格
            stop_price = self.lowest_price + atr * self.trail_stop_atr
            if high > stop_price:
                logger.info(f"生成空头止损信号, 收盘价: {close}, 止损价: {stop_price}")
                return True, SignalType.STOP_LOSS, close
                
            # 获利了结条件（空头）：
            # 1. 价格低于入场价格 - ATR * 获利目标系数
            profit_target = self.entry_price - atr * self.profit_target_atr
            if low < profit_target:
                logger.info(f"生成空头获利了结信号, 收盘价: {close}, 获利目标: {profit_target}")
                return True, SignalType.EXIT, close
            
            # 趋势反转条件（空头）：
            # 1. 趋势由下降转为上升
            if trend == TrendDirection.UP and self.current_trend == TrendDirection.DOWN:
                logger.info(f"生成空头趋势反转出场信号, 收盘价: {close}")
                return True, SignalType.EXIT, close
                
        # 时间止损条件：
        # 1. 持仓时间超过设定的时间止损周期
        if bars_since_entry > self.time_stop_bars:
            logger.info(f"生成时间止损信号, 收盘价: {close}, 持仓时间: {bars_since_entry}根K线")
            return True, SignalType.EXIT, close
            
        return False, SignalType.EXIT, None
        
    def calculate_scale_in_size(self, base_size: float) -> float:
        """
        计算加仓规模
        
        Args:
            base_size: 基础仓位规模
            
        Returns:
            加仓规模
        """
        # 金字塔加仓，每次加仓规模递减
        scale_factor = self.pyramid_factor ** self.pyramid_level
        return base_size * scale_factor
    
    def update_position(self, price: float, size: float, direction: TradeDirection, signal_type: SignalType, bar_index: int):
        """
        更新持仓状态
        
        Args:
            price: 交易价格
            size: 交易数量
            direction: 交易方向
            signal_type: 信号类型
            bar_index: K线索引
        """
        if signal_type == SignalType.ENTRY:
            # 入场信号
            self.current_position = size if direction == TradeDirection.LONG else -size
            self.position_direction = direction
            self.entry_price = price
            self.highest_price = price
            self.lowest_price = price
            self.pyramid_level = 1
            self.last_signal_bar = bar_index
            logger.info(f"入场: 方向={direction.name}, 价格={price}, 数量={size}")
            
        elif signal_type == SignalType.SCALE_IN:
            # 加仓信号
            additional_size = size * self.calculate_scale_in_size(1.0)
            if self.position_direction == TradeDirection.LONG:
                self.current_position += additional_size
            else:
                self.current_position -= additional_size
                
            self.pyramid_level += 1
            self.last_signal_bar = bar_index
            logger.info(f"加仓: 方向={self.position_direction.name}, 价格={price}, 数量={additional_size}, 金字塔层级={self.pyramid_level}")
            
        elif signal_type in [SignalType.EXIT, SignalType.STOP_LOSS]:
            # 出场信号
            old_position = self.current_position
            self.current_position = 0
            self.position_direction = TradeDirection.NONE
            self.pyramid_level = 0
            logger.info(f"出场: 信号类型={signal_type.name}, 价格={price}, 数量={abs(old_position)}")
    
    def get_position_status(self) -> Dict:
        """
        获取当前持仓状态
        
        Returns:
            持仓状态字典
        """
        return {
            "position": self.current_position,
            "direction": self.position_direction.name if self.position_direction else "NONE",
            "entry_price": self.entry_price,
            "pyramid_level": self.pyramid_level,
            "highest_price": self.highest_price,
            "lowest_price": self.lowest_price
        }
    
    def run_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        运行策略，生成交易信号
        
        Args:
            df: 包含OHLCV数据的DataFrame
            
        Returns:
            添加了交易信号的DataFrame
        """
        # 计算技术指标
        df = self.calculate_indicators(df)
        
        # 初始化信号列
        df['signal'] = 0
        df['position'] = 0
        
        # 重置状态
        self.current_position = 0
        self.position_direction = TradeDirection.NONE
        self.pyramid_level = 0
        
        # 遍历K线数据
        for i in range(self.ma_long_period, len(df)):
            # 更新当前趋势
            self.current_trend = self.identify_trend(df, i)
            
            # 如果没有持仓，检查入场信号
            if self.current_position == 0:
                has_signal, direction, price = self.generate_entry_signal(df, i)
                if has_signal and price is not None:
                    # 生成入场信号
                    df.loc[df.index[i], 'signal'] = 1 if direction == TradeDirection.LONG else -1
                    # 更新持仓
                    self.update_position(price, 1.0, direction, SignalType.ENTRY, i)
            else:
                # 如果有持仓，先检查出场信号
                has_exit, exit_type, exit_price = self.generate_exit_signal(df, i)
                if has_exit and exit_price is not None:
                    # 生成出场信号
                    df.loc[df.index[i], 'signal'] = 2 if self.position_direction == TradeDirection.LONG else -2
                    # 更新持仓
                    self.update_position(exit_price, abs(self.current_position), self.position_direction, exit_type, i)
                else:
                    # 如果没有出场信号，检查加仓信号
                    has_scale_in, scale_price = self.generate_scale_in_signal(df, i)
                    if has_scale_in and scale_price is not None:
                        # 生成加仓信号
                        df.loc[df.index[i], 'signal'] = 3 if self.position_direction == TradeDirection.LONG else -3
                        # 更新持仓
                        self.update_position(scale_price, 1.0, self.position_direction, SignalType.SCALE_IN, i)
            
            # 更新持仓列
            df.loc[df.index[i], 'position'] = self.current_position
        
        logger.info(f"策略运行完成, 生成信号数: {(df['signal'] != 0).sum()}")
        return df

# 创建默认策略实例
def create_pyramid_strategy(
    ma_short_period: int = None,
    ma_long_period: int = None,
    atr_period: int = None,
    breakout_periods: int = None,
    volume_factor: float = None,
    trail_stop_atr: float = None,
    time_stop_bars: int = None,
    profit_target_atr: float = None,
    max_pyramids: int = None,
    pyramid_factor: float = None,
    allow_short: bool = True
) -> PyramidStrategy:
    """
    创建金字塔交易策略实例
    
    从配置文件加载参数，如果有指定参数则使用指定参数
    
    Args:
        ma_short_period: 短期均线周期
        ma_long_period: 长期均线周期
        atr_period: ATR周期
        breakout_periods: 突破周期数
        volume_factor: 成交量放大因子
        trail_stop_atr: 追踪止损ATR乘数
        time_stop_bars: 时间止损周期数
        profit_target_atr: 获利目标ATR乘数
        max_pyramids: 最大金字塔层数
        pyramid_factor: 金字塔系数
        allow_short: 是否允许做空
        
    Returns:
        金字塔交易策略实例
    """
    # 从配置文件加载参数
    from utils.config import get_config
    
    # 如果参数为None，则从配置文件中加载
    if ma_short_period is None:
        ma_short_period = get_config("pyramid_strategy", "trend", {}).get("ma_short", 20)
    if ma_long_period is None:
        ma_long_period = get_config("pyramid_strategy", "trend", {}).get("ma_long", 60)
    if atr_period is None:
        atr_period = get_config("pyramid_strategy", "trend", {}).get("atr_period", 14)
    if breakout_periods is None:
        breakout_periods = get_config("pyramid_strategy", "entry", {}).get("breakout_periods", 20)
    if volume_factor is None:
        volume_factor = get_config("pyramid_strategy", "entry", {}).get("volume_factor", 1.5)
    if trail_stop_atr is None:
        trail_stop_atr = get_config("pyramid_strategy", "exit", {}).get("trailing_stop_atr", 2.0)
    if time_stop_bars is None:
        time_stop_bars = get_config("pyramid_strategy", "exit", {}).get("time_stop_bars", 10)
    if profit_target_atr is None:
        profit_target_atr = get_config("pyramid_strategy", "exit", {}).get("profit_target_atr", 5.0)
    if max_pyramids is None:
        max_pyramids = get_config("pyramid_strategy", "scale_in", {}).get("max_positions", 4)
    if pyramid_factor is None:
        pyramid_factor = get_config("pyramid_strategy", "scale_in", {}).get("position_scale", 0.5)
    
    return PyramidStrategy(
        ma_short_period=ma_short_period,
        ma_long_period=ma_long_period,
        atr_period=atr_period,
        breakout_periods=breakout_periods,
        volume_factor=volume_factor,
        trail_stop_atr=trail_stop_atr,
        time_stop_bars=time_stop_bars,
        profit_target_atr=profit_target_atr,
        max_pyramids=max_pyramids,
        pyramid_factor=pyramid_factor,
        allow_short=allow_short
    )

if __name__ == "__main__":
    # 测试代码
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta
    
    # 创建模拟数据
    dates = [datetime.now() - timedelta(days=i) for i in range(200, 0, -1)]
    data = {
        'open': np.random.normal(100, 1, 200),
        'high': np.random.normal(101, 1, 200),
        'low': np.random.normal(99, 1, 200),
        'close': np.random.normal(100, 1, 200),
        'volume': np.random.normal(1000000, 100000, 200)
    }
    
    # 确保high >= open和close，low <= open和close
    for i in range(len(data['high'])):
        data['high'][i] = max(data['high'][i], data['open'][i], data['close'][i])
        data['low'][i] = min(data['low'][i], data['open'][i], data['close'][i])
    
    df = pd.DataFrame(data, index=dates)
    
    # 创建策略实例
    strategy = create_pyramid_strategy()
    
    # 运行策略
    result_df = strategy.run_strategy(df)
    
    # 打印结果
    print(result_df[['close', 'ma_short', 'ma_long', 'signal', 'position']].tail(20)) 
"""
仓位管理模块 - 基于金字塔交易法的仓位管理与控制
"""
from typing import Dict, List, Tuple, Optional, Union
import pandas as pd
import numpy as np
from utils.logger import get_logger
from utils.risk_control import get_risk_controller
from core.pyramid import TradeDirection, SignalType

logger = get_logger("position")

class Position:
    """
    单个持仓的管理类
    """
    def __init__(
        self,
        symbol: str,
        direction: TradeDirection,
        entry_price: float,
        stop_price: float,
        position_size: float,
        entry_time: pd.Timestamp,
        entry_id: str = None
    ):
        """
        初始化持仓对象
        
        Args:
            symbol: 交易品种代码
            direction: 交易方向
            entry_price: 入场价格
            stop_price: 止损价格
            position_size: 持仓规模（股数/手数）
            entry_time: 入场时间
            entry_id: 入场标识
        """
        self.symbol = symbol
        self.direction = direction
        self.entry_price = entry_price
        self.stop_price = stop_price
        self.position_size = position_size
        self.entry_time = entry_time
        self.entry_id = entry_id or f"{symbol}_{entry_time.strftime('%Y%m%d%H%M%S')}"
        
        # 持仓状态
        self.is_open = True
        self.exit_price = None
        self.exit_time = None
        self.exit_reason = None
        self.realized_profit = 0.0
        self.unrealized_profit = 0.0
        
        # 加仓记录
        self.scale_ins: List[Dict] = []
        self.total_position_size = position_size
        self.average_entry_price = entry_price
        
        logger.info(f"创建持仓: {symbol}, 方向={direction.name}, 入场价={entry_price}, "
                   f"止损价={stop_price}, 规模={position_size}")
    
    def add_scale_in(self, price: float, size: float, time: pd.Timestamp):
        """
        添加加仓记录
        
        Args:
            price: 加仓价格
            size: 加仓规模
            time: 加仓时间
        """
        scale_in = {
            "price": price,
            "size": size,
            "time": time
        }
        self.scale_ins.append(scale_in)
        
        # 更新总持仓规模和平均入场价格
        old_total = self.total_position_size
        new_total = old_total + size
        self.average_entry_price = (self.average_entry_price * old_total + price * size) / new_total
        self.total_position_size = new_total
        
        logger.info(f"加仓: {self.symbol}, 价格={price}, 规模={size}, "
                   f"总规模={self.total_position_size}, 平均入场价={self.average_entry_price}")
    
    def close_position(self, price: float, time: pd.Timestamp, reason: str):
        """
        平仓
        
        Args:
            price: 平仓价格
            time: 平仓时间
            reason: 平仓原因
        """
        if not self.is_open:
            logger.warning(f"尝试平仓已关闭的持仓: {self.symbol}")
            return
        
        self.is_open = False
        self.exit_price = price
        self.exit_time = time
        self.exit_reason = reason
        
        # 计算平仓盈亏
        if self.direction == TradeDirection.LONG:
            profit = (price - self.average_entry_price) * self.total_position_size
        else:
            profit = (self.average_entry_price - price) * self.total_position_size
            
        self.realized_profit = profit
        self.unrealized_profit = 0.0
        
        logger.info(f"平仓: {self.symbol}, 价格={price}, 平均入场价={self.average_entry_price}, "
                   f"总规模={self.total_position_size}, 盈亏={profit}, 原因={reason}")
    
    def update_unrealized_profit(self, current_price: float):
        """
        更新未实现盈亏
        
        Args:
            current_price: 当前价格
        """
        if not self.is_open:
            self.unrealized_profit = 0.0
            return
        
        if self.direction == TradeDirection.LONG:
            self.unrealized_profit = (current_price - self.average_entry_price) * self.total_position_size
        else:
            self.unrealized_profit = (self.average_entry_price - current_price) * self.total_position_size
    
    def get_status(self) -> Dict:
        """
        获取持仓状态
        
        Returns:
            持仓状态字典
        """
        status = {
            "symbol": self.symbol,
            "direction": self.direction.name,
            "entry_price": self.entry_price,
            "average_entry_price": self.average_entry_price,
            "stop_price": self.stop_price,
            "position_size": self.position_size,
            "total_position_size": self.total_position_size,
            "entry_time": self.entry_time,
            "is_open": self.is_open,
            "unrealized_profit": self.unrealized_profit,
            "scale_in_count": len(self.scale_ins)
        }
        
        # 如果已平仓，添加平仓信息
        if not self.is_open:
            status.update({
                "exit_price": self.exit_price,
                "exit_time": self.exit_time,
                "exit_reason": self.exit_reason,
                "realized_profit": self.realized_profit,
                "holding_period": (self.exit_time - self.entry_time).total_seconds() / 86400  # 持仓天数
            })
            
        return status


class PositionManager:
    """
    仓位管理器，负责管理所有持仓
    """
    def __init__(self, initial_capital: float = 100000.0):
        """
        初始化仓位管理器
        
        Args:
            initial_capital: 初始资金
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        
        # 当前持仓
        self.positions: Dict[str, Position] = {}
        
        # 历史持仓
        self.closed_positions: List[Position] = []
        
        # 获取风险控制器
        self.risk_controller = get_risk_controller(initial_capital=initial_capital)
        
        logger.info(f"仓位管理器初始化完成，初始资金: {initial_capital}")
    
    def open_position(
        self,
        symbol: str,
        direction: TradeDirection,
        entry_price: float,
        stop_price: float,
        entry_time: pd.Timestamp,
        position_size: Optional[float] = None
    ) -> Optional[Position]:
        """
        开仓
        
        Args:
            symbol: 交易品种代码
            direction: 交易方向
            entry_price: 入场价格
            stop_price: 止损价格
            entry_time: 入场时间
            position_size: 持仓规模，如果为None则根据风险计算
            
        Returns:
            创建的持仓对象
        """
        # 检查是否已有该品种的持仓
        if symbol in self.positions:
            logger.warning(f"已存在持仓，不能重复开仓: {symbol}")
            return None
        
        # 如果未指定持仓规模，使用风险管理计算
        if position_size is None:
            position_size, risk_amount = self.risk_controller.calculate_position_size(
                symbol=symbol,
                entry_price=entry_price,
                stop_price=stop_price
            )
            
            # 检查是否允许交易
            if not self.risk_controller.is_trade_allowed(symbol, risk_amount):
                logger.warning(f"交易风险超过限制，拒绝开仓: {symbol}")
                return None
            
            # 如果计算出的头寸为0，表示无法满足风险要求
            if position_size <= 0:
                logger.warning(f"计算头寸规模为0，拒绝开仓: {symbol}")
                return None
        else:
            # 使用指定的头寸规模，计算风险金额
            risk_amount = abs(entry_price - stop_price) * position_size
        
        # 创建持仓对象
        position = Position(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_price=stop_price,
            position_size=position_size,
            entry_time=entry_time
        )
        
        # 添加到持仓列表
        self.positions[symbol] = position
        
        # 更新风险控制器
        self.risk_controller.add_position(symbol, position_size, risk_amount)
        
        # 更新资金
        trade_cost = entry_price * position_size
        self.current_capital -= trade_cost
        
        logger.info(f"开仓成功: {symbol}, 方向={direction.name}, 价格={entry_price}, "
                  f"规模={position_size}, 资金余额={self.current_capital}")
        
        return position
    
    def scale_in_position(
        self,
        symbol: str,
        price: float,
        time: pd.Timestamp,
        scale_factor: float = 0.5
    ) -> bool:
        """
        加仓
        
        Args:
            symbol: 交易品种代码
            price: 加仓价格
            time: 加仓时间
            scale_factor: 加仓规模因子，相对于初始仓位的比例
            
        Returns:
            是否加仓成功
        """
        # 检查是否有该品种的持仓
        if symbol not in self.positions:
            logger.warning(f"没有持仓，无法加仓: {symbol}")
            return False
        
        position = self.positions[symbol]
        
        # 计算加仓规模
        scale_in_size = position.position_size * scale_factor
        
        # 计算加仓风险
        if position.direction == TradeDirection.LONG:
            stop_price = position.stop_price
        else:
            stop_price = position.stop_price
            
        risk_amount = abs(price - stop_price) * scale_in_size
        
        # 检查是否允许交易
        if not self.risk_controller.is_trade_allowed(symbol, risk_amount):
            logger.warning(f"加仓风险超过限制，拒绝加仓: {symbol}")
            return False
        
        # 更新持仓
        position.add_scale_in(price, scale_in_size, time)
        
        # 更新风险控制器
        self.risk_controller.update_position_risk(symbol, risk_amount)
        
        # 更新资金
        trade_cost = price * scale_in_size
        self.current_capital -= trade_cost
        
        logger.info(f"加仓成功: {symbol}, 价格={price}, 规模={scale_in_size}, 资金余额={self.current_capital}")
        
        return True
    
    def close_position(
        self,
        symbol: str,
        price: float,
        time: pd.Timestamp,
        reason: str = "normal"
    ) -> bool:
        """
        平仓
        
        Args:
            symbol: 交易品种代码
            price: 平仓价格
            time: 平仓时间
            reason: 平仓原因
            
        Returns:
            是否平仓成功
        """
        # 检查是否有该品种的持仓
        if symbol not in self.positions:
            logger.warning(f"没有持仓，无法平仓: {symbol}")
            return False
        
        position = self.positions[symbol]
        
        # 平仓
        position.close_position(price, time, reason)
        
        # 更新资金
        trade_return = price * position.total_position_size
        self.current_capital += trade_return
        
        # 更新风险控制器
        self.risk_controller.remove_position(symbol)
        
        # 移动到历史持仓
        self.closed_positions.append(position)
        del self.positions[symbol]
        
        # 更新风险控制器的资金
        self.risk_controller.update_capital(self.current_capital)
        
        logger.info(f"平仓成功: {symbol}, 价格={price}, 总规模={position.total_position_size}, "
                  f"盈亏={position.realized_profit}, 资金余额={self.current_capital}")
        
        return True
    
    def update_positions(self, current_prices: Dict[str, float]):
        """
        更新所有持仓的未实现盈亏
        
        Args:
            current_prices: 当前价格字典，键为品种代码，值为价格
        """
        for symbol, position in self.positions.items():
            if symbol in current_prices:
                position.update_unrealized_profit(current_prices[symbol])
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        获取指定品种的持仓
        
        Args:
            symbol: 交易品种代码
            
        Returns:
            持仓对象，如果不存在则返回None
        """
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Position]:
        """
        获取所有当前持仓
        
        Returns:
            持仓字典，键为品种代码，值为持仓对象
        """
        return self.positions
    
    def get_position_summary(self) -> Dict:
        """
        获取持仓摘要
        
        Returns:
            持仓摘要字典
        """
        total_unrealized_profit = sum(p.unrealized_profit for p in self.positions.values())
        total_realized_profit = sum(p.realized_profit for p in self.closed_positions)
        
        return {
            "current_capital": self.current_capital,
            "unrealized_profit": total_unrealized_profit,
            "realized_profit": total_realized_profit,
            "total_profit": total_unrealized_profit + total_realized_profit,
            "return_rate": (self.current_capital + total_unrealized_profit - self.initial_capital) / self.initial_capital,
            "open_positions_count": len(self.positions),
            "closed_positions_count": len(self.closed_positions)
        }
    
    def process_signal(
        self,
        symbol: str,
        signal_type: SignalType,
        direction: TradeDirection,
        price: float,
        stop_price: Optional[float] = None,
        time: pd.Timestamp = None,
        position_size: Optional[float] = None
    ) -> bool:
        """
        处理交易信号
        
        Args:
            symbol: 交易品种代码
            signal_type: 信号类型
            direction: 交易方向
            price: 价格
            stop_price: 止损价格，仅入场信号需要
            time: 时间，默认为当前时间
            position_size: 持仓规模，如果为None则根据风险计算
            
        Returns:
            是否处理成功
        """
        if time is None:
            import pandas as pd
            time = pd.Timestamp.now()
        
        # 根据信号类型处理
        if signal_type == SignalType.ENTRY:
            # 入场信号
            if stop_price is None:
                logger.error(f"入场信号缺少止损价格: {symbol}")
                return False
                
            return self.open_position(
                symbol=symbol,
                direction=direction,
                entry_price=price,
                stop_price=stop_price,
                entry_time=time,
                position_size=position_size
            ) is not None
            
        elif signal_type == SignalType.SCALE_IN:
            # 加仓信号
            return self.scale_in_position(
                symbol=symbol,
                price=price,
                time=time
            )
            
        elif signal_type in [SignalType.EXIT, SignalType.STOP_LOSS]:
            # 出场信号
            reason = "stop_loss" if signal_type == SignalType.STOP_LOSS else "exit"
            return self.close_position(
                symbol=symbol,
                price=price,
                time=time,
                reason=reason
            )
            
        else:
            logger.warning(f"未知的信号类型: {signal_type}")
            return False

# 单例模式，提供全局访问点
_position_manager = None

def get_position_manager(initial_capital: float = None) -> PositionManager:
    """
    获取仓位管理器实例
    
    Args:
        initial_capital: 初始资金，仅在首次创建时有效
        
    Returns:
        仓位管理器实例
    """
    global _position_manager
    if _position_manager is None:
        if initial_capital is None:
            from utils.config import get_config
            initial_capital = get_config("account", "initial_capital", 100000.0)
            
        _position_manager = PositionManager(initial_capital=initial_capital)
        
    return _position_manager

if __name__ == "__main__":
    # 测试代码
    import pandas as pd
    
    # 创建仓位管理器
    manager = get_position_manager(initial_capital=100000.0)
    
    # 开仓
    entry_time = pd.Timestamp.now()
    position = manager.open_position(
        symbol="000001.SZ",
        direction=TradeDirection.LONG,
        entry_price=10.5,
        stop_price=10.0,
        entry_time=entry_time,
        position_size=1000
    )
    
    # 更新持仓未实现盈亏
    manager.update_positions({"000001.SZ": 10.8})
    
    # 加仓
    manager.scale_in_position(
        symbol="000001.SZ",
        price=10.8,
        time=pd.Timestamp.now(),
        scale_factor=0.5
    )
    
    # 再次更新未实现盈亏
    manager.update_positions({"000001.SZ": 11.0})
    
    # 获取持仓摘要
    summary = manager.get_position_summary()
    print("持仓摘要:", summary)
    
    # 获取持仓状态
    position_status = position.get_status()
    print("持仓状态:", position_status)
    
    # 平仓
    manager.close_position(
        symbol="000001.SZ",
        price=11.0,
        time=pd.Timestamp.now(),
        reason="take_profit"
    )
    
    # 获取更新后的持仓摘要
    summary = manager.get_position_summary()
    print("平仓后持仓摘要:", summary) 
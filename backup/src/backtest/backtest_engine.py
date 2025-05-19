"""
回测引擎模块 - 负责策略回测和性能评估
"""
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union, Callable, Any
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes
import seaborn as sns
from tqdm import tqdm

from core.pyramid import PyramidStrategy, TrendDirection, SignalType, TradeDirection
from core.position import Position, get_position_manager
from data.data_feed import get_data_feed
from utils.logger import get_logger
from utils.config import get_config

logger = get_logger("backtest_engine")

class BacktestEngine:
    """
    回测引擎
    
    提供策略回测、性能评估和结果可视化功能
    """
    
    def __init__(
        self,
        strategy_instance: Any = None,
        symbols: List[str] = None,
        start_date: str = None,
        end_date: str = None,
        timeframe: str = '1d',
        initial_capital: float = None,
        commission_rate: float = None,
        slippage: float = None
    ):
        """
        初始化回测引擎
        
        Args:
            strategy_instance: 策略实例，如果为None则创建默认的金字塔策略
            symbols: 交易品种列表，如果为None则从配置文件读取
            start_date: 回测开始日期，如果为None则默认为一年前
            end_date: 回测结束日期，如果为None则默认为当前日期
            timeframe: 回测时间周期，默认为日线'1d'
            initial_capital: 初始资金，如果为None则从配置文件读取
            commission_rate: 手续费率，如果为None则从配置文件读取
            slippage: 滑点，如果为None则从配置文件读取
        """
        # 读取配置
        if symbols is None:
            symbols = get_config("backtest", "symbols", [])
        if start_date is None:
            start_date = get_config("backtest", "start_date", (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
        if end_date is None:
            end_date = get_config("backtest", "end_date", datetime.now().strftime("%Y-%m-%d"))
        if initial_capital is None:
            initial_capital = get_config("account", "initial_capital", 100000.0)
        if commission_rate is None:
            commission_rate = get_config("account", "commission_rate", 0.0003)
        if slippage is None:
            slippage = get_config("account", "slippage", 0.0001)
            
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        
        # 创建数据源
        self.data_feed = get_data_feed()
        
        # 创建策略实例
        self.strategy = strategy_instance or PyramidStrategy()
        
        # 创建仓位管理器
        self.position_manager = get_position_manager(initial_capital=initial_capital)
        
        # 回测结果
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.trades: List[Dict] = []
        self.equity_curve: pd.DataFrame = None
        self.performance_metrics: Dict = {}
        
        logger.info(f"回测引擎初始化完成, 交易品种: {symbols}, 时间范围: {start_date} - {end_date}, 初始资金: {initial_capital}")
    
    def load_data(self) -> bool:
        """
        加载回测数据
        
        Returns:
            是否成功加载数据
        """
        success = True
        
        for symbol in self.symbols:
            try:
                # 获取历史数据
                df = self.data_feed.get_historical_data(
                    symbol=symbol,
                    start_date=self.start_date,
                    end_date=self.end_date,
                    timeframe=self.timeframe
                )
                
                if df.empty:
                    logger.warning(f"获取历史数据为空: {symbol}")
                    success = False
                    continue
                
                # 确保数据包含必要的列
                required_columns = ['open', 'high', 'low', 'close', 'volume']
                for col in required_columns:
                    if col not in df.columns:
                        logger.error(f"数据缺少必要列 {col}: {symbol}")
                        success = False
                        continue
                
                # 保存数据
                self.data_cache[symbol] = df
                
                logger.info(f"加载历史数据成功: {symbol}, 时间范围: {df.index[0]} - {df.index[-1]}, 数据长度: {len(df)}")
                
            except Exception as e:
                logger.error(f"加载历史数据失败: {symbol}, 错误: {str(e)}")
                success = False
        
        return success
    
    def run_backtest(self) -> Dict:
        """
        运行回测
        
        Returns:
            回测结果字典
        """
        logger.info("开始回测...")
        
        # 确保数据已加载
        if not self.data_cache:
            if not self.load_data():
                logger.error("数据加载失败，无法运行回测")
                return {}
        
        # 重置回测状态
        self.position_manager = get_position_manager(initial_capital=self.initial_capital)
        self.trades = []
        
        # 准备资金曲线数据
        dates = self._get_all_dates()
        self.equity_curve = pd.DataFrame(index=dates)
        self.equity_curve['equity'] = self.initial_capital
        self.equity_curve['cash'] = self.initial_capital
        self.equity_curve['position_value'] = 0.0
        self.equity_curve['return'] = 0.0
        
        # 对每个交易日进行回测
        logger.info("模拟交易中...")
        last_equity = self.initial_capital
        progress_bar = tqdm(total=len(dates), desc="回测进度")
        
        for i, date in enumerate(dates):
            # 更新当前日期的持仓价值
            current_position_value = 0.0
            positions = self.position_manager.get_all_positions()
            
            for symbol, position in positions.items():
                # 获取当日价格
                price = self._get_price_at_date(symbol, date)
                if price:
                    # 更新持仓未实现盈亏
                    position.update_unrealized_profit(price)
                    # 累加持仓价值
                    current_position_value += position.total_position_size * price
            
            # 更新资金曲线
            current_equity = self.position_manager.current_capital + current_position_value
            self.equity_curve.loc[date, 'equity'] = current_equity
            self.equity_curve.loc[date, 'cash'] = self.position_manager.current_capital
            self.equity_curve.loc[date, 'position_value'] = current_position_value
            
            # 计算当日收益率
            if i > 0 and last_equity > 0:
                daily_return = (current_equity - last_equity) / last_equity
                self.equity_curve.loc[date, 'return'] = daily_return
            
            last_equity = current_equity
            
            # 对每个交易品种生成信号并执行交易
            for symbol in self.symbols:
                self._process_symbol_at_date(symbol, date)
            
            progress_bar.update(1)
        
        progress_bar.close()
        
        # 计算绩效指标
        self._calculate_performance_metrics()
        
        # 生成回测报告
        report = self._generate_backtest_report()
        
        logger.info("回测完成")
        return report
    
    def _get_all_dates(self) -> pd.DatetimeIndex:
        """
        获取回测期间的所有交易日期
        
        Returns:
            交易日期索引
        """
        all_dates = set()
        
        for symbol, df in self.data_cache.items():
            all_dates.update(df.index)
        
        all_dates = sorted(list(all_dates))
        return pd.DatetimeIndex(all_dates)
    
    def _get_price_at_date(self, symbol: str, date: pd.Timestamp) -> Optional[float]:
        """
        获取指定日期的收盘价
        
        Args:
            symbol: 交易品种代码
            date: 日期
            
        Returns:
            收盘价，如果没有数据则返回None
        """
        df = self.data_cache.get(symbol)
        if df is None or date not in df.index:
            return None
        
        return df.loc[date, 'close']
    
    def _get_data_till_date(self, symbol: str, date: pd.Timestamp) -> Optional[pd.DataFrame]:
        """
        获取截至指定日期的历史数据
        
        Args:
            symbol: 交易品种代码
            date: 日期
            
        Returns:
            历史数据DataFrame，如果没有数据则返回None
        """
        df = self.data_cache.get(symbol)
        if df is None:
            return None
        
        # 获取截至当前日期的数据
        mask = df.index <= date
        return df.loc[mask].copy()
    
    def _process_symbol_at_date(self, symbol: str, date: pd.Timestamp):
        """
        处理指定日期的单个交易品种
        
        Args:
            symbol: 交易品种代码
            date: 日期
        """
        # 获取截至当前日期的数据
        df = self._get_data_till_date(symbol, date)
        if df is None or len(df) < 20:  # 确保有足够的数据
            return
        
        # 如果当前日期不在数据中，则跳过（非交易日）
        if date not in df.index:
            return
        
        # 计算技术指标
        df = self.strategy.calculate_indicators(df)
        
        # 获取当前价格
        current_price = df.iloc[-1]['close']
        
        # 获取当前持仓状态
        position = self.position_manager.get_position(symbol)
        has_position = position is not None and position.is_open
        
        # 添加交易成本
        slippage_cost = current_price * self.slippage
        commission_cost = current_price * self.commission_rate
        
        # 根据持仓状态生成信号
        if not has_position:
            # 无持仓，检查入场信号
            has_entry, direction, entry_price = self.strategy.generate_entry_signal(df)
            
            if has_entry and entry_price is not None:
                # 计算止损价格
                atr = df.iloc[-1]['atr']
                if direction == TradeDirection.LONG:
                    stop_price = current_price - atr * self.strategy.trail_stop_atr
                else:
                    stop_price = current_price + atr * self.strategy.trail_stop_atr
                
                # 计算交易量
                position_size, risk_amount = self.position_manager.risk_controller.calculate_position_size(
                    symbol=symbol,
                    entry_price=current_price,
                    stop_price=stop_price
                )
                
                # 执行入场交易
                if position_size > 0:
                    # 添加交易成本
                    actual_price = current_price + slippage_cost if direction == TradeDirection.LONG else current_price - slippage_cost
                    
                    # 创建持仓
                    self.position_manager.open_position(
                        symbol=symbol,
                        direction=direction,
                        entry_price=actual_price,
                        stop_price=stop_price,
                        entry_time=date,
                        position_size=position_size
                    )
                    
                    # 记录交易
                    trade = {
                        "symbol": symbol,
                        "type": "entry",
                        "direction": direction.name,
                        "price": actual_price,
                        "size": position_size,
                        "cost": position_size * actual_price,
                        "commission": position_size * actual_price * self.commission_rate,
                        "slippage": position_size * slippage_cost,
                        "time": date
                    }
                    self.trades.append(trade)
                    
                    logger.info(f"入场: {symbol}, 方向={direction.name}, 价格={actual_price}, 数量={position_size}, 时间={date}")
        else:
            # 有持仓，检查出场或加仓信号
            # 1. 先检查出场信号
            has_exit, exit_type, exit_price = self.strategy.generate_exit_signal(df)
            
            if has_exit and exit_price is not None:
                # 执行出场交易
                direction = position.direction
                actual_price = current_price - slippage_cost if direction == TradeDirection.LONG else current_price + slippage_cost
                position_size = position.total_position_size
                
                # 平仓
                self.position_manager.close_position(
                    symbol=symbol,
                    price=actual_price,
                    time=date,
                    reason=exit_type.name.lower()
                )
                
                # 记录交易
                trade = {
                    "symbol": symbol,
                    "type": "exit",
                    "exit_reason": exit_type.name,
                    "direction": "SELL" if direction == TradeDirection.LONG else "BUY",
                    "price": actual_price,
                    "size": position_size,
                    "cost": position_size * actual_price,
                    "commission": position_size * actual_price * self.commission_rate,
                    "slippage": position_size * slippage_cost,
                    "time": date
                }
                self.trades.append(trade)
                
                logger.info(f"出场: {symbol}, 原因={exit_type.name}, 价格={actual_price}, 数量={position_size}, 时间={date}")
            else:
                # 2. 如果没有出场信号，检查加仓信号
                has_scale_in, scale_price = self.strategy.generate_scale_in_signal(df)
                
                if has_scale_in and scale_price is not None and position.pyramid_level < self.strategy.max_pyramids:
                    # 计算加仓规模
                    base_size = position.position_size
                    scale_factor = self.strategy.pyramid_factor ** position.scale_in_count
                    scale_in_size = int(base_size * scale_factor)
                    
                    if scale_in_size > 0:
                        # 添加交易成本
                        direction = position.direction
                        actual_price = current_price + slippage_cost if direction == TradeDirection.LONG else current_price - slippage_cost
                        
                        # 执行加仓
                        self.position_manager.scale_in_position(
                            symbol=symbol,
                            price=actual_price,
                            time=date,
                            scale_factor=scale_factor
                        )
                        
                        # 记录交易
                        trade = {
                            "symbol": symbol,
                            "type": "scale_in",
                            "direction": direction.name,
                            "price": actual_price,
                            "size": scale_in_size,
                            "cost": scale_in_size * actual_price,
                            "commission": scale_in_size * actual_price * self.commission_rate,
                            "slippage": scale_in_size * slippage_cost,
                            "time": date,
                            "pyramid_level": position.pyramid_level
                        }
                        self.trades.append(trade)
                        
                        logger.info(f"加仓: {symbol}, 方向={direction.name}, 价格={actual_price}, 数量={scale_in_size}, 时间={date}, 金字塔层级={position.pyramid_level}")
    
    def _calculate_performance_metrics(self):
        """
        计算绩效指标
        """
        logger.info("计算绩效指标...")
        
        if self.equity_curve is None or len(self.equity_curve) == 0:
            logger.warning("资金曲线为空，无法计算绩效指标")
            return
        
        # 基本指标
        initial_equity = self.equity_curve['equity'].iloc[0]
        final_equity = self.equity_curve['equity'].iloc[-1]
        returns = self.equity_curve['return'].dropna()
        
        # 计算累计收益率
        total_return = (final_equity - initial_equity) / initial_equity
        
        # 计算年化收益率
        days = (self.equity_curve.index[-1] - self.equity_curve.index[0]).days
        if days > 0:
            annual_return = (1 + total_return) ** (365 / days) - 1
        else:
            annual_return = 0
        
        # 计算最大回撤
        # 1. 计算累计最大值曲线
        self.equity_curve['cummax'] = self.equity_curve['equity'].cummax()
        # 2. 计算回撤
        self.equity_curve['drawdown'] = (self.equity_curve['cummax'] - self.equity_curve['equity']) / self.equity_curve['cummax']
        # 3. 最大回撤
        max_drawdown = self.equity_curve['drawdown'].max()
        
        # 计算夏普比率
        risk_free_rate = get_config("backtest", "performance", {}).get("risk_free_rate", 0.03) / 365  # 日化无风险利率
        if len(returns) > 0:
            excess_returns = returns - risk_free_rate
            sharpe_ratio = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        # 计算索提诺比率
        if len(returns) > 0:
            downside_returns = returns[returns < 0]
            sortino_ratio = np.sqrt(252) * excess_returns.mean() / downside_returns.std() if len(downside_returns) > 0 and downside_returns.std() > 0 else 0
        else:
            sortino_ratio = 0
        
        # 计算胜率
        winning_trades = [t for t in self.trades if t.get("type") == "exit" and t.get("realized_profit", 0) > 0]
        win_rate = len(winning_trades) / len([t for t in self.trades if t.get("type") == "exit"]) if len(self.trades) > 0 else 0
        
        # 计算盈亏比
        avg_win = np.mean([t.get("realized_profit", 0) for t in winning_trades]) if winning_trades else 0
        losing_trades = [t for t in self.trades if t.get("type") == "exit" and t.get("realized_profit", 0) <= 0]
        avg_loss = np.mean([abs(t.get("realized_profit", 0)) for t in losing_trades]) if losing_trades else 1
        profit_factor = avg_win / avg_loss if avg_loss != 0 else 0
        
        # 存储绩效指标
        self.performance_metrics = {
            "initial_capital": initial_equity,
            "final_capital": final_equity,
            "total_return": total_return,
            "annual_return": annual_return,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "total_trades": len([t for t in self.trades if t.get("type") == "entry"]),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "backtest_days": days
        }
    
    def _generate_backtest_report(self) -> Dict:
        """
        生成回测报告
        
        Returns:
            回测报告字典
        """
        # 收集交易记录
        trades_info = []
        for position in self.position_manager.closed_positions:
            trade_info = position.get_status()
            trades_info.append(trade_info)
        
        # 生成报告
        report = {
            "summary": {
                "initial_capital": self.initial_capital,
                "final_capital": self.performance_metrics.get("final_capital", self.initial_capital),
                "total_return": self.performance_metrics.get("total_return", 0),
                "annual_return": self.performance_metrics.get("annual_return", 0),
                "backtest_start": self.start_date,
                "backtest_end": self.end_date,
                "backtest_days": self.performance_metrics.get("backtest_days", 0),
                "symbols": self.symbols
            },
            "trades": trades_info,
            "performance": self.performance_metrics,
            "equity_curve": self.equity_curve.to_dict() if self.equity_curve is not None else None
        }
        
        return report 
"""
金字塔交易策略模块 - 实现基于金字塔交易法的量化交易策略
"""
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union, Callable
import pandas as pd
import numpy as np
from threading import Thread, Event, Lock

from core.pyramid import PyramidStrategy, TrendDirection, SignalType, TradeDirection
from core.position import Position, get_position_manager
from data.data_feed import get_data_feed
from api.ths_api import get_ths_api, OrderDirection, OrderType
from utils.logger import get_logger
from utils.config import get_config

logger = get_logger("pyramid_strategy")

class PyramidTradingStrategy:
    """
    金字塔交易策略
    
    整合金字塔交易法核心算法与同花顺交易接口，实现自动化交易
    """
    
    def __init__(
        self,
        symbols: List[str] = None,
        timeframe: str = '1d',
        auto_trade: bool = False,
        paper_trading: bool = True,
        backtest_mode: bool = False
    ):
        """
        初始化金字塔交易策略
        
        Args:
            symbols: 交易品种列表，如果为None则从配置文件读取
            timeframe: 交易时间周期
            auto_trade: 是否启用自动交易
            paper_trading: 是否使用模拟交易
            backtest_mode: 是否为回测模式
        """
        # 读取配置
        if symbols is None:
            symbols = get_config("backtest", "symbols", [])
        
        self.symbols = symbols
        self.timeframe = timeframe
        self.auto_trade = auto_trade
        self.paper_trading = paper_trading
        self.backtest_mode = backtest_mode
        
        # 创建数据源
        self.data_feed = get_data_feed()
        
        # 创建交易API
        self.trade_api = get_ths_api() if not paper_trading else None
        
        # 创建仓位管理器
        self.position_manager = get_position_manager()
        
        # 创建金字塔策略实例
        self.pyramid_core = PyramidStrategy()
        
        # 策略运行状态
        self.running = False
        self.stop_event = Event()
        
        # 数据缓存
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.data_lock = Lock()
        
        # 订单缓存
        self.orders: Dict[str, Dict] = {}
        self.order_lock = Lock()
        
        # 未完成订单追踪
        self.pending_orders: Dict[str, Dict] = {}
        
        # 最近的信号
        self.last_signals: Dict[str, Dict] = {}
        
        logger.info(f"金字塔交易策略初始化完成，交易品种: {symbols}, 时间周期: {timeframe}, 自动交易: {auto_trade}")
    
    def initialize(self) -> bool:
        """
        初始化策略，包括数据加载、交易接口连接等
        
        Returns:
            初始化是否成功
        """
        try:
            # 加载历史数据
            for symbol in self.symbols:
                self._load_historical_data(symbol)
            
            # 如果不是回测模式且启用自动交易，连接交易接口
            if not self.backtest_mode and self.auto_trade and not self.paper_trading:
                if not self.trade_api.is_logged_in:
                    if not self.trade_api.login():
                        logger.error("交易接口登录失败")
                        return False
                    
                # 订阅订单和成交更新
                self.trade_api.subscribe_order_updates(self._on_order_update)
                self.trade_api.subscribe_trade_updates(self._on_trade_update)
                self.trade_api.subscribe_position_updates(self._on_position_update)
            
            logger.info("策略初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"策略初始化失败: {str(e)}")
            return False
    
    def _load_historical_data(self, symbol: str, days: int = 120) -> pd.DataFrame:
        """
        加载历史数据
        
        Args:
            symbol: 交易品种代码
            days: 加载的历史天数
            
        Returns:
            历史数据DataFrame
        """
        try:
            # 计算开始日期
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 获取历史数据
            df = self.data_feed.get_historical_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe=self.timeframe
            )
            
            if df.empty:
                logger.warning(f"获取历史数据为空: {symbol}")
                return pd.DataFrame()
            
            # 将数据添加到缓存
            with self.data_lock:
                self.data_cache[symbol] = df
            
            logger.info(f"加载历史数据成功: {symbol}, 数据长度: {len(df)}")
            return df
            
        except Exception as e:
            logger.error(f"加载历史数据失败: {symbol}, 错误: {str(e)}")
            return pd.DataFrame()
    
    def _on_order_update(self, order_data: Dict):
        """
        订单更新回调
        
        Args:
            order_data: 订单数据
        """
        try:
            order_id = order_data.get("order_id")
            if not order_id:
                return
                
            with self.order_lock:
                # 更新订单缓存
                self.orders[order_id] = order_data
                
                # 检查是否为未完成订单
                if order_id in self.pending_orders:
                    # 获取订单状态
                    status = order_data.get("status")
                    if status in ["已成", "已撤", "已拒绝"]:
                        # 订单已完成，处理后续逻辑
                        self._process_completed_order(order_id, order_data)
                
            logger.info(f"订单更新: ID={order_id}, 状态={order_data.get('status')}")
                
        except Exception as e:
            logger.error(f"处理订单更新异常: {str(e)}")
    
    def _on_trade_update(self, trade_data: Dict):
        """
        成交更新回调
        
        Args:
            trade_data: 成交数据
        """
        try:
            # 处理成交记录
            order_id = trade_data.get("order_id")
            symbol = trade_data.get("symbol")
            direction = trade_data.get("direction")
            price = trade_data.get("price")
            volume = trade_data.get("volume")
            
            logger.info(f"成交更新: 品种={symbol}, 方向={direction}, 价格={price}, 数量={volume}")
                
        except Exception as e:
            logger.error(f"处理成交更新异常: {str(e)}")
    
    def _on_position_update(self, position_data: Dict):
        """
        持仓更新回调
        
        Args:
            position_data: 持仓数据
        """
        try:
            # 处理持仓更新
            positions = position_data.get("positions", [])
            
            logger.info(f"持仓更新: 持仓数量={len(positions)}")
                
        except Exception as e:
            logger.error(f"处理持仓更新异常: {str(e)}")
    
    def _process_completed_order(self, order_id: str, order_data: Dict):
        """
        处理已完成的订单
        
        Args:
            order_id: 订单ID
            order_data: 订单数据
        """
        # 从未完成订单中移除
        pending_order = self.pending_orders.pop(order_id, None)
        if not pending_order:
            return
            
        symbol = pending_order.get("symbol")
        signal_type = pending_order.get("signal_type")
        
        # 获取订单状态
        status = order_data.get("status")
        
        if status == "已成":
            # 订单成交，更新仓位
            logger.info(f"订单已成交: {order_id}, 品种={symbol}, 信号类型={signal_type}")
            
            # TODO: 根据信号类型和成交结果更新仓位
            
        elif status == "已撤":
            # 订单已撤销
            logger.info(f"订单已撤销: {order_id}, 品种={symbol}, 信号类型={signal_type}")
            
        elif status == "已拒绝":
            # 订单被拒绝
            logger.warning(f"订单被拒绝: {order_id}, 品种={symbol}, 信号类型={signal_type}")
            
        # 更新最近信号状态
        if symbol in self.last_signals:
            self.last_signals[symbol]["processed"] = True 
    
    def start(self):
        """
        启动策略运行
        """
        if self.running:
            logger.warning("策略已在运行中")
            return
        
        # 初始化策略
        if not self.initialize():
            logger.error("策略初始化失败，无法启动")
            return
        
        self.running = True
        self.stop_event.clear()
        
        # 启动策略处理线程
        if not self.backtest_mode:
            Thread(target=self._strategy_loop).start()
            
            # 启动行情订阅
            self._start_market_subscription()
        
        logger.info("策略已启动")
    
    def stop(self):
        """
        停止策略运行
        """
        if not self.running:
            logger.warning("策略未在运行中")
            return
        
        self.running = False
        self.stop_event.set()
        
        # 停止行情订阅
        self._stop_market_subscription()
        
        # 如果不是模拟交易，登出交易接口
        if not self.paper_trading and self.trade_api and self.trade_api.is_logged_in:
            self.trade_api.logout()
        
        logger.info("策略已停止")
    
    def _strategy_loop(self):
        """
        策略处理主循环
        """
        while self.running and not self.stop_event.is_set():
            try:
                # 对每个交易品种进行处理
                for symbol in self.symbols:
                    self._process_symbol(symbol)
                
                # 每次循环后等待一段时间
                if self.timeframe == '1d':
                    # 日线级别，等待较长时间
                    wait_seconds = 60 * 5  # 5分钟
                else:
                    # 分钟级别，等待较短时间
                    wait_seconds = 10
                
                if self.stop_event.wait(wait_seconds):
                    break
                    
            except Exception as e:
                logger.error(f"策略循环处理异常: {str(e)}")
                # 发生异常后等待一段时间再继续
                time.sleep(10)
        
        logger.info("策略处理循环已退出")
    
    def _start_market_subscription(self):
        """
        启动行情订阅
        """
        try:
            # 订阅行情数据
            self.data_feed.subscribe(self.symbols, self._on_market_data)
            logger.info(f"行情订阅已启动, 品种: {self.symbols}")
        except Exception as e:
            logger.error(f"启动行情订阅失败: {str(e)}")
    
    def _stop_market_subscription(self):
        """
        停止行情订阅
        """
        try:
            # 取消订阅行情数据
            self.data_feed.unsubscribe(self.symbols)
            logger.info("行情订阅已停止")
        except Exception as e:
            logger.error(f"停止行情订阅失败: {str(e)}")
    
    def _on_market_data(self, market_data: Dict):
        """
        行情数据回调
        
        Args:
            market_data: 行情数据
        """
        try:
            # 解析行情数据
            symbol = market_data.get("symbol")
            if not symbol or symbol not in self.symbols:
                return
            
            # 更新缓存中的数据
            self._update_data_cache(symbol, market_data)
            
            # 处理实时信号
            self._process_real_time_signal(symbol, market_data)
                
        except Exception as e:
            logger.error(f"处理行情数据异常: {str(e)}")
    
    def _update_data_cache(self, symbol: str, market_data: Dict):
        """
        更新数据缓存
        
        Args:
            symbol: 交易品种代码
            market_data: 行情数据
        """
        with self.data_lock:
            # 获取已有数据
            df = self.data_cache.get(symbol)
            if df is None or df.empty:
                return
            
            # 提取当前K线数据
            current_time = pd.to_datetime(market_data.get("time"))
            current_data = {
                "open": market_data.get("open"),
                "high": market_data.get("high"),
                "low": market_data.get("low"),
                "close": market_data.get("close"),
                "volume": market_data.get("volume")
            }
            
            # 判断是否是新的K线
            if len(df) > 0 and df.index[-1] == current_time:
                # 更新最后一根K线
                for column, value in current_data.items():
                    df.loc[current_time, column] = value
            else:
                # 添加新的K线
                new_row = pd.DataFrame([current_data], index=[current_time])
                df = pd.concat([df, new_row])
            
            # 更新缓存
            self.data_cache[symbol] = df
    
    def _process_symbol(self, symbol: str):
        """
        处理单个交易品种
        
        Args:
            symbol: 交易品种代码
        """
        with self.data_lock:
            # 获取缓存数据
            df = self.data_cache.get(symbol)
            if df is None or df.empty:
                return
            
            # 计算指标
            df = self.pyramid_core.calculate_indicators(df)
            
            # 生成信号
            has_signal, signal_type, direction, price = self._generate_signal(symbol, df)
            
            if has_signal:
                # 处理信号
                self._process_signal(symbol, signal_type, direction, price, df)
    
    def _process_real_time_signal(self, symbol: str, market_data: Dict):
        """
        处理实时行情信号
        
        Args:
            symbol: 交易品种代码
            market_data: 行情数据
        """
        # 检查是否有未处理的信号
        last_signal = self.last_signals.get(symbol)
        if last_signal and not last_signal.get("processed", False):
            # 有未处理的信号，检查是否满足执行条件
            signal_type = last_signal["signal_type"]
            direction = last_signal["direction"]
            target_price = last_signal["price"]
            
            # 获取当前价格
            current_price = market_data.get("close")
            
            # 判断价格是否已达到目标价格
            price_met = False
            if direction == TradeDirection.LONG:
                if signal_type in [SignalType.ENTRY, SignalType.SCALE_IN]:
                    # 做多入场或加仓，价格上涨到目标价格
                    price_met = current_price >= target_price
                else:
                    # 做多出场，价格下跌到目标价格
                    price_met = current_price <= target_price
            else:
                if signal_type in [SignalType.ENTRY, SignalType.SCALE_IN]:
                    # 做空入场或加仓，价格下跌到目标价格
                    price_met = current_price <= target_price
                else:
                    # 做空出场，价格上涨到目标价格
                    price_met = current_price >= target_price
            
            if price_met:
                # 价格已达到目标，执行交易
                self._execute_trade(symbol, signal_type, direction, current_price)
                
                # 更新信号状态
                self.last_signals[symbol]["processed"] = True
                logger.info(f"实时信号已处理: {symbol}, 类型={signal_type}, 方向={direction}, 价格={current_price}")
    
    def _generate_signal(self, symbol: str, df: pd.DataFrame) -> Tuple[bool, Optional[SignalType], Optional[TradeDirection], Optional[float]]:
        """
        基于历史数据生成交易信号
        
        Args:
            symbol: 交易品种代码
            df: 历史数据DataFrame
            
        Returns:
            (是否有信号, 信号类型, 交易方向, 交易价格)
        """
        # 检查是否有足够的数据
        if len(df) < max(self.pyramid_core.ma_long_period, self.pyramid_core.breakout_periods) + 10:
            return False, None, None, None
        
        # 获取当前仓位状态
        position = self.position_manager.get_position(symbol)
        has_position = position is not None and position.is_open
        position_direction = position.direction if has_position else TradeDirection.NONE
        
        # 获取最新价格
        latest_price = df.iloc[-1]['close']
        
        # 如果没有持仓，检查入场信号
        if not has_position:
            # 检查入场信号
            has_entry, entry_direction, entry_price = self.pyramid_core.generate_entry_signal(df)
            if has_entry and entry_price is not None:
                return True, SignalType.ENTRY, entry_direction, entry_price
        else:
            # 已有持仓，检查是否有出场信号
            has_exit, exit_type, exit_price = self.pyramid_core.generate_exit_signal(df)
            if has_exit and exit_price is not None:
                return True, exit_type, position_direction, exit_price
            
            # 检查是否有加仓信号
            has_scale_in, scale_price = self.pyramid_core.generate_scale_in_signal(df)
            if has_scale_in and scale_price is not None:
                return True, SignalType.SCALE_IN, position_direction, scale_price
        
        return False, None, None, None
    
    def _process_signal(self, symbol: str, signal_type: SignalType, direction: TradeDirection, price: float, df: pd.DataFrame):
        """
        处理交易信号
        
        Args:
            symbol: 交易品种代码
            signal_type: 信号类型
            direction: 交易方向
            price: 交易价格
            df: 历史数据DataFrame
        """
        # 记录最新信号
        self.last_signals[symbol] = {
            "signal_type": signal_type,
            "direction": direction,
            "price": price,
            "time": pd.Timestamp.now(),
            "processed": False
        }
        
        logger.info(f"生成交易信号: {symbol}, 类型={signal_type}, 方向={direction}, 价格={price}")
        
        # 如果开启了自动交易，执行交易
        if self.auto_trade:
            self._execute_trade(symbol, signal_type, direction, price) 
    
    def _execute_trade(self, symbol: str, signal_type: SignalType, direction: TradeDirection, price: float):
        """
        执行交易
        
        Args:
            symbol: 交易品种代码
            signal_type: 信号类型
            direction: 交易方向
            price: 交易价格
        """
        # 获取当前行情，确定止损价格和仓位大小
        df = self.data_cache.get(symbol)
        if df is None or df.empty:
            logger.error(f"无法执行交易，缺少行情数据: {symbol}")
            return
        
        # 计算技术指标
        df = self.pyramid_core.calculate_indicators(df)
        
        # 计算止损价格
        stop_price = self._calculate_stop_price(df, direction, signal_type)
        if stop_price is None:
            logger.error(f"无法确定止损价格: {symbol}")
            return
        
        # 确定交易量
        volume = self._calculate_trade_volume(symbol, direction, price, stop_price, signal_type)
        if volume <= 0:
            logger.error(f"计算交易量为0或负数: {symbol}")
            return
        
        logger.info(f"执行交易: {symbol}, 类型={signal_type}, 方向={direction}, 价格={price}, 止损价={stop_price}, 数量={volume}")
        
        # 执行交易操作
        if self.paper_trading:
            # 模拟交易
            self._execute_paper_trade(symbol, signal_type, direction, price, stop_price, volume)
        else:
            # 实盘交易
            self._execute_real_trade(symbol, signal_type, direction, price, volume)
    
    def _calculate_stop_price(self, df: pd.DataFrame, direction: TradeDirection, signal_type: SignalType) -> Optional[float]:
        """
        计算止损价格
        
        Args:
            df: 历史数据
            direction: 交易方向
            signal_type: 信号类型
            
        Returns:
            止损价格
        """
        if df.empty or 'atr' not in df.columns:
            return None
            
        # 获取最新的ATR值
        atr = df.iloc[-1]['atr']
        
        # 获取最新价格
        latest_price = df.iloc[-1]['close']
        
        # 根据信号类型计算止损价格
        if signal_type == SignalType.ENTRY:
            # 入场信号的止损价格
            if direction == TradeDirection.LONG:
                # 做多，止损设置在入场价下方
                stop_price = latest_price - atr * self.pyramid_core.trail_stop_atr
            else:
                # 做空，止损设置在入场价上方
                stop_price = latest_price + atr * self.pyramid_core.trail_stop_atr
                
            return round(stop_price, 2)
            
        elif signal_type == SignalType.SCALE_IN:
            # 加仓信号，使用当前持仓的止损价格
            position = self.position_manager.get_position(df.index.name)
            if position:
                return position.stop_price
        
        # 其他信号类型不需要计算止损价格
        return None
    
    def _calculate_trade_volume(self, symbol: str, direction: TradeDirection, price: float, stop_price: float, signal_type: SignalType) -> int:
        """
        计算交易量
        
        Args:
            symbol: 交易品种代码
            direction: 交易方向
            price: 交易价格
            stop_price: 止损价格
            signal_type: 信号类型
            
        Returns:
            交易量（股数/手数）
        """
        # 获取账户信息
        account_info = {}
        if not self.paper_trading and self.trade_api and self.trade_api.is_logged_in:
            account_info = self.trade_api.get_account_info()
        
        # 获取可用资金
        available_cash = account_info.get("available", self.position_manager.current_capital)
        
        # 根据信号类型计算交易量
        if signal_type == SignalType.ENTRY:
            # 入场信号，根据风险计算头寸大小
            position_size, risk_amount = self.position_manager.risk_controller.calculate_position_size(
                symbol=symbol,
                entry_price=price,
                stop_price=stop_price
            )
            
            # 检查是否超过可用资金
            cost = position_size * price
            if cost > available_cash:
                position_size = int(available_cash / price)
                
            return position_size
            
        elif signal_type == SignalType.SCALE_IN:
            # 加仓信号，根据金字塔系数计算头寸大小
            position = self.position_manager.get_position(symbol)
            if position:
                # 根据金字塔系数计算加仓规模
                base_size = position.position_size
                scale_factor = self.pyramid_core.pyramid_factor ** position.scale_in_count
                position_size = int(base_size * scale_factor)
                
                # 检查是否超过可用资金
                cost = position_size * price
                if cost > available_cash:
                    position_size = int(available_cash / price)
                
                return position_size
        
        elif signal_type in [SignalType.EXIT, SignalType.STOP_LOSS]:
            # 出场信号，平掉全部持仓
            position = self.position_manager.get_position(symbol)
            if position:
                return position.total_position_size
        
        # 默认返回最小交易单位
        return 100  # 股票最小交易单位通常为100股
    
    def _execute_paper_trade(self, symbol: str, signal_type: SignalType, direction: TradeDirection, price: float, stop_price: float, volume: int):
        """
        执行模拟交易
        
        Args:
            symbol: 交易品种代码
            signal_type: 信号类型
            direction: 交易方向
            price: 交易价格
            stop_price: 止损价格
            volume: 交易量（股数/手数）
        """
        # 根据信号类型处理
        time_now = pd.Timestamp.now()
        
        if signal_type == SignalType.ENTRY:
            # 入场信号
            self.position_manager.process_signal(
                symbol=symbol,
                signal_type=signal_type,
                direction=direction,
                price=price,
                stop_price=stop_price,
                time=time_now,
                position_size=volume
            )
            logger.info(f"模拟交易 - 入场: {symbol}, 方向={direction}, 价格={price}, 数量={volume}")
            
        elif signal_type == SignalType.SCALE_IN:
            # 加仓信号
            self.position_manager.process_signal(
                symbol=symbol,
                signal_type=signal_type,
                direction=direction,
                price=price,
                time=time_now
            )
            logger.info(f"模拟交易 - 加仓: {symbol}, 方向={direction}, 价格={price}, 数量={volume}")
            
        elif signal_type in [SignalType.EXIT, SignalType.STOP_LOSS]:
            # 出场信号
            self.position_manager.process_signal(
                symbol=symbol,
                signal_type=signal_type,
                direction=direction,
                price=price,
                time=time_now
            )
            logger.info(f"模拟交易 - 出场: {symbol}, 方向={direction}, 价格={price}, 数量={volume}")
    
    def _execute_real_trade(self, symbol: str, signal_type: SignalType, direction: TradeDirection, price: float, volume: int):
        """
        执行实盘交易
        
        Args:
            symbol: 交易品种代码
            signal_type: 信号类型
            direction: 交易方向
            price: 交易价格
            volume: 交易量（股数/手数）
        """
        if not self.trade_api or not self.trade_api.is_logged_in:
            logger.error("交易接口未连接，无法执行实盘交易")
            return
        
        # 转换交易方向
        order_direction = OrderDirection.BUY if (
            (direction == TradeDirection.LONG and signal_type in [SignalType.ENTRY, SignalType.SCALE_IN]) or
            (direction == TradeDirection.SHORT and signal_type in [SignalType.EXIT, SignalType.STOP_LOSS])
        ) else OrderDirection.SELL
        
        # 执行交易
        success, order_id = self.trade_api.place_order(
            symbol=symbol,
            direction=order_direction,
            order_type=OrderType.LIMIT,
            price=price,
            volume=volume
        )
        
        if success and order_id:
            logger.info(f"实盘交易下单成功: {symbol}, 方向={order_direction.value}, 价格={price}, 数量={volume}, 订单ID={order_id}")
            
            # 记录未完成订单
            with self.order_lock:
                self.pending_orders[order_id] = {
                    "symbol": symbol,
                    "signal_type": signal_type,
                    "direction": direction,
                    "price": price,
                    "volume": volume,
                    "time": pd.Timestamp.now()
                }
                
            # 检查订单状态
            Thread(target=self._check_order_status, args=(order_id,)).start()
        else:
            logger.error(f"实盘交易下单失败: {symbol}, 方向={order_direction.value}, 价格={price}, 数量={volume}")
    
    def _check_order_status(self, order_id: str, max_wait_seconds: int = 60):
        """
        检查订单状态
        
        Args:
            order_id: 订单ID
            max_wait_seconds: 最大等待时间（秒）
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait_seconds:
            # 查询订单状态
            order_info = self.trade_api.get_order_status(order_id)
            
            if not order_info:
                time.sleep(2)
                continue
                
            status = order_info.get("status")
            
            # 如果订单已完成，处理后续逻辑
            if status in ["已成", "已撤", "已拒绝"]:
                self._process_completed_order(order_id, order_info)
                return
                
            # 如果订单处于挂单状态，等待一段时间后再查询
            time.sleep(2)
        
        # 超过最大等待时间，撤单
        logger.warning(f"订单 {order_id} 超过最大等待时间 {max_wait_seconds}秒，尝试撤单")
        self.trade_api.cancel_order(order_id)
    
    def get_strategy_status(self) -> Dict:
        """
        获取策略状态
        
        Returns:
            策略状态字典
        """
        status = {
            "running": self.running,
            "symbols": self.symbols,
            "timeframe": self.timeframe,
            "auto_trade": self.auto_trade,
            "paper_trading": self.paper_trading,
            "positions": {},
            "pending_orders": len(self.pending_orders),
            "last_signals": self.last_signals,
            "account_summary": self.position_manager.get_position_summary()
        }
        
        # 添加持仓信息
        positions = self.position_manager.get_all_positions()
        for symbol, position in positions.items():
            status["positions"][symbol] = position.get_status()
        
        return status
    
    def run_backtest(self, start_date: str, end_date: str = None) -> Dict:
        """
        运行回测
        
        Args:
            start_date: 回测开始日期
            end_date: 回测结束日期，默认为当前日期
            
        Returns:
            回测结果字典
        """
        if not self.backtest_mode:
            logger.warning("当前不是回测模式，无法运行回测")
            return {}
        
        # 加载回测数据
        self._load_backtest_data(start_date, end_date)
        
        # 初始化回测环境
        self.position_manager = get_position_manager()
        self.pyramid_core = PyramidStrategy()
        self.orders = {}
        self.pending_orders = {}
        self.last_signals = {}
        
        # 运行回测
        for symbol in self.symbols:
            self._run_symbol_backtest(symbol)
        
        # 生成回测报告
        report = self._generate_backtest_report()
        
        return report
    
    def _load_backtest_data(self, start_date: str, end_date: str = None):
        """
        加载回测数据
        
        Args:
            start_date: 回测开始日期
            end_date: 回测结束日期
        """
        for symbol in self.symbols:
            df = self.data_feed.get_historical_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe=self.timeframe
            )
            
            if df.empty:
                logger.warning(f"回测数据为空: {symbol}")
                continue
                
            with self.data_lock:
                self.data_cache[symbol] = df
                
            logger.info(f"加载回测数据成功: {symbol}, 数据长度: {len(df)}")
    
    def _run_symbol_backtest(self, symbol: str):
        """
        运行单个品种的回测
        
        Args:
            symbol: 交易品种代码
        """
        with self.data_lock:
            df = self.data_cache.get(symbol)
            if df is None or df.empty:
                return
        
        # 计算指标
        df = self.pyramid_core.calculate_indicators(df)
        
        # 初始化策略状态
        self.pyramid_core.current_position = 0
        self.pyramid_core.position_direction = TradeDirection.NONE
        self.pyramid_core.pyramid_level = 0
        
        # 遍历K线数据，模拟交易
        for i in range(max(self.pyramid_core.ma_long_period, self.pyramid_core.breakout_periods) + 10, len(df)):
            # 获取当前时间片的数据
            current_df = df.iloc[:i+1].copy()
            
            # 生成信号
            has_signal, signal_type, direction, price = self._generate_signal(symbol, current_df)
            
            if has_signal:
                # 计算止损价格
                stop_price = self._calculate_stop_price(current_df, direction, signal_type)
                
                # 计算交易量
                volume = self._calculate_trade_volume(symbol, direction, price, stop_price or 0, signal_type)
                
                # 执行模拟交易
                time = current_df.index[-1]
                self._execute_paper_trade(symbol, signal_type, direction, price, stop_price or 0, volume)
        
        logger.info(f"回测完成: {symbol}")
    
    def _generate_backtest_report(self) -> Dict:
        """
        生成回测报告
        
        Returns:
            回测报告字典
        """
        # 获取仓位摘要
        summary = self.position_manager.get_position_summary()
        
        # 获取交易记录
        trades = []
        for position in self.position_manager.closed_positions:
            trade_info = position.get_status()
            trades.append(trade_info)
        
        # 计算绩效指标
        performance = self._calculate_performance_metrics(summary, trades)
        
        # 生成报告
        report = {
            "summary": summary,
            "trades": trades,
            "performance": performance
        }
        
        return report
    
    def _calculate_performance_metrics(self, summary: Dict, trades: List[Dict]) -> Dict:
        """
        计算绩效指标
        
        Args:
            summary: 仓位摘要
            trades: 交易记录列表
            
        Returns:
            绩效指标字典
        """
        # 计算胜率
        winning_trades = [t for t in trades if t.get("realized_profit", 0) > 0]
        win_rate = len(winning_trades) / len(trades) if trades else 0
        
        # 计算盈亏比
        avg_win = np.mean([t.get("realized_profit", 0) for t in winning_trades]) if winning_trades else 0
        losing_trades = [t for t in trades if t.get("realized_profit", 0) <= 0]
        avg_loss = np.mean([abs(t.get("realized_profit", 0)) for t in losing_trades]) if losing_trades else 1
        profit_factor = avg_win / avg_loss if avg_loss != 0 else 0
        
        # 计算夏普比率
        # TODO: 需要更精确的收益率数据来计算夏普比率
        
        # 计算最大回撤
        max_drawdown = summary.get("max_drawdown", 0)
        
        performance = {
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "max_drawdown": max_drawdown,
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades)
        }
        
        return performance 

# 单例模式，提供全局访问点
_pyramid_strategy = None

def get_pyramid_strategy(
    symbols: List[str] = None,
    timeframe: str = '1d',
    auto_trade: bool = False,
    paper_trading: bool = True,
    backtest_mode: bool = False
) -> PyramidTradingStrategy:
    """
    获取金字塔交易策略实例
    
    Args:
        symbols: 交易品种列表
        timeframe: 交易时间周期
        auto_trade: 是否启用自动交易
        paper_trading: 是否使用模拟交易
        backtest_mode: 是否为回测模式
        
    Returns:
        金字塔交易策略实例
    """
    global _pyramid_strategy
    if _pyramid_strategy is None:
        _pyramid_strategy = PyramidTradingStrategy(
            symbols=symbols,
            timeframe=timeframe,
            auto_trade=auto_trade,
            paper_trading=paper_trading,
            backtest_mode=backtest_mode
        )
        
    return _pyramid_strategy


if __name__ == "__main__":
    """
    测试金字塔交易策略
    """
    import pandas as pd
    import matplotlib.pyplot as plt
    from datetime import datetime, timedelta
    
    # 解析命令行参数
    import argparse
    
    parser = argparse.ArgumentParser(description="金字塔交易策略测试")
    parser.add_argument("--symbols", type=str, nargs="+", help="交易品种列表")
    parser.add_argument("--backtest", action="store_true", help="是否运行回测")
    parser.add_argument("--start_date", type=str, help="回测开始日期，格式：YYYY-MM-DD")
    parser.add_argument("--end_date", type=str, help="回测结束日期，格式：YYYY-MM-DD")
    parser.add_argument("--paper", action="store_true", help="是否使用模拟交易")
    parser.add_argument("--auto", action="store_true", help="是否启用自动交易")
    
    args = parser.parse_args()
    
    # 设置默认参数
    symbols = args.symbols or ["000001.SH", "399001.SZ", "399006.SZ"]
    backtest_mode = args.backtest
    auto_trade = args.auto
    paper_trading = args.paper or not auto_trade
    
    # 创建策略实例
    strategy = PyramidTradingStrategy(
        symbols=symbols,
        timeframe='1d',  # 使用日线数据
        auto_trade=auto_trade,
        paper_trading=paper_trading,
        backtest_mode=backtest_mode
    )
    
    if backtest_mode:
        # 运行回测
        start_date = args.start_date or (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        end_date = args.end_date or datetime.now().strftime("%Y-%m-%d")
        
        print(f"运行回测: {symbols}, 时间范围: {start_date} 至 {end_date}")
        
        # 初始化策略
        strategy.initialize()
        
        # 运行回测
        report = strategy.run_backtest(start_date, end_date)
        
        # 打印回测结果
        print("\n=== 回测结果摘要 ===")
        print(f"起始资金: {report['summary']['initial_capital']}")
        print(f"结束资金: {report['summary']['current_capital']}")
        print(f"总收益率: {report['summary']['return_rate']:.2%}")
        print(f"总交易次数: {report['performance']['total_trades']}")
        print(f"胜率: {report['performance']['win_rate']:.2%}")
        print(f"盈亏比: {report['performance']['profit_factor']:.2f}")
        print(f"最大回撤: {report['performance']['max_drawdown']:.2%}")
        print(f"平均盈利: {report['performance']['avg_win']:.2f}")
        print(f"平均亏损: {report['performance']['avg_loss']:.2f}")
        
        # 绘制回测结果图表
        # TODO: 实现回测结果图表绘制
        
    else:
        # 实盘/模拟交易
        mode = "模拟交易" if paper_trading else "实盘交易"
        auto = "自动交易" if auto_trade else "手动交易"
        print(f"启动{mode}({auto}): {symbols}")
        
        # 初始化策略
        if strategy.initialize():
            # 启动策略
            strategy.start()
            
            try:
                # 运行一段时间
                print("策略运行中，按Ctrl+C停止...")
                
                # 模拟主循环
                while True:
                    # 每10秒打印一次状态
                    time.sleep(10)
                    status = strategy.get_strategy_status()
                    
                    # 打印持仓状态
                    positions = status.get("positions", {})
                    print(f"\n当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"当前持仓数: {len(positions)}")
                    
                    for symbol, pos in positions.items():
                        direction = pos.get("direction", "")
                        entry_price = pos.get("average_entry_price", 0)
                        profit = pos.get("unrealized_profit", 0)
                        print(f"  {symbol}: 方向={direction}, 价格={entry_price}, 未实现盈亏={profit}")
                    
            except KeyboardInterrupt:
                # 用户中断，停止策略
                print("\n用户中断，停止策略...")
                strategy.stop()
                print("策略已停止")
                
        else:
            print("策略初始化失败") 
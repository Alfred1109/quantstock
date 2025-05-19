"""
金字塔交易法LLM策略

该策略结合了金字塔交易法则和大语言模型分析，
实现了基于趋势分析的分批建仓和减仓策略。
"""

from .base_strategy import BaseStrategy
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import pandas as pd

# 修改相对导入为绝对导入
from llm_module.prompt_engineering import (
    get_market_trend_analysis_prompt,
    get_entry_point_prompt,
    get_position_sizing_prompt,
    get_exit_strategy_prompt
)

# 导入策略模块的工具函数
from .utils import format_utils, parser_utils, trade_actions

# 获取logger
logger = logging.getLogger('app')

class PyramidLLMStrategy(BaseStrategy):
    """
    基于金字塔交易法的LLM策略
    
    该策略使用大语言模型分析市场趋势，并根据金字塔交易法则
    进行分批建仓和减仓，逐步扩大盈利头寸，并在趋势反转时及时减仓或退出。
    
    金字塔交易的核心理念：
    1. 趋势确认后，先小仓位进入
    2. 趋势继续发展，逐步增加仓位
    3. 趋势减弱或反转，逐步减仓
    4. 使用严格的止损控制风险
    """
    
    def __init__(
        self, 
        config: Dict[str, Any], 
        data_provider: Any, 
        llm_client: Any,
        broker_client: Any = None,
        risk_manager: Any = None
    ):
        """
        初始化金字塔LLM策略
        
        Args:
            config: 策略配置参数
            data_provider: 数据提供者实例
            llm_client: 大语言模型客户端，用于市场分析和信号生成
            broker_client: 券商接口客户端（可选）
            risk_manager: 风险管理器（可选）
        """
        super().__init__(config, data_provider, llm_client, broker_client, risk_manager)
        
        # 添加logger作为实例属性
        self.logger = logger
        
        # 金字塔策略特定参数，将从config中加载或使用默认值
        self.pyramid_params = {
            # 最大金字塔层级（最多加仓次数）
            'max_pyramid_levels': config.get('max_pyramid_levels', 3),
            
            # 初始仓位大小（占总资金百分比）
            'initial_position_size': config.get('initial_position_size', 0.1),
            
            # 后续加仓大小（相对于初始仓位的倍数）
            'position_size_multiplier': config.get('position_size_multiplier', 1.5),
            
            # LLM信号置信度阈值，低于此值不执行信号
            'llm_signal_confidence_threshold': config.get('llm_signal_confidence_threshold', 0.6),
            
            # 技术分析指标参数
            'technical_indicators': config.get('technical_indicators', {
                'ma_short': 5,   # 短期移动平均
                'ma_medium': 20, # 中期移动平均
                'ma_long': 50,   # 长期移动平均
                'rsi_period': 14 # RSI周期
            }),
            
            # 止损配置 (例如 ATR的倍数)
            'stop_loss_atr_multiplier': config.get('stop_loss_atr_multiplier', 2.0),
            
            # 趋势强度阈值（1-10），高于此值才考虑入场
            'trend_strength_threshold': config.get('trend_strength_threshold', 6)
        }
        
        # 当前市场趋势状态
        self.market_trend = {
            'direction': None,  # 'up', 'down', 或 'sideways'
            'strength': 0,      # 趋势强度 1-10
            'last_update': None # 最后更新时间
        }
        
        # 每个资产的金字塔状态
        self.pyramid_status = {}
        
        # 打印初始化完成消息
        self.logger.info(f"金字塔LLM策略已初始化，最大层级: {self.pyramid_params['max_pyramid_levels']}")

    def on_data(self, data_event: Dict[str, Any]) -> None:
        """
        处理新的市场数据事件
        
        当新的市场数据可用时被调用，用于更新策略状态和生成交易信号。
        
        Args:
            data_event: 市场数据事件，包含时间戳、资产代码、价格和成交量等信息
        """
        self.logger.debug(f"收到新的市场数据: {data_event.get('symbol')} at {data_event.get('timestamp')}")
        
        signals_to_execute = [] # Store signals generated in this on_data call

        try:
            # 提取基本信息
            symbol = data_event.get('symbol')
            timestamp = data_event.get('timestamp')
            
            if not symbol:
                self.logger.warning("数据事件缺少symbol字段，无法处理")
                return
                
            # 1. 获取与处理市场数据
            market_data = self._prepare_market_data(symbol, data_event)
            
            # 2. 执行技术分析
            technical_analysis = self._perform_technical_analysis(market_data)
            
            # 3. 根据当前持仓状态选择合适的行动
            signal = None
            if symbol in self.current_positions and self.current_positions[symbol]['quantity'] > 0:
                # 已有持仓，判断是否需要加仓、减仓或退出
                signal = self._manage_existing_position(symbol, market_data, technical_analysis)
            else:
                # 无持仓，判断是否寻找入场点
                signal = self._find_entry_opportunity(symbol, market_data, technical_analysis)
            
            if signal and signal.get('action') != 'HOLD':
                signals_to_execute.append(signal)
                
        except Exception as e:
            self.logger.error(f"处理市场数据时发生错误: {str(e)}", exc_info=True)

        # 4. 执行生成的信号 (if any)
        for sig in signals_to_execute:
            self.execute_signal(sig)

    def generate_signals(self, symbol: str, market_data: Dict[str, Any], technical_analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        根据当前市场数据和分析生成交易信号。
        这个方法会被 on_data 调用，或者在回测引擎中被独立调用。
        """
        self.logger.info(f"PyramidLLMStrategy 为 {symbol} 生成信号...")
        signal = None
        try:
            if symbol in self.current_positions and self.current_positions[symbol]['quantity'] > 0:
                signal = self._manage_existing_position(symbol, market_data, technical_analysis)
            else:
                signal = self._find_entry_opportunity(symbol, market_data, technical_analysis)
        except Exception as e:
            self.logger.error(f"为 {symbol} 生成信号时发生错误: {str(e)}", exc_info=True)
            return {"action": "HOLD", "symbol": symbol, "reason": f"Error generating signal: {str(e)}"}

        if signal:
            self.logger.info(f"为 {symbol} 生成的信号: {signal}")
            return signal
        else:
            return {"action": "HOLD", "symbol": symbol, "reason": "无明确交易信号"}

    def execute_signal(self, signal: Dict[str, Any]) -> None:
        """
        执行交易信号
        
        Args:
            signal: 交易信号字典，包含action, symbol, quantity, price, reason等
        """
        self.logger.info(f"PyramidLLMStrategy 准备执行信号: {signal}")

        if not signal or signal.get('action') == 'HOLD':
            self.logger.info(f"信号为HOLD或无效，不执行: {signal}")
            return

        symbol = signal.get('symbol')
        action = signal.get('action') # BUY, SELL

        # (可选) 风险管理检查
        if self.risk_manager:
            try:
                is_valid, validation_reason = self.risk_manager.validate_signal(signal, self.portfolio, self.current_positions.get(symbol))
                if not is_valid:
                    self.logger.warning(f"信号未通过风险管理检查: {validation_reason}. 信号: {signal}")
                    self.trade_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'symbol': symbol,
                        'action': action,
                        'quantity': signal.get('quantity'),
                        'price': signal.get('price'),
                        'status': 'REJECTED_RISK',
                        'reason': validation_reason
                    })
                    return
            except Exception as e:
                self.logger.error(f"风险管理检查时出错: {str(e)}", exc_info=True)
                # 根据配置决定是否继续执行或中止
                # For now, we'll log and continue, assuming critical risk checks are part of broker client
        
        # 准备调用交易执行函数
        # 实际执行将通过 broker_client，这里先用 trade_actions 中的逻辑模拟并记录
        
        execution_result = None
        market_data_for_trade = self._prepare_market_data(symbol, {'symbol': symbol, 'timestamp': datetime.now().isoformat(), 'close': signal.get('price')}) # simplified market_data for trade actions

        if action == 'BUY':
            # For initial buy, position_advice might be directly in the signal or derived
            # For add_to_position, it expects a richer position_advice
            # We need to make sure `signal` has enough info or structure it as `position_advice`
            
            # Assuming the signal from _find_entry_opportunity or _manage_existing_position is structured
            # similarly to what trade_actions expects for `position_advice`
            
            if signal.get('type') == 'INITIAL_ENTRY': # A new type to distinguish
                 # Construct position_advice for initial entry
                pos_advice = {
                    'percentage': signal.get('initial_position_ratio', self.pyramid_params['initial_position_size']), # needs to be part of signal
                    'stop_loss': signal.get('stop_loss'),
                    'reason': signal.get('reason')
                }
                # For initial buy, we need a slightly different flow than add_to_position
                # Let's create a new trade_action or handle it here.
                # For now, let's assume initial buy sets up the first level of pyramid.
                
                # Simplified initial buy:
                order_to_place = {
                    'action': 'BUY',
                    'symbol': symbol,
                    'quantity': signal.get('quantity'), # Must be calculated based on initial_position_size
                    'price': signal.get('price'),
                    'reason': signal.get('reason')
                }
                if self.broker_client:
                    execution_result = self.broker_client.place_order(order_to_place)
                else: # Simulate
                    execution_result = {'status': 'success', 'order_id': 'sim_order_123', 'filled_quantity': signal.get('quantity'), 'filled_price': signal.get('price')}
                
                if execution_result and execution_result.get('status') == 'success':
                    self.pyramid_status[symbol] = {
                        'level': 1,
                        'entries': [{
                            'price': execution_result.get('filled_price'),
                            'quantity': execution_result.get('filled_quantity'),
                            'timestamp': datetime.now().isoformat(),
                            'type': 'initial_entry'
                        }],
                        'stop_loss': signal.get('stop_loss') # From LLM entry analysis
                    }
                    self.logger.info(f"初始买入成功: {symbol}, 更新金字塔状态: {self.pyramid_status[symbol]}")


            elif signal.get('type') == 'ADD_POSITION': # signal from _manage_existing_position for adding
                position_advice_for_add = signal.get('position_advice', {}) # _manage_existing_position should put advice here
                execution_result = trade_actions.add_to_position(
                    symbol=symbol,
                    position_advice=position_advice_for_add,
                    market_data=market_data_for_trade,
                    current_positions=self.current_positions,
                    pyramid_status=self.pyramid_status,
                    account_value=self._get_account_value(),
                    execute_signal_func=self.broker_client.place_order if self.broker_client else self._simulated_place_order
                )
        elif action == 'SELL':
            if signal.get('type') == 'REDUCE_POSITION':
                position_advice_for_reduce = signal.get('position_advice', {})
                execution_result = trade_actions.reduce_position(
                    symbol=symbol,
                    position_advice=position_advice_for_reduce,
                    market_data=market_data_for_trade,
                    current_positions=self.current_positions,
                    pyramid_status=self.pyramid_status,
                    execute_signal_func=self.broker_client.place_order if self.broker_client else self._simulated_place_order
                )
            elif signal.get('type') == 'EXIT_POSITION':
                position_advice_for_exit = signal.get('position_advice', {})
                execution_result = trade_actions.exit_position(
                    symbol=symbol,
                    position_advice=position_advice_for_exit,
                    market_data=market_data_for_trade,
                    current_positions=self.current_positions,
                    pyramid_status=self.pyramid_status,
                    execute_signal_func=self.broker_client.place_order if self.broker_client else self._simulated_place_order
                )
        
        # 更新持仓和交易历史
        if execution_result and execution_result.get('status') == 'success':
            filled_quantity = execution_result.get('filled_quantity', signal.get('quantity'))
            filled_price = execution_result.get('filled_price', signal.get('price'))
            
            self.update_position(
                symbol=symbol,
                action=action,
                quantity=filled_quantity,
                price=filled_price
            )
            self.trade_history.append({
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'action': action,
                'quantity': filled_quantity,
                'price': filled_price,
                'status': 'EXECUTED',
                'order_id': execution_result.get('order_id'),
                'reason': signal.get('reason')
            })
            self.logger.info(f"信号执行成功并更新持仓: {signal}")
        elif execution_result:
            self.logger.warning(f"信号执行失败或部分成功: {execution_result.get('reason', 'Unknown reason')}. Signal: {signal}")
            self.trade_history.append({
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'action': action,
                'quantity': signal.get('quantity'),
                'price': signal.get('price'),
                'status': execution_result.get('status', 'FAILED_EXECUTION'),
                'reason': execution_result.get('reason', signal.get('reason'))
            })
        else:
            self.logger.error(f"执行信号后未收到明确的执行结果. Signal: {signal}")
            self.trade_history.append({
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'action': action,
                'quantity': signal.get('quantity'),
                'price': signal.get('price'),
                'status': 'FAILED_UNKNOWN',
                'reason': signal.get('reason')
            })
            
    def _simulated_place_order(self, order: Dict[str,Any]) -> Dict[str, Any]:
        """模拟下单函数，用于测试。"""
        self.logger.info(f"模拟下单: {order}")
        return {
            'status': 'success', 
            'order_id': f"sim_{datetime.now().timestamp()}", 
            'filled_quantity': order.get('quantity'), 
            'filled_price': order.get('price')
        }

    def _prepare_market_data(self, symbol: str, data_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        准备和整理市场数据，供后续分析使用
        
        Args:
            symbol: 资产代码
            data_event: 原始市场数据事件
            
        Returns:
            处理后的市场数据字典
        """
        # 从数据提供者获取更完整的市场数据
        # 这可能包括获取历史数据，以便进行技术分析
        try:
            # 使用get_historical_data获取历史数据
            start_date = (datetime.now() - timedelta(days=100)).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
            
            # 检查data_provider是否存在
            if not hasattr(self, 'data_provider') or self.data_provider is None:
                self.logger.error("数据提供者(data_provider)不存在或为None")
                raise ValueError("数据提供者不存在")
            
            # 处理股票代码，去掉后缀，AKShare通常需要纯代码
            pure_symbol = symbol.split('.')[0] if '.' in symbol else symbol
            self.logger.debug(f"原始股票代码: {symbol}, 处理后代码: {pure_symbol}")
            
            recent_data = None
            # 添加重试机制
            import time
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    # 尝试使用get_historical_data方法
                    self.logger.debug(f"尝试第{attempt+1}次获取 {pure_symbol} 的历史数据，从 {start_date} 到 {end_date}")
                    recent_data = self.data_provider.get_historical_data(
                        symbol=pure_symbol,  # 使用处理后的纯代码
                        start_date=start_date,
                        end_date=end_date,
                        timeframe="1d"  # 日K线
                    )
                    
                    # 检查返回的数据是否为Pandas DataFrame且非空
                    if recent_data is None:
                        self.logger.warning(f"{pure_symbol} 历史数据返回为None")
                        raise ValueError("返回数据为None")
                    elif not isinstance(recent_data, pd.DataFrame):
                        self.logger.warning(f"{pure_symbol} 历史数据不是DataFrame，而是 {type(recent_data)}")
                        raise ValueError("返回数据不是DataFrame")
                    elif recent_data.empty:
                        self.logger.warning(f"{pure_symbol} 历史数据为空DataFrame")
                        raise ValueError("返回的DataFrame为空")
                    
                    # 如果成功获取数据，跳出重试循环
                    self.logger.info(f"成功获取 {pure_symbol} 的历史数据, 共 {len(recent_data)} 行")
                    break
                    
                except Exception as e:
                    self.logger.warning(f"第 {attempt+1} 次获取历史数据失败: {str(e)}")
                    if attempt < max_retries - 1:
                        self.logger.info(f"等待 1 秒后重试...")
                        time.sleep(1)  # 等待1秒后重试
                    else:
                        self.logger.error(f"已达到最大重试次数 {max_retries}，无法获取历史数据")
                        recent_data = pd.DataFrame()  # 设置为空DataFrame
            
            # 组合最新数据和历史数据
            market_data = {
                'symbol': symbol,
                'timestamp': data_event.get('timestamp'),
                'current': {
                    'open': data_event.get('open'),
                    'high': data_event.get('high'),
                    'low': data_event.get('low'),
                    'close': data_event.get('close'),
                    'volume': data_event.get('volume')
                },
                'history': recent_data
            }
            
            return market_data
            
        except Exception as e:
            self.logger.error(f"准备市场数据时出错: {str(e)}", exc_info=True)
            self.logger.error(f"数据事件内容: {data_event}")
            # 返回基本数据
            return {
                'symbol': symbol,
                'timestamp': data_event.get('timestamp'),
                'current': {
                    'open': data_event.get('open'),
                    'high': data_event.get('high'),
                    'low': data_event.get('low'),
                    'close': data_event.get('close'),
                    'volume': data_event.get('volume')
                }
            }

    def _perform_technical_analysis(self, market_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        对市场数据执行技术分析
        
        Args:
            market_data: 市场数据字典
            
        Returns:
            技术分析结果字典
        """
        self.logger.debug(f"为 {market_data.get('symbol')} 执行技术分析...")
        
        # 获取历史数据
        history = None
        symbol = None
        if 'history' in market_data and isinstance(market_data['history'], pd.DataFrame):
            history = market_data['history']
            symbol = market_data.get('symbol')
        else:
            # 如果market_data是一个字典，包含多个symbol的数据
            primary_symbol = self.config.get('base_symbol', '')
            if not primary_symbol and market_data:
                # 尝试从字典中获取第一个key作为symbol
                try:
                    primary_symbol = list(market_data.keys())[0]
                except:
                    pass
            
            if primary_symbol and primary_symbol in market_data:
                history = market_data.get(primary_symbol)
                symbol = primary_symbol

        if history is None or not isinstance(history, pd.DataFrame) or history.empty:
            self.logger.warning(f"无可用市场数据进行技术分析")
            return {
                'symbol': symbol or 'unknown',
                'timestamp': datetime.now().isoformat(),
                'indicators': {},
                'patterns': [],
                'support_levels': [],
                'resistance_levels': []
            }
        
        try:
            # 确保数据包含必要的列
            required_columns = ['close', 'high', 'low', 'open', 'volume']
            missing_columns = [col for col in required_columns if col not in history.columns]
            
            if missing_columns:
                self.logger.warning(f"技术分析所需列缺失: {missing_columns}")
                # 尝试映射常见的中文列名
                column_mapping = {
                    '收盘': 'close',
                    '最高': 'high',
                    '最低': 'low',
                    '开盘': 'open',
                    '成交量': 'volume'
                }
                for cn_col, en_col in column_mapping.items():
                    if cn_col in history.columns and en_col in missing_columns:
                        history[en_col] = history[cn_col]
                        missing_columns.remove(en_col)
                
                # 如果仍有缺失列
                if missing_columns:
                    self.logger.warning(f"无法映射以下列，将使用默认值: {missing_columns}")
                    for col in missing_columns:
                        if col == 'volume' and col not in history.columns:
                            history['volume'] = 0
            
            # 确保索引是日期类型
            if 'date' in history.columns:
                history = history.set_index('date')
            
            # 使用pandas计算移动平均线
            ma_periods = {
                'ma_short': self.pyramid_params['technical_indicators'].get('ma_short', 5),
                'ma_medium': self.pyramid_params['technical_indicators'].get('ma_medium', 20),
                'ma_long': self.pyramid_params['technical_indicators'].get('ma_long', 50),
            }
            
            ma_indicators = {}
            for name, period in ma_periods.items():
                if len(history) >= period:
                    ma_indicators[name] = history['close'].rolling(window=period).mean().iloc[-1]
                else:
                    ma_indicators[name] = history['close'].mean()
            
            # 计算RSI
            rsi_period = self.pyramid_params['technical_indicators'].get('rsi_period', 14)
            rsi = None
            if len(history) >= rsi_period:
                delta = history['close'].diff()
                gain = delta.where(delta > 0, 0)
                loss = -delta.where(delta < 0, 0)
                avg_gain = gain.rolling(window=rsi_period).mean()
                avg_loss = loss.rolling(window=rsi_period).mean()
                rs = avg_gain / avg_loss.replace(0, 1e-8)  # 避免除零错误
                rsi = 100 - (100 / (1 + rs)).iloc[-1]
            else:
                rsi = 50  # 默认值
            
            # 计算MACD
            short_ema_period = 12
            long_ema_period = 26
            signal_period = 9
            
            short_ema = history['close'].ewm(span=short_ema_period, adjust=False).mean()
            long_ema = history['close'].ewm(span=long_ema_period, adjust=False).mean()
            macd_line = short_ema - long_ema
            signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
            macd_histogram = macd_line - signal_line
            
            macd_values = {
                'macd_line': macd_line.iloc[-1],
                'signal_line': signal_line.iloc[-1],
                'histogram': macd_histogram.iloc[-1]
            }
            
            # 计算ATR (Average True Range)
            atr_period = 14
            high_low = history['high'] - history['low']
            high_close = (history['high'] - history['close'].shift()).abs()
            low_close = (history['low'] - history['close'].shift()).abs()
            
            true_ranges = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = true_ranges.rolling(window=atr_period).mean().iloc[-1]
            
            # 计算成交量变化
            volume_change = 0
            if 'volume' in history.columns and len(history) > 1:
                current_vol = history['volume'].iloc[-1]
                prev_vol = history['volume'].iloc[-2]
                volume_change = ((current_vol - prev_vol) / prev_vol * 100) if prev_vol != 0 else 0
            
            # 识别支撑位和阻力位 (简单实现)
            support_levels = []
            resistance_levels = []
            
            if len(history) >= 20:
                # 获取最近的价格
                recent_prices = history['close'][-20:]
                current_price = recent_prices.iloc[-1]
                
                # 获取最近的低点作为支撑位
                local_min = recent_prices.iloc[:-1].min()
                if local_min < current_price:
                    support_levels.append(local_min)
                
                # 获取最近的高点作为阻力位
                local_max = recent_prices.iloc[:-1].max()
                if local_max > current_price:
                    resistance_levels.append(local_max)
                    
                # 添加其他支撑位和阻力位的计算逻辑
                # 例如使用历史低点和高点聚类
            
            # 识别常见蜡烛图形态 (简单实现)
            patterns = []
            if len(history) >= 3:
                # 检测看涨吞没形态
                prev1 = history.iloc[-2]
                prev2 = history.iloc[-3]
                current = history.iloc[-1]
                
                # 简单的看涨吞没形态
                if (prev2['close'] < prev2['open'] and  # 前一天是阴线
                    current['close'] > current['open'] and  # 当前是阳线
                    current['open'] < prev2['close'] and  # 当前开盘低于前一天收盘
                    current['close'] > prev2['open']):  # 当前收盘高于前一天开盘
                    patterns.append('看涨吞没形态')
                
                # 简单的十字星形态
                if abs(current['close'] - current['open']) / (current['high'] - current['low'] + 1e-8) < 0.1:
                    patterns.append('十字星形态')
            
            # 整合所有技术指标
            analysis = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'indicators': {
                    'ma_short': ma_indicators.get('ma_short'),
                    'ma_medium': ma_indicators.get('ma_medium'),
                    'ma_long': ma_indicators.get('ma_long'),
                    'rsi': rsi,
                    'macd': macd_values,
                    'atr': atr,
                    'volume_change': volume_change
                },
                'patterns': patterns,
                'support_levels': support_levels,
                'resistance_levels': resistance_levels
            }
            
            self.logger.debug(f"完成技术分析: {symbol}")
            return analysis
            
        except Exception as e:
            self.logger.error(f"执行技术分析时出错: {str(e)}", exc_info=True)
            # 返回一个最小化的分析结果，防止下游处理出错
            return {
                'symbol': symbol or 'unknown',
                'timestamp': datetime.now().isoformat(),
                'indicators': {
                    'ma_short': history['close'].mean() if 'close' in history else 0,
                    'ma_medium': history['close'].mean() if 'close' in history else 0,
                    'ma_long': history['close'].mean() if 'close' in history else 0,
                    'rsi': 50,
                    'volume_change': 0
                },
                'patterns': [],
                'support_levels': [],
                'resistance_levels': []
            }

    def _manage_existing_position(self, symbol: str, market_data: Dict[str, Any], technical_analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        管理现有持仓：判断是否加仓、减仓、止损或止盈
        
        Returns:
            交易信号字典或None
        """
        self.logger.info(f"为 {symbol} 管理现有持仓...")
        position = self.current_positions.get(symbol)
        pyramid_info = self.pyramid_status.get(symbol)

        if not position or not pyramid_info:
            self.logger.warning(f"无法管理持仓: {symbol} 不在当前持仓或金字塔状态中。")
            return None # Or a HOLD signal

        current_price = market_data.get('current', {}).get('close')
        if not current_price:
            self.logger.warning(f"无法管理持仓: {symbol} 当前价格不可用。")
            return None # Or a HOLD signal

        # 1. 检查止损
        stop_loss_price = pyramid_info.get('stop_loss')
        if stop_loss_price and current_price <= stop_loss_price:
            self.logger.info(f"{symbol} 触发止损位 {stop_loss_price} at {current_price}。准备清仓。")
            exit_advice = {'reason': f'Stop-loss triggered at {stop_loss_price}', 'action': 'exit'}
            return {
                "action": "SELL", 
                "symbol": symbol, 
                "quantity": "all", # Placeholder, will be determined by exit_position
                "price": current_price,
                "reason": exit_advice['reason'],
                "type": "EXIT_POSITION",
                "position_advice": exit_advice
            }

        # 2. (可选) 检查止盈 (如果策略定义了止盈逻辑)
        # take_profit_price = pyramid_info.get('take_profit')
        # if take_profit_price and current_price >= take_profit_price:
        #     logger.info(f"{symbol} 触发止盈位 {take_profit_price}。准备减仓或清仓。")
        #     # ... (生成减仓/清仓信号)

        # 3. 重新分析市场趋势
        trend_analysis = self._analyze_market_trend(symbol, market_data, technical_analysis)
        self.market_trend['direction'] = trend_analysis.get('trend')
        self.market_trend['strength'] = trend_analysis.get('strength')
        self.market_trend['last_update'] = datetime.now().isoformat()

        # 4. 获取LLM仓位管理建议
        position_advice = self._get_position_sizing_advice(
            symbol, trend_analysis, position, market_data, technical_analysis
        )
        
        action = position_advice.get('action')
        llm_confidence = position_advice.get('confidence', 1.0) # Assume 1.0 if not present

        if llm_confidence < self.pyramid_params['llm_signal_confidence_threshold']:
            self.logger.info(f"LLM仓位建议置信度 ({llm_confidence}) 低于阈值，不执行: {position_advice.get('reason')}")
            return {"action": "HOLD", "symbol": symbol, "reason": "LLM建议置信度低"}


        if action == 'add' and pyramid_info['level'] < self.pyramid_params['max_pyramid_levels']:
            self.logger.info(f"{symbol} 收到加仓建议: {position_advice.get('reason')}")
            # 加仓逻辑在 trade_actions.add_to_position 中处理数量计算
            return {
                "action": "BUY", 
                "symbol": symbol, 
                # quantity will be calculated by add_to_position based on advice percentage
                "price": current_price, # Use current market price for signal
                "reason": position_advice.get('reason'),
                "type": "ADD_POSITION",
                "position_advice": position_advice
            }
        elif action == 'reduce':
            self.logger.info(f"{symbol} 收到减仓建议: {position_advice.get('reason')}")
            # 减仓逻辑在 trade_actions.reduce_position 中处理数量计算
            return {
                "action": "SELL", 
                "symbol": symbol, 
                "price": current_price,
                "reason": position_advice.get('reason'),
                "type": "REDUCE_POSITION",
                "position_advice": position_advice
            }
        elif action == 'exit':
            self.logger.info(f"{symbol} 收到清仓建议: {position_advice.get('reason')}")
            return {
                "action": "SELL", 
                "symbol": symbol, 
                "price": current_price,
                "reason": position_advice.get('reason'),
                "type": "EXIT_POSITION",
                "position_advice": position_advice
            }
        else: # maintain or unknown
            self.logger.info(f"{symbol} 仓位管理建议: 维持现状或未知 ({action})")
            return {"action": "HOLD", "symbol": symbol, "reason": position_advice.get('reason', "维持现状")}

    def _find_entry_opportunity(self, symbol: str, market_data: Dict[str, Any], technical_analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        寻找新的入场机会
        
        Returns:
            交易信号字典或None
        """
        self.logger.info(f"为 {symbol} 寻找入场机会...")

        # 1. 分析市场总体趋势
        trend_analysis = self._analyze_market_trend(symbol, market_data, technical_analysis)
        self.market_trend['direction'] = trend_analysis.get('trend') # e.g., '上升趋势'
        self.market_trend['strength'] = trend_analysis.get('strength') # e.g., 7
        self.market_trend['last_update'] = datetime.now().isoformat()

        # 检查趋势是否满足入场条件
        # 例如，只在上升趋势且强度足够时考虑做多
        # (这里简化，假设只做多)
        is_bullish_trend = self.market_trend['direction'] == '上升趋势' and \
                           self.market_trend['strength'] >= self.pyramid_params['trend_strength_threshold']
        
        if not is_bullish_trend:
            self.logger.info(f"{symbol} 当前趋势不满足入场条件: {self.market_trend['direction']} (强度 {self.market_trend['strength']})")
            return {"action": "HOLD", "symbol": symbol, "reason": "趋势不满足入场条件"}

        # 2. 分析具体入场点
        entry_analysis = self._analyze_entry_point(symbol, market_data, trend_analysis, technical_analysis)
        
        entry_decision = entry_analysis.get('entry_decision') # '是' or '否'
        entry_confidence = entry_analysis.get('confidence', 0) # 1-10
        
        # 检查LLM入场决策和置信度
        if entry_decision != '是' or entry_confidence < self.pyramid_params['llm_signal_confidence_threshold'] * 10: # Scale confidence to 0-100 if LLM gives 1-10
            self.logger.info(f"{symbol} LLM入场分析决策为 '{entry_decision}' 或置信度 ({entry_confidence}/10) 过低。")
            return {"action": "HOLD", "symbol": symbol, "reason": f"LLM入场决策为'{entry_decision}', 置信度低"}

        # 3. 如果决定入场，计算初始仓位并生成买入信号
        current_price = market_data.get('current', {}).get('close')
        if not current_price:
            self.logger.warning(f"无法入场: {symbol} 当前价格不可用。")
            return {"action": "HOLD", "symbol": symbol, "reason": "当前价格不可用"}

        initial_position_ratio = entry_analysis.get('initial_position', self.pyramid_params['initial_position_size'])
        account_value = self._get_account_value()
        initial_investment = account_value * initial_position_ratio
        quantity_to_buy = int(initial_investment / current_price) if current_price > 0 else 0

        if quantity_to_buy <= 0:
            self.logger.warning(f"{symbol} 计算的初始买入数量为0，无法入场。")
            return {"action": "HOLD", "symbol": symbol, "reason": "初始买入数量为0"}
            
        stop_loss_price = entry_analysis.get('stop_loss')

        self.logger.info(f"{symbol} 发现入场机会: {entry_analysis.get('reason')}")
        return {
            "action": "BUY",
            "symbol": symbol,
            "quantity": quantity_to_buy,
            "price": current_price, # Or use entry_analysis.get('price_range')[0] if more conservative
            "reason": entry_analysis.get('reason'),
            "stop_loss": stop_loss_price,
            "initial_position_ratio": initial_position_ratio,
            "type": "INITIAL_ENTRY"
        }

    def _get_account_value(self) -> float:
        """获取账户总价值"""
        # 从经纪商客户端获取账户信息
        try:
            if self.broker_client:
                account_info = self.broker_client.get_account_summary()
                if account_info and 'total_equity' in account_info:
                    return float(account_info['total_equity'])
                elif account_info and 'cash_balance' in account_info:
                    return float(account_info['cash_balance'])
            
            # 如果无法从broker获取，尝试从portfolio获取
            if hasattr(self, 'portfolio') and self.portfolio:
                return self.portfolio.get_total_value()
                
            self.logger.warning("无法从broker或portfolio获取真实账户价值，使用默认值")
            return 100000.0  # 默认值，仅用于无法获取真实数据时
        except Exception as e:
            self.logger.error(f"获取账户价值时发生错误: {e}", exc_info=True)
            return 100000.0  # 发生错误时的安全值

    def _analyze_market_trend(self, symbol: str, market_data: Dict[str, Any], technical_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """使用LLM分析市场趋势"""
        self.logger.debug(f"为 {symbol} 分析市场趋势...")
        
        # 准备Prompt所需数据
        price_data_fmt = format_utils.format_price_data(market_data)
        volume_data_fmt = format_utils.format_volume_data(market_data)
        tech_indicators_fmt = format_utils.format_technical_indicators(technical_analysis, self.pyramid_params['technical_indicators'])
        recent_price_action_fmt = format_utils.format_recent_price_action(market_data, days=10) # 近10天
        # news_headlines_fmt = self._get_news_headlines(symbol) # 假设有此方法获取新闻

        prompt = get_market_trend_analysis_prompt(
            ticker=symbol,
            price_data=price_data_fmt,
            volume_data=volume_data_fmt,
            technical_indicators=tech_indicators_fmt,
            # news_headlines=news_headlines_fmt # Uncomment if used
        )
        
        try:
            llm_response = self.llm_client.generate_text(prompt)
            parsed_analysis = parser_utils.parse_trend_analysis(llm_response)
            self.logger.debug(f"LLM趋势分析 ({symbol}): {parsed_analysis}")
            return parsed_analysis
        except Exception as e:
            self.logger.error(f"LLM趋势分析失败 ({symbol}): {str(e)}", exc_info=True)
            return {"trend": "unknown", "strength": 0, "analysis": "LLM call failed"}

    def _analyze_entry_point(self, symbol: str, market_data: Dict[str, Any], trend_analysis: Dict[str, Any], technical_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """使用LLM分析入场点"""
        self.logger.debug(f"为 {symbol} 分析入场点...")
        
        price_data_fmt = format_utils.format_price_data(market_data)
        volume_data_fmt = format_utils.format_volume_data(market_data)
        tech_indicators_fmt = format_utils.format_technical_indicators(technical_analysis, self.pyramid_params['technical_indicators'])
        formatted_trend_analysis = format_utils.format_trend_analysis(trend_analysis) # 从之前的结果格式化
        recent_price_action_fmt = format_utils.format_recent_price_action(market_data, days=10) # 近10天
        # risk_appetite = "中等" # 可以从策略配置中获取

        prompt = get_entry_point_prompt(
            ticker=symbol,
            price_data=price_data_fmt,
            overall_trend=formatted_trend_analysis,
            recent_price_action=recent_price_action_fmt,
            technical_indicators=tech_indicators_fmt
            # risk_appetite=risk_appetite # Uncomment if used
        )
        
        try:
            llm_response = self.llm_client.generate_text(prompt)
            parsed_entry = parser_utils.parse_entry_analysis(llm_response)
            self.logger.debug(f"LLM入场点分析 ({symbol}): {parsed_entry}")
            return parsed_entry
        except Exception as e:
            self.logger.error(f"LLM入场点分析失败 ({symbol}): {str(e)}", exc_info=True)
            return {"entry_decision": "否", "reason": "LLM call failed"}

    def _get_position_sizing_advice(self, symbol: str, trend_analysis: Dict[str, Any], 
                                    position: Dict[str, Any], market_data: Dict[str, Any], 
                                    technical_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """使用LLM获取仓位管理建议"""
        self.logger.debug(f"为 {symbol} 获取仓位管理建议...")
        
        price_data_fmt = format_utils.format_price_data(market_data)
        formatted_trend_analysis = format_utils.format_trend_analysis(trend_analysis)
        formatted_position_info = format_utils.format_position_info(position)
        # 获取真实账户信息
        account_info_fmt = self._get_account_info_formatted()
        # 获取真实风险指标
        risk_metrics_fmt = self._get_risk_metrics_formatted(symbol)
        # 获取真实价格波动性数据
        price_volatility_fmt = self._get_price_volatility_formatted(symbol, market_data)
        pyramid_level = self.pyramid_status.get(symbol, {}).get('level', 0)

        prompt = get_position_sizing_prompt(
            ticker=symbol,
            current_trend=formatted_trend_analysis,
            current_position=formatted_position_info,
            risk_metrics=risk_metrics_fmt,
            account_info=account_info_fmt,
            price_volatility=price_volatility_fmt
        )
        
        try:
            llm_response = self.llm_client.generate_text(prompt)
            parsed_advice = parser_utils.parse_position_advice(llm_response)
            self.logger.debug(f"LLM仓位建议 ({symbol}): {parsed_advice}")
            return parsed_advice
        except Exception as e:
            self.logger.error(f"LLM仓位建议获取失败 ({symbol}): {str(e)}", exc_info=True)
            return {"action": "maintain", "reason": "LLM call failed"}

    # --------------------------------------------------------------------------
    # 数据格式化辅助方法 (这些可以移到 format_utils.py 如果通用性强)
    # --------------------------------------------------------------------------
    # 已移至 format_utils.py:
    # _format_price_data, _format_volume_data, _format_technical_indicators,
    # _format_trend_analysis, _format_recent_price_action
    # --------------------------------------------------------------------------

    def _get_news_headlines(self, symbol: str) -> str:
        """获取相关新闻标题"""
        self.logger.debug(f"为 {symbol} 获取新闻标题...")
        try:
            # 优先使用AKShare获取新闻
            news_list = []
            
            # 判断是否有AKShare数据源
            if hasattr(self.data_provider, 'get_stock_news') and callable(getattr(self.data_provider, 'get_stock_news')):
                # 调用AKShare的新闻接口
                news_df = self.data_provider.get_stock_news(symbol=symbol, count=5)
                if not news_df.empty:
                    for idx, row in news_df.iterrows():
                        title = row.get('title', '')
                        date = row.get('date', '')
                        if title and date:
                            news_list.append(f"{date}: {title}")
            
            # 如果AKShare未能获取到新闻，尝试使用其他途径
            if not news_list and hasattr(self.data_provider, 'get_market_news'):
                news_df = self.data_provider.get_market_news(count=5)
                if not news_df.empty:
                    for idx, row in news_df.iterrows():
                        title = row.get('title', '')
                        date = row.get('date', '')
                        if title and date:
                            news_list.append(f"{date}: {title}")
            
            # 如果仍然没有获取到新闻，返回默认消息
            if not news_list:
                return "暂无相关新闻数据。"
            
            formatted_news = "最近相关新闻:\n" + "\n".join(news_list)
            return formatted_news
            
        except Exception as e:
            self.logger.error(f"获取新闻标题时发生错误: {e}", exc_info=True)
            return "获取新闻失败，请检查网络连接和API状态。"
    
    def _get_account_info_formatted(self) -> str:
        """获取格式化的账户信息"""
        try:
            account_info = None
            if self.broker_client:
                account_info = self.broker_client.get_account_summary()
            
            if not account_info or 'status' in account_info and account_info['status'] == 'failed':
                # 尝试从portfolio获取
                if hasattr(self, 'portfolio') and self.portfolio:
                    total_value = self.portfolio.get_total_value()
                    cash_balance = self.portfolio.get_cash_balance()
                    invested_value = total_value - cash_balance
                    
                    return (
                        f"可用资金: {cash_balance:,.2f}元\n"
                        f"已使用资金: {invested_value:,.2f}元\n"
                        f"总资金: {total_value:,.2f}元"
                    )
            else:
                # 使用broker返回的账户信息
                cash = account_info.get('cash_balance', 0)
                total = account_info.get('total_equity', 0)
                market_value = account_info.get('market_value', 0)
                
                return (
                    f"可用资金: {cash:,.2f}元\n"
                    f"已使用资金: {market_value:,.2f}元\n"
                    f"总资金: {total:,.2f}元"
                )
            
            # 如果上面两种方式都失败，返回一个默认值
            self.logger.warning("无法获取真实账户信息，使用默认值")
            return "可用资金: 100,000元\n已使用资金: 20,000元\n总资金: 120,000元"
            
        except Exception as e:
            self.logger.error(f"获取账户信息时发生错误: {e}", exc_info=True)
            return "可用资金: 100,000元\n已使用资金: 20,000元\n总资金: 120,000元"
    
    def _get_risk_metrics_formatted(self, symbol: str) -> str:
        """获取格式化的风险指标"""
        try:
            if self.risk_manager:
                # 尝试从风险管理器获取风险指标
                risk_metrics = self.risk_manager.get_risk_metrics(symbol)
                if risk_metrics:
                    max_drawdown = risk_metrics.get('max_drawdown', 5)
                    volatility = risk_metrics.get('volatility', 2)
                    risk_level = risk_metrics.get('risk_level', '中等')
                    
                    return (
                        f"最大回撤: {max_drawdown}%\n"
                        f"日波动率: {volatility}%\n"
                        f"风险评级: {risk_level}"
                    )
            
            # 如果无法从风险管理器获取，尝试从历史数据计算
            if 'history' in market_data and isinstance(market_data['history'], pd.DataFrame):
                df = market_data['history']
                if not df.empty and 'close' in df.columns:
                    # 计算20日波动率
                    if len(df) > 20:
                        returns = df['close'].pct_change().dropna()
                        volatility = returns.std() * 100
                        
                        # 简单估算最大回撤
                        max_price = df['close'].rolling(window=20).max()
                        drawdown = ((max_price - df['close']) / max_price) * 100
                        max_drawdown = drawdown.max()
                        
                        # 简单风险评级
                        if volatility < 1:
                            risk_level = '低'
                        elif volatility < 3:
                            risk_level = '中等'
                        else:
                            risk_level = '高'
                            
                        return (
                            f"最大回撤: {max_drawdown:.2f}%\n"
                            f"日波动率: {volatility:.2f}%\n"
                            f"风险评级: {risk_level}"
                        )
            
            # 如果上面两种方式都失败，返回一个默认值
            self.logger.warning("无法计算真实风险指标，使用默认值")
            return "最大回撤: 5%\n日波动率: 2%\n风险评级: 中等"
            
        except Exception as e:
            self.logger.error(f"计算风险指标时发生错误: {e}", exc_info=True)
            return "最大回撤: 5%\n日波动率: 2%\n风险评级: 中等"
    
    def _get_price_volatility_formatted(self, symbol: str, market_data: Dict[str, Any]) -> str:
        """获取格式化的价格波动性数据"""
        try:
            # 从市场数据中提取历史价格
            if 'history' in market_data and isinstance(market_data['history'], pd.DataFrame):
                df = market_data['history']
                if not df.empty and all(col in df.columns for col in ['open', 'high', 'low', 'close']):
                    # 计算日内波幅 (high-low)/close
                    daily_range = ((df['high'] - df['low']) / df['close']) * 100
                    
                    # 计算日均波动率
                    avg_volatility = daily_range.mean()
                    
                    # 计算最大日内波幅
                    max_range = daily_range.max()
                    
                    # 判断波动趋势
                    recent_volatility = daily_range.tail(5).mean()
                    older_volatility = daily_range.iloc[:-5].mean() if len(daily_range) > 5 else avg_volatility
                    
                    if recent_volatility > older_volatility * 1.2:
                        trend = "上升"
                    elif recent_volatility < older_volatility * 0.8:
                        trend = "下降"
                    else:
                        trend = "稳定"
                        
                    return (
                        f"日均波动率: {avg_volatility:.2f}%\n"
                        f"最大日内波幅: {max_range:.2f}%\n"
                        f"波动趋势: {trend}"
                    )
            
            # 如果无法计算，返回一个默认值
            self.logger.warning("无法计算价格波动性指标，使用默认值")
            return "日均波动率: 1.8%\n最大日内波幅: 3.5%\n波动趋势: 稳定"
            
        except Exception as e:
            self.logger.error(f"计算价格波动性时发生错误: {e}", exc_info=True)
            return "日均波动率: 1.8%\n最大日内波幅: 3.5%\n波动趋势: 稳定"
        
    # def _format_position_info(self, position: Dict[str, Any]) -> str:
    # 已移至 format_utils.py
    
    # def _get_account_info_formatted(self) -> str:
        # """ (占位符) 获取格式化的账户信息 """
        # return format_utils.format_account_info(self.portfolio.get_summary() if self.portfolio else None)


    # --------------------------------------------------------------------------
    # LLM响应解析辅助方法 (这些可以移到 parser_utils.py 如果通用性强)
    # --------------------------------------------------------------------------
    # 已移至 parser_utils.py:
    # _parse_trend_analysis, _parse_entry_analysis, _parse_position_advice
    # --------------------------------------------------------------------------


    # ... (其他方法保持不变)
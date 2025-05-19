import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import pandas as pd

logger = logging.getLogger('app')

class Portfolio:
    """
    投资组合管理模块。

    负责跟踪和管理交易账户的整体状态，包括：
    - 现金余额
    - 持仓详情 (股票、数量、平均成本、当前市值、未实现盈亏)
    - 交易历史
    - 投资组合整体价值和基本绩效指标
    """

    def __init__(self, initial_cash: float = 100000.0, market_data_provider: Optional[Any] = None):
        """
        初始化投资组合。

        Args:
            initial_cash: 初始现金。
            market_data_provider: (可选)市场数据提供者，用于获取实时价格更新市值。
        """
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: Dict[str, Dict[str, Any]] = {}  # symbol -> {quantity, avg_price, ...}
        self.trade_log: List[Dict[str, Any]] = []
        self.market_data_provider = market_data_provider # For live price updates
        self.portfolio_history: List[Dict[str, Any]] = [] # To track portfolio value over time

        logger.info(f"Portfolio initialized with initial cash: {self.initial_cash}")
        self._record_portfolio_value() # Record initial state

    def update_fill(self, fill_event: Dict[str, Any]):
        """
        处理一个已成交的订单（fill event），并更新持仓和现金。

        Args:
            fill_event: 成交事件字典，应包含:
                'timestamp': (str) 成交时间戳 (ISO format)
                'symbol': (str) 资产代码
                'action': (str) 'BUY' or 'SELL'
                'quantity': (float) 成交数量
                'price': (float) 成交价格
                'commission': (float, optional) 交易佣金
                'order_id': (str, optional) 原始订单ID
        """
        timestamp = fill_event.get('timestamp', datetime.now().isoformat())
        symbol = fill_event.get('symbol')
        action = fill_event.get('action', '').upper()
        quantity = float(fill_event.get('quantity', 0))
        price = float(fill_event.get('price', 0))
        commission = float(fill_event.get('commission', 0.0))

        if not all([symbol, action, quantity > 0, price > 0]):
            logger.error(f"Portfolio: Invalid fill event received: {fill_event}")
            return

        logger.info(f"Portfolio: Processing fill - {action} {quantity} {symbol} @ {price}")

        # 更新现金
        if action == 'BUY':
            self.cash -= (quantity * price) + commission
        elif action == 'SELL':
            self.cash += (quantity * price) - commission
        else:
            logger.warning(f"Portfolio: Unknown action '{action}' in fill event. No cash update.")
            return # Do not proceed further if action is unknown

        # 更新持仓
        if symbol not in self.positions:
            if action == 'BUY':
                self.positions[symbol] = {
                    'quantity': 0,
                    'avg_price': 0.0,
                    'total_cost': 0.0, # For more accurate PnL upon full exit
                    'realized_pnl': 0.0
                }
            else: # Selling a position not in portfolio (should not happen in a consistent system)
                logger.error(f"Portfolio: Attempted to SELL {symbol} which is not in positions.")
                # Potentially revert cash change if strict
                self.cash -= (quantity * price) - commission # Revert cash
                return
        
        pos = self.positions[symbol]
        if action == 'BUY':
            new_total_cost = (pos['quantity'] * pos['avg_price']) + (quantity * price)
            pos['quantity'] += quantity
            pos['total_cost'] += (quantity * price) # Track cost basis for this lot
            pos['avg_price'] = new_total_cost / pos['quantity'] if pos['quantity'] > 0 else 0
        
        elif action == 'SELL':
            if pos['quantity'] < quantity:
                logger.error(f"Portfolio: Cannot sell {quantity} of {symbol}, only hold {pos['quantity']}. Fill event: {fill_event}")
                # Revert cash change due to invalid sell
                self.cash -= (quantity * price) - commission
                return
            
            # Calculate realized PnL for this sale
            cost_of_sold_shares = pos['avg_price'] * quantity
            proceeds = quantity * price
            realized_pnl_this_trade = proceeds - cost_of_sold_shares - commission # Consider commission in PnL
            pos['realized_pnl'] = pos.get('realized_pnl', 0.0) + realized_pnl_this_trade
            
            pos['quantity'] -= quantity
            pos['total_cost'] -= cost_of_sold_shares # Reduce total cost basis

            if pos['quantity'] == 0:
                logger.info(f"Portfolio: Position for {symbol} closed. Realized PnL from this position: {pos['realized_pnl']}")
                # Option: remove symbol from positions or keep it with 0 quantity
                # For simplicity, we keep it to retain realized_pnl history for the symbol.
                # pos['avg_price'] = 0 # Reset avg_price if preferred for closed positions
        
        # 记录交易日志
        self.trade_log.append({
            **fill_event,
            'realized_pnl_trade': realized_pnl_this_trade if action == 'SELL' else 0.0,
            'cash_after_trade': self.cash
        })
        
        self._update_market_values() # Update market values after trade
        self._record_portfolio_value() # Record portfolio value after trade
        logger.debug(f"Portfolio updated: Cash {self.cash:.2f}, Positions: {self.positions}")

    def _update_market_values(self, specific_symbol: Optional[str] = None):
        """更新持仓的当前市场价值和未实现盈亏。"""
        symbols_to_update = [specific_symbol] if specific_symbol else self.positions.keys()

        for symbol in symbols_to_update:
            pos = self.positions.get(symbol)
            if not pos or pos['quantity'] == 0:
                if pos: # Ensure market_value and PNL are zero if quantity is zero
                    pos['current_price'] = 0
                    pos['market_value'] = 0
                    pos['unrealized_pnl'] = 0
                continue

            current_price = pos['avg_price'] # Default if no live price
            if self.market_data_provider:
                try:
                    # 获取市场数据
                    market_info = self.market_data_provider.get_current_price(symbol) 
                    
                    # 正确处理DataFrame，避免直接使用DataFrame作为条件判断
                    if isinstance(market_info, pd.DataFrame):
                        if not market_info.empty:
                            # 从DataFrame中提取第一行数据
                            if 'close' in market_info.columns and market_info['close'].iloc[0] is not None:
                                current_price = float(market_info['close'].iloc[0])
                            elif 'price' in market_info.columns and market_info['price'].iloc[0] is not None:
                                current_price = float(market_info['price'].iloc[0])
                            else:
                                logger.warning(f"Portfolio: DataFrame returned for {symbol} does not contain 'close' or 'price' column. Using average cost.")
                        else:
                            logger.warning(f"Portfolio: Empty DataFrame returned for {symbol}. Using average cost.")
                    # 处理字典类型的返回值
                    elif isinstance(market_info, dict):
                        if market_info.get('close') is not None and isinstance(market_info.get('close'), (int, float)):
                            current_price = market_info['close']
                        elif market_info.get('price') is not None and isinstance(market_info.get('price'), (int, float)):
                            current_price = market_info['price']
                        else:
                            logger.warning(f"Portfolio: Invalid market data format for {symbol}. Using average cost.")
                    else:
                        logger.warning(f"Portfolio: Unexpected return type from get_current_price for {symbol}: {type(market_info)}. Using average cost.")
                except Exception as e:
                    logger.warning(f"Portfolio: Error fetching live price for {symbol}: {str(e)}. Using average cost.")
            
            pos['current_price'] = current_price
            pos['market_value'] = pos['quantity'] * current_price
            pos['unrealized_pnl'] = (current_price - pos['avg_price']) * pos['quantity']

    def get_total_value(self) -> float:
        """计算并返回投资组合的总当前价值 (现金 + 所有持仓的市值)。"""
        self._update_market_values() # Ensure market values are current
        positions_value = sum(pos.get('market_value', 0) for pos in self.positions.values())
        return self.cash + positions_value

    def _record_portfolio_value(self):
        """记录当前投资组合的总价值和时间戳。"""
        current_total_value = self.get_total_value()
        self.portfolio_history.append({
            'timestamp': datetime.now().isoformat(),
            'total_value': current_total_value,
            'cash': self.cash,
            'positions_value': current_total_value - self.cash
        })
        logger.debug(f"Portfolio value recorded: {current_total_value:.2f}")

    def get_summary(self) -> Dict[str, Any]:
        """返回投资组合的摘要信息。"""
        self._update_market_values()
        total_value = self.get_total_value()
        positions_value = total_value - self.cash
        total_realized_pnl = sum(pos.get('realized_pnl', 0) for pos in self.positions.values())
        total_unrealized_pnl = sum(pos.get('unrealized_pnl', 0) for pos in self.positions.values())

        return {
            'timestamp': datetime.now().isoformat(),
            'initial_cash': self.initial_cash,
            'current_cash': self.cash,
            'positions_market_value': positions_value,
            'total_portfolio_value': total_value,
            'total_realized_pnl': total_realized_pnl,
            'total_unrealized_pnl': total_unrealized_pnl,
            'net_profit_loss': total_value - self.initial_cash,
            'num_trades': len(self.trade_log)
        }

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取特定资产的持仓信息。"""
        if symbol in self.positions and self.positions[symbol].get('quantity', 0) > 0:
            self._update_market_values(specific_symbol=symbol) # Ensure this position is up-to-date
            return self.positions[symbol]
        return None

    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """获取所有当前持仓。"""
        self._update_market_values()
        return {sym: pos for sym, pos in self.positions.items() if pos.get('quantity', 0) > 0}

    def get_trade_log(self) -> List[Dict[str, Any]]:
        """返回交易日志。"""
        return self.trade_log

    def get_portfolio_history(self) -> List[Dict[str, Any]]:
        """返回投资组合历史价值记录。"""
        return self.portfolio_history

    def set_market_data_provider(self, provider: Any):
        """设置市场数据提供者，用于获取实时价格。"""
        self.market_data_provider = provider
        logger.info("Portfolio: Market data provider has been set.")
        self._update_market_values() # Update with new provider immediately 
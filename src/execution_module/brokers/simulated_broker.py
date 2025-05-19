import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import uuid
import pandas as pd

from .base_broker import BaseBroker

logger = logging.getLogger('app')

class SimulatedBroker(BaseBroker):
    """
    模拟券商接口实现。

    用于在没有真实券商连接的情况下测试交易逻辑。
    它会维护一个简单的内存状态来模拟账户、持仓和订单。
    支持市价单(MARKET)、限价单(LIMIT)和止损单(STOP)。
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.is_connected = False
        self.account_id = config.get('account_id', 'sim_account_001')
        self.initial_cash = config.get('initial_cash', 100000.0)
        self.cash_balance = self.initial_cash
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self.market_data_provider = None # Optional: for fetching current prices if needed
        
        # 订单队列 - 用于存储待处理的限价单(LIMIT)和止损单(STOP)
        self.pending_orders: Dict[str, Dict[str, Any]] = {}
        
        # Simulation parameters
        self.commission_per_trade = config.get('commission_per_trade', 0.0)
        self.slippage_model = config.get('slippage_model', 'none') # 'none', 'fixed', 'percentage'
        self.fixed_slippage = config.get('fixed_slippage', 0.01) # Fixed amount per share
        self.percentage_slippage = config.get('percentage_slippage', 0.0005) # 0.05%
        
        # 控制部分成交的概率 (0.0-1.0) - 默认为0，不模拟部分成交
        self.partial_fill_probability = config.get('partial_fill_probability', 0.0)
        # 部分成交的比例范围 (0.1-0.9) - 默认为0.5-0.8之间
        self.partial_fill_range = config.get('partial_fill_range', (0.5, 0.8))

        self.portfolio_ref: Optional[Any] = None # Portfolio reference for update_fill

        logger.info(f"SimulatedBroker initialized for account {self.account_id} with initial cash {self.initial_cash}")

    def set_market_data_provider(self, provider):
        self.market_data_provider = provider

    def set_portfolio_reference(self, portfolio: Any) -> None:
        """设置投资组合对象的引用，用于在成交后调用update_fill。"""
        self.portfolio_ref = portfolio
        logger.info("SimulatedBroker: Portfolio reference set.")

    def connect(self) -> bool:
        logger.info("SimulatedBroker: Connecting...")
        self.is_connected = True
        logger.info("SimulatedBroker: Connected successfully.")
        return True

    def disconnect(self) -> None:
        logger.info("SimulatedBroker: Disconnecting...")
        self.is_connected = False
        logger.info("SimulatedBroker: Disconnected.")

    def process_pending_orders(self, current_market_data: Dict[str, Dict[str, Any]]) -> None:
        """
        处理待执行的限价单和止损单。
        
        Args:
            current_market_data: 当前市场数据，格式为 {symbol: {'open': x, 'high': y, 'low': z, 'close': w}}
        """
        if not self.is_connected or not self.pending_orders:
            return
            
        orders_to_process = list(self.pending_orders.items())
        
        for order_id, order in orders_to_process:
            symbol = order.get('symbol')
            if symbol not in current_market_data:
                continue
                
            order_type = order.get('order_type', '').upper()
            action = order.get('action', '').upper()
            limit_price = order.get('price')
            stop_price = order.get('stop_price')
            
            market_data = current_market_data[symbol]
            current_price = market_data.get('close')
            
            # 检查是否满足执行条件
            should_execute = False
            
            if order_type == 'LIMIT':
                # 限价单: 买入时价格低于等于限价，卖出时价格高于等于限价
                if action == 'BUY' and current_price <= limit_price:
                    should_execute = True
                elif action == 'SELL' and current_price >= limit_price:
                    should_execute = True
            
            elif order_type == 'STOP':
                # 止损单: 买入时价格高于等于止损价，卖出时价格低于等于止损价
                if action == 'BUY' and current_price >= stop_price:
                    should_execute = True
                elif action == 'SELL' and current_price <= stop_price:
                    should_execute = True
            
            elif order_type == 'STOP_LIMIT':
                # 止损限价单: 首先检查止损触发条件，然后检查限价条件
                stop_triggered = (action == 'BUY' and current_price >= stop_price) or \
                                (action == 'SELL' and current_price <= stop_price)
                                
                if stop_triggered:
                    # 触发后转为限价单逻辑
                    if action == 'BUY' and current_price <= limit_price:
                        should_execute = True
                    elif action == 'SELL' and current_price >= limit_price:
                        should_execute = True
            
            if should_execute:
                # 执行订单
                # 从待处理队列中移除
                del self.pending_orders[order_id]
                
                # 使用当前价格执行订单
                order_copy = order.copy()
                # 覆盖价格为当前市场价格
                order_copy['price'] = current_price
                # 将订单视为市价单执行
                order_copy['order_type'] = 'MARKET'
                
                # 执行订单
                self._execute_order(order_copy)

    def _apply_slippage(self, price: float, action: str) -> float:
        """应用滑点模型计算实际成交价格"""
        if self.slippage_model == 'none':
            return price
        
        slippage_amount = 0
        if self.slippage_model == 'fixed':
            slippage_amount = self.fixed_slippage
        elif self.slippage_model == 'percentage':
            slippage_amount = price * self.percentage_slippage
        
        if action.upper() == 'BUY':
            return price + slippage_amount # Buys at a slightly higher price
        elif action.upper() == 'SELL':
            return price - slippage_amount # Sells at a slightly lower price
        return price

    def _execute_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行订单的实际处理逻辑。
        
        Args:
            order: 包含订单信息的字典。
            
        Returns:
            Dict[str, Any]: 订单执行结果。
        """
        if not self.is_connected:
            return {'status': 'failed', 'message': 'Broker not connected'}
            
        order_id = order.get('order_id', str(uuid.uuid4()))
        symbol = order.get('symbol')
        action = order.get('action', '').upper()
        quantity = float(order.get('quantity', 0))
        requested_price = order.get('price')  # 用于市价单的参考价格
        
        if not all([symbol, action, quantity > 0, requested_price is not None]):
            logger.error(f"SimulatedBroker: Invalid order fields: {order}")
            return {'status': 'failed', 'order_id': order_id, 'message': 'Invalid order fields'}
            
        # 获取执行价格 - 对于市价单，尝试获取当前市场价格或使用请求价格
        execution_price = requested_price
        if self.market_data_provider:
            try:
                current_market_info = self.market_data_provider.get_current_price(symbol)
                # 正确处理DataFrame数据类型，避免直接作为条件判断
                if isinstance(current_market_info, pd.DataFrame):
                    if not current_market_info.empty:
                        # 从DataFrame中提取价格数据
                        if 'close' in current_market_info.columns:
                            execution_price = float(current_market_info['close'].iloc[0])
                        elif 'price' in current_market_info.columns:
                            execution_price = float(current_market_info['price'].iloc[0])
                        else:
                            logger.warning(f"SimulatedBroker: DataFrame for {symbol} does not contain price data. Using requested price.")
                    else:
                        logger.warning(f"SimulatedBroker: Empty DataFrame returned for {symbol}. Using requested price.")
                # 处理字典类型返回值
                elif isinstance(current_market_info, dict):
                    if current_market_info.get('close') is not None:
                        execution_price = float(current_market_info['close'])
                    elif current_market_info.get('price') is not None:
                        execution_price = float(current_market_info['price'])
                    else:
                        logger.warning(f"SimulatedBroker: Market data for {symbol} does not contain price data. Using requested price.")
                else:
                    logger.warning(f"SimulatedBroker: Unexpected return type from get_current_price: {type(current_market_info)}. Using requested price.")
            except Exception as e:
                logger.warning(f"SimulatedBroker: Could not fetch market price for {symbol}, using requested. Error: {str(e)}")
                
        # 应用滑点
        filled_price = self._apply_slippage(execution_price, action)
        
        # 计算订单价值和总成本
        order_value = quantity * filled_price
        total_cost = order_value + self.commission_per_trade
        
        # 更新订单状态
        if order_id not in self.orders:
            self.orders[order_id] = {
                **order,
                'order_id': order_id,
                'status': 'pending_execution',
                'timestamp': datetime.now().isoformat()
            }
            
        # 处理买入订单
        if action == 'BUY':
            if self.cash_balance >= total_cost:
                self.cash_balance -= total_cost
                
                # 更新持仓
                if symbol not in self.positions:
                    self.positions[symbol] = {'quantity': 0, 'avg_price': 0.0, 'market_value': 0, 'unrealized_pnl': 0}
                
                current_qty = self.positions[symbol]['quantity']
                current_avg_price = self.positions[symbol]['avg_price']
                
                new_total_value = (current_qty * current_avg_price) + (quantity * filled_price)
                new_total_qty = current_qty + quantity
                self.positions[symbol]['avg_price'] = new_total_value / new_total_qty if new_total_qty > 0 else 0
                self.positions[symbol]['quantity'] = new_total_qty
                
                status = 'filled'
                message = f'BUY order for {quantity} {symbol} @ {filled_price:.2f} filled.'
                logger.info(f"SimulatedBroker: {message}")
            else:
                status = 'rejected'
                message = 'Insufficient cash'
                logger.warning(f"SimulatedBroker: BUY order rejected - {message}. Order: {order}")
                
        # 处理卖出订单
        elif action == 'SELL':
            if symbol in self.positions and self.positions[symbol]['quantity'] >= quantity:
                self.cash_balance += order_value - self.commission_per_trade
                
                self.positions[symbol]['quantity'] -= quantity
                if self.positions[symbol]['quantity'] == 0:
                    # 数量为0时重置平均价格
                    self.positions[symbol]['avg_price'] = 0 
                
                status = 'filled'
                message = f'SELL order for {quantity} {symbol} @ {filled_price:.2f} filled.'
                logger.info(f"SimulatedBroker: {message}")
            else:
                status = 'rejected'
                message = 'Insufficient position'
                logger.warning(f"SimulatedBroker: SELL order rejected - {message}. Order: {order}")
        else:
            status = 'failed'
            message = 'Invalid action'
            logger.error(f"SimulatedBroker: Invalid action in order: {action}")
            
        # 更新订单状态
        self.orders[order_id].update({
            'status': status,
            'filled_quantity': quantity if status == 'filled' else 0,
            'avg_fill_price': filled_price if status == 'filled' else None,
            'message': message,
            'executed_timestamp': datetime.now().isoformat()
        })
        
        # 处理成交事件
        if status == 'filled':
            self.trade_history.append(self.orders[order_id])
            # 如果设置了portfolio引用，调用其update_fill方法
            if self.portfolio_ref:
                fill_event = {
                    'timestamp': self.orders[order_id].get('executed_timestamp', datetime.now().isoformat()),
                    'symbol': symbol,
                    'action': action,
                    'quantity': quantity,
                    'price': filled_price,
                    'commission': self.commission_per_trade,
                    'order_id': order_id
                }
                try:
                    self.portfolio_ref.update_fill(fill_event)
                    logger.info(f"SimulatedBroker: Called portfolio.update_fill for order {order_id}")
                except Exception as e:
                    logger.error(f"SimulatedBroker: Error calling portfolio.update_fill for order {order_id}: {e}", exc_info=True)
            else:
                logger.warning(f"SimulatedBroker: Portfolio reference not set. Cannot call update_fill for order {order_id}.")
                
        return {
            'status': status,
            'order_id': order_id,
            'message': message,
            'filled_quantity': quantity if status == 'filled' else 0,
            'filled_price': filled_price if status == 'filled' else None
        }

    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        下单。支持市价单(MARKET)、限价单(LIMIT)、止损单(STOP)和止损限价单(STOP_LIMIT)。
        
        Args:
            order: 订单信息字典，包含以下字段：
                - symbol: 交易标的代码
                - action: 交易动作，'BUY'或'SELL'
                - quantity: 交易数量
                - order_type: 订单类型，'MARKET'、'LIMIT'、'STOP'或'STOP_LIMIT'
                - price: 限价单的限价或市价单的参考价格
                - stop_price: (仅止损单和止损限价单) 触发价格
                
        Returns:
            Dict[str, Any]: 订单处理结果
        """
        if not self.is_connected:
            return {'status': 'failed', 'message': 'Broker not connected'}
            
        order_id = str(uuid.uuid4())
        symbol = order.get('symbol')
        action = order.get('action', '').upper()
        quantity = float(order.get('quantity', 0))
        order_type = order.get('order_type', 'MARKET').upper()
        price = order.get('price')  # 限价或市价单的参考价格
        stop_price = order.get('stop_price')  # 止损单的触发价格
        
        # 基本验证
        if not all([symbol, action in ['BUY', 'SELL'], quantity > 0]):
            logger.error(f"SimulatedBroker: Invalid order basic fields: {order}")
            return {'status': 'failed', 'order_id': order_id, 'message': 'Invalid order fields'}
            
        # 验证订单类型特定的字段
        if order_type in ['LIMIT', 'STOP_LIMIT'] and price is None:
            logger.error(f"SimulatedBroker: Missing price for {order_type} order: {order}")
            return {'status': 'failed', 'order_id': order_id, 'message': f'Missing price for {order_type} order'}
            
        if order_type in ['STOP', 'STOP_LIMIT'] and stop_price is None:
            logger.error(f"SimulatedBroker: Missing stop_price for {order_type} order: {order}")
            return {'status': 'failed', 'order_id': order_id, 'message': f'Missing stop_price for {order_type} order'}
            
        # 添加order_id到订单中
        order_with_id = {**order, 'order_id': order_id}
        
        # 根据订单类型处理
        if order_type == 'MARKET':
            # 市价单立即执行
            return self._execute_order(order_with_id)
        else:
            # 条件单(LIMIT/STOP/STOP_LIMIT)加入待处理队列
            self.orders[order_id] = {
                **order_with_id,
                'status': 'pending',
                'timestamp': datetime.now().isoformat(),
                'message': f'{order_type} order pending execution'
            }
            
            self.pending_orders[order_id] = order_with_id
            logger.info(f"SimulatedBroker: {order_type} order {order_id} for {symbol} placed, waiting for execution condition.")
            
            return {
                'status': 'pending',
                'order_id': order_id,
                'message': f'{order_type} order accepted and pending execution'
            }

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        取消订单。
        
        支持取消待处理的限价单、止损单和止损限价单。
        已成交、已拒绝和已取消的订单无法再次取消。
        
        Args:
            order_id: 订单ID
            
        Returns:
            Dict[str, Any]: 取消结果
        """
        if order_id in self.orders:
            order_info = self.orders[order_id]
            # 只有未成交的订单才能取消
            if order_info['status'] not in ['filled', 'rejected', 'cancelled', 'failed']:
                # 如果是待处理的条件单，从待处理队列中移除
                if order_id in self.pending_orders:
                    del self.pending_orders[order_id]
                
                order_info['status'] = 'cancelled'
                order_info['message'] = 'Order cancelled by user.'
                logger.info(f"SimulatedBroker: Order {order_id} cancelled.")
                return {'status': 'cancelled', 'message': 'Order cancelled successfully.'}
            else:
                logger.warning(f"SimulatedBroker: Order {order_id} cannot be cancelled, status is {order_info['status']}.")
                return {'status': 'failed', 'message': f'Order cannot be cancelled (status: {order_info["status"]}).'}
        return {'status': 'failed', 'message': 'Order ID not found'}

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        if order_id in self.orders:
            return self.orders[order_id]
        return {'status': 'not_found', 'message': 'Order ID not found'}

    def get_account_summary(self) -> Dict[str, Any]:
        if not self.is_connected:
            return {'error': 'Broker not connected'}
        
        open_positions_value = sum(
            pos.get('quantity', 0) * (self.market_data_provider.get_current_price(sym)['close'] if self.market_data_provider and self.market_data_provider.get_current_price(sym) else pos.get('avg_price',0) ) 
            for sym, pos in self.positions.items() if pos.get('quantity', 0) > 0
        )

        return {
            'account_id': self.account_id,
            'total_equity': self.cash_balance + open_positions_value,
            'cash_balance': self.cash_balance,
            'buying_power': self.cash_balance,  # Simplified, real brokers have margin rules
            'open_positions_value': open_positions_value
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        
        current_positions_list = []
        for symbol, pos_data in self.positions.items():
            if pos_data.get('quantity', 0) > 0:
                current_price = pos_data.get('avg_price') # Default to avg_price if no market data
                if self.market_data_provider:
                    try:
                         market_info = self.market_data_provider.get_current_price(symbol)
                         if market_info and market_info.get('close'):
                             current_price = market_info.get('close')
                    except Exception:
                        pass # Keep default
                
                market_value = pos_data['quantity'] * current_price
                unrealized_pnl = (current_price - pos_data['avg_price']) * pos_data['quantity']
                
                current_positions_list.append({
                    'symbol': symbol,
                    'quantity': pos_data['quantity'],
                    'avg_price': pos_data['avg_price'],
                    'current_price': current_price,
                    'market_value': market_value,
                    'unrealized_pnl': unrealized_pnl
                })
        return current_positions_list

    # Example usage for testing:
    # if __name__ == '__main__':
    #     sim_broker = SimulatedBroker(config={'initial_cash': 50000, 'commission_per_trade': 1.0})
    #     sim_broker.connect()
        
    #     # Mock market data provider for testing get_account_summary and get_positions
    #     class MockDataProvider:
    #         def get_current_price(self, symbol):
    #             if symbol == 'AAPL': return {'close': 155.0}
    #             if symbol == 'GOOG': return {'close': 2550.0}
    #             return None
    #     sim_broker.set_market_data_provider(MockDataProvider())

    #     # Mock portfolio for testing update_fill
    #     class MockPortfolio:
    #         def update_fill(self, fill_event):
    #             print(f"Portfolio update_fill called with: {fill_event}")
    #     sim_broker.set_portfolio_reference(MockPortfolio())
        
    #     print("Initial Account Summary:", sim_broker.get_account_summary())
        
    #     buy_order1 = sim_broker.place_order({'symbol': 'AAPL', 'action': 'BUY', 'quantity': 10, 'order_type': 'MARKET', 'price': 150.0})
    #     print("Buy Order 1:", buy_order1)
    #     print("Account Summary after buy 1:", sim_broker.get_account_summary())
    #     print("Positions:", sim_broker.get_positions())

    #     buy_order2 = sim_broker.place_order({'symbol': 'AAPL', 'action': 'BUY', 'quantity': 5, 'order_type': 'MARKET', 'price': 152.0})
    #     print("Buy Order 2:", buy_order2)
    #     print("Account Summary after buy 2:", sim_broker.get_account_summary())
    #     print("Positions:", sim_broker.get_positions())

    #     sell_order1 = sim_broker.place_order({'symbol': 'AAPL', 'action': 'SELL', 'quantity': 8, 'order_type': 'MARKET', 'price': 155.0})
    #     print("Sell Order 1:", sell_order1)
    #     print("Account Summary after sell 1:", sim_broker.get_account_summary())
    #     print("Positions:", sim_broker.get_positions())
        
    #     print("Order status for buy_order1:", sim_broker.get_order_status(buy_order1['order_id']))
        
    #     sim_broker.disconnect() 
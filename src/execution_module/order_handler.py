import logging
from typing import Dict, Any, Optional, List

from .brokers.base_broker import BaseBroker
from src.risk_module.base_risk_manager import BaseRiskManager # 修改为绝对导入
from src.portfolio_module.portfolio import Portfolio # 修改为绝对导入

logger = logging.getLogger('app')

class OrderHandler:
    """
    订单处理器。

    负责接收策略生成的交易信号，通过风险管理器进行验证和调整，
    然后通过券商接口执行订单，并更新投资组合状态。
    """

    def __init__(self, 
                 broker_client: BaseBroker, 
                 risk_manager: Optional[BaseRiskManager] = None,
                 portfolio: Optional[Portfolio] = None):
        """
        初始化订单处理器。

        Args:
            broker_client: 券商客户端实例。
            risk_manager: 风险管理器实例 (可选)。
            portfolio: 投资组合实例 (可选, 用于风险管理和状态更新)。
        """
        self.broker_client = broker_client
        self.risk_manager = risk_manager
        self.portfolio = portfolio # The strategy should update the portfolio based on fills
        
        if not self.broker_client.is_connected:
            logger.info("OrderHandler: Broker client not connected. Attempting to connect.")
            if not self.broker_client.connect():
                 logger.error("OrderHandler: Failed to connect to broker. Order execution will fail.")
            else:
                logger.info("OrderHandler: Successfully connected to broker.")

    def process_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理交易信号并尝试执行订单。

        Args:
            signal: 交易信号字典 from the strategy, e.g., 
                    {'action': 'BUY', 'symbol': 'AAPL', 'quantity': 10, 'price': 150.0, 
                     'order_type': 'LIMIT', 'reason': 'Strategy signal'}

        Returns:
            执行结果字典, 包含订单状态、ID和消息。
        """
        logger.info(f"OrderHandler received signal: {signal}")

        if not signal or signal.get('action', '').upper() == 'HOLD':
            logger.info("OrderHandler: Signal is HOLD or invalid. No action taken.")
            return {"status": "ignored", "message": "Signal was HOLD or invalid."}

        order_to_place = signal.copy() # Start with the original signal as the base for the order

        # 1. (Optional) Risk Management Validation & Adjustment
        if self.risk_manager and self.portfolio:
            portfolio_summary = self.portfolio.get_summary() # Portfolio needs get_summary()
            # position_state requires getting specific position from portfolio
            current_position = self.portfolio.get_position(signal.get('symbol')) 
            
            is_valid, reason = self.risk_manager.validate_signal(order_to_place, portfolio_summary, current_position)
            if not is_valid:
                logger.warning(f"OrderHandler: Signal for {signal.get('symbol')} failed risk validation: {reason}")
                return {"status": "rejected_risk", "message": reason, "original_signal": signal}
            
            # Adjust order size based on risk rules
            # The strategy might have already sized it, but risk manager can fine-tune or cap it.
            adjusted_order = self.risk_manager.adjust_order_size(order_to_place, portfolio_summary, current_position)
            if adjusted_order.get('quantity', 0) <= 0 and adjusted_order.get('action') != 'HOLD':
                 logger.warning(f"OrderHandler: Order for {signal.get('symbol')} quantity adjusted to 0 by risk manager. Reason: {adjusted_order.get('reason')}")
                 return {"status": "rejected_risk_adjusted_to_zero", "message": adjusted_order.get('reason', "Quantity zero after risk adjustment"), "original_signal": signal}
            order_to_place = adjusted_order
            logger.info(f"OrderHandler: Signal for {signal.get('symbol')} passed risk validation. Adjusted order: {order_to_place}")
        else:
            logger.info("OrderHandler: No risk manager or portfolio provided, proceeding with original signal.")

        # 2. Ensure essential order fields for broker
        if 'order_type' not in order_to_place:
            order_to_place['order_type'] = 'MARKET' # Default to MARKET if not specified
            logger.debug(f"OrderHandler: Defaulting order_type to MARKET for {order_to_place.get('symbol')}")
        
        if order_to_place['order_type'].upper() == 'LIMIT' and not order_to_place.get('price'):
            logger.error(f"OrderHandler: LIMIT order for {order_to_place.get('symbol')} missing price.")
            return {"status": "failed", "message": "LIMIT order missing price", "order": order_to_place}
        elif order_to_place['order_type'].upper() == 'MARKET' and not order_to_place.get('price'):
            # For market orders, price in signal might be a reference. Broker will use market price.
            # Some brokers might not need a price for MARKET orders, others might use it as a cap (not handled here).
            logger.debug(f"OrderHandler: MARKET order for {order_to_place.get('symbol')} - price field in signal is {order_to_place.get('price')}, actual execution price by broker.")


        # 3. Place order via Broker Client
        try:
            logger.info(f"OrderHandler: Placing order with broker: {order_to_place}")
            execution_result = self.broker_client.place_order(order_to_place)
            logger.info(f"OrderHandler: Broker execution result for {order_to_place.get('symbol')}: {execution_result}")
            
            # 4. (Simplified) Update portfolio based on fills - THIS SHOULD IDEALLY BE EVENT DRIVEN FROM BROKER
            # For simulation, we can assume immediate fill for market orders if status is good.
            # The strategy itself is already updating its internal current_positions and trade_history.
            # The Portfolio object, if used by OrderHandler, should be updated based on actual fills from broker events.
            # Here, we just return the broker's response.
            
            return execution_result
            
        except Exception as e:
            logger.error(f"OrderHandler: Error placing order for {order_to_place.get('symbol')}: {str(e)}", exc_info=True)
            return {"status": "failed", "message": f"Exception during order placement: {str(e)}", "order": order_to_place}

    def check_order_status(self, order_id: str) -> Dict[str, Any]:
        """Delegates to broker client to get order status."""
        return self.broker_client.get_order_status(order_id)

    def cancel_trade_order(self, order_id: str) -> Dict[str, Any]:
        """Delegates to broker client to cancel an order."""
        return self.broker_client.cancel_order(order_id)

    def get_broker_account_summary(self) -> Dict[str, Any]:
        """Delegates to broker client to get account summary."""
        return self.broker_client.get_account_summary()

    def get_broker_positions(self) -> List[Dict[str, Any]]:
        """Delegates to broker client to get current positions."""
        return self.broker_client.get_positions() 
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

class BaseBroker(ABC):
    """
    交易执行模块中券商接口的基类。

    定义了与券商进行交互（如获取账户信息、下单、查询订单状态等）的标准接口。
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化券商客户端。

        Args:
            config: 券商相关配置 (e.g., API密钥, 账户ID, 终端地址等)。
        """
        self.config = config
        self.client = None # Placeholder for the actual broker API client library

    @abstractmethod
    def connect(self) -> bool:
        """
        连接到券商服务。

        Returns:
            True如果连接成功，否则False。
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """
        断开与券商服务的连接。
        """
        pass

    @abstractmethod
    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        向券商提交订单。

        Args:
            order: 订单字典, e.g., {
                'symbol': 'AAPL', 
                'action': 'BUY'/'SELL', 
                'quantity': 100, 
                'order_type': 'LIMIT'/'MARKET', 
                'price': 150.00 (for LIMIT orders),
                'time_in_force': 'DAY'/'GTC' (可选)
            }

        Returns:
            订单提交结果, e.g., {
                'status': 'submitted'/'failed'/'pending',
                'order_id': 'broker_order_id_123',
                'message': '订单已提交' / '错误信息'
            }
            如果成功，应包含券商返回的订单ID。
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        取消一个未执行或部分执行的订单。

        Args:
            order_id: 要取消的订单的券商ID。

        Returns:
            取消结果, e.g., {'status': 'cancelled'/'failed', 'message': '...'}
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        查询订单的当前状态。

        Args:
            order_id: 订单的券商ID。

        Returns:
            订单状态信息, e.g., {
                'order_id': 'broker_order_id_123',
                'status': 'filled'/'partially_filled'/'pending'/'cancelled'/'rejected',
                'filled_quantity': 50,
                'avg_fill_price': 150.10,
                'remaining_quantity': 50,
                'timestamp': 'YYYY-MM-DDTHH:MM:SSZ'
            }
        """
        pass

    @abstractmethod
    def get_account_summary(self) -> Dict[str, Any]:
        """
        获取账户摘要信息。

        Returns:
            账户摘要, e.g., {
                'account_id': '12345',
                'total_equity': 100000.00,
                'cash_balance': 50000.00,
                'buying_power': 200000.00,
                'open_positions_value': 50000.00
            }
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        获取当前持仓列表。

        Returns:
            持仓列表, e.g., [
                {
                    'symbol': 'AAPL', 
                    'quantity': 100, 
                    'avg_price': 145.00, 
                    'current_price': 150.00, 
                    'market_value': 15000.00,
                    'unrealized_pnl': 500.00
                }
            ]
        """
        pass

    def health_check(self) -> Dict[str, Any]:
        """
        检查券商连接和服务的健康状况。
        默认实现为简单调用 connect 后断开。
        """
        try:
            if self.connect():
                self.disconnect()
                return {"status": "ok", "message": "Broker connection successful."}
            else:
                return {"status": "error", "message": "Broker connection failed."}
        except Exception as e:
            return {"status": "error", "message": f"Broker health check failed: {str(e)}"} 
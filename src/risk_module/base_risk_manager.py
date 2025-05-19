from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional

class BaseRiskManager(ABC):
    """
    风险管理模块基类

    定义了风险管理模块应遵循的接口。
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化风险管理器。

        Args:
            config: 风险管理相关配置。
        """
        self.config = config

    def update_portfolio_state(self, portfolio_state: Dict[str, Any]):
        """
        可选方法，用于让风险管理器更新其内部关于投资组合状态的视图。
        例如，更新当前总资本、已实现盈亏等，用于更复杂的风险计算如回撤。

        Args:
            portfolio_state: 最新的投资组合状态字典。
        """
        # Base implementation can be a pass, concrete classes can override.
        pass

    @abstractmethod
    def validate_signal(self, 
                        signal: Dict[str, Any], 
                        portfolio_state: Optional[Dict[str, Any]], 
                        position_state: Optional[Dict[str, Any]]
                       ) -> Tuple[bool, str]:
        """
        验证交易信号是否符合风险规定。

        Args:
            signal: 交易信号字典 (e.g., {'action': 'BUY', 'symbol': 'AAPL', 'quantity': 100, 'price': 150.0}).
            portfolio_state: 当前投资组合状态 (e.g., {'total_value': 100000, 'cash': 50000}).
            position_state: 该资产的当前持仓状态 (e.g., {'quantity': 200, 'avg_price': 140.0}).

        Returns:
            一个元组 (is_valid, reason)。is_valid为True表示信号通过验证，reason为验证结果说明。
        """
        pass

    @abstractmethod
    def calculate_max_position_size(self, 
                                    symbol: str, 
                                    current_price: float, 
                                    portfolio_state: Dict[str, Any],
                                    volatility: Optional[float] = None,
                                    confidence: Optional[float] = None
                                   ) -> float:
        """
        计算给定资产允许的最大持仓规模（金额或股数）。

        Args:
            symbol: 资产代码。
            current_price: 当前价格。
            portfolio_state: 当前投资组合状态。
            volatility: 资产波动率 (可选)。
            confidence: 交易信号置信度 (可选)。

        Returns:
            允许的最大持仓金额或数量。
        """
        pass

    @abstractmethod
    def adjust_order_size(self, 
                          original_order: Dict[str, Any], 
                          portfolio_state: Dict[str, Any],
                          position_state: Optional[Dict[str, Any]]
                         ) -> Dict[str, Any]:
        """
        根据风险规则调整订单大小。

        Args:
            original_order: 原始订单请求。
            portfolio_state: 当前投资组合状态。
            position_state: 该资产的当前持仓状态。

        Returns:
            调整后的订单。
        """
        pass

    def get_risk_assessment(self, symbol: str, portfolio_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取特定资产或整个投资组合的风险评估。
        （可选实现，具体内容根据风险模型定义）

        Args:
            symbol: 资产代码 (如果为None，则评估整个投资组合)。
            portfolio_state: 当前投资组合状态。

        Returns:
            风险评估结果字典。
        """
        return {"message": "Risk assessment not implemented in base class."} 
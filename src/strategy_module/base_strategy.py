"""
交易策略基类，定义了所有策略的通用接口和基础功能。
"""

from abc import ABC, abstractmethod
from datetime import datetime
import logging
from typing import Dict, Any, List, Optional, Union

# 获取logger
logger = logging.getLogger('app')

class BaseStrategy(ABC):
    """
    所有交易策略的抽象基类。
    
    定义了策略的基本接口和通用功能，包括数据处理、信号生成、交易执行等。
    具体策略通过继承此类并实现相应的抽象方法来定义特定的交易逻辑。
    """
    
    def __init__(
        self, 
        config: Dict[str, Any], 
        data_provider: Any, 
        llm_client: Any = None,
        broker_client: Any = None,
        risk_manager: Any = None,
        portfolio: Any = None
    ):
        """
        初始化策略基类
        
        Args:
            config: 策略配置参数
            data_provider: 数据提供者实例，用于获取市场数据
            llm_client: 大语言模型客户端，用于生成分析和信号（可选）
            broker_client: 券商接口客户端，用于执行交易（可选）
            risk_manager: 风险管理器，用于评估和控制风险（可选）
            portfolio: 投资组合对象，用于管理持仓和交易（可选）
        """
        self.config = config
        self.data_provider = data_provider
        self.llm_client = llm_client
        self.broker_client = broker_client
        self.risk_manager = risk_manager
        self.portfolio = portfolio
        
        # 策略参数，可通过load_parameters加载或更新
        self.parameters = {}
        
        # 当前持仓信息
        self.current_positions = {}
        
        # 策略组合（可能是Portfolio类的实例）
        self.portfolio = None
        
        # 策略的历史交易记录
        self.trade_history = []
        
        # 策略性能指标
        self.performance_metrics = {}
        
        # 初始化完成后记录日志
        logger.info(f"策略 {self.__class__.__name__} 已初始化")

    def load_parameters(self, params: Dict[str, Any]) -> None:
        """
        加载或更新策略参数
        
        Args:
            params: 策略参数字典
        """
        self.parameters.update(params)
        logger.info(f"策略 {self.__class__.__name__} 参数已加载: {self.parameters}")

    @abstractmethod
    def on_data(self, data_event: Dict[str, Any]) -> None:
        """
        处理新的市场数据事件
        
        当新的市场数据可用时被调用，用于更新策略状态并可能生成新的交易信号。
        
        Args:
            data_event: 市场数据事件，包含时间戳、价格、成交量等信息
        """
        raise NotImplementedError("子类必须实现on_data方法")

    @abstractmethod
    def generate_signals(self, market_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        基于市场数据和分析生成交易信号
        
        Args:
            market_data: 市场数据，如价格和成交量数据
            **kwargs: 其他可能的参数，如技术分析结果
            
        Returns:
            交易信号字典，包含操作类型、目标资产、数量等信息
        """
        raise NotImplementedError("子类必须实现generate_signals方法")

    @abstractmethod
    def execute_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行交易信号
        
        Args:
            signal: 交易信号字典
            
        Returns:
            执行结果，包含订单状态、成交信息等
        """
        raise NotImplementedError("子类必须实现execute_signal方法")
    
    def update_position(self, trade_info: Dict[str, Any]) -> None:
        """
        根据成交信息更新持仓状态
        
        Args:
            trade_info: 成交信息，包含资产、数量、价格等
        """
        symbol = trade_info.get('symbol')
        if not symbol:
            logger.warning("更新持仓失败: 交易信息中没有symbol字段")
            return
            
        action = trade_info.get('action', '').upper()
        quantity = trade_info.get('quantity', 0)
        price = trade_info.get('price', 0)
        
        if symbol not in self.current_positions:
            self.current_positions[symbol] = {
                'quantity': 0,
                'avg_price': 0,
                'last_update': datetime.now().isoformat(),
                'trades': []
            }
        
        position = self.current_positions[symbol]
        
        if action == 'BUY':
            # 计算新的平均价格
            total_cost = position['quantity'] * position['avg_price'] + quantity * price
            new_quantity = position['quantity'] + quantity
            
            if new_quantity > 0:
                position['avg_price'] = total_cost / new_quantity
            position['quantity'] = new_quantity
            
        elif action == 'SELL':
            position['quantity'] -= quantity
            
            # 如果全部卖出，重置平均价格
            if position['quantity'] <= 0:
                position['quantity'] = 0
                position['avg_price'] = 0
                
        # 记录交易
        trade_record = {**trade_info, 'timestamp': datetime.now().isoformat()}
        position['trades'].append(trade_record)
        self.trade_history.append(trade_record)
        
        # 更新最后更新时间
        position['last_update'] = datetime.now().isoformat()
        
        logger.info(f"持仓已更新: {symbol} - 数量: {position['quantity']}, 均价: {position['avg_price']}")
    
    def run_backtest(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        运行策略回测
        
        Args:
            symbol: 回测资产代码
            start_date: 回测开始日期
            end_date: 回测结束日期
            parameters: 回测参数，可选
            
        Returns:
            回测结果，包含性能指标、交易记录等
        """
        logger.info(f"开始回测 {self.__class__.__name__} 策略 - 资产: {symbol}, 时间范围: {start_date} 至 {end_date}")
        
        # 加载回测参数
        if parameters:
            self.load_parameters(parameters)
        
        # 这里通常会涉及回测引擎
        # 具体实现可能需要根据项目的回测模块来定义
        
        return {"status": "未实现", "message": "回测功能需要与回测引擎集成"}

    def run_live(self, parameters: Optional[Dict[str, Any]] = None) -> None:
        """
        运行实时交易
        
        Args:
            parameters: 实时交易参数，可选
        """
        logger.info(f"开始实时交易 {self.__class__.__name__} 策略")
        
        # 加载实时交易参数
        if parameters:
            self.load_parameters(parameters)
        
        # 这里通常会涉及连接实时数据源和交易接口
        # 具体实现取决于项目的实时交易基础设施
        
        logger.warning("实时交易功能未完全实现，需要与实时数据源和交易接口集成")

    def set_broker_client(self, broker_client: Any) -> None:
        """设置券商客户端。"""
        self.broker_client = broker_client
        logger.info(f"{self.__class__.__name__}: Broker client set.")

    def set_portfolio_object(self, portfolio: Any) -> None:
        """设置投资组合对象。"""
        self.portfolio = portfolio
        # Update current_positions based on portfolio if it has them
        if self.portfolio:
            current_broker_positions = self.portfolio.get_all_positions()
            # Sync strategy's view of positions if portfolio is the source of truth at start
            # This is a simple sync; more complex logic might be needed
            # For now, assume strategy manages its own current_positions during run,
            # but can be initialized from portfolio.
            # self.current_positions = { # Reformat if necessary
            #    sym: {'quantity': data['quantity'], 'avg_price': data['avg_price']}
            #    for sym, data in current_broker_positions.items()
            # }
            logger.info(f"{self.__class__.__name__}: Portfolio object set. Current positions potentially synced.")
        else:
            logger.warning(f"{self.__class__.__name__}: Portfolio object set to None.")

    def set_risk_manager(self, risk_manager: Any) -> None:
        """设置风险管理对象。"""
        self.risk_manager = risk_manager
        logger.info(f"{self.__class__.__name__}: Risk manager set.") 
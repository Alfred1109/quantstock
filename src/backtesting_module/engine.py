import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from src.data_module.providers.base_provider import BaseDataProvider
from src.strategy_module.base_strategy import BaseStrategy
from src.portfolio_module.portfolio import Portfolio
from src.portfolio_module.performance import PerformanceCalculator
from src.execution_module.brokers.simulated_broker import SimulatedBroker
from src.execution_module.order_handler import OrderHandler
from src.risk_module.base_risk_manager import BaseRiskManager


logger = logging.getLogger('app')

class BacktestingEngine:
    """
    回测引擎，负责协调整个回测流程。
    """

    def __init__(self,
                 start_date: datetime,
                 end_date: datetime,
                 data_provider: BaseDataProvider,
                 strategy: BaseStrategy,
                 portfolio: Portfolio,
                 broker: SimulatedBroker,
                 order_handler: OrderHandler,
                 initial_capital: float,
                 risk_manager: Optional[BaseRiskManager] = None):
        """
        初始化回测引擎。

        Args:
            start_date: 回测开始日期。
            end_date: 回测结束日期。
            data_provider: 数据提供者实例。
            strategy: 策略实例。
            portfolio: 投资组合实例。
            broker: 模拟券商实例。
            order_handler: 订单处理器实例。
            initial_capital: 初始资金。
            risk_manager: (可选) 风险管理器实例。
        """
        self.start_date = start_date
        self.end_date = end_date
        self.data_provider = data_provider
        self.strategy = strategy
        self.portfolio = portfolio
        self.broker = broker # The strategy and order_handler will use this
        self.order_handler = order_handler # The strategy will generate signals, order_handler processes them
        self.initial_capital = initial_capital
        self.risk_manager = risk_manager # The order_handler or strategy might use this

        # Link components if not already linked
        self.strategy.set_broker_client(self.broker)
        self.strategy.set_portfolio_object(self.portfolio) # Strategy needs to update its state from portfolio
        if self.risk_manager:
            self.strategy.set_risk_manager(self.risk_manager) # If strategy directly uses risk manager
            # OrderHandler is already initialized with risk_manager if provided

        self.portfolio.set_market_data_provider(self.data_provider) # For portfolio to update MTM
        self.broker.set_market_data_provider(self.data_provider) # For simulated broker to get prices


        self.event_queue = [] # For a more advanced event-driven backtester
        self.current_datetime: Optional[datetime] = None
        self.data_stream: Optional[List[Dict[str, Any]]] = None # To store pre-fetched data
        self.results: Optional[Dict[str, Any]] = None

        logger.info(f"BacktestingEngine initialized for period: {start_date} to {end_date}")

    def _prepare_data(self, symbols: List[str], timeframe: str = '1d') -> None:
        """
        准备回测所需的数据。
        获取指定时间范围和资产列表的历史数据。
        """
        logger.info(f"Preparing data for symbols: {symbols} from {self.start_date} to {self.end_date}")
        # This is a simplified data preparation.
        # A more robust engine might fetch data for each symbol and interleave it,
        # or use a generator to yield data points chronologically.
        
        # For now, let's assume data_provider can give us a combined stream or we fetch per symbol
        # and then sort by date.
        
        all_data = []
        for symbol in symbols:
            # Assuming data_provider has a method like get_historical_data_for_backtest
            # which returns a list of data points (dicts) for that symbol in the date range.
            # Each dict should have 'timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume'.
            try:
                # 检查data_provider.get_historical_data方法是否接受timeframe参数
                import inspect
                params = inspect.signature(self.data_provider.get_historical_data).parameters
                
                # 准备调用参数
                kwargs = {
                    "symbol": symbol,
                    "start_date": self.start_date.strftime('%Y-%m-%d'),
                    "end_date": self.end_date.strftime('%Y-%m-%d'),
                }
                
                # 只有当方法接受timeframe参数时，才传入该参数
                if 'timeframe' in params:
                    kwargs['timeframe'] = timeframe
                # 如果方法接受period参数，可能需要将timeframe映射到period
                elif 'period' in params:
                    # 简单映射timeframe到period
                    period_map = {
                        '1d': 'daily',
                        '1w': 'weekly',
                        '1mo': 'monthly'
                    }
                    kwargs['period'] = period_map.get(timeframe, 'daily')
                
                symbol_data = self.data_provider.get_historical_data(**kwargs)
                
                if not symbol_data.empty:
                    # Convert DataFrame to list of dictionaries
                    symbol_data_list = symbol_data.to_dict('records')
                    
                    # Ensure data has symbol and timestamp in correct format
                    for dp in symbol_data_list:
                        dp['symbol'] = symbol # Ensure symbol is in each data point
                        if 'date' in dp and 'timestamp' not in dp:
                            # Convert 'date' field to 'timestamp' if needed
                            dp['timestamp'] = dp['date']
                            
                        if isinstance(dp.get('timestamp'), str):
                             dp['timestamp'] = datetime.fromisoformat(dp['timestamp'].replace('Z', '+00:00'))
                        elif not isinstance(dp.get('timestamp'), datetime):
                            # Try to parse if it's a common format, or log error
                            logger.warning(f"Timestamp for {symbol} is not datetime object: {dp.get('timestamp')}")
                            # Attempt to handle common string formats or skip
                            try:
                                dp['timestamp'] = datetime.strptime(str(dp.get('timestamp')), "%Y-%m-%d %H:%M:%S") # common example
                            except:
                                logger.error(f"Could not parse timestamp for {dp}, skipping data point.")
                                continue # Skip this data point

                    all_data.extend(symbol_data_list)
                else:
                    logger.warning(f"No data found for symbol {symbol} in the given date range.")
            except Exception as e:
                logger.error(f"Error fetching data for symbol {symbol}: {str(e)}", exc_info=True)

        # Sort all data points by timestamp
        self.data_stream = sorted(all_data, key=lambda x: x['timestamp'])
        if not self.data_stream:
            logger.error("No data loaded for backtest after attempting all symbols.")
            raise ValueError("Failed to load any data for the backtest period.")
        logger.info(f"Data preparation complete. Total data points: {len(self.data_stream)}")


    def run_backtest(self, symbols: List[str], strategy_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行回测。

        Args:
            symbols: 需要回测的资产代码列表。
            strategy_params: (可选) 传递给策略的参数。
        """
        logger.info("Starting backtest run...")
        if strategy_params:
            self.strategy.load_parameters(strategy_params) # Allow strategy to reconfigure

        self._prepare_data(symbols) # Fetch and sort all data upfront

        if not self.data_stream:
            logger.error("Backtest cannot run: Data stream is empty after preparation.")
            return {"error": "No data to process for backtest."}

        # Initialize portfolio with initial capital before simulation loop
        self.portfolio = Portfolio(initial_cash=self.initial_capital, market_data_provider=self.data_provider)
        # Re-link because portfolio was recreated
        self.strategy.set_portfolio_object(self.portfolio)
        self.order_handler.portfolio = self.portfolio # Ensure order_handler also has the new portfolio


        logger.info(f"Simulating data stream with {len(self.data_stream)} events...")
        # 用于保存每个数据点的当前价格，以便处理条件单
        current_market_data = {}
        
        for data_event in self.data_stream:
            self.current_datetime = data_event['timestamp']
            if self.current_datetime > self.end_date:
                logger.info(f"Reached end date {self.end_date}. Stopping simulation.")
                break
            
            logger.debug(f"Processing event: {self.current_datetime} - {data_event.get('symbol')}")
            
            # 更新当前市场数据快照，用于处理条件单
            symbol = data_event.get('symbol')
            if symbol:
                current_market_data[symbol] = {
                    'open': data_event.get('open', 0.0),
                    'high': data_event.get('high', 0.0),
                    'low': data_event.get('low', 0.0),
                    'close': data_event.get('close', 0.0),
                    'volume': data_event.get('volume', 0)
                }

            # 1. Update portfolio with current market prices (important for MTM before strategy acts)
            # The portfolio's market_data_provider (set to self.data_provider)
            # needs a way to know what the "current" prices are for all holdings.
            # This is tricky if data_provider only gives historical series.
            # A simple way: portfolio's _update_market_values uses the data_event if it matches.
            # More robust: data_provider should have a `get_current_price(symbol, current_datetime)`
            # For now, the strategy's on_data will receive the current data_event.
            # The portfolio's _update_market_values should be smart enough.
            
            # Let's explicitly update the MTM of all portfolio holdings using the data_provider
            # This assumes data_provider can provide the "current" price for any symbol at self.current_datetime
            # This might be slow if called for many symbols on each event.
            # A better approach is for data_provider to have a "current_snapshot" view.
            self.portfolio._update_market_values() # Portfolio uses its data_provider


            # 2. Strategy processes data and generates signals
            # The `PyramidLLMStrategy`'s `on_data` directly calls `execute_signal`,
            # which then uses `trade_actions` that eventually call the broker.
            # The `execute_signal` in `BaseStrategy` updates `self.current_positions` and `self.trade_history`.
            # The `Portfolio` object gets updated via `update_fill` which should be called by the (simulated) broker
            # when a trade is "filled".
            
            # The signal generated by strategy.generate_signals is now passed to order_handler.
            # The strategy's on_data method should call self.generate_signals and then self.order_handler.process_signal
            # Let's adjust BaseStrategy and PyramidLLMStrategy later if needed.
            # For now, assume strategy's on_data eventually calls broker.place_order.
            # The SimulatedBroker then needs to call portfolio.update_fill.

            # Let's ensure the SimulatedBroker has access to the portfolio to call update_fill
            self.broker.set_portfolio_reference(self.portfolio) # Add this method to SimulatedBroker

            self.strategy.on_data(data_event) # This will trigger signal generation and execution

            # 3. 处理待执行的条件单(LIMIT, STOP, STOP_LIMIT)
            # 检查当前价格是否满足条件单的执行条件
            if hasattr(self.broker, 'process_pending_orders') and callable(getattr(self.broker, 'process_pending_orders')):
                self.broker.process_pending_orders(current_market_data)
            
            # 4. Record portfolio value at the end of this data event's processing
            self.portfolio._record_portfolio_value() # Ensures portfolio history is captured


        logger.info("Backtest simulation loop finished.")
        return self._calculate_performance_metrics()

    def _calculate_performance_metrics(self) -> Dict[str, Any]:
        """
        回测结束后计算并返回绩效指标。
        """
        logger.info("Calculating performance metrics...")
        if not self.portfolio or not self.portfolio.portfolio_history:
            logger.error("Cannot calculate performance: Portfolio or its history is missing.")
            return {"error": "Portfolio history not available for performance calculation."}

        calculator = PerformanceCalculator(
            portfolio_history=self.portfolio.get_portfolio_history(),
            trade_log=self.portfolio.get_trade_log(),
            initial_capital=self.initial_capital
        )
        
        self.results = calculator.get_all_metrics()
        logger.info(f"Performance Metrics: {self.results}")
        return self.results

    def get_results(self) -> Optional[Dict[str, Any]]:
        """
        获取回测结果。
        """
        if self.results:
            return self.results
        else:
            logger.warning("Backtest results not yet available. Run backtest first.")
            return None

# Example Usage (Illustrative - would be in a main script)
if __name__ == '__main__':
    # This is a conceptual example. Actual setup requires concrete implementations
    # of DataProvider, Strategy, etc., and proper configuration.

    from src.data_module.providers.simulated_data_provider import SimulatedDataProvider # Assuming this exists
    from src.strategy_module.pyramid_llm_strategy import PyramidLLMStrategy # Example strategy
    from src.llm_module.clients.simulated_llm_client import SimulatedLLMClient # Assuming this exists
    
    # --- Configuration ---
    start_dt = datetime(2023, 1, 1)
    end_dt = datetime(2023, 12, 31)
    cap = 100000.0
    test_symbols = ['AAPL', 'MSFT']

    # --- Setup Components (Simplified) ---
    # 1. Data Provider
    sim_data_config = {
        'data_path': 'path/to/simulated_data.csv', # Or configure for generation
        'symbols': test_symbols,
        'start_date': start_dt.strftime('%Y-%m-%d'),
        'end_date': end_dt.strftime('%Y-%m-%d')
    }
    data_prov = SimulatedDataProvider(config=sim_data_config)

    # 2. LLM Client (Simulated)
    llm_cli = SimulatedLLMClient(config={})

    # 3. Broker (Simulated)
    sim_broker_config = {'initial_cash': cap, 'commission_per_trade': 1.0}
    sim_broker = SimulatedBroker(config=sim_broker_config)
    
    # 4. Portfolio
    # The engine will create a new portfolio for each run, but an initial one can be passed
    # to initialize strategy/order_handler if they need it before run_backtest
    initial_portfolio = Portfolio(initial_cash=cap) 

    # 5. Risk Manager (Optional, Simulated)
    # from src.risk_module.simple_risk_manager import SimpleRiskManager
    # risk_conf = {'max_order_value_pct': 0.1, 'max_position_pct_asset': 0.2}
    # risk_man = SimpleRiskManager(config=risk_conf)
    risk_man = None


    # 6. Strategy
    strategy_conf = {
        'symbol_list': test_symbols, # Or strategy gets this from engine
        'llm_signal_confidence_threshold': 0.6,
        # ... other pyramid strategy params
    }
    # Strategy needs LLM client, and will get broker/portfolio from engine
    strat = PyramidLLMStrategy(config=strategy_conf, data_provider=data_prov, llm_client=llm_cli)

    # 7. Order Handler
    # OrderHandler links broker, (optional) risk manager, and (optional) portfolio
    ord_handler = OrderHandler(broker_client=sim_broker, risk_manager=risk_man, portfolio=initial_portfolio)


    # --- Engine ---
    engine = BacktestingEngine(
        start_date=start_dt,
        end_date=end_dt,
        data_provider=data_prov,
        strategy=strat,
        portfolio=initial_portfolio, # Engine recreates this for the run
        broker=sim_broker,
        order_handler=ord_handler,
        initial_capital=cap,
        risk_manager=risk_man
    )

    logger.info("Running backtest engine example...")
    try:
        # For the example to run, SimulatedDataProvider and SimulatedLLMClient need to be implemented
        # and provide data/responses. PyramidLLMStrategy also needs to be fully functional with these.
        # For now, this will likely raise errors due to missing methods or data.
        # results = engine.run_backtest(symbols=test_symbols, strategy_params={'some_param': 'value'})
        # print("Backtest Results:", results)
        print("BacktestingEngine example setup complete. Uncomment run_backtest and ensure components are fully implemented to execute.")
    except Exception as e:
        print(f"Error during example backtest run: {e}") 
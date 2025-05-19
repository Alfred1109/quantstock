#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
金字塔交易法量化系统主入口
"""

import os
import sys
import argparse
import logging # Keep for basic logger configuration by name
from datetime import datetime, timedelta
import yaml # For loading YAML config files
from typing import Dict, Optional, Any # Added for type hinting
from dotenv import load_dotenv
import time

# --- Path Setup ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# --- Utility Imports ---
from src.utils.config_loader import load_yaml_config # Import from new location

# --- Enhanced Imports for New Modules ---
from monitoring_module.logger import Logger # New Logger

# Data Module
from data_module.providers.base_provider import BaseDataProvider
# Assuming a simulated one exists or will be created in this path for the example to be runnable:
from data_module.providers.simulated_data_provider import SimulatedDataProvider

# LLM Module
from llm_module.clients.base_llm_client import BaseLLMClient
from llm_module.clients.deepseek_client import DeepSeekClient
# Assuming a simulated one exists or will be created in this path for the example to be runnable:
from llm_module.clients.simulated_llm_client import SimulatedLLMClient 

# Strategy Module
from strategy_module.base_strategy import BaseStrategy
from strategy_module.pyramid_llm_strategy import PyramidLLMStrategy

# Risk Module
from risk_module.base_risk_manager import BaseRiskManager
from risk_module.simple_risk_manager import SimpleRiskManager

# Execution Module
from execution_module.brokers.simulated_broker import SimulatedBroker
from execution_module.order_handler import OrderHandler

# Portfolio Module
from portfolio_module.portfolio import Portfolio

# Backtesting Module
from backtesting_module.engine import BacktestingEngine
from backtesting_module.reporting import BacktestReporter


# --- Global Variables ---
# Logger will be initialized in setup_system
logger: Optional[logging.Logger] = None
app_settings: Optional[Dict[str, Any]] = None # Type hint added for app_settings

# --- System Setup ---
def setup_system() -> tuple[Optional[logging.Logger], Optional[Dict[str, Any]]]: # Type hint added
    """Initializes logging and loads main application settings."""
    global logger, app_settings

    # Load main settings
    settings_path = os.path.join(BASE_DIR, 'config', 'settings.yaml')
    app_settings = load_yaml_config(settings_path)
    if not app_settings:
        print("CRITICAL: Main settings.yaml failed to load. Exiting.")
        sys.exit(1)

    # Setup main logger using Logger class from monitoring_module
    log_config = app_settings.get('logging', {})
    log_dir_from_settings = log_config.get('directory', 'output/logs') # Relative to BASE_DIR
    
    if not isinstance(log_dir_from_settings, str):
        print("CRITICAL: Logging directory in settings.yaml is not a string. Exiting.")
        sys.exit(1)

    if os.path.isabs(log_dir_from_settings):
        log_directory = log_dir_from_settings
    else:
        log_directory = os.path.join(BASE_DIR, log_dir_from_settings)
        
    os.makedirs(log_directory, exist_ok=True)

    Logger.configure(
        log_level=str(log_config.get('level', 'INFO')).upper(),
        log_file=os.path.join(log_directory, str(log_config.get('filename', 'app.log'))),
        console_logging=bool(log_config.get('console', True)),
        max_bytes=int(log_config.get('max_bytes', 10*1024*1024)),
        backup_count=int(log_config.get('backup_count', 5))
    )
    logger = Logger.get_logger('main_app') # Get a named logger instance
    logger.info(f"System initialized. Application settings loaded from: {settings_path}")
    logger.info(f"Logging to directory: {log_directory}, Level: {str(log_config.get('level', 'INFO')).upper()}")

    return logger, app_settings


# --- Mode Specific Functions ---
def run_backtest(args: argparse.Namespace, main_logger: logging.Logger, config: Dict[str, Any]): # Type hint added
    """运行回测模式 (Refactored)"""
    main_logger.info("Starting Backtest Mode...")

    # --- 1. Load Configurations ---
    llm_conf_path = os.path.join(BASE_DIR, 'config', args.llm_config)
    broker_conf_path = os.path.join(BASE_DIR, 'config', args.broker_config)
    strategy_params_path = os.path.join(BASE_DIR, 'config', 'strategy_params', args.strategy_params)
    
    llm_config = load_yaml_config(llm_conf_path) 
    broker_config = load_yaml_config(broker_conf_path)
    strategy_params_config = load_yaml_config(strategy_params_path)

    if not llm_config or not broker_config or not strategy_params_config:
        main_logger.error("One or more essential configuration files failed to load for backtest. Exiting.")
        return

    # --- 2. Parse Dates ---
    try:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    except ValueError as e:
        main_logger.error(f"Invalid date format for start_date/end_date. Use YYYY-MM-DD. Error: {e}")
        return

    # --- 3. Instantiate Components ---
    main_logger.info("Instantiating backtesting components...")
    
    # 数据提供器选择 - 始终优先使用AKShare真实数据
    # 从配置中读取数据提供器设置
    data_provider_config = config.get('data_providers', {}).get('akshare', {})
    
    try:
        # 优先使用AKShare数据提供器
        from data_module.providers.akshare_provider import AKShareDataProvider
        data_provider = AKShareDataProvider(config=data_provider_config)
        main_logger.info(f"Data Provider: AKShare initialized for data source.")
    except Exception as e:
        main_logger.error(f"Failed to initialize AKShare Data Provider: {e}", exc_info=True)
        # 只有在AKShare初始化失败时才回退到模拟数据
        main_logger.warning("Falling back to SimulatedDataProvider - THIS IS FOR TESTING ONLY.")
        sim_data_provider_config = {
            'start_date': args.start_date,
            'end_date': args.end_date,
            'symbols': args.symbols.split(','),
        }
        try:
            data_provider: BaseDataProvider = SimulatedDataProvider(config=sim_data_provider_config)
            main_logger.info(f"Data Provider: {data_provider.__class__.__name__} initialized (fallback).")
        except Exception as e2:
            main_logger.error(f"Failed to initialize fallback SimulatedDataProvider: {e2}", exc_info=True)
            return

    # 始终优先使用DeepSeek真实LLM客户端
    try:
        # 从环境变量加载API密钥
        load_dotenv()
        
        # 优先使用配置文件中的直接API密钥，如果没有则尝试从环境变量加载
        api_key = llm_config.get('deepseek_settings', {}).get('api_key')
        if not api_key:
            api_key_env = llm_config.get('deepseek_settings', {}).get('api_key_env_var', 'DEEPSEEK_API_KEY')
            api_key = os.getenv(api_key_env)
        
        if not api_key:
            main_logger.error(f"DeepSeek API密钥未在配置文件或环境变量中找到，无法使用真实LLM服务")
            main_logger.warning("回退到模拟LLM客户端 - 仅用于测试，结果不可靠")
            llm_client: BaseLLMClient = SimulatedLLMClient(config=llm_config.get('simulated_settings', {}))
        else:
            model_name = llm_config.get('deepseek_settings', {}).get('model_name', 'deepseek-v3-250324')
            base_url = llm_config.get('deepseek_settings', {}).get('base_url')
            use_openai_client = llm_config.get('deepseek_settings', {}).get('use_openai_client', True)
            llm_client: BaseLLMClient = DeepSeekClient(
                api_key=api_key, 
                model_name=model_name, 
                base_url=base_url,
                use_openai_client=use_openai_client
            )
            main_logger.info(f"已成功初始化真实LLM客户端: {model_name}")
    except Exception as e:
        main_logger.error(f"初始化LLM客户端失败: {e}", exc_info=True)
        main_logger.warning("回退到模拟LLM客户端 - 仅用于测试，结果不可靠")
        llm_client: BaseLLMClient = SimulatedLLMClient(config=llm_config.get('simulated_settings', {}))
        
    main_logger.info(f"LLM Client: {llm_client.__class__.__name__} initialized.")

    try:
        sim_broker = SimulatedBroker(config=broker_config.get('simulated_broker_settings', {}))
        main_logger.info("Simulated Broker initialized.")
    except Exception as e:
        main_logger.error(f"Failed to initialize Simulated Broker: {e}", exc_info=True)
        return
    
    initial_portfolio_for_setup = Portfolio(initial_cash=args.initial_capital)

    risk_manager_settings = config.get('risk_management', {})
    risk_manager: Optional[BaseRiskManager] = None
    if risk_manager_settings.get('enabled', False):
        try:
            risk_manager = SimpleRiskManager(config=risk_manager_settings.get('settings', {}))
            main_logger.info("Risk Manager (SimpleRiskManager) initialized.")
        except Exception as e:
            main_logger.error(f"Failed to initialize Risk Manager: {e}", exc_info=True)

    try:
        strategy: BaseStrategy = PyramidLLMStrategy(
            config=strategy_params_config, 
            data_provider=data_provider,
            llm_client=llm_client
        )
        main_logger.info(f"Strategy: {strategy.__class__.__name__} initialized.")
    except Exception as e:
        main_logger.error(f"Failed to initialize Strategy: {e}", exc_info=True)
        return

    try:
        order_handler = OrderHandler(
            broker_client=sim_broker,
            risk_manager=risk_manager,
            portfolio=initial_portfolio_for_setup 
        )
        main_logger.info("Order Handler initialized.")
    except Exception as e:
        main_logger.error(f"Failed to initialize Order Handler: {e}", exc_info=True)
        return

    try:
        engine = BacktestingEngine(
            start_date=start_date,
            end_date=end_date,
            data_provider=data_provider,
            strategy=strategy,
            portfolio=initial_portfolio_for_setup, 
            broker=sim_broker,
            order_handler=order_handler,
            initial_capital=args.initial_capital,
            risk_manager=risk_manager
        )
        main_logger.info("Backtesting Engine initialized.")
    except Exception as e:
        main_logger.error(f"Failed to initialize Backtesting Engine: {e}", exc_info=True)
        return

    main_logger.info(f"Running backtest for symbols: {args.symbols} from {args.start_date} to {args.end_date}")
    try:
        results = engine.run_backtest(
            symbols=args.symbols.split(','),
            strategy_params=strategy_params_config
        )
    except Exception as e:
        main_logger.error(f"Error during backtest execution: {e}", exc_info=True)
        results = {"error": f"Backtest execution failed: {e}"}

    if results and not results.get("error"):
        main_logger.info("Backtest finished. Generating report...")
        reporter = BacktestReporter(results)
        text_report = reporter.generate_text_report()
        print("\n" + text_report)

        report_output_dir = os.path.join(BASE_DIR, 'output', 'results')
        os.makedirs(report_output_dir, exist_ok=True)
        report_filename = f"backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        report_filepath = os.path.join(report_output_dir, report_filename)
        try:
            reporter.save_text_report(report_filepath)
            main_logger.info(f"Backtest report saved to: {report_filepath}")
        except Exception as e:
            main_logger.error(f"Failed to save backtest report: {e}", exc_info=True)
    else:
        main_logger.error(f"Backtest failed or produced no results. Error: {results.get('error', 'Unknown error')}")

    main_logger.info("Backtest Mode Finished.")


def run_optimize(args: argparse.Namespace, main_logger: logging.Logger, config: Dict[str, Any]):
    main_logger.info("Parameter Optimization Mode is not fully implemented yet.")

def run_trade(args: argparse.Namespace, main_logger: logging.Logger, config: Dict[str, Any]):
    """运行实盘交易模式"""
    main_logger.info("Starting Live Trading Mode...")

    # --- 1. Load Configurations ---
    llm_conf_path = os.path.join(BASE_DIR, 'config', args.llm_config)
    broker_conf_path = os.path.join(BASE_DIR, 'config', args.broker_config)
    strategy_params_path = os.path.join(BASE_DIR, 'config', 'strategy_params', args.strategy_params)
    
    llm_config = load_yaml_config(llm_conf_path) 
    broker_config = load_yaml_config(broker_conf_path)
    strategy_params_config = load_yaml_config(strategy_params_path)

    if not llm_config or not broker_config or not strategy_params_config:
        main_logger.error("One or more essential configuration files failed to load for live trading. Exiting.")
        return

    # --- 2. Parse Dates ---
    try:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    except ValueError as e:
        main_logger.error(f"Invalid date format for start_date/end_date. Use YYYY-MM-DD. Error: {e}")
        return

    # --- 3. Initialize Realtime Data Service ---
    main_logger.info("Initializing realtime data service...")
    try:
        # Import the realtime service
        from src.services.realtime_service import get_realtime_service
        realtime_service = get_realtime_service()
        main_logger.info("Realtime service initialized.")
    except Exception as e:
        main_logger.error(f"Failed to initialize realtime service: {e}", exc_info=True)
        return

    # --- 4. Instantiate Components ---
    main_logger.info("Instantiating trading components...")
    
    # Initialize data provider (AKShare for real trading)
    main_logger.info("Initializing AKShare data provider for real-time data...")
    from data_module.providers.akshare_provider import AKShareDataProvider
    
    try:
        data_provider_config = config.get('data_providers', {}).get('akshare', {})
        data_provider = AKShareDataProvider(config=data_provider_config)
        main_logger.info(f"Data Provider: AKShareDataProvider initialized for live trading")
    except Exception as e:
        main_logger.error(f"Failed to initialize AKShare Data Provider: {e}", exc_info=True)
        return

    # Initialize LLM client
    llm_client_type = llm_config.get('client_type', 'simulated')
    try:
        if llm_client_type == 'deepseek':
            # Load API key from environment variables
            load_dotenv()
            
            # Use direct API key from config file if available, otherwise try env var
            api_key = llm_config.get('deepseek_settings', {}).get('api_key')
            if not api_key:
                api_key_env = llm_config.get('deepseek_settings', {}).get('api_key_env_var', 'DEEPSEEK_API_KEY')
                api_key = os.getenv(api_key_env)
            
            if not api_key:
                main_logger.error(f"DeepSeek API key not found in config or environment variables, falling back to simulated client")
                from llm_module.clients.simulated_llm_client import SimulatedLLMClient
                llm_client = SimulatedLLMClient(config=llm_config.get('simulated_settings', {}))
            else:
                model_name = llm_config.get('deepseek_settings', {}).get('model_name', 'deepseek-v3-250324')
                base_url = llm_config.get('deepseek_settings', {}).get('base_url')
                use_openai_client = llm_config.get('deepseek_settings', {}).get('use_openai_client', True)
                from llm_module.clients.deepseek_client import DeepSeekClient
                llm_client = DeepSeekClient(
                    api_key=api_key, 
                    model_name=model_name, 
                    base_url=base_url,
                    use_openai_client=use_openai_client
                )
        else:
            from llm_module.clients.simulated_llm_client import SimulatedLLMClient
            llm_client = SimulatedLLMClient(config=llm_config.get('simulated_settings', {}))
        main_logger.info(f"LLM Client: {llm_client.__class__.__name__} initialized.")
    except Exception as e:
        main_logger.error(f"Failed to initialize LLM Client: {e}", exc_info=True)
        return

    # Initialize broker (using real broker for live trading)
    try:
        # Determine broker type from config
        broker_type = broker_config.get('broker_type', 'simulated')
        
        if broker_type == 'real':
            # 尝试使用真实券商接口
            from execution_module.brokers.real_broker import RealBroker
            real_broker_config = broker_config.get('real_broker_settings', {})
            broker = RealBroker(config=real_broker_config)
            
            # 测试连接
            connection_successful = broker.connect()
            if connection_successful:
                main_logger.info(f"成功连接到真实券商接口: {real_broker_config.get('broker_name', 'unknown')}")
            else:
                main_logger.warning("无法连接到真实券商接口，将回退到模拟券商")
                from execution_module.brokers.simulated_broker import SimulatedBroker
                broker = SimulatedBroker(config=broker_config.get('simulated_broker_settings', {}))
                main_logger.info("使用模拟券商进行实盘交易（仅作测试用途）")
        else:
            # 使用模拟券商（适用于测试或模拟环境）
            from execution_module.brokers.simulated_broker import SimulatedBroker
            broker = SimulatedBroker(config=broker_config.get('simulated_broker_settings', {}))
            main_logger.info("使用模拟券商进行实盘交易（仅作测试用途）")
            
    except Exception as e:
        main_logger.error(f"初始化券商接口失败: {e}", exc_info=True)
        main_logger.warning("回退到模拟券商接口")
        from execution_module.brokers.simulated_broker import SimulatedBroker
        broker = SimulatedBroker(config=broker_config.get('simulated_broker_settings', {}))
        main_logger.info("使用模拟券商进行实盘交易（仅作测试用途）")
        # 即使回退到模拟券商也继续执行，不返回
    
    # Initialize portfolio
    from portfolio_module.portfolio import Portfolio
    initial_portfolio = Portfolio(initial_cash=args.initial_capital)

    # Initialize risk manager
    risk_manager_settings = config.get('risk_management', {})
    risk_manager = None
    if risk_manager_settings.get('enabled', False):
        try:
            from risk_module.simple_risk_manager import SimpleRiskManager
            risk_manager = SimpleRiskManager(config=risk_manager_settings.get('settings', {}))
            main_logger.info("Risk Manager (SimpleRiskManager) initialized.")
        except Exception as e:
            main_logger.error(f"Failed to initialize Risk Manager: {e}", exc_info=True)

    # Initialize strategy
    try:
        from strategy_module.pyramid_llm_strategy import PyramidLLMStrategy
        strategy = PyramidLLMStrategy(
            config=strategy_params_config, 
            data_provider=data_provider,
            llm_client=llm_client
        )
        main_logger.info(f"Strategy: {strategy.__class__.__name__} initialized.")
    except Exception as e:
        main_logger.error(f"Failed to initialize Strategy: {e}", exc_info=True)
        return

    # Initialize order handler
    try:
        from execution_module.order_handler import OrderHandler
        order_handler = OrderHandler(
            broker_client=broker,
            risk_manager=risk_manager,
            portfolio=initial_portfolio 
        )
        main_logger.info("Order Handler initialized.")
    except Exception as e:
        main_logger.error(f"Failed to initialize Order Handler: {e}", exc_info=True)
        return

    # --- 5. Launch Trading Process ---
    main_logger.info(f"Starting live trading for symbols: {args.symbols}")
    
    # Parse symbols
    symbols = args.symbols.split(',')
    
    try:
        main_logger.info("Entering trading loop...")
        
        # 实现连续的交易循环，并根据实际交易时间规则进行交易
        from datetime import datetime, time as dt_time
        import time
        import threading
        import signal
        
        # 交易相关参数设置
        trading_interval = config.get('trading', {}).get('interval_seconds', 60)  # 默认每分钟执行一次
        check_market_status_interval = 5  # 每5秒检查一次市场状态
        
        # 交易时间段设置（中国A股：9:30-11:30, 13:00-15:00）
        MORNING_START = dt_time(9, 30)
        MORNING_END = dt_time(11, 30)
        AFTERNOON_START = dt_time(13, 0)
        AFTERNOON_END = dt_time(15, 0)
        
        # 上次交易检查时间
        last_trading_check = datetime.now()
        
        # 交易状态
        is_running = True
        
        # 设置中断处理
        def handle_interrupt(sig, frame):
            nonlocal is_running
            main_logger.info("收到中断信号，准备退出交易循环...")
            is_running = False
        
        signal.signal(signal.SIGINT, handle_interrupt)
        
        def is_trading_time():
            """检查当前是否为交易时间"""
            now = datetime.now().time()
            # 检查是否是工作日（周一至周五）
            if datetime.now().weekday() >= 5:  # 5=周六，6=周日
                return False
                
            # 检查是否在交易时间段内
            morning_session = MORNING_START <= now <= MORNING_END
            afternoon_session = AFTERNOON_START <= now <= AFTERNOON_END
            return morning_session or afternoon_session
        
        def format_next_trading_time():
            """格式化下一个交易时间"""
            now = datetime.now()
            today = now.date()
            weekday = now.weekday()
            
            # 如果当前是周末
            if weekday >= 5:
                days_to_monday = 7 - weekday
                next_trading_day = today + timedelta(days=days_to_monday)
                return f"下一个交易日 {next_trading_day.strftime('%Y-%m-%d')} {MORNING_START.strftime('%H:%M')}"
            
            # 如果当前时间早于早市
            if now.time() < MORNING_START:
                return f"今日早市开盘 {MORNING_START.strftime('%H:%M')}"
            
            # 如果当前时间在早市和午市之间
            if MORNING_END < now.time() < AFTERNOON_START:
                return f"今日午市开盘 {AFTERNOON_START.strftime('%H:%M')}"
            
            # 如果当前时间晚于午市
            if now.time() > AFTERNOON_END:
                if weekday == 4:  # 周五
                    return f"下一个交易日 {(today + timedelta(days=3)).strftime('%Y-%m-%d')} {MORNING_START.strftime('%H:%M')}"
                else:
                    return f"明日早市开盘 {MORNING_START.strftime('%H:%M')}"
            
            return "当前正处于交易时间"
        
        # 初始化技术分析缓存
        tech_analysis_cache = {}
        
        main_logger.info("进入交易循环，按Ctrl+C中断...")
        
        try:
            while is_running:
                current_time = datetime.now()
                
                # 检查是否是交易时间
                if is_trading_time():
                    # 检查是否到了交易间隔
                    time_since_last_check = (current_time - last_trading_check).total_seconds()
                    
                    if time_since_last_check >= trading_interval:
                        main_logger.info(f"执行交易检查: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        last_trading_check = current_time
                        
                        # 获取最新市场数据
                        latest_data = {}
                        for symbol in symbols:
                            try:
                                # 获取实时价格数据
                                price_data = data_provider.get_current_price(symbol)
                                if not isinstance(price_data, pd.DataFrame) or price_data.empty:
                                    main_logger.warning(f"无法获取 {symbol} 的价格数据")
                                    continue
                                    
                                # 获取历史数据用于技术分析
                                hist_data = data_provider.get_historical_data(
                                    symbol=symbol,
                                    start_date=(current_time - timedelta(days=60)).strftime('%Y-%m-%d'),
                                    end_date=current_time.strftime('%Y-%m-%d'),
                                    timeframe='1d'
                                )
                                
                                # 构建合适的market_data格式
                                market_data = {
                                    'symbol': symbol,
                                    'timestamp': current_time.isoformat(),
                                    'current': price_data.iloc[0].to_dict() if len(price_data) > 0 else {},
                                    'history': hist_data
                                }
                                
                                latest_data[symbol] = market_data
                                
                                # 记录最新价格
                                price_value = price_data['price'].iloc[0] if 'price' in price_data.columns and len(price_data) > 0 else 'N/A'
                                main_logger.info(f"获取 {symbol} 最新价格: {price_value}")
                                
                            except Exception as e:
                                main_logger.error(f"获取 {symbol} 数据时出错: {e}", exc_info=True)
                        
                        # 生成交易信号
                        try:
                            signals = []
                            for symbol in symbols:
                                if symbol not in latest_data:
                                    continue
                                    
                                # 执行技术分析
                                technical_analysis = strategy._perform_technical_analysis(latest_data[symbol])
                                tech_analysis_cache[symbol] = technical_analysis
                                
                                # 生成信号
                                signal = strategy.generate_signals(symbol, latest_data[symbol], technical_analysis)
                                if signal and signal.get('action') != 'HOLD':
                                    signals.append(signal)
                            
                            if signals:
                                main_logger.info(f"生成交易信号: {signals}")
                                
                                # 执行交易信号
                                for signal in signals:
                                    try:
                                        order_result = order_handler.process_signal(signal)
                                        main_logger.info(f"订单执行结果: {order_result}")
                                    except Exception as e:
                                        main_logger.error(f"执行订单时出错: {e}", exc_info=True)
                            else:
                                main_logger.info("未生成交易信号")
                                
                        except Exception as e:
                            main_logger.error(f"生成交易信号时出错: {e}", exc_info=True)
                    
                    # 短暂休眠以避免过于频繁的检查
                    time.sleep(1)
                else:
                    # 非交易时间，显示下一个交易时间
                    next_trading = format_next_trading_time()
                    main_logger.info(f"当前非交易时间，{next_trading}，等待中...")
                    
                    # 在非交易时间，可以进行一些其他工作，如市场数据分析、策略回测等
                    
                    # 非交易时间可以降低检查频率
                    time.sleep(check_market_status_interval)
        
        except KeyboardInterrupt:
            main_logger.info("用户中断交易循环")
        except Exception as e:
            main_logger.error(f"交易循环中发生错误: {e}", exc_info=True)
        finally:
            # 确保在退出前断开券商连接
            if broker and hasattr(broker, 'disconnect'):
                broker.disconnect()
            main_logger.info("交易循环已结束")
        
    except KeyboardInterrupt:
        main_logger.info("Trading stopped by user")
    except Exception as e:
        main_logger.error(f"Error in trading loop: {e}", exc_info=True)
    
    main_logger.info("Live Trading Mode finished.")


def run_frontend(args: argparse.Namespace, main_logger: logging.Logger, config: Dict[str, Any]):
    """启动Web前端界面，同时支持实时交易功能"""
    main_logger.info("启动Web前端界面和实时交易功能...")
    
    # --- 1. 初始化交易相关组件（从run_trade复制） ---
    # 配置加载
    llm_conf_path = os.path.join(BASE_DIR, 'config', args.llm_config)
    broker_conf_path = os.path.join(BASE_DIR, 'config', args.broker_config)
    strategy_params_path = os.path.join(BASE_DIR, 'config', 'strategy_params', args.strategy_params)
    
    llm_config = load_yaml_config(llm_conf_path) 
    broker_config = load_yaml_config(broker_conf_path)
    strategy_params_config = load_yaml_config(strategy_params_path)

    if not llm_config or not broker_config or not strategy_params_config:
        main_logger.error("One or more essential configuration files failed to load. 前端可能无法正常工作")

    # 解析日期
    try:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    except ValueError as e:
        main_logger.error(f"Invalid date format for start_date/end_date. Use YYYY-MM-DD. Error: {e}")
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()

    # 初始化实时数据服务
    try:
        from src.services.realtime_service import get_realtime_service
        realtime_service = get_realtime_service()
        main_logger.info("Realtime service initialized.")
        
        # 启动实时数据服务（在后台线程中运行）
        import threading
        def start_realtime_service():
            main_logger.info("Starting realtime service in background thread")
            import asyncio
            asyncio.run(realtime_service.start())
            
        realtime_thread = threading.Thread(target=start_realtime_service)
        realtime_thread.daemon = True  # 设置为守护线程，这样主程序退出时线程也会退出
        realtime_thread.start()
        main_logger.info("Realtime service thread started")
    except Exception as e:
        main_logger.error(f"Failed to initialize realtime service: {e}", exc_info=True)
        realtime_service = None
    
    # --- 2. 启动 Flask Web 应用 ---
    try:
        # 导入前端模块
        from src.frontend.app import run_app
        
        # 获取前端配置
        frontend_config = config.get('frontend', {})
        port = frontend_config.get('port', 5000)
        
        # 如果命令行指定了端口，则优先使用命令行端口
        if hasattr(args, 'port') and args.port:
            port = args.port
            
        # 检查调试模式
        debug = False
        if hasattr(args, 'debug') and args.debug:
            debug = True
        
        main_logger.info(f"Web前端将在端口 {port} 启动，实时交易功能已在后台运行")
        
        # 启动Flask应用
        run_app(port=port, debug=debug)
    except ImportError as e:
        main_logger.error(f"导入前端模块失败: {e}", exc_info=True)
        print(f"错误: 导入前端模块失败。确保已安装Flask和其他必要依赖。")
    except Exception as e:
        main_logger.error(f"启动Web前端失败: {e}", exc_info=True)
        print(f"错误: 启动Web前端失败: {e}")


# --- Main Execution ---
def main():
    """Main application entry point (Refactored)"""
    try:
        logger, settings = setup_system()
        
        # Command line argument parsing
        parser = argparse.ArgumentParser(description='Pyramid Trading Quantitative System')
        parser.add_argument('--mode', required=False, choices=['backtest', 'optimize', 'trade', 'frontend'], 
                          default='backtest', help='Operation mode')
        parser.add_argument('--symbols', required=False, default='000001.SH',
                          help='Comma-separated list of symbols (e.g., 000001.SH,600000.SH)')
        parser.add_argument('--start-date', required=False, 
                          default=(datetime.now().replace(day=1) - timedelta(days=30)).strftime('%Y-%m-%d'),
                          help='Start date in YYYY-MM-DD format')
        parser.add_argument('--end-date', required=False, 
                          default=datetime.now().strftime('%Y-%m-%d'),
                          help='End date in YYYY-MM-DD format')
        parser.add_argument('--initial-capital', required=False, type=float, default=100000,
                          help='Initial capital amount')
        parser.add_argument('--llm-config', required=False, default='llm_config.yaml',
                          help='LLM configuration file (in config directory)')
        parser.add_argument('--broker-config', required=False, default='broker_config.yaml',
                          help='Broker configuration file (in config directory)')
        parser.add_argument('--strategy-params', required=False, default='pyramid_default.yaml',
                          help='Strategy parameters file (in config/strategy_params directory)')
        parser.add_argument('--use-akshare', action='store_true', 
                          help='Use AKShare as data provider instead of simulated data')
        
        # 前端模式特有参数
        parser.add_argument('--port', type=int, default=5000, 
                          help='Web server port (for frontend mode)')
        parser.add_argument('--debug', action='store_true',
                          help='Enable debug mode (for frontend mode)')
        
        args = parser.parse_args()

        if args.mode == 'backtest':
            run_backtest(args, logger, settings)
        elif args.mode == 'optimize':
            run_optimize(args, logger, settings)
        elif args.mode == 'trade':
            run_trade(args, logger, settings)
        elif args.mode == 'frontend':
            run_frontend(args, logger, settings)
        else:
            parser.print_help()
    except KeyboardInterrupt:
        if logger:
            logger.info("程序被用户中断")
        print("\n程序已被用户中断")
    except Exception as e:
        import traceback
        import json
        import copy
        
        # 记录错误到日志
        if logger:
            logger.critical(f"主进程发生致命错误: {e}", exc_info=True)
        else:
            print(f"CRITICAL ERROR: {e}")
            traceback.print_exc()
        
        # 创建详细的错误报告
        try:
            # 确保日志目录存在
            log_directory = os.path.join(BASE_DIR, 'logs')
            os.makedirs(log_directory, exist_ok=True)
            
            # 创建错误日志文件
            error_log_path = os.path.join(log_directory, f'critical_error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            
            with open(error_log_path, 'w', encoding='utf-8') as error_file:
                error_file.write(f"时间: {datetime.now().isoformat()}\n")
                error_file.write(f"错误: {str(e)}\n")
                error_file.write(f"追踪: {traceback.format_exc()}\n")
                
                # 记录系统状态
                error_file.write("\n系统状态:\n")
                
                # 记录运行时配置
                if 'settings' in locals() and settings:
                    error_file.write("\n配置:\n")
                    # 移除敏感信息如API密钥
                    safe_settings = copy.deepcopy(settings)
                    if 'api_keys' in safe_settings:
                        safe_settings['api_keys'] = {k: '***REDACTED***' for k in safe_settings['api_keys']}
                    error_file.write(json.dumps(safe_settings, indent=2, ensure_ascii=False))
                
                # 记录命令行参数
                if 'args' in locals() and args:
                    error_file.write("\n命令行参数:\n")
                    args_dict = vars(args)
                    error_file.write(json.dumps(args_dict, indent=2, ensure_ascii=False))
                
                # 记录系统环境信息
                error_file.write("\n系统环境:\n")
                error_file.write(f"Python版本: {sys.version}\n")
                error_file.write(f"操作系统: {sys.platform}\n")
                error_file.write(f"工作目录: {os.getcwd()}\n")
                
                # 记录已加载模块
                error_file.write("\n已加载模块:\n")
                for name, module in sorted(sys.modules.items()):
                    if hasattr(module, '__version__'):
                        try:
                            version = module.__version__
                            error_file.write(f"{name}: {version}\n")
                        except:
                            pass
            
            if logger:
                logger.info(f"错误详情已保存至: {error_log_path}")
            else:
                print(f"错误详情已保存至: {error_log_path}")
                
            # 实现错误恢复机制
            if 'settings' in locals() and settings and 'error_handling' in settings:
                error_config = settings.get('error_handling', {})
                retry_count = error_config.get('max_retries', 0)
                retry_delay = error_config.get('retry_delay_seconds', 30)
                
                if retry_count > 0:
                    retry_remaining = retry_count
                    
                    # 检查是否有计数文件
                    retry_counter_file = os.path.join(log_directory, 'retry_counter.txt')
                    if os.path.exists(retry_counter_file):
                        try:
                            with open(retry_counter_file, 'r') as f:
                                retry_remaining = int(f.read().strip())
                                retry_remaining -= 1
                        except:
                            retry_remaining = retry_count - 1
                    else:
                        retry_remaining = retry_count - 1
                    
                    # 更新重试计数
                    try:
                        with open(retry_counter_file, 'w') as f:
                            f.write(str(retry_remaining))
                    except:
                        pass
                    
                    if retry_remaining > 0:
                        message = f"将在{retry_delay}秒后尝试重启程序 (剩余重试次数: {retry_remaining})"
                        if logger:
                            logger.info(message)
                        print(message)
                        
                        # 等待一段时间后重启
                        try:
                            time.sleep(retry_delay)
                            os.execv(sys.executable, [sys.executable] + sys.argv)
                        except Exception as restart_error:
                            if logger:
                                logger.critical(f"重启失败: {restart_error}")
                            print(f"重启失败: {restart_error}")
                            sys.exit(2)
                    else:
                        # 清理重试计数文件
                        try:
                            if os.path.exists(retry_counter_file):
                                os.remove(retry_counter_file)
                        except:
                            pass
                            
                        message = "达到最大重试次数，程序将退出"
                        if logger:
                            logger.critical(message)
                        print(message)
                        sys.exit(1)
        except Exception as log_error:
            print(f"记录错误信息时出错: {log_error}")
            traceback.print_exc()
            
        sys.exit(1)

if __name__ == "__main__":
    main() 
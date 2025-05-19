#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
量化交易系统Web前端
"""

import os
import sys
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# 初始化日志
import logging
logger = logging.getLogger("app")

# 创建Flask应用
app = Flask(__name__)

# 让request对象在所有模板中可用
@app.context_processor
def inject_request():
    """将request对象注入到所有模板中"""
    return {'request': request}

# API蓝图直接通过Flask路由实现，不单独导入
# 后续可以根据需要分离API到单独的蓝图

@app.route('/')
def index():
    """首页"""
    return render_template('index.html')

@app.route('/stock/<symbol>')
def stock_detail(symbol):
    """股票详情页"""
    return render_template('stock_detail.html', symbol=symbol)

@app.route('/market')
def market_overview():
    """市场概览"""
    return render_template('market_overview.html')

@app.route('/watchlist')
def watchlist():
    """自选股"""
    return render_template('watchlist.html')

@app.route('/settings')
def settings():
    """设置页面"""
    return render_template('settings.html')

@app.route('/backtest')
def backtest_page():
    """回测页面"""
    return render_template('backtest.html')

@app.route('/config')
def config_page():
    """配置页面"""
    return render_template('config.html')

@app.route('/api/status')
def api_status():
    """API状态"""
    return jsonify({
        "status": "online",
        "version": "1.0.0",
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/kline/<symbol>')
def api_kline(symbol):
    """获取K线数据"""
    # 这里返回模拟数据，实际项目中应该连接到数据源
    period = request.args.get('period', 'day')
    
    # 生成模拟数据
    now = datetime.now()
    data = []
    
    for i in range(60):
        date = (now - timedelta(days=60-i)).strftime('%Y-%m-%d')
        base_price = 3000 + i * 10 + (hash(date) % 100)
        
        data.append({
            "date": date,
            "open": round(base_price * (1 + (hash(date+"-open") % 10) / 100), 2),
            "high": round(base_price * (1 + (hash(date+"-high") % 15) / 100), 2),
            "low": round(base_price * (1 - (hash(date+"-low") % 8) / 100), 2),
            "close": round(base_price * (1 + (hash(date+"-close") % 12 - 6) / 100), 2),
            "volume": int(100000 + hash(date+"-volume") % 50000)
        })
    
    return jsonify({
        "code": 0,
        "message": "success",
        "data": {
            "symbol": symbol,
            "period": period,
            "klines": data
        }
    })

@app.route('/api/quote/<symbol>')
def api_quote(symbol):
    """获取行情数据"""
    # 生成模拟数据
    now = datetime.now()
    seed = hash(symbol + now.strftime('%Y-%m-%d'))
    
    base_price = 3000 + (seed % 1000)
    change = round((seed % 200 - 100) / 100, 2)
    
    return jsonify({
        "code": 0,
        "message": "success",
        "data": {
            "symbol": symbol,
            "name": f"模拟指数{symbol[-6:-3]}",
            "price": round(base_price, 2),
            "open": round(base_price * 0.995, 2),
            "high": round(base_price * 1.01, 2),
            "low": round(base_price * 0.99, 2),
            "change": change,
            "changepct": round(change / base_price * 100, 2),
            "volume": int(1000000 + seed % 500000),
            "time": now.strftime('%Y-%m-%d %H:%M:%S')
        }
    })

# --- Import Core Components ---
from src.data_module.factory import get_data_provider # Using factory
from src.llm_module.clients.deepseek_client import DeepSeekClient # Example client
from src.strategy_module.pyramid_llm_strategy import PyramidLLMStrategy
from src.utils.config_loader import load_yaml_config # Assuming a utility for this

# --- Global Component Initialization (Simplified for now) ---
# This is a basic approach; a more robust app would use Flask app context or blueprints
# and manage configurations more dynamically.

main_app_config_path = os.path.join(project_root, 'config', 'settings.yaml')
main_app_config = load_yaml_config(main_app_config_path)
if not main_app_config:
    logger.error("CRITICAL: Main settings.yaml failed to load for Flask app. Using defaults.")
    main_app_config = {}

llm_config_path = os.path.join(project_root, 'config', 'llm_config.yaml')
llm_config = load_yaml_config(llm_config_path)
if not llm_config:
    logger.error("CRITICAL: llm_config.yaml failed to load for Flask app. LLM might not work.")
    llm_config = {}

strategy_params_path = os.path.join(project_root, 'config', 'strategy_params', 'pyramid_default.yaml') # Example
strategy_params_config = load_yaml_config(strategy_params_path)
if not strategy_params_config:
    logger.error("CRITICAL: strategy_params_config failed to load. Strategy might not work.")
    strategy_params_config = {}

# Initialize components (error handling should be more robust in a real app)
try:
    # Defaulting to simulated provider for frontend interaction for now
    # In a real app, this might be configurable via UI or specific to endpoint
    data_provider_instance = get_data_provider(provider_type="simulated") 
    
    deepseek_api_key = os.getenv(llm_config.get('deepseek_settings', {}).get('api_key_env_var', 'DEEPSEEK_API_KEY'))
    if not deepseek_api_key: # Check if key from env is None or empty
        deepseek_api_key = llm_config.get('deepseek_settings', {}).get('api_key', '') # Fallback to config direct key if any
    
    if not deepseek_api_key:
         logger.warning("DeepSeek API key not found in env or config. LLM calls will likely fail.")
         # Optionally, initialize a simulated LLM client here as a fallback
         # from src.llm_module.clients.simulated_llm_client import SimulatedLLMClient
         # llm_client_instance = SimulatedLLMClient(config=llm_config.get('simulated_settings', {}))
         # For now, let it proceed and potentially fail at runtime if DeepSeek is chosen & key missing.
         llm_client_instance = None # Or initialize a dummy/simulated one
    else:
        llm_client_instance = DeepSeekClient(
            api_key=deepseek_api_key,
            model_name=llm_config.get('deepseek_settings', {}).get('model_name', 'deepseek-v3-250324'),
            base_url=llm_config.get('deepseek_settings', {}).get('base_url'),
            use_openai_client=llm_config.get('deepseek_settings', {}).get('use_openai_client', True)
        )

    if llm_client_instance:
        strategy_instance = PyramidLLMStrategy(
            config=strategy_params_config,
            data_provider=data_provider_instance,
            llm_client=llm_client_instance
            # broker_client and risk_manager can be added if needed by frontend flows
        )
        logger.info("Core components (DataProvider, LLMClient, Strategy) initialized for Flask app.")
    else:
        strategy_instance = None
        logger.error("LLM Client could not be initialized. Strategy functionality will be impaired.")

except Exception as e:
    logger.error(f"Error initializing core components for Flask app: {e}", exc_info=True)
    data_provider_instance = None
    llm_client_instance = None
    strategy_instance = None
# --- End Global Component Initialization ---

# --- New API Endpoint for Strategy ---
@app.route('/api/strategy/find_entry/<symbol>', methods=['GET', 'POST'])
def api_find_entry_opportunity(symbol):
    if not strategy_instance or not data_provider_instance:
        return jsonify({"error": "Strategy or DataProvider not initialized"}), 500

    try:
        # For an interactive frontend, the "data_event" would typically be
        # the latest fetched price, or user could specify a point in time.
        # Here, we'll simulate a "current" data event.
        # A more robust implementation would fetch live data or allow user input.
        
        # Attempt to get "current" data for the symbol using the data_provider
        # This part is highly dependent on how you want the frontend to behave.
        # Is it analyzing based on the absolute latest tick? Or a user-provided scenario?
        
        # Simplistic "current data" event for now:
        current_data_event = data_provider_instance.get_current_price(symbol)
        if not current_data_event:
            # If get_current_price returns None or empty, create a placeholder
            logger.warning(f"Could not fetch current price for {symbol} via data_provider. Using placeholder.")
            current_data_event = {'symbol': symbol, 'timestamp': datetime.now().isoformat(), 'close': 0} # Minimal data

        # 1. Prepare market data (history + current)
        # The _prepare_market_data method in the strategy might need adjustment
        # if it expects data_event to be a specific structure not provided by get_current_price.
        # Assuming _prepare_market_data can handle a dict from get_current_price
        # or a minimal dict if get_current_price fails.
        
        # The strategy's _prepare_market_data needs data_event as an argument.
        # Let's ensure what `get_current_price` returns is suitable,
        # or adapt it. `get_current_price` for SimulatedDataProvider returns:
        # {'symbol': symbol, 'price': price, 'close': price, 'timestamp': datetime.now().isoformat()}
        # This should be mostly fine for _prepare_market_data's current price needs.

        market_data_for_symbol = strategy_instance._prepare_market_data(symbol, current_data_event)
        
        # 2. Perform technical analysis
        # _perform_technical_analysis expects Dict[str, pd.DataFrame]
        # but _prepare_market_data returns Dict[str, Any] (with 'history' as DataFrame, 'current' as Dict)
        # This type mismatch was handled in _perform_technical_analysis by:
        #   primary_symbol = self.config.get('base_symbol', list(market_data.keys())[0])
        #   history = market_data.get(primary_symbol)
        # This needs careful review. The _perform_technical_analysis expects the *input* `market_data`
        # to be the dict {'symbol': DataFrame, ...}, but _prepare_market_data returns the other structure.
        # For a single symbol analysis triggered by API, we pass the direct output of _prepare_market_data.
        
        # The `_perform_technical_analysis` method in PyramidLLMStrategy has its type hint as:
        # def _perform_technical_analysis(self, market_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        # However, it's called with the output of _prepare_market_data, which is Dict[str, Any]
        # where market_data['history'] is a DataFrame and market_data['current'] is a Dict.
        # Inside _perform_technical_analysis, it does:
        #   primary_symbol = self.config.get('base_symbol', list(market_data.keys())[0])
        #   history = market_data.get(primary_symbol) <-- This would fail if market_data is the dict from _prepare_market_data
        # This part needs correction. _perform_technical_analysis should probably take the actual history DataFrame.

        # Let's assume _perform_technical_analysis needs the historical DataFrame directly for the given symbol.
        # And the 'current' data is already in market_data_for_symbol.
        
        # Correct approach for _perform_technical_analysis given its current implementation:
        # It seems to expect a dict where keys are symbols and values are dataframes.
        # This is a mismatch with how _prepare_market_data (for a single symbol) returns data.
        # We should either:
        # 1. Adapt _perform_technical_analysis to take the output of _prepare_market_data (Dict[str, Any] for one symbol)
        # 2. Or, construct the Dict[str, pd.DataFrame] here.
        
        # For now, let's assume _perform_technical_analysis should be called with the history DataFrame.
        # This part of the strategy logic needs careful alignment.
        # The simplest path for now is to make a small adjustment to how _perform_technical_analysis gets its history.
        # The _perform_technical_analysis was recently edited to:
        # primary_symbol = self.config.get('base_symbol', list(market_data.keys())[0])
        # history = market_data.get(primary_symbol)
        # This is okay if `market_data` passed to it IS Dict[str, pd.DataFrame]
        # But if we are calling for one symbol, the `market_data` for _perform_technical_analysis argument
        # should just be the history DataFrame for that symbol.
        # Let's pass the `market_data_for_symbol['history']` to a potentially refactored technical analysis function,
        # or adjust `_perform_technical_analysis` to directly use `market_data_for_symbol['history']`.

        # Given the existing structure of _perform_technical_analysis, it expects
        # the input `market_data` to be a dict where it can do `market_data.get(primary_symbol)`.
        # So, we should pass it as ` {symbol: market_data_for_symbol['history']} `
        # if `market_data_for_symbol['history']` is the DataFrame.
        
        history_df = market_data_for_symbol.get('history')
        if history_df is None or history_df.empty:
             return jsonify({"error": f"No historical data found for {symbol} to perform technical analysis"}), 404
        
        # Construct the input for _perform_technical_analysis as it currently expects
        # (a dictionary where the key is the symbol and value is its history DataFrame)
        # This assumes `_perform_technical_analysis` is primarily concerned with the history part
        # for its TA calculations, and other parts of `market_data_for_symbol` (like 'current') are used elsewhere.
        technical_analysis_input = {symbol: history_df}
        technical_analysis_result = strategy_instance._perform_technical_analysis(technical_analysis_input)

        if not technical_analysis_result: # It returns {} on failure/no data
            logger.info(f"Technical analysis for {symbol} returned no results.")
            # Fallback or error response
            return jsonify({"symbol": symbol, "opportunity": "unknown", "reason": "Technical analysis failed or insufficient data", "details": {}})
            
        # 3. Find entry opportunity
        # _find_entry_opportunity expects market_data (output of _prepare_market_data) and technical_analysis
        entry_opportunity = strategy_instance._find_entry_opportunity(symbol, market_data_for_symbol, technical_analysis_result)
        
        if not entry_opportunity:
            return jsonify({"error": "Could not determine entry opportunity"}), 500
            
        return jsonify(entry_opportunity)

    except Exception as e:
        logger.error(f"Error in /api/strategy/find_entry/{symbol}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# --- End New API Endpoint ---

# --- New Trading Control API Endpoints ---
@app.route('/api/trading/start', methods=['POST'])
def api_start_trading():
    """启动交易功能"""
    # 这里可以实现真正的交易启动逻辑
    # 例如：
    # 1. 启动实时数据订阅
    # 2. 初始化交易引擎
    # 3. 开始信号生成和订单执行
    
    # 在生产环境中，你应该有一个交易管理器的单例实例
    # 现在我们只是返回一个成功响应
    return jsonify({
        "status": "success",
        "message": "Trading system started",
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/trading/stop', methods=['POST'])
def api_stop_trading():
    """停止交易功能"""
    # 这里实现交易停止逻辑
    return jsonify({
        "status": "success",
        "message": "Trading system stopped",
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/trading/status', methods=['GET'])
def api_trading_status():
    """获取交易系统状态"""
    # 这里应该从交易管理器获取真实状态
    is_trading_active = True  # 在实际应用中这应该是真实的状态检查
    return jsonify({
        "status": "success",
        "is_active": is_trading_active,
        "last_signal_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "active_orders": 0,  # 示例数据，实际应从订单管理器获取
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/trading/signals', methods=['GET'])
def api_trading_signals():
    """获取最近的交易信号"""
    # 这里应该从信号生成器获取真实信号
    # 现在返回模拟数据
    signals = [
        {
            "symbol": "000001.SH",
            "time": (datetime.now() - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S'),
            "action": "BUY",
            "reason": "满足金字塔买入信号条件",
            "price": 3210.45,
            "executed": True
        },
        {
            "symbol": "600000.SH",
            "time": (datetime.now() - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S'),
            "action": "SELL",
            "reason": "触发止损条件",
            "price": 12.75,
            "executed": True
        }
    ]
    return jsonify({
        "status": "success",
        "signals": signals,
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/trading/positions', methods=['GET'])
def api_trading_positions():
    """获取当前持仓信息"""
    # 这里应该从账户管理器获取真实持仓
    positions = [
        {
            "symbol": "000001.SH",
            "quantity": 100,
            "entry_price": 3180.50,
            "current_price": 3210.45,
            "profit_loss": "0.94%"
        }
    ]
    return jsonify({
        "status": "success",
        "positions": positions,
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

# 新增交易页面路由
@app.route('/trading')
def trading_page():
    """交易控制页面"""
    return render_template('trading.html')

# --- End Trading Control API Endpoints ---

# 启动函数
def run_app(port=5000, debug=False):
    """
    启动Flask应用
    
    Args:
        port: 端口号
        debug: 是否开启调试模式
    """
    logger.info(f"启动Web前端，端口: {port}, 调试模式: {debug}")
    app.run(host='0.0.0.0', port=port, debug=debug)

# 主函数
def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="量化交易系统Web前端")
    parser.add_argument("--port", type=int, default=5000, help="服务器端口号")
    parser.add_argument("--debug", action="store_true", help="开启调试模式")
    
    args = parser.parse_args()
    
    # 运行Flask应用
    run_app(port=args.port, debug=args.debug)

if __name__ == "__main__":
    main() 
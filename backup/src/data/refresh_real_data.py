#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
同花顺真实数据刷新脚本
用于清除数据库中的模拟数据，并从同花顺API获取真实市场数据
"""

import os
import sys
import time
import argparse
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, List, Any, Optional
import json
import numpy as np

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# 设置SDK环境变量
sdk_dir = os.path.abspath(os.path.join(project_root, "vendor/ths_sdk/extracted/bin"))
sdk_bin64_dir = os.path.abspath(os.path.join(project_root, "vendor/ths_sdk/extracted/bin64"))

# 添加SDK库目录到LD_LIBRARY_PATH
if "LD_LIBRARY_PATH" in os.environ:
    os.environ["LD_LIBRARY_PATH"] = f"{os.environ['LD_LIBRARY_PATH']}:{sdk_dir}:{sdk_bin64_dir}"
else:
    os.environ["LD_LIBRARY_PATH"] = f"{sdk_dir}:{sdk_bin64_dir}"

print(f"设置SDK路径: {sdk_dir}")
print(f"设置SDK 64位路径: {sdk_bin64_dir}")
print(f"LD_LIBRARY_PATH: {os.environ['LD_LIBRARY_PATH']}")

# 导入项目模块
from src.utils.logger import get_logger
from src.utils.config import get_config
from src.data.db_manager import get_db_manager
from src.data.ths_data_feed import get_ths_data_feed

# 获取logger
logger = get_logger("refresh_real_data")

# 默认配置
DEFAULT_SYMBOLS = [
    # 指数
    "000001.SH",  # 上证指数
    "399001.SZ",  # 深证成指
    "399006.SZ",  # 创业板指
    "000300.SH",  # 沪深300
    "000016.SH",  # 上证50
    # 热门股票
    "600519.SH",  # 贵州茅台
    "000858.SZ",  # 五粮液
    "601318.SH",  # 中国平安
    "600036.SH",  # 招商银行
    "000001.SZ",  # 平安银行
    "600030.SH",  # 中信证券
    "601166.SH",  # 兴业银行
    "600000.SH",  # 浦发银行
    "601398.SH",  # 工商银行
    "601288.SH",  # 农业银行
]

def clear_database_tables(clear_all: bool = False):
    """
    清空数据库表
    
    Args:
        clear_all: 是否清空所有表，默认只清空K线和行情表
    """
    db_manager = get_db_manager()
    
    try:
        # 连接数据库
        db_manager.connect()
        
        # 清空实时行情表
        db_manager.execute_query("DELETE FROM real_time_quotes")
        logger.info("已清空实时行情表")
        
        # 清空K线数据表
        db_manager.execute_query("DELETE FROM kline_data")
        logger.info("已清空K线数据表")
        
        if clear_all:
            # 清空交易标的表
            db_manager.execute_query("DELETE FROM symbols")
            logger.info("已清空交易标的表")
            
            # 清空数据源表
            db_manager.execute_query("DELETE FROM data_sources")
            logger.info("已清空数据源表")
        
        db_manager.conn.commit()
        logger.info("数据库表清空完成")
    except Exception as e:
        db_manager.conn.rollback()
        logger.error(f"清空数据库表时出错: {str(e)}")
    finally:
        # 关闭数据库连接
        db_manager.close()

def initialize_ths_api():
    """
    初始化同花顺数据源
    
    Returns:
        同花顺数据源实例，初始化失败时返回None
    """
    try:
        # 从配置文件获取同花顺API配置
        username = str(get_config("ths_api", "username", ""))
        password = str(get_config("ths_api", "password", ""))
        
        logger.info(f"初始化同花顺SDK API，用户名: {username}")
        
        if not username or not password:
            logger.error("未配置同花顺用户名或密码")
            return None
        
        # 使用数据源工厂创建SDK数据源
        ths_data_feed = get_ths_data_feed(
            api_type="sdk",
            username=username,
            password=password,
            force_new=True
        )
        
        logger.info("初始化同花顺SDK数据源成功")
        return ths_data_feed
    except Exception as e:
        logger.error(f"初始化同花顺SDK数据源失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def fetch_and_save_symbols(ths_api):
    """
    获取并保存股票和指数列表
    
    Args:
        ths_api: 同花顺数据源实例，如为None则使用默认列表
    """
    db_manager = get_db_manager()
    
    try:
        # 获取指数列表 - 由于SDK可能没有直接获取列表的函数，这里使用默认指数列表
        index_list = [
            {"code": "000001.SH", "name": "上证指数", "exchange": "SH"},
            {"code": "399001.SZ", "name": "深证成指", "exchange": "SZ"},
            {"code": "399006.SZ", "name": "创业板指", "exchange": "SZ"},
            {"code": "000300.SH", "name": "沪深300", "exchange": "SH"},
            {"code": "000016.SH", "name": "上证50", "exchange": "SH"},
            {"code": "000905.SH", "name": "中证500", "exchange": "SH"},
            {"code": "000852.SH", "name": "中证1000", "exchange": "SH"}
        ]
        
        # 获取热门股票列表 - 同样使用默认列表
        stock_list = [
            {"code": "600519.SH", "name": "贵州茅台", "exchange": "SH"},
            {"code": "000858.SZ", "name": "五粮液", "exchange": "SZ"},
            {"code": "601318.SH", "name": "中国平安", "exchange": "SH"},
            {"code": "600036.SH", "name": "招商银行", "exchange": "SH"},
            {"code": "000001.SZ", "name": "平安银行", "exchange": "SZ"},
            {"code": "600030.SH", "name": "中信证券", "exchange": "SH"},
            {"code": "601166.SH", "name": "兴业银行", "exchange": "SH"},
            {"code": "600000.SH", "name": "浦发银行", "exchange": "SH"},
            {"code": "601398.SH", "name": "工商银行", "exchange": "SH"},
            {"code": "601288.SH", "name": "农业银行", "exchange": "SH"}
        ]
        
        # 如果有API连接，尝试获取更多股票信息（未来扩展）
        if ths_api is not None:
            # 目前直接使用默认列表，未来可扩展为从API获取完整列表
            pass
        else:
            logger.info("无同花顺API连接，使用默认股票和指数列表")
        
        # 准备保存的数据
        symbols = []
        
        # 处理股票
        for stock in stock_list:
            symbols.append({
                "symbol": stock["code"],
                "name": stock["name"],
                "exchange": stock["exchange"],
                "category": "STOCK",
                "status": "active"
            })
        
        # 处理指数
        for index in index_list:
            symbols.append({
                "symbol": index["code"],
                "name": index["name"],
                "exchange": index["exchange"],
                "category": "INDEX",
                "status": "active"
            })
        
        # 保存到数据库
        logger.info(f"保存{len(symbols)}个交易标的到数据库...")
        count = db_manager.insert_symbols(symbols)
        logger.info(f"成功保存{count}个交易标的")
        
    except Exception as e:
        logger.error(f"获取并保存股票和指数列表失败: {str(e)}")

def fetch_and_save_kline_data(ths_api, symbols: List[str], days: int = 365, timeframes: List[str] = None):
    """
    获取并保存K线数据
    
    Args:
        ths_api: 同花顺数据源实例
        symbols: 交易标的代码列表
        days: 获取最近多少天的数据
        timeframes: 时间周期列表，默认为日线
    """
    db_manager = get_db_manager()
    
    # 默认只获取日线数据
    if timeframes is None:
        timeframes = ["D"]
    
    # 计算开始日期 - 需要 YYYY-MM-DD 格式
    end_date_dt = datetime.now()
    start_date_dt = end_date_dt - timedelta(days=days)
    
    end_date_str = end_date_dt.strftime("%Y-%m-%d")
    start_date_str = start_date_dt.strftime("%Y-%m-%d")
    
    logger.info(f"获取K线数据，周期: {timeframes}, 日期范围: {start_date_str} - {end_date_str}")
    
    # 检查SDK环境变量
    logger.info(f"LD_LIBRARY_PATH: {os.environ.get('LD_LIBRARY_PATH', '未设置')}")
    sdk_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "vendor/ths_sdk/extracted/bin"))
    logger.info(f"SDK目录: {sdk_dir}, 存在: {os.path.exists(sdk_dir)}")
    
    # 确保导入了THS功能
    try:
        from iFinDPy import THS_HistoryQuotes, THS_iFinDLogin, THS_iFinDLogout
        
        # 确保已登录
        from src.utils.config import get_config
        username = str(get_config("ths_api", "username", ""))
        password = str(get_config("ths_api", "password", ""))
        logger.info(f"重新登录同花顺API: {username}")
        login_result = THS_iFinDLogin(username, password)
        logger.info(f"登录结果: {login_result}")
        
        if login_result != 0:
            logger.error(f"登录失败，错误码: {login_result}")
            return
        
        total_count = 0
        for symbol in symbols:
            try:
                for tf in timeframes:
                    # 目前仅支持日线数据
                    if tf != "D":
                        logger.warning(f"当前只支持日线数据，跳过 {tf} 周期")
                        continue
                    
                    # 转换timeframe格式
                    db_tf = "1d" 
                    ths_period_option = "period:D" # For THS_HistoryQuotes options
                    
                    logger.info(f"获取标的 {symbol} 的 {tf} 周期K线数据...")
                    
                    indicators = "open;high;low;close;volume;amount"
                    options = f"{ths_period_option};format:json" # format:json might not be needed if we always decode bytes

                    try:
                        history_quotes_result = THS_HistoryQuotes(
                            symbol,
                            indicators,
                            "",  # Empty string for indicator-specific params
                            start_date_str, 
                            end_date_str,
                            options 
                        )
                        
                        logger.info(f"THS_HistoryQuotes返回数据类型: {type(history_quotes_result)} for symbol {symbol}")

                        # 处理可能的bytes类型的返回值
                        if isinstance(history_quotes_result, bytes):
                            try:
                                decoded_string = history_quotes_result.decode('utf-8')
                                # logger.debug(f"成功解码bytes: {decoded_string[:500]}...") 
                                history_quotes_result = json.loads(decoded_string)
                                logger.info(f"成功解析bytes为JSON for symbol {symbol}")
                            except Exception as e:
                                logger.error(f"解析bytes失败 for symbol {symbol}: {str(e)}")
                                history_quotes_result = {"errorcode": -99, "errmsg": f"Failed to decode/parse bytes response: {e}"}
                        
                        # 检查返回结果
                        if isinstance(history_quotes_result, dict) and history_quotes_result.get('errorcode') == 0:
                            logger.info(f"THS_HistoryQuotes成功获取数据: {symbol}")
                            
                            if 'tables' in history_quotes_result and history_quotes_result['tables']:
                                data_content = history_quotes_result['tables'][0] # First table usually has the data
                                
                                if 'table' in data_content and 'time' in data_content:
                                    kline_table = data_content['table']
                                    dates = data_content['time']
                                    
                                    # Ensure all necessary fields are present
                                    required_fields = ['open', 'high', 'low', 'close', 'volume', 'amount']
                                    if not all(field in kline_table for field in required_fields):
                                        logger.warning(f"返回数据缺少必要字段 for symbol {symbol}. Fields: {kline_table.keys()}")
                                        continue

                                    formatted_data = []
                                    num_records = len(dates)

                                    for i in range(num_records):
                                        record_date_str = dates[i]
                                        try:
                                            # Ensure date is in YYYY-MM-DD format for the database
                                            record_date = datetime.strptime(record_date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
                                        except ValueError:
                                            try: # Try YYYYMMDD if first parse fails
                                                record_date = datetime.strptime(record_date_str, "%Y%m%d").strftime("%Y-%m-%d")
                                            except ValueError:
                                                logger.warning(f"日期格式无法解析: {record_date_str} for symbol {symbol}. 跳过此记录.")
                                                continue
                                        
                                        try:
                                            record = {
                                                "date": record_date,
                                                "open": float(kline_table['open'][i]),
                                                "high": float(kline_table['high'][i]),
                                                "low": float(kline_table['low'][i]),
                                                "close": float(kline_table['close'][i]),
                                                "volume": int(kline_table['volume'][i]),
                                                "amount": float(kline_table['amount'][i])
                                            }
                                            formatted_data.append(record)
                                        except (ValueError, TypeError, IndexError) as e_val:
                                            logger.warning(f"数据转换错误 for symbol {symbol}, date {record_date_str}: {e_val}. Record: { {k: kline_table[k][i] for k in required_fields if k in kline_table and i < len(kline_table[k])} }")
                                            continue # Skip this problematic record
                                    
                                    if formatted_data:
                                        count = db_manager.insert_kline_data(
                                            symbol=symbol,
                                            kline_data=formatted_data,
                                            timeframe=db_tf, # e.g., "1d"
                                            source="ths_sdk"
                                        )
                                        logger.info(f"成功保存{count}条{tf}周期K线数据，标的: {symbol}")
                                        total_count += count
                                    else:
                                        logger.info(f"没有格式化数据可保存 for symbol {symbol}")
                                else:
                                    logger.warning(f"THS_HistoryQuotes返回数据结构不符合预期 ('table' or 'time' missing) for symbol {symbol}")
                            else:
                                logger.warning(f"THS_HistoryQuotes返回结果没有tables或tables为空 for symbol {symbol}")
                        else:
                            error_msg = history_quotes_result.get('errmsg', '未知错误') if isinstance(history_quotes_result, dict) else '响应不是字典'
                            logger.warning(f"THS_HistoryQuotes返回错误 for symbol {symbol}: {error_msg}")
                    except Exception as e:
                        logger.error(f"使用THS_HistoryQuotes获取数据失败 for symbol {symbol}: {str(e)}")
                        import traceback
                        logger.error(traceback.format_exc())
                
                # 避免频繁请求
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"获取并保存标的 {symbol} 的K线数据失败: {str(e)}")
        
        logger.info(f"K线数据获取完成，共保存{total_count}条记录")
        
    except Exception as e:
        logger.error(f"导入或初始化THS_HistoryQuotes失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

def fetch_and_save_realtime_quotes(ths_api, symbols: List[str]):
    """
    获取并保存实时行情数据
    
    Args:
        ths_api: 同花顺数据源实例
        symbols: 交易标的代码列表
    """
    db_manager = get_db_manager()
    
    logger.info(f"获取{len(symbols)}个标的的实时行情...")
    
    success_count = 0
    for symbol in symbols:
        try:
            # 直接使用iFinDPy模块获取实时行情
            try:
                # 导入iFinDPy模块
                from iFinDPy import THS_RealtimeQuotes, THS_iFinDLogin, THS_iFinDLogout
                
                # 确保已登录
                from src.utils.config import get_config
                username = str(get_config("ths_api", "username", ""))
                password = str(get_config("ths_api", "password", ""))
                logger.info(f"尝试重新登录同花顺API: {username}")
                login_result = THS_iFinDLogin(username, password)
                logger.info(f"登录结果: {login_result}")
                
                # 尝试不同方式获取实时行情
                success = False
                
                # 方式1: 标准参数方式 - 按照官方文档
                logger.info(f"尝试方式1: 官方标准参数方式 - 获取 {symbol} 的实时行情...")
                try:
                    indicators = "open;high;low;now;volume;amount;turnover;pe;pb"
                    params = "pricetype:1,Ispandas:1"
                    quote_result = THS_RealtimeQuotes(
                        symbol,          # thscode
                        indicators,      # jsonIndicator
                        params,          # jsonparam
                        False            # outflag
                    )
                    
                    # 处理返回的bytes类型数据
                    if isinstance(quote_result, bytes):
                        try:
                            import json
                            quote_result = json.loads(quote_result.decode('utf-8'))
                            logger.info(f"方式1: 成功解析实时行情bytes数据")
                            success = True
                        except Exception as e:
                            logger.error(f"方式1: 解析实时行情bytes数据失败: {str(e)}")
                except Exception as e:
                    logger.error(f"方式1: 调用实时行情失败: {str(e)}")
                
                # 方式2: 最简参数方式
                if not success:
                    logger.info(f"尝试方式2: 最简参数方式 - 获取 {symbol} 的实时行情...")
                    try:
                        quote_result = THS_RealtimeQuotes(
                            symbol,        # thscode
                            "now",         # jsonIndicator
                            ""             # jsonparam
                        )
                        
                        if isinstance(quote_result, bytes):
                            try:
                                import json
                                quote_result = json.loads(quote_result.decode('utf-8'))
                                logger.info(f"方式2: 成功解析实时行情bytes数据")
                                success = True
                            except Exception as e:
                                logger.error(f"方式2: 解析实时行情bytes数据失败: {str(e)}")
                    except Exception as e:
                        logger.error(f"方式2: 调用实时行情失败: {str(e)}")
                
                # 检查是否成功获取数据
                if not success:
                    logger.error(f"所有尝试都失败，无法获取 {symbol} 的实时行情")
                    continue
                
                # 检查是否有错误信息
                if isinstance(quote_result, dict) and quote_result.get('errorcode', -1) != 0:
                    logger.warning(f"获取标的 {symbol} 的实时行情失败: {quote_result.get('errmsg', '未知错误')}")
                    continue
                
                # 解析数据
                if isinstance(quote_result, dict):
                    # 检查是否有tables字段
                    if 'tables' in quote_result and len(quote_result['tables']) > 0:
                        data = quote_result['tables'][0]
                        if len(data) > 0:
                            # 获取第一条数据
                            item = data[0]
                            logger.info(f"成功获取 {symbol} 的实时行情数据: {item}")
                            
                            # 构建标准格式的行情数据
                            quote = {
                                "symbol": symbol,
                                "price": float(item.get("now", 0)),
                                "open": float(item.get("open", 0)),
                                "high": float(item.get("high", 0)),
                                "low": float(item.get("low", 0)),
                                "volume": float(item.get("volume", 0)),
                                "amount": float(item.get("amount", 0)),
                                "turnover": float(item.get("turnoverRatio", 0)),
                                "pe": float(item.get("pe", 0)),
                                "pb": float(item.get("pb", 0)),
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            
                            # 检查价格有效性
                            if quote["price"] <= 0:
                                logger.warning(f"跳过无效数据: {symbol}, 价格为 {quote['price']}")
                                continue
                            
                            # 保存到数据库
                            success = db_manager.update_real_time_quote(
                                symbol=symbol,
                                quote_data=quote,
                                source="ths_sdk"
                            )
                            
                            if success:
                                success_count += 1
                                logger.info(f"成功保存标的 {symbol} 的实时行情")
                            else:
                                logger.warning(f"保存标的 {symbol} 的实时行情到数据库失败")
                        else:
                            logger.warning(f"获取标的 {symbol} 的实时行情失败: 数据为空")
                    else:
                        logger.warning(f"获取标的 {symbol} 的实时行情失败: 未找到表格数据")
                else:
                    logger.warning(f"获取标的 {symbol} 的实时行情失败: 返回格式不支持: {type(quote_result)}")
                    
            except Exception as e:
                logger.error(f"直接调用THS_RealtimeQuotes获取数据失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            
            # 避免频繁请求
            time.sleep(0.2)
            
        except Exception as e:
            logger.error(f"获取并保存标的 {symbol} 的实时行情失败: {str(e)}")
    
    logger.info(f"实时行情获取完成，成功保存{success_count}条记录")

def register_ths_as_data_source():
    """
    注册同花顺作为数据源
    """
    db_manager = get_db_manager()
    
    try:
        # 获取同花顺API配置
        from src.utils.config import get_config
        
        # 创建配置字典，确保所有值都是字符串类型
        config = {
            "api_type": "sdk",
            "username": str(get_config("ths_api", "username", "")),
            "password": str(get_config("ths_api", "password", "")),
            "sdk_path": str(get_config("ths_api", "sdk_path", ""))
        }
        
        # 将config转换为JSON字符串
        config_str = json.dumps(config)
        
        success = db_manager.register_data_source(
            name="ths_sdk",
            source_type="ths_sdk",
            config=config_str
        )
        
        if success:
            logger.info("成功注册同花顺作为数据源")
        else:
            logger.error("注册同花顺作为数据源失败")
            
    except Exception as e:
        logger.error(f"注册同花顺作为数据源时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

def get_all_db_symbols() -> List[str]:
    """
    获取数据库中所有交易标的
    
    Returns:
        标的代码列表
    """
    db_manager = get_db_manager()
    symbols = db_manager.get_symbols()
    return [s["symbol"] for s in symbols]

def generate_and_save_mock_data(symbols: List[str], days: int = 365, timeframes: List[str] = None):
    """
    生成并保存模拟数据，用于在同花顺API无法访问时提供测试数据
    
    Args:
        symbols: 交易标的代码列表
        days: 生成最近多少天的数据
        timeframes: 时间周期列表，默认为日线
    """
    db_manager = get_db_manager()
    
    # 默认只生成日线数据
    if timeframes is None:
        timeframes = ["D"]
    
    # 计算开始日期
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    logger.info(f"生成模拟K线数据，周期: {timeframes}, 日期范围: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    total_count = 0
    for symbol in symbols:
        try:
            for tf in timeframes:
                # 转换timeframe格式
                db_tf = "1d" if tf == "D" else "1w" if tf == "W" else "1m" if tf == "M" else tf
                
                logger.info(f"生成标的 {symbol} 的 {tf} 周期模拟K线数据...")
                
                # 生成日期序列
                date_range = pd.date_range(start=start_date, end=end_date, freq='D')
                if tf == "W":
                    date_range = pd.date_range(start=start_date, end=end_date, freq='W')
                elif tf == "M":
                    date_range = pd.date_range(start=start_date, end=end_date, freq='M')
                
                # 生成模拟价格和成交量数据
                np.random.seed(hash(symbol) % 100000)  # 使用标的代码作为随机种子
                
                # 起始价格 (50-500之间的随机值)
                base_price = np.random.uniform(50, 500)
                
                # 生成价格变动
                volatility = np.random.uniform(0.01, 0.05)  # 1%-5%的波动率
                returns = np.random.normal(0, volatility, len(date_range))
                price_changes = base_price * returns
                
                # 构建OHLCV数据
                formatted_data = []
                current_price = base_price
                
                for i, date in enumerate(date_range):
                    if date.weekday() >= 5:  # 跳过周末
                        continue
                        
                    # 更新价格
                    current_price += price_changes[i]
                    if current_price < 1:
                        current_price = np.random.uniform(1, 10)
                    
                    # 生成当日OHLC
                    daily_vol = np.random.uniform(0.005, 0.03)  # 0.5%-3%的日内波动
                    open_price = current_price * (1 + np.random.uniform(-daily_vol, daily_vol))
                    high_price = max(open_price, current_price) * (1 + np.random.uniform(0, daily_vol))
                    low_price = min(open_price, current_price) * (1 - np.random.uniform(0, daily_vol))
                    
                    # 生成成交量 (基于价格的相对波动)
                    volume = np.random.randint(100000, 10000000)  # 10万-1000万股
                    amount = volume * current_price  # 成交额
                    
                    formatted_data.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "open": round(open_price, 2),
                        "high": round(high_price, 2),
                        "low": round(low_price, 2),
                        "close": round(current_price, 2),
                        "volume": int(volume),
                        "amount": round(amount, 2)
                    })
                
                # 保存到数据库
                count = db_manager.insert_kline_data(
                    symbol=symbol,
                    kline_data=formatted_data,
                    timeframe=db_tf,
                    source="mock_data"
                )
                
                logger.info(f"成功保存{count}条模拟{tf}周期K线数据，标的: {symbol}")
                total_count += count
                
        except Exception as e:
            logger.error(f"生成并保存标的 {symbol} 的模拟K线数据失败: {str(e)}")
    
    logger.info(f"模拟K线数据生成完成，共保存{total_count}条记录")
    
    # 生成并保存实时行情
    generate_and_save_mock_realtime_quotes(symbols)

def generate_and_save_mock_realtime_quotes(symbols: List[str]):
    """
    生成并保存模拟实时行情数据
    
    Args:
        symbols: 交易标的代码列表
    """
    db_manager = get_db_manager()
    
    logger.info(f"生成{len(symbols)}个标的的模拟实时行情...")
    
    success_count = 0
    for symbol in symbols:
        try:
            # 获取该标的最新的K线数据作为基准
            kline_data = db_manager.get_kline_data(symbol, 
                                                (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"), 
                                                datetime.now().strftime("%Y-%m-%d"))
            
            if len(kline_data) > 0:
                close_price = float(kline_data['close'].iloc[-1])
            else:
                # 如果没有K线数据，生成随机价格
                np.random.seed(hash(symbol) % 100000)
                close_price = round(np.random.uniform(50, 500), 2)
            
            # 生成模拟实时行情
            daily_vol = np.random.uniform(0.002, 0.01)  # 0.2%-1%的日内波动
            current_price = close_price * (1 + np.random.uniform(-daily_vol, daily_vol))
            open_price = close_price * (1 + np.random.uniform(-daily_vol, daily_vol))
            high_price = max(open_price, current_price) * (1 + np.random.uniform(0, daily_vol))
            low_price = min(open_price, current_price) * (1 - np.random.uniform(0, daily_vol))
            
            # 生成成交量和成交额
            volume = np.random.randint(100000, 5000000)  # 10万-500万股
            amount = volume * current_price  # 成交额
            
            # 生成涨跌幅
            change_amount = current_price - close_price
            change_percent = (change_amount / close_price) * 100 if close_price > 0 else 0
            
            # 构建行情数据
            quote = {
                "symbol": symbol,
                "price": round(current_price, 2),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "volume": int(volume),
                "amount": round(amount, 2),
                "turnover": round(np.random.uniform(0.5, 5), 2),  # 0.5%-5%的换手率
                "pe": round(np.random.uniform(10, 50), 2),  # 10-50的市盈率
                "pb": round(np.random.uniform(1, 10), 2),  # 1-10的市净率
                "change_amount": round(change_amount, 2),
                "change_percent": round(change_percent, 2),
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 保存到数据库
            success = db_manager.update_real_time_quote(
                symbol=symbol,
                quote_data=quote,
                source="mock_data"
            )
            
            if success:
                success_count += 1
                logger.debug(f"成功保存标的 {symbol} 的模拟实时行情")
                
        except Exception as e:
            logger.error(f"生成并保存标的 {symbol} 的模拟实时行情失败: {str(e)}")
    
    logger.info(f"模拟实时行情生成完成，成功保存{success_count}条记录")

def main():
    """
    主函数
    """
    # 检查SDK环境变量是否正确设置
    try:
        # 获取项目根目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        
        # 检查SDK库路径是否存在
        sdk_dir = os.path.abspath(os.path.join(project_root, "vendor/ths_sdk/extracted/bin"))
        sdk_bin64_dir = os.path.abspath(os.path.join(project_root, "vendor/ths_sdk/extracted/bin64"))
        
        if not os.path.exists(sdk_dir) or not os.path.exists(sdk_bin64_dir):
            logger.warning(f"SDK路径不存在: {sdk_dir} 或 {sdk_bin64_dir}")
            logger.warning("请确保已解压同花顺SDK安装包到vendor/ths_sdk/extracted目录")
        else:
            # 将SDK路径添加到环境变量
            if "LD_LIBRARY_PATH" in os.environ:
                if sdk_dir not in os.environ["LD_LIBRARY_PATH"] or sdk_bin64_dir not in os.environ["LD_LIBRARY_PATH"]:
                    os.environ["LD_LIBRARY_PATH"] = f"{os.environ['LD_LIBRARY_PATH']}:{sdk_dir}:{sdk_bin64_dir}"
                    logger.info(f"已更新LD_LIBRARY_PATH: {os.environ['LD_LIBRARY_PATH']}")
            else:
                os.environ["LD_LIBRARY_PATH"] = f"{sdk_dir}:{sdk_bin64_dir}"
                logger.info(f"已设置LD_LIBRARY_PATH: {os.environ['LD_LIBRARY_PATH']}")
    except Exception as e:
        logger.error(f"设置SDK环境变量出错: {str(e)}")
    
    # 命令行参数解析
    parser = argparse.ArgumentParser(description="同花顺真实数据刷新脚本")
    parser.add_argument("--clear-all", action="store_true", help="清空所有表（包括符号表和数据源表）")
    parser.add_argument("--symbols", action="store_true", help="刷新交易标的列表")
    parser.add_argument("--kline", action="store_true", help="刷新K线数据")
    parser.add_argument("--quotes", action="store_true", help="刷新实时行情")
    parser.add_argument("--days", type=int, default=365, help="获取最近多少天的K线数据")
    parser.add_argument("--timeframes", type=str, default="D", help="获取哪些周期的K线数据，用逗号分隔（如D,W,M）")
    parser.add_argument("--all", action="store_true", help="刷新所有数据")
    parser.add_argument("--mock", action="store_true", help="使用模拟数据，不连接同花顺API")
    parser.add_argument("--force-real", action="store_true", help="强制使用真实API，即使测试连接失败")
    
    args = parser.parse_args()
    
    # 如果没有指定任何操作，默认刷新所有
    if not (args.symbols or args.kline or args.quotes) and not args.all:
        args.all = True
    
    # 清空数据库表
    clear_database_tables(args.clear_all)
    
    # 解析时间周期
    timeframes = args.timeframes.split(",") if args.timeframes else ["D"]
    
    # 如果指定使用模拟数据，直接生成模拟数据
    if args.mock:
        logger.info("使用模拟数据模式")
        using_mock = True
    else:
        # 测试同花顺API连接
        using_mock = False
        try:
            # 导入iFinDPy模块，测试连接
            logger.info("测试同花顺API连接...")
            import importlib
            ifindpy_spec = importlib.util.find_spec("iFinDPy")
            if not ifindpy_spec:
                logger.error("未找到iFinDPy模块，将使用模拟数据")
                using_mock = True
            else:
                try:
                    from iFinDPy import THS_iFinDLogin, THS_iFinDLogout
                    # 从配置文件获取同花顺API配置
                    username = str(get_config("ths_api", "username", ""))
                    password = str(get_config("ths_api", "password", ""))
                    
                    if not username or not password:
                        logger.error("未配置同花顺用户名或密码，将使用模拟数据")
                        using_mock = True
                    else:
                        # 尝试登录
                        login_result = THS_iFinDLogin(username, password)
                        logger.info(f"同花顺API登录测试结果: {login_result}")
                        
                        if login_result != 0:
                            logger.error(f"同花顺API登录失败，错误码: {login_result}，将使用模拟数据")
                            using_mock = True
                        else:
                            logger.info("同花顺API登录成功，将使用真实数据")
                            # 登出
                            THS_iFinDLogout()
                except Exception as e:
                    logger.error(f"测试同花顺API连接时出错: {str(e)}")
                    logger.error("将使用模拟数据")
                    using_mock = True
        except Exception as e:
            logger.error(f"导入iFinDPy模块失败: {str(e)}")
            logger.error("将使用模拟数据")
            using_mock = True
    
    # 如果强制使用真实API，则忽略连接测试结果
    if args.force_real:
        logger.info("强制使用真实API，忽略连接测试结果")
        using_mock = False
    
    # 根据决定的模式进行数据获取
    if using_mock:
        # 注册模拟数据源
        db_manager = get_db_manager()
        mock_desc = "模拟数据，用于测试" if args.mock else "模拟数据，用于测试（API连接失败自动替代）"
        db_manager.register_data_source(
            name="mock_data",
            source_type="mock",
            config={"description": mock_desc}
        )
        
        # 刷新交易标的列表 - 使用默认列表
        if args.symbols or args.all:
            fetch_and_save_symbols(None)
        
        # 获取交易标的列表
        symbols_for_data = DEFAULT_SYMBOLS
        if not args.symbols and not args.all:
            symbols_for_data = get_all_db_symbols()
            if not symbols_for_data:
                symbols_for_data = DEFAULT_SYMBOLS
        
        # 生成并保存模拟数据
        if args.kline or args.all:
            generate_and_save_mock_data(symbols_for_data, days=args.days, timeframes=timeframes)
        
        # 生成模拟实时行情
        if args.quotes or args.all:
            generate_and_save_mock_realtime_quotes(symbols_for_data)
        
        logger.info("模拟数据刷新完成")
    else:
        # 使用真实API获取数据
        # 初始化同花顺API
        ths_api = initialize_ths_api()
        
        # 注册同花顺作为数据源
        register_ths_as_data_source()
        
        # 刷新交易标的列表
        if args.symbols or args.all:
            fetch_and_save_symbols(ths_api)
        
        # 获取交易标的列表
        symbols_for_data = DEFAULT_SYMBOLS
        if not args.symbols and not args.all:
            symbols_for_data = get_all_db_symbols()
            if not symbols_for_data:
                symbols_for_data = DEFAULT_SYMBOLS
        
        # 刷新K线数据
        if args.kline or args.all:
            fetch_and_save_kline_data(ths_api, symbols_for_data, days=args.days, timeframes=timeframes)
        
        # 刷新实时行情
        if args.quotes or args.all:
            fetch_and_save_realtime_quotes(ths_api, symbols_for_data)
        
        logger.info("真实数据刷新完成")

if __name__ == "__main__":
    main() 
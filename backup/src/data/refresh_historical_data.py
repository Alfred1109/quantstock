#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
同花顺历史数据定时获取脚本
每日自动获取前一交易日的历史K线数据
"""

import os
import sys
import time
import argparse
from datetime import datetime, timedelta
import logging
import pandas as pd
import json

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

# 导入项目模块
from src.utils.logger import get_logger
from src.utils.config import get_config
from src.data.db_manager import get_db_manager
from src.data.ths_data_feed import get_ths_data_feed
from src.data.refresh_real_data import DEFAULT_SYMBOLS, initialize_ths_api, register_ths_as_data_source

# 获取logger
logger = get_logger("refresh_historical_data")

def is_trading_day(date_str):
    """
    判断是否为交易日（简化判断，仅排除周末）
    
    Args:
        date_str: 日期字符串，格式为YYYY-MM-DD
        
    Returns:
        是交易日返回True，否则返回False
    """
    # 将日期字符串转换为datetime对象
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    
    # 简单判断是否为周末
    return date_obj.weekday() < 5  # 0-4为周一至周五

def get_previous_trading_day(days_back=1):
    """
    获取前N个交易日的日期
    
    Args:
        days_back: 向前推多少个交易日，默认为1
        
    Returns:
        交易日日期字符串，格式为YYYY-MM-DD
    """
    # 从当前日期开始计算
    current_date = datetime.now()
    
    # 找到前N个交易日
    trading_days_found = 0
    while trading_days_found < days_back:
        current_date = current_date - timedelta(days=1)
        # 判断是否为交易日
        if is_trading_day(current_date.strftime("%Y-%m-%d")):
            trading_days_found += 1
    
    return current_date.strftime("%Y-%m-%d")

def fetch_single_day_kline_data(ths_api, symbols, date_str, timeframes=None):
    """
    获取并保存指定日期的K线数据
    
    Args:
        ths_api: 同花顺数据源实例
        symbols: 交易标的代码列表
        date_str: 日期字符串，格式为YYYY-MM-DD
        timeframes: 时间周期列表，默认为日线
    """
    db_manager = get_db_manager()
    
    # 默认只获取日线数据
    if timeframes is None:
        timeframes = ["D"]
    
    logger.info(f"获取日期 {date_str} 的K线数据，周期: {timeframes}")
    
    # 确保导入了THS功能
    try:
        from iFinDPy import THS_HistoryQuotes, THS_iFinDLogin, THS_iFinDLogout
        
        # 确保已登录
        from src.utils.config import get_config
        username = str(get_config("ths_api", "username", ""))
        password = str(get_config("ths_api", "password", ""))
        logger.info(f"登录同花顺API: {username}")
        login_result = THS_iFinDLogin(username, password)
        logger.info(f"登录结果: {login_result}")
        
        if login_result != 0:
            logger.error(f"登录失败，错误码: {login_result}")
            return 0  # 返回0表示没有获取到数据
        
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
                    ths_period_option = "period:D"
                    
                    logger.info(f"获取标的 {symbol} 的 {date_str} K线数据...")
                    
                    indicators = "open;high;low;close;volume;amount"
                    options = f"{ths_period_option};format:json"

                    try:
                        history_quotes_result = THS_HistoryQuotes(
                            symbol,
                            indicators,
                            "",
                            date_str,  # 开始日期和结束日期都是同一天
                            date_str, 
                            options 
                        )
                        
                        logger.info(f"THS_HistoryQuotes返回数据类型: {type(history_quotes_result)}")

                        # 处理可能的bytes类型的返回值
                        if isinstance(history_quotes_result, bytes):
                            try:
                                decoded_string = history_quotes_result.decode('utf-8')
                                history_quotes_result = json.loads(decoded_string)
                                logger.info(f"成功解析bytes为JSON，symbol={symbol}")
                            except Exception as e:
                                logger.error(f"解析bytes失败: {str(e)}")
                                history_quotes_result = {"errorcode": -99, "errmsg": f"Failed to decode/parse bytes response: {e}"}
                        
                        # 检查返回结果
                        if isinstance(history_quotes_result, dict) and history_quotes_result.get('errorcode') == 0:
                            logger.info(f"THS_HistoryQuotes成功获取数据: {symbol}")
                            
                            if 'tables' in history_quotes_result and history_quotes_result['tables']:
                                data_content = history_quotes_result['tables'][0]
                                
                                if 'table' in data_content and 'time' in data_content:
                                    kline_table = data_content['table']
                                    dates = data_content['time']
                                    
                                    # 确保所需字段都存在
                                    required_fields = ['open', 'high', 'low', 'close', 'volume', 'amount']
                                    if not all(field in kline_table for field in required_fields):
                                        logger.warning(f"返回数据缺少必要字段: {kline_table.keys()}")
                                        continue

                                    # 确保有数据返回
                                    if not dates:
                                        logger.warning(f"日期 {date_str} 没有数据: {symbol}")
                                        continue
                                        
                                    formatted_data = []
                                    num_records = len(dates)

                                    for i in range(num_records):
                                        record_date_str = dates[i]
                                        
                                        # 确保日期格式正确
                                        try:
                                            record_date = datetime.strptime(record_date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
                                        except ValueError:
                                            try:
                                                record_date = datetime.strptime(record_date_str, "%Y%m%d").strftime("%Y-%m-%d")
                                            except ValueError:
                                                logger.warning(f"日期格式无法解析: {record_date_str}")
                                                continue
                                        
                                        # 构建K线记录
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
                                            logger.warning(f"数据转换错误: {e_val}")
                                            continue
                                    
                                    # 保存到数据库
                                    if formatted_data:
                                        count = db_manager.insert_kline_data(
                                            symbol=symbol,
                                            kline_data=formatted_data,
                                            timeframe=db_tf,
                                            source="ths_sdk"
                                        )
                                        logger.info(f"成功保存{count}条{tf}周期K线数据，标的: {symbol}, 日期: {date_str}")
                                        total_count += count
                                    else:
                                        logger.warning(f"没有有效数据可保存: {symbol}, 日期: {date_str}")
                                else:
                                    logger.warning(f"数据结构不符合预期: {symbol}")
                            else:
                                logger.warning(f"返回结果没有tables或tables为空: {symbol}")
                        else:
                            error_msg = history_quotes_result.get('errmsg', '未知错误') if isinstance(history_quotes_result, dict) else '响应不是字典'
                            logger.warning(f"THS_HistoryQuotes返回错误: {error_msg}")
                    except Exception as e:
                        logger.error(f"获取数据失败: {str(e)}")
                        import traceback
                        logger.error(traceback.format_exc())
                
                # 避免频繁请求
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"处理标的 {symbol} 时出错: {str(e)}")
        
        # 登出
        THS_iFinDLogout()
        logger.info("已成功登出同花顺API")
        
        return total_count
        
    except Exception as e:
        logger.error(f"初始化THS_HistoryQuotes失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return 0

def verify_data_integrity(db_manager, symbol, date_str):
    """
    验证数据完整性
    
    Args:
        db_manager: 数据库管理器实例
        symbol: 交易标的代码
        date_str: 日期字符串
        
    Returns:
        数据完整返回True，否则返回False
    """
    try:
        # 获取该日期的K线数据
        data = db_manager.get_kline_data(symbol, date_str, date_str)
        
        # 检查是否有数据
        if len(data) == 0:
            logger.warning(f"数据完整性检查: {symbol} 在 {date_str} 没有数据")
            return False
        
        # 检查数据字段是否完整
        required_fields = ['open', 'high', 'low', 'close', 'volume']
        for field in required_fields:
            if field not in data.columns or data[field].isnull().any():
                logger.warning(f"数据完整性检查: {symbol} 在 {date_str} 缺少字段 {field}")
                return False
        
        return True
    except Exception as e:
        logger.error(f"验证数据完整性时出错: {str(e)}")
        return False

def update_data_source_status(db_manager, name, status, last_update=None):
    """
    更新数据源状态
    
    Args:
        db_manager: 数据库管理器实例
        name: 数据源名称
        status: 状态
        last_update: 最后更新时间
    """
    try:
        if last_update is None:
            last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        result = db_manager.update_data_source_status(name, status, last_update)
        if result:
            logger.info(f"数据源 {name} 状态已更新为 {status}")
        else:
            logger.warning(f"数据源 {name} 状态更新失败")
    except Exception as e:
        logger.error(f"更新数据源状态时出错: {str(e)}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="同花顺历史数据定时获取脚本")
    parser.add_argument("--date", type=str, help="指定获取的日期，格式为YYYY-MM-DD，默认为前一交易日")
    parser.add_argument("--days-back", type=int, default=1, help="获取前几个交易日的数据，默认为1")
    parser.add_argument("--symbols", type=str, help="指定获取的交易标的，用逗号分隔，默认使用配置的默认标的")
    parser.add_argument("--verify", action="store_true", help="验证数据完整性")
    args = parser.parse_args()
    
    # 获取需要处理的日期
    if args.date:
        target_date = args.date
    else:
        target_date = get_previous_trading_day(args.days_back)
    
    logger.info(f"开始获取 {target_date} 的历史数据")
    
    # 初始化同花顺API
    ths_api = initialize_ths_api()
    if ths_api is None:
        logger.error("初始化同花顺API失败，退出")
        return
    
    # 注册同花顺作为数据源
    register_ths_as_data_source()
    
    # 确定要获取的交易标的
    symbols_to_fetch = []
    if args.symbols:
        symbols_to_fetch = args.symbols.split(",")
    else:
        db_manager = get_db_manager()
        symbols_from_db = [s["symbol"] for s in db_manager.get_symbols()]
        
        if symbols_from_db:
            symbols_to_fetch = symbols_from_db
        else:
            symbols_to_fetch = DEFAULT_SYMBOLS
    
    logger.info(f"将获取 {len(symbols_to_fetch)} 个交易标的的数据")
    
    # 获取数据
    count = fetch_single_day_kline_data(ths_api, symbols_to_fetch, target_date)
    logger.info(f"共获取并保存了 {count} 条K线记录")
    
    # 更新数据源状态
    db_manager = get_db_manager()
    update_data_source_status(db_manager, "ths_sdk", "active")
    
    # 验证数据完整性
    if args.verify and count > 0:
        logger.info("开始验证数据完整性...")
        all_verified = True
        
        for symbol in symbols_to_fetch:
            if not verify_data_integrity(db_manager, symbol, target_date):
                all_verified = False
                logger.warning(f"标的 {symbol} 在 {target_date} 的数据不完整")
        
        if all_verified:
            logger.info("数据完整性验证通过")
        else:
            logger.warning("部分数据不完整，请查看日志了解详情")
    
    logger.info(f"{target_date} 的历史数据获取完成")

if __name__ == "__main__":
    main() 
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
量化交易系统API端点
提供数据访问接口
"""

import os
from datetime import datetime, timedelta
import pandas as pd
from flask import Flask, jsonify, request, Blueprint
from typing import Dict, List, Any, Union, Optional

from monitoring_module.logger import Logger
from data_module.storage.sqlite_handler import get_symbols, get_kline_data, get_latest_market_data, execute_query

# 创建Blueprint
api = Blueprint('api', __name__)
logger = Logger.get_logger("api_endpoints")

@api.route('/symbols', methods=['GET'])
def get_symbols_endpoint():
    """
    获取交易标的列表
    
    查询参数:
    - category: 标的类别，如STOCK（股票）或INDEX（指数）
    - status: 标的状态，默认为active
    
    返回:
    {
        "code": 0,
        "message": "success",
        "data": [
            {
                "symbol": "000001.SH",
                "name": "上证指数",
                "exchange": "SH",
                "category": "INDEX",
                "status": "active"
            },
            ...
        ]
    }
    """
    category = request.args.get('category')
    status = request.args.get('status', 'active')
    
    try:
        # 获取交易标的
        symbols_data = get_symbols(status=status)
        
        # 按类别过滤
        if category:
            symbols_data = [s for s in symbols_data if s.get('category') == category]
        
        return jsonify({
            "code": 0,
            "message": "success",
            "data": symbols_data
        })
    except Exception as e:
        logger.error(f"获取交易标的失败: {str(e)}")
        return jsonify({
            "code": 500,
            "message": f"获取交易标的失败: {str(e)}",
            "data": None
        }), 500

@api.route('/kline/<symbol>', methods=['GET'])
def get_kline(symbol):
    """
    获取K线数据
    
    路径参数:
    - symbol: 交易标的代码，如000001.SH
    
    查询参数:
    - period: 周期，如day、week等，默认为day
    - start_date: 开始日期，默认为30天前
    - end_date: 结束日期，默认为今天
    - include_today: 是否包含今日实时数据，默认为true
    
    返回:
    {
        "code": 0,
        "message": "success",
        "data": {
            "symbol": "000001.SH",
            "period": "day",
            "klines": [
                {
                    "date": "2023-01-01",
                    "open": 3100.0,
                    "high": 3150.0,
                    "low": 3080.0,
                    "close": 3120.0,
                    "volume": 100000000,
                    "amount": 10000000000.0
                },
                ...
            ]
        }
    }
    """
    period = request.args.get('period', 'day')
    
    # 时间周期转换
    period_map = {
        'day': '1d',
        'week': '1w',
        'month': '1m',
        'hour': '1h',
        'minute': '1m',
        '15minute': '15m',
        '30minute': '30m',
        '60minute': '60m'
    }
    timeframe = period_map.get(period, '1d')
    
    # 日期范围
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    start_date = request.args.get('start_date', 
                                (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d'))
    
    # 是否包含今日实时数据
    include_today = request.args.get('include_today', 'true').lower() == 'true'
    
    try:
        # 获取历史K线数据
        kline_data = get_kline_data(symbol, start_date, end_date, timeframe)
        
        # 如果需要包含今日数据，则获取最新报价构建当日K线
        today = datetime.now().strftime('%Y-%m-%d')
        today_data = None
        
        if include_today and today > end_date:
            end_date = today
        
        if include_today and (kline_data.empty or kline_data['date'].max() < today):
            # 获取最新实时报价
            latest_quotes = get_latest_market_data()
            latest_quote = next((q for q in latest_quotes if q.get('symbol') == symbol), None)
            
            if latest_quote and latest_quote.get('price'):
                quote_date = latest_quote.get('time', '').split(' ')[0]
                
                if quote_date == today:
                    # 构建当日K线
                    today_data = {
                        'date': today,
                        'open': latest_quote.get('open', latest_quote.get('price')),
                        'high': latest_quote.get('high', latest_quote.get('price')),
                        'low': latest_quote.get('low', latest_quote.get('price')),
                        'close': latest_quote.get('price'),
                        'volume': latest_quote.get('volume', 0),
                        'amount': latest_quote.get('amount', 0)
                    }
                    
                    # 添加到DataFrame
                    if not kline_data.empty:
                        today_df = pd.DataFrame([today_data])
                        kline_data = pd.concat([kline_data, today_df], ignore_index=True)
                    else:
                        kline_data = pd.DataFrame([today_data])
        
        # 转换为JSON格式
        if kline_data.empty:
            klines = []
        else:
            # 确保日期有序
            kline_data = kline_data.sort_values('date')
            klines = kline_data.to_dict('records')
        
        return jsonify({
            "code": 0,
            "message": "success",
            "data": {
                "symbol": symbol,
                "period": period,
                "klines": klines
            }
        })
    except Exception as e:
        logger.error(f"获取K线数据失败: {str(e)}")
        return jsonify({
            "code": 500,
            "message": f"获取K线数据失败: {str(e)}",
            "data": None
        }), 500

@api.route('/quote/<symbol>', methods=['GET'])
def get_quote(symbol):
    """
    获取实时行情数据
    
    路径参数:
    - symbol: 交易标的代码，如000001.SH
    
    返回:
    {
        "code": 0,
        "message": "success",
        "data": {
            "symbol": "000001.SH",
            "price": 3120.0,
            "open": 3100.0,
            "high": 3150.0,
            "low": 3080.0,
            "volume": 100000000,
            "amount": 10000000000.0,
            "change": 20.0,
            "change_percent": 0.65,
            "turnover": 1.5,
            "pe": 15.3,
            "pb": 1.2,
            "time": "2023-01-01 15:00:00"
        }
    }
    """
    try:
        # 获取最新实时报价
        latest_quotes = get_latest_market_data()
        latest_quote = next((q for q in latest_quotes if q.get('symbol') == symbol), None)
        
        if not latest_quote:
            return jsonify({
                "code": 404,
                "message": f"未找到交易标的 {symbol} 的实时行情数据",
                "data": None
            }), 404
        
        return jsonify({
            "code": 0,
            "message": "success",
            "data": latest_quote
        })
    except Exception as e:
        logger.error(f"获取实时行情数据失败: {str(e)}")
        return jsonify({
            "code": 500,
            "message": f"获取实时行情数据失败: {str(e)}",
            "data": None
        }), 500

@api.route('/kline-realtime/<symbol>', methods=['GET'])
def get_kline_with_realtime(symbol):
    """
    获取K线数据并包含实时最新价格
    
    路径参数:
    - symbol: 交易标的代码，如000001.SH
    
    查询参数:
    - period: 周期，如day、week等，默认为day
    - start_date: 开始日期，默认为30天前
    - end_date: 结束日期，默认为今天
    
    返回:
    {
        "code": 0,
        "message": "success",
        "data": {
            "symbol": "000001.SH",
            "period": "day",
            "klines": [...],
            "latest": {
                "price": 3120.0,
                "change": 20.0,
                "change_percent": 0.65,
                "time": "2023-01-01 15:00:00"
            }
        }
    }
    """
    # 获取K线数据
    kline_result = get_kline(symbol)
    kline_data = kline_result.get_json()
    
    # 获取实时行情
    quote_result = get_quote(symbol)
    quote_data = quote_result.get_json()
    
    # 整合数据
    if kline_data.get('code') == 0 and quote_data.get('code') == 0:
        result = kline_data
        result['data']['latest'] = {
            'price': quote_data['data'].get('price'),
            'change': quote_data['data'].get('change'),
            'change_percent': quote_data['data'].get('change_percent'),
            'time': quote_data['data'].get('time')
        }
    else:
        # 有错误时，返回第一个错误
        if kline_data.get('code') != 0:
            result = kline_data
        else:
            result = quote_data
    
    return jsonify(result)

@api.route('/status', methods=['GET'])
def get_status():
    """
    获取系统状态
    
    返回:
    {
        "code": 0,
        "message": "success",
        "data": {
            "database": true,
            "data_sources": [
                {
                    "name": "ths_sdk",
                    "type": "ths_sdk",
                    "status": "active",
                    "last_update": "2023-01-01 15:00:00"
                }
            ],
            "timestamp": "2023-01-01 15:00:00"
        }
    }
    """
    try:
        db_manager = get_db_manager()
        db_manager.connect()
        
        # 检查数据库连接
        database_ok = db_manager.conn is not None
        
        # 获取数据源状态
        data_sources = []
        try:
            sources = db_manager.execute_query("SELECT * FROM data_sources")
            for source in sources:
                data_sources.append({
                    "name": source.get("name"),
                    "type": source.get("type"),
                    "status": source.get("status"),
                    "last_update": source.get("last_update")
                })
        except Exception as e:
            logger.error(f"获取数据源状态失败: {str(e)}")
        
        return jsonify({
            "code": 0,
            "message": "success",
            "data": {
                "database": database_ok,
                "data_sources": data_sources,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        })
    except Exception as e:
        logger.error(f"获取系统状态失败: {str(e)}")
        return jsonify({
            "code": 500,
            "message": f"获取系统状态失败: {str(e)}",
            "data": None
        }), 500
    finally:
        if db_manager:
            db_manager.close()

# 创建Flask应用并注册Blueprint
def create_app():
    app = Flask(__name__)
    app.register_blueprint(api, url_prefix='/api')
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8082, debug=True) 
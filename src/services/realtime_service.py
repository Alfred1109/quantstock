#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
实时行情数据服务
- 使用AKShare获取实时行情数据
- 通过WebSocket向客户端推送数据
- 支持客户端订阅特定标的
"""

import os
import sys
import time
import json
import logging
import asyncio
import threading
import websockets
from datetime import datetime
from threading import Thread, Lock
from typing import Dict, List, Set, Any

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入项目模块
from monitoring_module.logger import Logger
from utils.config import get_config
from data_module.storage.sqlite_handler import get_symbols, execute_query, save_kline_data

# 获取logger
logger = Logger.get_logger("realtime_service")

# 初始化AKShare行情接口
def initialize_akshare_api():
    """初始化AKShare API"""
    import time
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(1, max_retries + 1):
        try:
            import akshare as ak
            logger.info(f"尝试初始化AKShare API (尝试 {attempt}/{max_retries})...")
            
            # 首先尝试使用腾讯指数接口，不使用日期参数
            try:
                logger.info("尝试使用腾讯指数数据源测试...")
                test_data = ak.stock_zh_index_daily_tx("sz000001")
                if test_data is not None and not test_data.empty:
                    logger.info("腾讯指数数据源测试成功")
                    return True
            except Exception as e_tx:
                logger.warning(f"腾讯指数数据源测试失败: {str(e_tx)}")
            
            # 尝试腾讯股票历史数据接口
            try:
                logger.info("尝试使用腾讯股票历史数据接口测试...")
                test_data = ak.stock_zh_a_hist_tx(symbol="sz000001")
                if test_data is not None and not test_data.empty:
                    logger.info("腾讯股票历史数据接口测试成功")
                    return True
            except Exception as e_tx_hist:
                logger.warning(f"腾讯股票历史数据接口测试失败: {str(e_tx_hist)}")
            
            # 尝试东方财富指数接口
            try:
                logger.info("尝试使用东方财富指数数据源测试...")
                test_data = ak.stock_zh_index_spot_em()
                if test_data is not None and not test_data.empty:
                    logger.info("东方财富指数数据源测试成功")
                    return True
            except Exception as e_em:
                logger.warning(f"东方财富指数数据源测试失败: {str(e_em)}")
            
            # 尝试东方财富股票接口
            try:
                logger.info("尝试使用东方财富股票数据接口测试...")
                test_data = ak.stock_zh_a_hist(symbol="000001")
                if test_data is not None and not test_data.empty:
                    logger.info("东方财富股票数据接口测试成功")
                    return True
            except Exception as e_em_hist:
                logger.warning(f"东方财富股票数据接口测试失败: {str(e_em_hist)}")
            
            # 所有数据源都失败，需要重试
            if attempt < max_retries:
                logger.warning(f"所有数据源测试失败，{retry_delay}秒后重试...")
                time.sleep(retry_delay)
                retry_delay *= 2  # 指数退避
            else:
                logger.error("所有数据源测试均失败，AKShare API初始化失败")
                return False
                
        except ImportError:
            logger.error("无法导入akshare模块，请确保已正确安装")
            return False
        except Exception as e:
            logger.error(f"初始化AKShare API失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            if attempt < max_retries:
                logger.warning(f"{retry_delay}秒后重试...")
                time.sleep(retry_delay)
                retry_delay *= 2  # 指数退避
            else:
                return False
    
    # 所有重试都失败
    return False

class Subscription:
    """订阅信息类"""
    def __init__(self, websocket, symbols=None):
        self.websocket = websocket
        self.symbols = set(symbols or [])  # 订阅的标的列表
        self.subscribe_all = False  # 是否订阅所有标的
        
    def add_symbol(self, symbol):
        """添加订阅标的"""
        self.symbols.add(symbol)
        
    def remove_symbol(self, symbol):
        """移除订阅标的"""
        if symbol in self.symbols:
            self.symbols.remove(symbol)
            
    def subscribe_to_all(self):
        """订阅所有标的"""
        self.subscribe_all = True
        
    def unsubscribe_from_all(self):
        """取消订阅所有标的"""
        self.subscribe_all = False
        self.symbols.clear()
        
    def is_subscribed(self, symbol):
        """检查是否订阅了指定标的"""
        return self.subscribe_all or symbol in self.symbols

class RealtimeService:
    """实时行情数据服务类"""
    def __init__(self, websocket_port=8083, fetch_interval=30):
        """
        初始化实时数据服务
        
        Args:
            websocket_port: WebSocket服务器端口
            fetch_interval: 数据获取间隔(秒)
        """
        self.symbols = []  # 所有交易标的
        self.akshare_api_initialized = False  # AKShare API初始化状态
        self.active = False  # 服务活动状态
        self.websocket_port = websocket_port
        self.fetch_interval = fetch_interval
        self.subscriptions = {}  # 客户端订阅信息
        self.subscription_lock = Lock()  # 订阅信息锁
        self.last_quotes = {}  # 上次获取的行情数据
        
    async def start(self):
        """启动实时数据服务"""
        self.active = True
        
        # 初始化
        await self.initialize()
        
        # 启动数据获取线程
        self.fetch_thread = Thread(target=self.run_fetch_loop)
        self.fetch_thread.daemon = True
        self.fetch_thread.start()
        
        # 启动WebSocket服务器
        logger.info(f"启动WebSocket服务器，端口: {self.websocket_port}")
        async with websockets.serve(self.handle_websocket, "0.0.0.0", self.websocket_port):
            # 服务器启动后，保持运行状态
            while self.active:
                await asyncio.sleep(1)
    
    async def initialize(self):
        """初始化服务"""
        # 获取所有交易标的
        try:
            self.symbols = [s["symbol"] for s in get_symbols()]
            logger.info(f"成功获取 {len(self.symbols)} 个交易标的")
        except Exception as e:
            logger.warning(f"获取交易标的失败: {str(e)}，使用默认标的")
            # 添加默认交易标的：科沃斯和江苏银行
            self.symbols = ["603486.SH", "600919.SH"]
            logger.info(f"使用默认交易标的: {self.symbols}")
        
        # 初始化AKShare API
        self.akshare_api_initialized = initialize_akshare_api()
        if not self.akshare_api_initialized:
            logger.warning("AKShare API初始化失败，将使用数据库中的最新数据")
    
    def run_fetch_loop(self):
        """运行数据获取循环"""
        logger.info("启动数据获取循环")
        
        # 确保有交易标的可用
        if not self.symbols:
            # 添加默认交易标的
            self.symbols = ["603486.SH", "600919.SH"]
            logger.info(f"数据获取循环中使用默认交易标的: {self.symbols}")
        
        while self.active:
            try:
                # 获取实时行情
                quotes = self.fetch_realtime_quotes()
                
                # 如果成功获取了数据，保存并推送
                if quotes:
                    self.save_to_database(quotes)
                    asyncio.run(self.broadcast_quotes(quotes))
                    # 记录本次获取的数据
                    for symbol, quote in quotes.items():
                        self.last_quotes[symbol] = quote
                else:
                    logger.debug("本次获取实时行情数据为空")
                
            except Exception as e:
                logger.error(f"数据获取循环发生错误: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            
            # 等待下一次获取
            time.sleep(self.fetch_interval)
    
    def fetch_realtime_quotes(self) -> Dict[str, Dict]:
        """
        使用AKShare获取实时行情数据
        
        Returns:
            标的代码为键，行情数据为值的字典
        """
        # 确保有交易标的
        if not self.symbols:
            # 使用默认交易标的
            self.symbols = ["603486.SH", "600919.SH"]
            logger.info(f"使用默认交易标的获取行情: {self.symbols}")
        
        if not self.akshare_api_initialized:
            logger.warning("AKShare API未初始化，跳过获取实时行情")
            return {}
            
        quotes = {}
        
        try:
            import akshare as ak
            import pandas as pd
            
            # 根据标的类型批量获取
            # 将标的分组：股票、指数、期货等
            stock_symbols = []
            index_symbols = []
            
            for symbol in self.symbols:
                if symbol.endswith('.SH') or symbol.endswith('.SZ'):
                    # 转换为AKShare格式（如 000001.SH -> sh000001）
                    exchange = 'sh' if symbol.endswith('.SH') else 'sz'
                    code = symbol.split('.')[0]
                    if len(code) == 6 and code.startswith(('0', '3', '6')):  # 股票
                        stock_symbols.append(f"{exchange}{code}")
                    else:  # 指数
                        index_symbols.append(f"{exchange}{code}")
            
            # 获取股票实时行情
            if stock_symbols:
                logger.info(f"正在获取 {len(stock_symbols)} 只股票的实时行情")
                for symbol in stock_symbols:
                    try:
                        # 使用AKShare获取单只股票行情
                        stock_df = ak.stock_zh_a_spot_em()
                        if isinstance(stock_df, pd.DataFrame) and not stock_df.empty:
                            # 找到对应的行
                            stock_df = stock_df[stock_df['代码'] == symbol[2:]]  # 去掉sh/sz前缀
                            
                            if not stock_df.empty:
                                row = stock_df.iloc[0]
                                # 转回原始格式 (sh000001 -> 000001.SH)
                                prefix = symbol[:2].upper()
                                code = symbol[2:]
                                original_symbol = f"{code}.{prefix}"
                                
                                quote = {
                                    "symbol": original_symbol,
                                    "price": float(row.get("最新价", 0)),
                                    "open": float(row.get("开盘价", 0)),
                                    "high": float(row.get("最高价", 0)),
                                    "low": float(row.get("最低价", 0)),
                                    "volume": float(row.get("成交量", 0)),
                                    "amount": float(row.get("成交额", 0)),
                                    "turnover": float(row.get("换手率", 0)),
                                    "preclose": float(row.get("昨收", 0)),
                                    "change": float(row.get("涨跌额", 0)),
                                    "changepct": float(row.get("涨跌幅", 0)),
                                    "pe": float(row.get("市盈率-动态", 0)),
                                    "pb": float(row.get("市净率", 0)),
                                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                quotes[original_symbol] = quote
                    except Exception as e:
                        logger.error(f"获取股票 {symbol} 行情失败: {str(e)}")
            
            # 获取指数实时行情
            if index_symbols:
                logger.info(f"正在获取 {len(index_symbols)} 个指数的实时行情")
                try:
                    # 使用AKShare获取指数行情
                    index_df = ak.stock_zh_index_spot_em()
                    if isinstance(index_df, pd.DataFrame) and not index_df.empty:
                        for symbol in index_symbols:
                            # 找到对应的行
                            code = symbol[2:]  # 去掉sh/sz前缀
                            index_row = index_df[index_df['代码'] == code]
                            
                            if not index_row.empty:
                                row = index_row.iloc[0]
                                # 转回原始格式
                                prefix = symbol[:2].upper()
                                original_symbol = f"{code}.{prefix}"
                                
                                quote = {
                                    "symbol": original_symbol,
                                    "price": float(row.get("最新价", 0)),
                                    "open": float(row.get("开盘价", 0)),
                                    "high": float(row.get("最高价", 0)),
                                    "low": float(row.get("最低价", 0)),
                                    "volume": float(row.get("成交量", 0)),
                                    "amount": float(row.get("成交额", 0)),
                                    "turnover": 0.0,  # 指数没有换手率
                                    "preclose": float(row.get("昨收", 0)),
                                    "change": float(row.get("涨跌额", 0)),
                                    "changepct": float(row.get("涨跌幅", 0)),
                                    "pe": 0.0,  # 指数没有市盈率
                                    "pb": 0.0,  # 指数没有市净率
                                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                quotes[original_symbol] = quote
                except Exception as e:
                    logger.error(f"获取指数行情失败: {str(e)}")
            
            logger.info(f"成功获取 {len(quotes)} 个标的的实时行情")
            
        except ImportError:
            logger.error("无法导入akshare模块，请确保已正确安装")
        except Exception as e:
            logger.error(f"获取实时行情时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
        return quotes
    
    def save_to_database(self, quotes: Dict[str, Dict]):
        """
        将行情数据保存到数据库
        
        Args:
            quotes: 标的代码为键，行情数据为值的字典
        """
        try:
            success_count = 0
            for symbol, quote in quotes.items():
                # 获取当前时间戳
                current_timestamp = int(datetime.now().timestamp())
                
                # 尝试更新现有记录
                result = execute_query(
                    "UPDATE real_time_quotes SET price = ?, open = ?, high = ?, low = ?, volume = ?, amount = ?, turnover = ?, preclose = ?, change = ?, changepct = ?, pe = ?, pb = ?, time = ?, timestamp = ? WHERE symbol = ?",
                    (quote["price"], quote["open"], quote["high"], quote["low"], quote["volume"], quote["amount"], 
                     quote["turnover"], quote["preclose"], quote["change"], quote["changepct"], quote["pe"], 
                     quote["pb"], quote["time"], current_timestamp, symbol)
                )
                
                # 如果没有更新任何记录，尝试插入新记录
                if not result:
                    execute_query(
                        "INSERT INTO real_time_quotes (symbol, price, open, high, low, volume, amount, turnover, preclose, change, changepct, pe, pb, time, timestamp, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (symbol, quote["price"], quote["open"], quote["high"], quote["low"], quote["volume"], 
                         quote["amount"], quote["turnover"], quote["preclose"], quote["change"], quote["changepct"], 
                         quote["pe"], quote["pb"], quote["time"], current_timestamp, "akshare")
                    )
                
                success_count += 1
            
            logger.info(f"成功保存 {success_count}/{len(quotes)} 条实时行情记录到数据库")
            
            # 更新数据源状态
            execute_query(
                "UPDATE data_sources SET status = ?, last_update = ? WHERE name = ?",
                ("active", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "akshare")
            )
        except Exception as e:
            logger.error(f"保存实时行情到数据库时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def handle_websocket(self, websocket, path):
        """
        处理WebSocket连接
        
        Args:
            websocket: WebSocket连接
            path: 请求路径
        """
        # 创建订阅
        subscription = Subscription(websocket)
        
        # 注册客户端
        with self.subscription_lock:
            self.subscriptions[websocket] = subscription
        
        logger.info(f"客户端连接: {websocket.remote_address}")
        
        try:
            # 发送初始数据
            await self.send_initial_data(websocket)
            
            # 处理订阅请求
            async for message in websocket:
                await self.process_message(websocket, message)
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"客户端断开连接: {websocket.remote_address}")
        except Exception as e:
            logger.error(f"处理WebSocket连接时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # 取消注册
            with self.subscription_lock:
                if websocket in self.subscriptions:
                    del self.subscriptions[websocket]
    
    async def send_initial_data(self, websocket):
        """
        发送初始数据到客户端
        
        Args:
            websocket: WebSocket连接
        """
        # 发送可用的交易标的列表
        symbols_message = {
            "type": "symbols",
            "data": self.symbols
        }
        await websocket.send(json.dumps(symbols_message))
        
        # 发送最新的行情数据
        if self.last_quotes:
            quotes_message = {
                "type": "quotes",
                "data": list(self.last_quotes.values())
            }
            await websocket.send(json.dumps(quotes_message))
    
    async def process_message(self, websocket, message):
        """
        处理客户端消息
        
        Args:
            websocket: WebSocket连接
            message: 客户端消息
        """
        try:
            data = json.loads(message)
            action = data.get("action")
            
            if action == "subscribe":
                # 订阅特定标的
                symbol = data.get("symbol")
                if symbol:
                    with self.subscription_lock:
                        if websocket in self.subscriptions:
                            self.subscriptions[websocket].add_symbol(symbol)
                            logger.info(f"客户端 {websocket.remote_address} 订阅标的: {symbol}")
                            
                            # 发送确认消息
                            await websocket.send(json.dumps({
                                "type": "subscription",
                                "status": "success",
                                "symbol": symbol,
                                "action": "subscribe"
                            }))
            
            elif action == "unsubscribe":
                # 取消订阅特定标的
                symbol = data.get("symbol")
                if symbol:
                    with self.subscription_lock:
                        if websocket in self.subscriptions:
                            self.subscriptions[websocket].remove_symbol(symbol)
                            logger.info(f"客户端 {websocket.remote_address} 取消订阅标的: {symbol}")
                            
                            # 发送确认消息
                            await websocket.send(json.dumps({
                                "type": "subscription",
                                "status": "success",
                                "symbol": symbol,
                                "action": "unsubscribe"
                            }))
            
            elif action == "subscribe_all":
                # 订阅所有标的
                with self.subscription_lock:
                    if websocket in self.subscriptions:
                        self.subscriptions[websocket].subscribe_to_all()
                        logger.info(f"客户端 {websocket.remote_address} 订阅所有标的")
                        
                        # 发送确认消息
                        await websocket.send(json.dumps({
                            "type": "subscription",
                            "status": "success",
                            "action": "subscribe_all"
                        }))
            
            elif action == "unsubscribe_all":
                # 取消订阅所有标的
                with self.subscription_lock:
                    if websocket in self.subscriptions:
                        self.subscriptions[websocket].unsubscribe_from_all()
                        logger.info(f"客户端 {websocket.remote_address} 取消订阅所有标的")
                        
                        # 发送确认消息
                        await websocket.send(json.dumps({
                            "type": "subscription",
                            "status": "success",
                            "action": "unsubscribe_all"
                        }))
            
            elif action == "get_quotes":
                # 获取最新行情数据
                symbols = data.get("symbols", [])
                quotes = []
                
                for symbol in symbols:
                    if symbol in self.last_quotes:
                        quotes.append(self.last_quotes[symbol])
                
                # 发送行情数据
                await websocket.send(json.dumps({
                    "type": "quotes",
                    "data": quotes
                }))
            
        except json.JSONDecodeError:
            logger.warning(f"收到无效JSON消息: {message}")
        except Exception as e:
            logger.error(f"处理消息时出错: {str(e)}")
    
    async def broadcast_quotes(self, quotes: Dict[str, Dict]):
        """
        向订阅客户端广播行情数据
        
        Args:
            quotes: 标的代码为键，行情数据为值的字典
        """
        if not quotes:
            return
        
        with self.subscription_lock:
            # 获取所有订阅的副本
            subscriptions = list(self.subscriptions.items())
        
        # 发送数据到每个客户端
        for websocket, subscription in subscriptions:
            try:
                # 找出该客户端订阅的标的的行情
                client_quotes = []
                
                for symbol, quote in quotes.items():
                    if subscription.is_subscribed(symbol):
                        client_quotes.append(quote)
                
                # 如果有数据，发送给客户端
                if client_quotes:
                    message = {
                        "type": "quotes",
                        "data": client_quotes
                    }
                    # 使用create_task避免阻塞当前协程
                    asyncio.create_task(websocket.send(json.dumps(message)))
            
            except Exception as e:
                logger.error(f"向客户端 {websocket.remote_address} 发送数据时出错: {str(e)}")
    
    def stop(self):
        """停止实时数据服务"""
        logger.info("停止实时数据服务")
        self.active = False

# 全局服务实例
_service_instance = None

def get_realtime_service() -> RealtimeService:
    """
    获取实时数据服务实例（单例模式）
    
    Returns:
        RealtimeService实例
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = RealtimeService()
    return _service_instance

async def start_service():
    """启动实时数据服务"""
    service = get_realtime_service()
    await service.start()

def main():
    """主函数"""
    logger.info("启动实时行情数据服务")
    
    try:
        # 运行事件循环
        asyncio.run(start_service())
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    except Exception as e:
        logger.error(f"服务运行出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    
    logger.info("实时行情数据服务已停止")

if __name__ == "__main__":
    main() 
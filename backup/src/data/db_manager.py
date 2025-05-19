"""
数据库管理模块 - 负责SQLite数据库的初始化和操作
"""
import os
import sqlite3
from datetime import datetime
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Union, Any
import json
from src.utils.logger import get_logger

logger = get_logger("db_manager")

# 数据库文件路径
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "market_data.db")

class DBManager:
    """
    数据库管理类，负责与SQLite数据库的交互
    """
    
    def __init__(self, db_path: str = DB_PATH):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.conn = None
        self.ensure_db_exists()
        
    def ensure_db_exists(self):
        """
        确保数据库文件存在，如果不存在则创建
        """
        # 确保目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # 连接数据库（如果不存在会自动创建）
        self.connect()
        
        # 创建必要的表
        self._create_tables()
        
        # 关闭连接
        self.close()
        
        logger.info(f"数据库初始化完成: {self.db_path}")
    
    def connect(self):
        """
        连接到数据库
        """
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            # 启用外键约束
            self.conn.execute("PRAGMA foreign_keys = ON")
            # 配置Row工厂模式，返回类字典对象
            self.conn.row_factory = sqlite3.Row
    
    def close(self):
        """
        关闭数据库连接
        """
        if self.conn is not None:
            self.conn.close()
            self.conn = None
    
    def _create_tables(self):
        """
        创建数据库表
        """
        cursor = self.conn.cursor()
        
        # 交易标的表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS symbols (
            symbol TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            exchange TEXT,
            category TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # K线数据表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS kline_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            amount REAL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date, timeframe)
        )
        ''')
        
        # 实时行情表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS real_time_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            price REAL,
            change_amount REAL,
            change_percent REAL,
            volume INTEGER,
            amount REAL,
            bid_price REAL,
            ask_price REAL,
            timestamp TIMESTAMP,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, timestamp)
        )
        ''')
        
        # 数据源表，记录数据来源
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS data_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            last_update TIMESTAMP,
            status TEXT DEFAULT 'active',
            config TEXT,  -- JSON配置
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name)
        )
        ''')
        
        # 保存更改
        self.conn.commit()
        logger.info("数据库表创建成功")
    
    def insert_symbols(self, symbols: List[Dict]) -> int:
        """
        批量插入交易标的数据
        
        Args:
            symbols: 交易标的列表，每个标的为字典，包含symbol, name等字段
            
        Returns:
            插入的记录数
        """
        self.connect()
        cursor = self.conn.cursor()
        count = 0
        
        try:
            for symbol_data in symbols:
                # 准备数据
                symbol = symbol_data.get('symbol')
                name = symbol_data.get('name')
                exchange = symbol_data.get('exchange', '')
                category = symbol_data.get('category', '')
                status = symbol_data.get('status', 'active')
                
                # 检查记录是否已存在
                cursor.execute("SELECT symbol FROM symbols WHERE symbol = ?", (symbol,))
                exists = cursor.fetchone()
                
                if exists:
                    # 更新已存在的记录
                    cursor.execute('''
                    UPDATE symbols SET 
                        name = ?,
                        exchange = ?,
                        category = ?,
                        status = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = ?
                    ''', (name, exchange, category, status, symbol))
                else:
                    # 插入新记录
                    cursor.execute('''
                    INSERT INTO symbols (symbol, name, exchange, category, status)
                    VALUES (?, ?, ?, ?, ?)
                    ''', (symbol, name, exchange, category, status))
                
                count += 1
            
            # 提交事务
            self.conn.commit()
            logger.info(f"成功保存{count}个交易标的")
            
        except Exception as e:
            # 回滚事务
            self.conn.rollback()
            logger.error(f"保存交易标的时出错: {str(e)}")
            count = 0
        
        return count
    
    def get_symbols(self, status: str = 'active') -> List[Dict]:
        """
        获取交易标的列表
        
        Args:
            status: 标的状态，默认为'active'
            
        Returns:
            交易标的列表
        """
        self.connect()
        cursor = self.conn.cursor()
        
        try:
            if status:
                cursor.execute("SELECT * FROM symbols WHERE status = ?", (status,))
            else:
                cursor.execute("SELECT * FROM symbols")
            
            rows = cursor.fetchall()
            # 转换为字典列表
            symbols = [dict(row) for row in rows]
            logger.info(f"获取到{len(symbols)}个交易标的")
            return symbols
            
        except Exception as e:
            logger.error(f"获取交易标的列表时出错: {str(e)}")
            return []
    
    def insert_kline_data(self, symbol: str, kline_data: List[Dict], timeframe: str = '1d', source: str = 'unknown') -> int:
        """
        批量插入K线数据
        
        Args:
            symbol: 交易标的代码
            kline_data: K线数据列表，每条数据为字典，包含date, open, high, low, close, volume等字段
            timeframe: 时间周期，默认为'1d'（日线）
            source: 数据来源
            
        Returns:
            插入的记录数
        """
        self.connect()
        cursor = self.conn.cursor()
        count = 0
        
        try:
            for kline in kline_data:
                # 准备数据
                date = kline.get('date')
                open_price = kline.get('open')
                high = kline.get('high')
                low = kline.get('low')
                close = kline.get('close')
                volume = kline.get('volume', 0)
                amount = kline.get('amount', 0)
                
                # 插入或更新记录
                cursor.execute('''
                INSERT INTO kline_data 
                    (symbol, date, timeframe, open, high, low, close, volume, amount, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, date, timeframe) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    source = excluded.source,
                    updated_at = CURRENT_TIMESTAMP
                ''', (symbol, date, timeframe, open_price, high, low, close, volume, amount, source))
                
                count += 1
            
            # 提交事务
            self.conn.commit()
            logger.info(f"成功保存{count}条K线数据，标的: {symbol}, 周期: {timeframe}")
            
        except Exception as e:
            # 回滚事务
            self.conn.rollback()
            logger.error(f"保存K线数据时出错: {str(e)}")
            count = 0
        
        return count
    
    def get_kline_data(self, symbol: str, start_date: str, end_date: str = None, timeframe: str = '1d') -> pd.DataFrame:
        """
        获取K线数据
        
        Args:
            symbol: 交易标的代码
            start_date: 开始日期
            end_date: 结束日期，默认为当前日期
            timeframe: 时间周期，默认为'1d'（日线）
            
        Returns:
            包含K线数据的DataFrame
        """
        self.connect()
        
        # 如果没有指定结束日期，则使用当前日期
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        try:
            # 直接使用pandas从SQL查询获取DataFrame
            query = f"""
            SELECT date, open, high, low, close, volume, amount
            FROM kline_data
            WHERE symbol = ? AND timeframe = ? AND date BETWEEN ? AND ?
            ORDER BY date
            """
            
            df = pd.read_sql_query(
                query,
                self.conn,
                params=(symbol, timeframe, start_date, end_date)
            )
            
            # 将date转换为datetime类型
            df['date'] = pd.to_datetime(df['date'])
            
            logger.info(f"获取到{len(df)}条K线数据，标的: {symbol}, 时间范围: {start_date} - {end_date}, 周期: {timeframe}")
            return df
            
        except Exception as e:
            logger.error(f"获取K线数据时出错: {str(e)}")
            return pd.DataFrame()
    
    def update_real_time_quote(self, symbol: str, quote_data: Dict, source: str = 'unknown') -> bool:
        """
        更新实时行情数据
        
        Args:
            symbol: 交易标的代码
            quote_data: 行情数据，包含price, change等字段
            source: 数据来源
            
        Returns:
            是否成功
        """
        self.connect()
        cursor = self.conn.cursor()
        
        try:
            # 准备数据
            price = quote_data.get('price')
            change_amount = quote_data.get('change_amount')
            change_percent = quote_data.get('change_percent')
            volume = quote_data.get('volume', 0)
            amount = quote_data.get('amount', 0)
            bid_price = quote_data.get('bid', price)
            ask_price = quote_data.get('ask', price)
            timestamp = quote_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            # 插入或更新记录
            cursor.execute('''
            INSERT INTO real_time_quotes 
                (symbol, price, change_amount, change_percent, volume, amount, bid_price, ask_price, timestamp, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timestamp) DO UPDATE SET
                price = excluded.price,
                change_amount = excluded.change_amount,
                change_percent = excluded.change_percent,
                volume = excluded.volume,
                amount = excluded.amount,
                bid_price = excluded.bid_price,
                ask_price = excluded.ask_price,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            ''', (symbol, price, change_amount, change_percent, volume, amount, bid_price, ask_price, timestamp, source))
            
            # 提交事务
            self.conn.commit()
            logger.info(f"成功更新实时行情数据，标的: {symbol}")
            return True
            
        except Exception as e:
            # 回滚事务
            self.conn.rollback()
            logger.error(f"更新实时行情数据时出错: {str(e)}")
            return False
    
    def get_latest_quote(self, symbol: str) -> Dict:
        """
        获取最新行情数据
        
        Args:
            symbol: 交易标的代码
            
        Returns:
            最新行情数据字典
        """
        self.connect()
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('''
            SELECT * FROM real_time_quotes
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
            ''', (symbol,))
            
            row = cursor.fetchone()
            if row:
                # 转换为字典
                return dict(row)
            else:
                logger.warning(f"未找到标的{symbol}的实时行情数据")
                return {}
                
        except Exception as e:
            logger.error(f"获取最新行情数据时出错: {str(e)}")
            return {}
    
    def register_data_source(self, name: str, source_type: str, config: Dict = None) -> bool:
        """
        注册数据源
        
        Args:
            name: 数据源名称
            source_type: 数据源类型（如'ths', 'csv', 'mock'）
            config: 数据源配置
            
        Returns:
            是否成功
        """
        self.connect()
        cursor = self.conn.cursor()
        
        try:
            # 将配置转换为JSON字符串
            config_json = json.dumps(config) if config else None
            
            # 插入或更新记录
            cursor.execute('''
            INSERT INTO data_sources (name, type, config)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                type = excluded.type,
                config = excluded.config,
                updated_at = CURRENT_TIMESTAMP
            ''', (name, source_type, config_json))
            
            # 提交事务
            self.conn.commit()
            logger.info(f"成功注册数据源: {name}, 类型: {source_type}")
            return True
            
        except Exception as e:
            # 回滚事务
            self.conn.rollback()
            logger.error(f"注册数据源时出错: {str(e)}")
            return False
    
    def update_data_source_status(self, name: str, status: str, last_update: str = None) -> bool:
        """
        更新数据源状态
        
        Args:
            name: 数据源名称
            status: 状态（如'active', 'inactive', 'error'）
            last_update: 最后更新时间
            
        Returns:
            是否成功
        """
        self.connect()
        cursor = self.conn.cursor()
        
        try:
            if last_update is None:
                last_update = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
            cursor.execute('''
            UPDATE data_sources SET 
                status = ?,
                last_update = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = ?
            ''', (status, last_update, name))
            
            # 提交事务
            self.conn.commit()
            logger.info(f"成功更新数据源状态: {name}, 状态: {status}")
            return True
            
        except Exception as e:
            # 回滚事务
            self.conn.rollback()
            logger.error(f"更新数据源状态时出错: {str(e)}")
            return False
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """
        执行自定义SQL查询
        
        Args:
            query: SQL查询语句
            params: 查询参数
            
        Returns:
            查询结果列表
        """
        self.connect()
        cursor = self.conn.cursor()
        
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
                
            rows = cursor.fetchall()
            # 转换为字典列表
            results = [dict(row) for row in rows]
            return results
            
        except Exception as e:
            logger.error(f"执行SQL查询时出错: {str(e)}, 查询: {query}")
            return []
    
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """
        批量执行SQL语句
        
        Args:
            query: SQL语句
            params_list: 参数列表
            
        Returns:
            受影响的行数
        """
        self.connect()
        cursor = self.conn.cursor()
        
        try:
            cursor.executemany(query, params_list)
            # 提交事务
            self.conn.commit()
            return cursor.rowcount
            
        except Exception as e:
            # 回滚事务
            self.conn.rollback()
            logger.error(f"批量执行SQL语句时出错: {str(e)}, 查询: {query}")
            return 0

# 创建单例实例
db_manager = DBManager()

def get_db_manager() -> DBManager:
    """
    获取数据库管理器实例
    
    Returns:
        数据库管理器实例
    """
    return db_manager 
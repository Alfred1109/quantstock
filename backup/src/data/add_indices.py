#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
为数据库添加索引，提高查询性能
"""

import os
import sys

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.utils.logger import get_logger
from src.data.db_manager import get_db_manager

logger = get_logger("add_indices")

def add_database_indices():
    """添加数据库索引以提高查询性能"""
    db_manager = get_db_manager()
    
    try:
        # 连接数据库
        db_manager.connect()
        
        # 为kline_data表添加索引
        queries = [
            "CREATE INDEX IF NOT EXISTS idx_kline_symbol_date ON kline_data(symbol, date)",
            "CREATE INDEX IF NOT EXISTS idx_kline_symbol ON kline_data(symbol)",
            "CREATE INDEX IF NOT EXISTS idx_kline_date ON kline_data(date)",
            "CREATE INDEX IF NOT EXISTS idx_kline_timeframe ON kline_data(timeframe)",
            
            # 为real_time_quotes表添加索引
            "CREATE INDEX IF NOT EXISTS idx_quotes_symbol ON real_time_quotes(symbol)",
            "CREATE INDEX IF NOT EXISTS idx_quotes_timestamp ON real_time_quotes(timestamp)",
            
            # 为symbols表添加索引 (虽然symbol是主键，但为category和status添加索引)
            "CREATE INDEX IF NOT EXISTS idx_symbols_category ON symbols(category)",
            "CREATE INDEX IF NOT EXISTS idx_symbols_status ON symbols(status)"
        ]
        
        # 执行索引创建
        for query in queries:
            db_manager.execute_query(query)
            logger.info(f"执行SQL: {query}")
        
        # 提交事务
        db_manager.conn.commit()
        logger.info("数据库索引创建成功")
        
    except Exception as e:
        if db_manager.conn:
            db_manager.conn.rollback()
        logger.error(f"创建索引失败: {str(e)}")
    finally:
        # 关闭数据库连接
        db_manager.close()

if __name__ == "__main__":
    logger.info("开始添加数据库索引...")
    add_database_indices()
    logger.info("索引添加完成.") 
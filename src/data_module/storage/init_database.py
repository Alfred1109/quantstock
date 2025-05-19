#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据库初始化脚本
- 创建数据库和表结构
- 添加默认股票
"""

import os
import sys
import sqlite3
from datetime import datetime

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入自定义模块
from src.data_module.storage.sqlite_handler import init_database, get_db_path, execute_query

def initialize_database():
    """初始化数据库，创建表结构"""
    print("开始初始化数据库...")
    if init_database():
        print("数据库表结构创建成功")
        return True
    else:
        print("数据库表结构创建失败")
        return False

def add_default_symbols():
    """添加默认股票"""
    print("开始添加默认股票...")
    
    # 默认股票列表 (科沃斯和江苏银行)
    symbols = [
        {
            "symbol": "603486.SH",
            "name": "科沃斯",
            "exchange": "SH",
            "asset_type": "STOCK",
            "status": "active",
            "listed_date": "2018-05-28",
            "delisted_date": None,
            "extra_info": None
        },
        {
            "symbol": "600919.SH",
            "name": "江苏银行",
            "exchange": "SH",
            "asset_type": "STOCK",
            "status": "active",
            "listed_date": "2016-08-02",
            "delisted_date": None,
            "extra_info": None
        }
    ]
    
    db_path = get_db_path()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        for symbol_data in symbols:
            # 检查是否已存在
            cursor.execute("SELECT COUNT(*) FROM symbols WHERE symbol = ?", (symbol_data["symbol"],))
            count = cursor.fetchone()[0]
            
            if count == 0:
                # 插入新记录
                cursor.execute(
                    """
                    INSERT INTO symbols (symbol, name, exchange, asset_type, status, listed_date, delisted_date, extra_info)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol_data["symbol"], 
                        symbol_data["name"], 
                        symbol_data["exchange"],
                        symbol_data["asset_type"], 
                        symbol_data["status"], 
                        symbol_data["listed_date"],
                        symbol_data["delisted_date"], 
                        symbol_data["extra_info"]
                    )
                )
                print(f"添加股票: {symbol_data['symbol']} ({symbol_data['name']})")
            else:
                print(f"股票已存在: {symbol_data['symbol']} ({symbol_data['name']})")
        
        # 添加数据源信息
        cursor.execute(
            """
            INSERT OR REPLACE INTO data_sources (name, type, status, last_update, config)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "akshare",
                "API",
                "active",
                int(datetime.now().timestamp()),
                None
            )
        )
        
        conn.commit()
        conn.close()
        print("默认股票添加完成")
        return True
    except Exception as e:
        print(f"添加默认股票失败: {e}")
        return False

def main():
    """主函数"""
    if not os.path.exists(os.path.dirname(get_db_path())):
        os.makedirs(os.path.dirname(get_db_path()), exist_ok=True)
        print(f"数据目录已创建: {os.path.dirname(get_db_path())}")
    
    if initialize_database():
        add_default_symbols()
        print(f"数据库初始化完成，路径: {get_db_path()}")
    else:
        print("数据库初始化失败")

if __name__ == "__main__":
    main() 
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
修复数据库结构
- 添加缺失的列
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
from src.data_module.storage.sqlite_handler import get_db_path

def fix_database_structure():
    """修复数据库结构，添加缺失的列"""
    print("开始修复数据库结构...")
    
    db_path = get_db_path()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查real_time_quotes表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='real_time_quotes'")
        if cursor.fetchone() is None:
            print("表 real_time_quotes 不存在，将创建新表")
            cursor.execute("""
                CREATE TABLE real_time_quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    price REAL,
                    open REAL,
                    high REAL,
                    low REAL,
                    volume REAL,
                    amount REAL,
                    turnover REAL,
                    preclose REAL,
                    change REAL,
                    changepct REAL,
                    pe REAL,
                    pb REAL,
                    time TEXT,
                    timestamp INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    source TEXT,
                    extra_info TEXT,
                    UNIQUE(symbol)
                )
            """)
            print("表 real_time_quotes 创建成功")
        else:
            # 检查列
            cursor.execute("PRAGMA table_info(real_time_quotes)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # 检查timestamp列是否存在
            if 'timestamp' not in columns:
                print("表 real_time_quotes 缺少 timestamp 列，正在添加...")
                # 添加timestamp列，使用当前时间戳作为默认值
                cursor.execute("ALTER TABLE real_time_quotes ADD COLUMN timestamp INTEGER NOT NULL DEFAULT (strftime('%s','now'))")
                print("timestamp 列添加成功")
            else:
                print("timestamp 列已存在")
            
            # 检查其他列
            if 'turnover' not in columns:
                print("表 real_time_quotes 缺少 turnover 列，正在添加...")
                cursor.execute("ALTER TABLE real_time_quotes ADD COLUMN turnover REAL")
                print("turnover 列添加成功")
            else:
                print("turnover 列已存在")
            
            # 检查其他可能缺失的列
            required_columns = [
                ('price', 'REAL'), ('open', 'REAL'), ('high', 'REAL'), ('low', 'REAL'),
                ('volume', 'REAL'), ('amount', 'REAL'), ('preclose', 'REAL'),
                ('change', 'REAL'), ('changepct', 'REAL'), ('pe', 'REAL'),
                ('pb', 'REAL'), ('time', 'TEXT'), ('source', 'TEXT'), ('extra_info', 'TEXT')
            ]
            
            for col_name, col_type in required_columns:
                if col_name not in columns:
                    print(f"表 real_time_quotes 缺少 {col_name} 列，正在添加...")
                    cursor.execute(f"ALTER TABLE real_time_quotes ADD COLUMN {col_name} {col_type}")
                    print(f"{col_name} 列添加成功")
        
        conn.commit()
        conn.close()
        print(f"数据库结构修复完成，路径: {db_path}")
        return True
    except Exception as e:
        print(f"修复数据库结构失败: {e}")
        return False

def main():
    """主函数"""
    fix_database_structure()

if __name__ == "__main__":
    main() 
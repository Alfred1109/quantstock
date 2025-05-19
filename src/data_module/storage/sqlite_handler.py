"""
数据库工具模块 - 提供一些常用的数据库操作函数
(Migrated from src/utils/db_utils.py)
"""
import os
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import logging # Changed from custom logger
import json # For storing JSON data
import uuid # For generating unique run_ids

logger = logging.getLogger(__name__) # Standard module logger

_PROJECT_ROOT = None

def _get_project_root() -> str:
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        # Path from src/data_module/storage/sqlite_handler.py to project root
        _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return _PROJECT_ROOT

def get_db_path(db_filename: str = "market_data.db") -> str:
    """
    获取数据库文件路径, 默认在项目根目录下的 data/ 文件夹中。
    """
    return os.path.join(_get_project_root(), "data", db_filename)

# --- Database Initialization and Schema --- 
def get_default_db_schema() -> Dict[str, str]:
    return {
        "symbols": (
            "CREATE TABLE IF NOT EXISTS symbols ("
            "symbol TEXT PRIMARY KEY,"
            "name TEXT,"
            "exchange TEXT,"
            "asset_type TEXT, " # e.g., STOCK, FUTURE, OPTION, INDEX, CRYPTO
            "status TEXT DEFAULT 'active', " # e.g., active, inactive, delisted
            "listed_date TEXT,"
            "delisted_date TEXT,"
            "extra_info TEXT"  # JSON string for other info
            ")"
        ),
        "kline_data": (
            "CREATE TABLE IF NOT EXISTS kline_data ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "symbol TEXT NOT NULL,"
            "timeframe TEXT NOT NULL, " # e.g., 1m, 5m, 1h, 1d, 1wk, 1mo
            "timestamp INTEGER NOT NULL, " # UNIX timestamp (seconds) for precision and timezone neutrality
            "date TEXT NOT NULL, " # YYYY-MM-DD representation of the bar's date
            "open REAL NOT NULL,"
            "high REAL NOT NULL,"
            "low REAL NOT NULL,"
            "close REAL NOT NULL,"
            "volume REAL,"
            "amount REAL, " # Turnover/QuoteVolume
            "UNIQUE (symbol, timeframe, timestamp)"
            ")"
        ),
        "real_time_quotes": (
            "CREATE TABLE IF NOT EXISTS real_time_quotes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "symbol TEXT NOT NULL,"
            "timestamp INTEGER NOT NULL,"
            "price REAL,"
            "volume REAL,"
            "amount REAL,"
            "open REAL, high REAL, low REAL, prev_close REAL,"
            "bid_price REAL, ask_price REAL,"
            "bid_volume REAL, ask_volume REAL,"
            "change REAL, change_percent REAL,"
            "extra_info TEXT"  # JSON for other fields
            ")"
        ),
        "data_sources": (
            "CREATE TABLE IF NOT EXISTS data_sources ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT UNIQUE NOT NULL, " # e.g., Binance, LocalCSV, AKShare
            "type TEXT, " # e.g., API, FILE, DB
            "status TEXT, " # e.g., connected, disconnected, error
            "last_update INTEGER, " # Timestamp of last successful update/connection
            "config TEXT"  # JSON for source-specific config if needed
            ")"
        ),
        "trade_log": (
            "CREATE TABLE IF NOT EXISTS trade_log (" 
            "trade_id TEXT PRIMARY KEY,"
            "timestamp INTEGER NOT NULL,"
            "run_id TEXT NOT NULL, "  # Added run_id
            "order_id TEXT,"
            "symbol TEXT NOT NULL,"
            "action TEXT NOT NULL, " # BUY, SELL, SHORT, COVER
            "quantity REAL NOT NULL,"
            "price REAL NOT NULL,"
            "commission REAL DEFAULT 0,"
            "slippage REAL DEFAULT 0,"
            "pnl REAL,"
            "portfolio_id TEXT, " # If multiple portfolios are managed
            "strategy_name TEXT,"
            "FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)" # Added FK
            ")"
        ),
        "backtest_runs": (
            "CREATE TABLE IF NOT EXISTS backtest_runs (" 
            "run_id TEXT PRIMARY KEY,"
            "strategy_name TEXT,"
            "config_params TEXT,"
            "start_timestamp INTEGER,"
            "end_timestamp INTEGER,"
            "execution_status TEXT, " # e.g., COMPLETED, FAILED, RUNNING
            "notes TEXT"
            ")"
        ),
        "portfolio_history": (
            "CREATE TABLE IF NOT EXISTS portfolio_history (" 
            "entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "run_id TEXT NOT NULL,"
            "timestamp INTEGER NOT NULL,"
            "total_value REAL NOT NULL,"
            "cash REAL,"
            "positions_value REAL,"
            "pnl REAL,"
            "FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)"
            ")"
        ),
        "performance_metrics": (
            "CREATE TABLE IF NOT EXISTS performance_metrics (" 
            "metric_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "run_id TEXT NOT NULL,"
            "metric_name TEXT NOT NULL,"
            "metric_value TEXT,"
            "UNIQUE (run_id, metric_name),"
            "FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)"
            ")"
        )
    }

def init_database(db_path: Optional[str] = None) -> bool:
    """初始化数据库并创建表结构（如果不存在）。"""
    db_path = db_path or get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        schema = get_default_db_schema()
        for table_name, create_sql in schema.items():
            logger.info(f"Creating table {table_name} if not exists...")
            cursor.execute(create_sql)
        conn.commit()
        conn.close()
        logger.info(f"Database initialized/verified at {db_path}")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed at {db_path}: {e}", exc_info=True)
        return False


def execute_query(query: str, params: tuple = None, fetch: bool = True, db_path: Optional[str] = None) -> List[Dict]:
    """
    执行SQL查询
    """
    db_path = db_path or get_db_path()
    try:
        # Attempting to import db_manager can be problematic if it's not always available
        # or causes circular dependencies. For a util script, direct access might be cleaner.
        # from data_module.storage.db_manager import get_db_manager 
        # db_manager = get_db_manager(db_path=db_path)
        # return db_manager.execute_query(query, params, fetch=fetch)
        pass # Placeholder for db_manager logic if it's ever added back
    except ImportError:
        logger.debug("db_manager not found. This is fine, direct sqlite3 will be used.")
        pass # Continue to direct sqlite3 logic

    # Direct sqlite3 logic as fallback or primary method
    if not os.path.exists(db_path):
        logger.error(f"Database file does not exist: {db_path}")
        # Avoid initializing DB on every select query to non-existent DB.
        # init_database should be called explicitly if a new DB is intended.
        return []
            
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if fetch:
            rows = cursor.fetchall()
            results = [dict(row) for row in rows]
        else:
            conn.commit()
            results = [] 
        
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Error executing SQL query on {db_path}: {e}", exc_info=True)
        return []

# --- Utility for Run ID ---
def generate_run_id(strategy_name: Optional[str] = "run") -> str:
    """Generates a unique run ID combining strategy name, timestamp and UUID."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = str(uuid.uuid4()).split('-')[0]
    return f"{strategy_name.replace(' ', '_')}_{ts}_{short_uuid}"

# --- Backtest Data Persistence Functions ---

def save_backtest_run(
    run_data: Dict[str, Any],
    db_path: Optional[str] = None
) -> Optional[str]:
    """
    Saves metadata for a backtest run.
    Expects run_data to contain keys like: 
    'run_id' (optional, will be generated if missing), 
    'strategy_name', 'config_params' (dict or JSON string), 
    'start_timestamp', 'end_timestamp', 'execution_status', 'notes'.
    Returns the run_id if successful, else None.
    """
    db_path = db_path or get_db_path()
    
    run_id = run_data.get('run_id') or generate_run_id(run_data.get('strategy_name', 'generic_run'))
    strategy_name = run_data.get('strategy_name')
    config_params = run_data.get('config_params')
    start_timestamp = run_data.get('start_timestamp') # Should be Unix timestamp
    end_timestamp = run_data.get('end_timestamp')   # Should be Unix timestamp
    execution_status = run_data.get('execution_status', 'PENDING')
    notes = run_data.get('notes', '')

    if isinstance(config_params, dict):
        config_params_str = json.dumps(config_params)
    elif isinstance(config_params, str):
        config_params_str = config_params
    else:
        config_params_str = None

    query = ("INSERT INTO backtest_runs (run_id, strategy_name, config_params, "
             "start_timestamp, end_timestamp, execution_status, notes) "
             "VALUES (?, ?, ?, ?, ?, ?, ?)")
    params = (run_id, strategy_name, config_params_str, start_timestamp, 
              end_timestamp, execution_status, notes)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        logger.info(f"Backtest run metadata saved with run_id: {run_id}")
        return run_id
    except sqlite3.IntegrityError as e:
        logger.error(f"Failed to save backtest run {run_id}. Integrity error (e.g., run_id already exists?): {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error saving backtest run metadata for run_id {run_id}: {e}", exc_info=True)
        return None

def save_trade_log(
    trade_data: List[Dict[str, Any]], 
    run_id: str, 
    db_path: Optional[str] = None
) -> bool:
    """
    Saves a list of trade records to the trade_log table, associating them with a run_id.
    Each dictionary in trade_data should correspond to the trade_log schema.
    The 'trade_id' should be unique for each trade.
    'timestamp' should be a Unix timestamp.
    """
    db_path = db_path or get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add run_id to each trade record dictionary before insertion
        # Ensure all required fields are present and types are correct for DB insertion
        records_to_insert = []
        for trade in trade_data:
            # Ensure all fields exist, provide defaults for optional ones if not present
            # This is a simplified example; more robust validation might be needed.
            records_to_insert.append((
                trade.get('trade_id'), 
                trade.get('timestamp'), # Unix timestamp
                run_id, # Added field
                trade.get('order_id'), 
                trade.get('symbol'), 
                trade.get('action'), 
                trade.get('quantity'), 
                trade.get('price'), 
                trade.get('commission', 0),
                trade.get('slippage', 0),
                trade.get('pnl'),
                trade.get('portfolio_id'),
                trade.get('strategy_name')
            ))

        # Note: The trade_log schema was missing run_id. It should be added for proper association.
        # For now, I will assume the table will be altered or this is a new design aspect.
        # Let's adjust the insert query to include run_id if it was intended to be part of the trade_log table.
        # Original schema: trade_id, timestamp, order_id, symbol, action, quantity, price, commission, slippage, pnl, portfolio_id, strategy_name
        # If run_id is a new conceptual link but not a DB column in trade_log directly, then it's for filtering if other tables link trade_id to run_id.
        # Assuming run_id is NOT directly in trade_log, but linked externally or implicitly.
        # Let's re-evaluate. The prompt requests to save trade_log associated with run_id.
        # The simplest way is to add run_id to the trade_log table schema.
        # I'll proceed assuming the schema needs to be updated or I will add a new field to the insert.

        # Let's assume the table `trade_log` has been (or will be) updated to include `run_id`
        # If not, the save_trade_log might need to save to a *new* table like `backtest_trade_log`
        # with a `run_id` column.
        # For now, I will modify the insert to include `run_id` and make a note to update the schema.
        # No, the schema above in this same file *does not* have run_id in trade_log. 
        # I will add a new field to `trade_log` schema directly in this edit for consistency of this PR.

        # The schema for `trade_log` provided earlier does not have `run_id`.
        # Let's add it to the insert assuming the user will update the schema or this is for a *new* table.
        # This is tricky without modifying the schema definition in the same step.
        # I will proceed by adding `run_id` to the insert statement for `trade_log`
        # and the user should ensure the `trade_log` table schema definition is updated to include `run_id TEXT`. 
        # The schema for trade_log is in the same file, I will update it there as part of this change. (Self-correction)
        
        # Insert query for the trade_log table (assuming it now has run_id)
        query = ("INSERT INTO trade_log (trade_id, timestamp, run_id, order_id, symbol, action, "
                 "quantity, price, commission, slippage, pnl, portfolio_id, strategy_name) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")

        cursor.executemany(query, records_to_insert)
        conn.commit()
        logger.info(f"Saved {len(records_to_insert)} trade records for run_id: {run_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving trade log for run_id {run_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def save_portfolio_history(
    history_data: List[Dict[str, Any]], 
    run_id: str, 
    db_path: Optional[str] = None
) -> bool:
    """
    Saves portfolio history data to the portfolio_history table.
    Each dictionary in history_data should correspond to the portfolio_history schema (excluding entry_id).
    'timestamp' should be a Unix timestamp.
    """
    db_path = db_path or get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        records_to_insert = []
        for record in history_data:
            records_to_insert.append((
                run_id,
                record.get('timestamp'), # Unix timestamp
                record.get('total_value'),
                record.get('cash'),
                record.get('positions_value'),
                record.get('pnl')
            ))
        
        query = ("INSERT INTO portfolio_history (run_id, timestamp, total_value, cash, "
                 "positions_value, pnl) VALUES (?, ?, ?, ?, ?, ?)")
        
        cursor.executemany(query, records_to_insert)
        conn.commit()
        logger.info(f"Saved {len(records_to_insert)} portfolio history records for run_id: {run_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving portfolio history for run_id {run_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def save_performance_metrics(
    metrics_data: Dict[str, Any], 
    run_id: str, 
    db_path: Optional[str] = None
) -> bool:
    """
    Saves performance metrics to the performance_metrics table.
    metrics_data is a dictionary where keys are metric names and values are metric values.
    """
    db_path = db_path or get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        records_to_insert = []
        for name, value in metrics_data.items():
            records_to_insert.append((
                run_id,
                name,
                str(value) # Store all metric values as text for flexibility, convert on load if needed
            ))
            
        query = ("INSERT INTO performance_metrics (run_id, metric_name, metric_value) "
                 "VALUES (?, ?, ?)")
        
        cursor.executemany(query, records_to_insert)
        conn.commit()
        logger.info(f"Saved {len(records_to_insert)} performance metrics for run_id: {run_id}")
        return True
    except sqlite3.IntegrityError as e: # Handles UNIQUE constraint (run_id, metric_name)
        logger.warning(f"Integrity error saving metrics for run_id {run_id} (possibly duplicate metric names?): {e}")
        # Optionally, implement an UPDATE ON CONFLICT REPLACE strategy if metrics can be updated
        # For now, we just log and don't save duplicates that violate constraint.
        if conn: conn.rollback()
        return False # Or True if partial success / ignoring duplicates is acceptable
    except Exception as e:
        logger.error(f"Error saving performance metrics for run_id {run_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

# --- Data Access Functions (examples from original db_utils) --- 

def get_symbols(status: str = 'active', db_path: Optional[str] = None) -> List[Dict]:
    db_path = db_path or get_db_path()
    if status:
        query = "SELECT * FROM symbols WHERE status = ?"
        return execute_query(query, (status,), db_path=db_path)
    else:
        query = "SELECT * FROM symbols"
        return execute_query(query, db_path=db_path)

def get_kline_data(symbol: str, start_date: str, end_date: Optional[str] = None, timeframe: str = '1d', db_path: Optional[str] = None) -> pd.DataFrame:
    db_path = db_path or get_db_path()
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    query = ("SELECT timestamp, date, open, high, low, close, volume, amount "
             "FROM kline_data "
             "WHERE symbol = ? AND timeframe = ? AND date BETWEEN ? AND ? "
             "ORDER BY timestamp")
    
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(query, conn, params=(symbol, timeframe, start_date, end_date))
        conn.close()
        if 'timestamp' in df.columns:
             df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s') 
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        return df
    except Exception as e:
        logger.error(f"Error getting kline data for {symbol} from {db_path}: {e}", exc_info=True)
        return pd.DataFrame()

def save_kline_data(df: pd.DataFrame, symbol: str, timeframe: str, db_path: Optional[str] = None):
    """Saves kline DataFrame to the database."""
    db_path = db_path or get_db_path()
    if df.empty:
        logger.info(f"DataFrame for {symbol} ({timeframe}) is empty. Nothing to save.")
        return

    df_to_save = df.copy()
    df_to_save['symbol'] = symbol
    df_to_save['timeframe'] = timeframe

    if 'timestamp' in df_to_save.columns and pd.api.types.is_datetime64_any_dtype(df_to_save['timestamp']):
        df_to_save['timestamp'] = (df_to_save['timestamp'].dt.tz_localize(None) - pd.Timestamp("1970-01-01")) // pd.Timedelta('1s')
    if 'date' in df_to_save.columns and pd.api.types.is_datetime64_any_dtype(df_to_save['date']):
        df_to_save['date'] = df_to_save['date'].dt.strftime('%Y-%m-%d')
    
    db_columns = ['symbol', 'timeframe', 'timestamp', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount']
    df_to_save = df_to_save.reindex(columns=db_columns)
    
    try:
        conn = sqlite3.connect(db_path)
        df_to_save.to_sql('kline_data', conn, if_exists='append', index=False, method=None)
        conn.commit()
        conn.close()
        logger.info(f"Saved {len(df_to_save)} rows for {symbol} ({timeframe}) to kline_data in {db_path}")
    except sqlite3.IntegrityError:
        logger.warning(f"Integrity error (likely duplicate) saving kline for {symbol} ({timeframe}) to {db_path}. Data not saved.")
    except Exception as e:
        logger.error(f"Error saving kline data for {symbol} ({timeframe}) to {db_path}: {e}", exc_info=True)


def get_latest_market_data(db_path: Optional[str] = None) -> List[Dict]:
    db_path = db_path or get_db_path()
    query = ("SELECT s.symbol, s.name, q.price, q.change_percent, q.volume, q.timestamp "
             "FROM symbols s "
             "LEFT JOIN ( "
             "    SELECT symbol, price, change_percent, volume, timestamp, "
             "           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) as rn "
             "    FROM real_time_quotes "
             ") q ON s.symbol = q.symbol AND q.rn = 1 "
             "WHERE s.status = 'active'")
    
    results = execute_query(query, db_path=db_path)
    for row in results:
        if row.get('timestamp') and isinstance(row['timestamp'], (int, float)):
            row['timestamp'] = datetime.fromtimestamp(row['timestamp']).isoformat()
    return results

def get_data_sources_status(db_path: Optional[str] = None) -> List[Dict]:
    db_path = db_path or get_db_path()
    query = "SELECT name, type, status, last_update, config FROM data_sources ORDER BY last_update DESC"
    results = execute_query(query, db_path=db_path)
    for row in results:
        if row.get('last_update') and isinstance(row['last_update'], (int, float)):
            row['last_update'] = datetime.fromtimestamp(row['last_update']).isoformat()
    return results

def get_database_stats(db_path: Optional[str] = None) -> Dict:
    db_path = db_path or get_db_path()
    stats = {}
    table_counts = {
        "symbols": "symbols_count",
        "kline_data": "klines_count",
        "real_time_quotes": "quotes_count",
        "data_sources": "sources_count",
        "trade_log": "trade_log_entries_count"
    }
    for table, count_key in table_counts.items():
        query = f"SELECT COUNT(*) as count FROM {table}"
        result = execute_query(query, db_path=db_path)
        stats[count_key] = result[0]["count"] if result and result[0] else 0

    query_dates = "SELECT MIN(timestamp) as earliest_ts, MAX(timestamp) as latest_ts FROM kline_data"
    result_dates = execute_query(query_dates, db_path=db_path)
    if result_dates and result_dates[0] and result_dates[0]["earliest_ts"] is not None:
        stats["earliest_kline_timestamp"] = datetime.fromtimestamp(result_dates[0]["earliest_ts"]).isoformat()
        stats["latest_kline_timestamp"] = datetime.fromtimestamp(result_dates[0]["latest_ts"]).isoformat()
    else:
        stats["earliest_kline_timestamp"] = None
        stats["latest_kline_timestamp"] = None
    
    if os.path.exists(db_path):
        stats["db_size_bytes"] = os.path.getsize(db_path)
        stats["db_size_mb"] = round(stats["db_size_bytes"] / (1024 * 1024), 2)
    else:
        stats["db_size_bytes"] = 0
        stats["db_size_mb"] = 0
    return stats

def backup_database(backup_dir: Optional[str] = None, db_path: Optional[str] = None) -> Optional[str]:
    import shutil
    db_path = db_path or get_db_path()
    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}. Cannot backup.")
        return None
    
    backup_dir = backup_dir or os.path.join(_get_project_root(), "data", "backups")
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_base_name = os.path.basename(db_path)
    db_name_part = db_base_name.split('.')[0] if '.' in db_base_name else db_base_name
    backup_filename = f"{db_name_part}_backup_{timestamp}.db"
    final_backup_path = os.path.join(backup_dir, backup_filename)
    
    try:
        shutil.copy2(db_path, final_backup_path)
        logger.info(f"Database backed up successfully to: {final_backup_path}")
        return final_backup_path
    except Exception as e:
        logger.error(f"Database backup to {final_backup_path} failed: {e}", exc_info=True)
        return None

def vacuum_database(db_path: Optional[str] = None) -> bool:
    db_path = db_path or get_db_path()
    logger.info(f"Attempting to VACUUM database: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM")
        conn.close()
        logger.info(f"Database {db_path} vacuumed successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to VACUUM database {db_path}: {e}", exc_info=True)
        return False

def load_backtest_run_info(run_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Loads metadata for a specific backtest run."""
    db_path = db_path or get_db_path()
    query = "SELECT * FROM backtest_runs WHERE run_id = ?"
    results = execute_query(query, (run_id,), fetch=True, db_path=db_path)
    if results:
        run_info = results[0]
        # Convert config_params back to dict if it was stored as JSON string
        if 'config_params' in run_info and isinstance(run_info['config_params'], str):
            try:
                run_info['config_params'] = json.loads(run_info['config_params'])
            except json.JSONDecodeError:
                logger.warning(f"Could not parse config_params JSON for run_id {run_id}. Returning as string.")
        return run_info
    return None

def list_backtest_runs(db_path: Optional[str] = None) -> pd.DataFrame:
    """Lists all saved backtest runs."""
    db_path = db_path or get_db_path()
    query = "SELECT run_id, strategy_name, start_timestamp, end_timestamp, execution_status, notes FROM backtest_runs ORDER BY start_timestamp DESC"
    
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(query, conn)
        conn.close()
        if 'start_timestamp' in df.columns:
            df['start_timestamp'] = pd.to_datetime(df['start_timestamp'], unit='s', errors='coerce')
        if 'end_timestamp' in df.columns:
            df['end_timestamp'] = pd.to_datetime(df['end_timestamp'], unit='s', errors='coerce')
        return df
    except Exception as e:
        logger.error(f"Error listing backtest runs from {db_path}: {e}", exc_info=True)
        return pd.DataFrame()

def load_trade_log(run_id: Optional[str] = None, db_path: Optional[str] = None) -> pd.DataFrame:
    """Loads trade log, optionally filtered by run_id."""
    db_path = db_path or get_db_path()
    if run_id:
        query = "SELECT * FROM trade_log WHERE run_id = ? ORDER BY timestamp ASC"
        params = (run_id,)
    else:
        query = "SELECT * FROM trade_log ORDER BY timestamp ASC"
        params = ()
    
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', errors='coerce')
        return df
    except Exception as e:
        logger.error(f"Error loading trade log for run_id {run_id} from {db_path}: {e}", exc_info=True)
        return pd.DataFrame()

def load_portfolio_history(run_id: Optional[str] = None, db_path: Optional[str] = None) -> pd.DataFrame:
    """Loads portfolio history, optionally filtered by run_id."""
    db_path = db_path or get_db_path()
    if run_id:
        query = "SELECT * FROM portfolio_history WHERE run_id = ? ORDER BY timestamp ASC"
        params = (run_id,)
    else:
        query = "SELECT * FROM portfolio_history ORDER BY timestamp ASC"
        params = ()

    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', errors='coerce')
        return df
    except Exception as e:
        logger.error(f"Error loading portfolio history for run_id {run_id} from {db_path}: {e}", exc_info=True)
        return pd.DataFrame()

def load_performance_metrics(run_id: Optional[str] = None, db_path: Optional[str] = None) -> pd.DataFrame:
    """Loads performance metrics, optionally filtered by run_id. Pivots to wide format."""
    db_path = db_path or get_db_path()
    if run_id:
        query = "SELECT run_id, metric_name, metric_value FROM performance_metrics WHERE run_id = ?"
        params = (run_id,)
    else:
        query = "SELECT run_id, metric_name, metric_value FROM performance_metrics"
        params = ()
        
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if not df.empty:
            # Pivot the table to have metric_name as columns
            # For metrics stored as text, they remain text. Numeric conversion should happen application-side if needed.
            df_pivot = df.pivot(index='run_id', columns='metric_name', values='metric_value').reset_index()
            return df_pivot
        return pd.DataFrame() # Return empty DataFrame if no metrics found
    except Exception as e:
        logger.error(f"Error loading performance metrics for run_id {run_id} from {db_path}: {e}", exc_info=True)
        return pd.DataFrame()

if __name__ == "__main__":
    # Configure logger for testing this module directly
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    db_file = get_db_path(db_filename="test_market_data_sqlite_handler.db")
    logger.info(f"Using test database: {db_file}")
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
            logger.info(f"Removed existing test database: {db_file}")
        except OSError as e:
            logger.error(f"Error removing existing test database {db_file}: {e}. Please check permissions or if the file is in use.")
            # Optionally, exit or raise if the test DB cannot be cleared
            # sys.exit(1) 
            
    init_success = init_database(db_path=db_file)
    logger.info(f"Test DB initialization successful: {init_success}")

    if init_success:
        sample_data = {
            'timestamp': [datetime(2023, 1, 1, 10, 0, 0), datetime(2023, 1, 1, 10, 1, 0)],
            'date': ["2023-01-01", "2023-01-01"],
            'open': [100.0, 101.0],
            'high': [102.0, 101.5],
            'low': [99.5, 100.5],
            'close': [101.0, 100.8],
            'volume': [1000, 1200],
            'amount': [100500.0, 120800.0]
        }
        sample_df = pd.DataFrame(sample_data)
        save_kline_data(sample_df, "TEST_AAPL", "1m", db_path=db_file)
        save_kline_data(sample_df, "TEST_AAPL", "1m", db_path=db_file)

        retrieved_df = get_kline_data("TEST_AAPL", "2023-01-01", "2023-01-01", "1m", db_path=db_file)
        logger.info(f"Retrieved kline data for TEST_AAPL (1m):\n{retrieved_df}")
        
        stats = get_database_stats(db_path=db_file)
        logger.info(f"Database stats:\n{stats}")

        backup_file_path = backup_database(db_path=db_file)
        if backup_file_path:
            logger.info(f"Backup created at: {backup_file_path}")
            if os.path.exists(backup_file_path):
                 try:
                     os.remove(backup_file_path)
                 except OSError as e:
                     logger.warning(f"Could not remove test backup {backup_file_path}: {e}")

        vacuum_success = vacuum_database(db_path=db_file)
        logger.info(f"Vacuum successful: {vacuum_success}")

    if os.path.exists(db_file):
        try:
            os.remove(db_file)
            logger.info(f"Cleaned up test database {db_file}")
        except OSError as e:
            logger.warning(f"Could not remove test database {db_file} after tests: {e}") 
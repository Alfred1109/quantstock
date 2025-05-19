"""
同花顺数据获取模块 - 统一支持SDK和HTTP API两种方式
"""
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import numpy as np
from src.utils.logger import get_logger
from src.utils.config import get_config
from src.data.data_feed import DataFeed

logger = get_logger("ths_data_feed")

class THSDataFeed(DataFeed):
    """
    同花顺数据源类
    统一支持SDK和HTTP API两种访问方式
    """
    
    def __init__(
        self,
        api_type: str = None,
        username: str = None,
        password: str = None, 
        refresh_token: str = None,
        access_token: str = None,
        use_cache: bool = True,
        cache_dir: str = None
    ):
        """
        初始化同花顺数据源
        
        Args:
            api_type: API类型，'sdk'或'http'，如果为None则自动选择
            username: 同花顺SDK用户名（SDK方式需要）
            password: 同花顺SDK密码（SDK方式需要）
            refresh_token: 同花顺HTTP API的refresh_token（HTTP方式需要）
            access_token: 同花顺HTTP API的access_token（HTTP方式需要，优先于refresh_token）
            use_cache: 是否使用缓存
            cache_dir: 缓存目录，如果为None则根据API类型自动设置
        """
        # 确定API类型
        if api_type is None:
            api_type = "http" if get_config("ths_api", "use_http_api", False) else "sdk"
        
        self.api_type = api_type.lower()
        self.username = username
        self.password = password
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.use_cache = use_cache
        
        # 如果未提供凭据，从配置文件获取
        if self.api_type == "sdk" and (not username or not password):
            auth_config = get_config("ths_api", "auth", {})
            self.username = username or auth_config.get("username")
            self.password = password or auth_config.get("password")
        
        if self.api_type == "http" and not refresh_token and not access_token:
            self.refresh_token = get_config("ths_api", "refresh_token", "")
            self.access_token = get_config("ths_api", "access_token", "")
        
        # 设置缓存目录
        if cache_dir is None:
            if self.api_type == "sdk":
                self.cache_dir = "./output/data/cache/ths_sdk"
            else:
                self.cache_dir = "./output/data/cache/ths_http"
        else:
            self.cache_dir = cache_dir
            
        # 确保缓存目录存在
        if use_cache:
            os.makedirs(self.cache_dir, exist_ok=True)
        
        # 订阅回调
        self.callbacks = {}
        
        # 尝试导入数据库管理器
        try:
            from src.data.db_manager import get_db_manager
            self.db_manager = get_db_manager()
            logger.info(f"成功导入数据库管理器到THSDataFeed ({self.api_type})")
            
            # 注册数据源
            config = {"api_type": self.api_type}
            if self.api_type == "sdk":
                config["username"] = self.username
            else:
                if self.access_token:
                    config["access_token"] = self.access_token
                else:
                    config["refresh_token"] = self.refresh_token
                
            self.db_manager.register_data_source(
                name=f"ths_{self.api_type}", 
                source_type="external", 
                config=config
            )
        except ImportError as e:
            logger.error(f"导入数据库管理器失败: {e}")
            self.db_manager = None
        
        # API实例(延迟初始化)
        self.api = None
        
        logger.info(f"初始化同花顺数据源 (类型: {self.api_type})")
        
        # 验证配置
        self._validate_config()
    
    def _validate_config(self):
        """
        验证配置是否正确
        """
        if self.api_type == "sdk":
            if not self.username or not self.password:
                logger.error("使用SDK方式需要用户名和密码")
                raise ValueError("使用SDK方式需要提供同花顺iFinD的用户名和密码")
        elif self.api_type == "http":
            if not self.refresh_token and not self.access_token:
                logger.error("使用HTTP API方式需要refresh_token或access_token")
                logger.error("您可以通过以下方式获取refresh_token:")
                logger.error("1. 登录'超级命令客户端'，在工具-refresh_token查询")
                logger.error("2. 访问网页版超级命令：https://quantapi.10jqka.com.cn/gwstatic/static/ds_web/super-command-web/index.html")
                raise ValueError("使用HTTP API方式需要提供同花顺的refresh_token或access_token")
        else:
            logger.error(f"不支持的API类型: {self.api_type}")
            raise ValueError(f"不支持的API类型: {self.api_type}，支持的类型为'sdk'和'http'")
    
    def _get_api(self):
        """
        获取或创建API实例
        
        Returns:
            API实例
        """
        if self.api is None:
            if self.api_type == "sdk":
                try:
                    # 设置SDK环境变量
                    sdk_dir = os.path.abspath(os.path.join("vendor", "ths_sdk", "extracted", "bin"))
                    os.environ["LD_LIBRARY_PATH"] = os.environ.get("LD_LIBRARY_PATH", "") + ":" + sdk_dir
                    logger.info(f"设置SDK环境变量LD_LIBRARY_PATH: {sdk_dir}")
                    
                    # 导入SDK模块
                    from src.utils.thsifind import get_ths_ifind
                    self.api = get_ths_ifind(self.username, self.password)
                    logger.info("同花顺SDK实例创建成功")
                except ImportError as e:
                    logger.error(f"导入SDK模块失败: {str(e)}")
                    logger.error("请确保同花顺iFinD客户端已安装且iFinDPy可访问")
                    raise
                except Exception as e:
                    logger.error(f"创建SDK实例失败: {str(e)}")
                    raise
            else:
                try:
                    # 导入HTTP API模块
                    from src.api.ths_http_api import get_ths_http_api
                    if self.access_token:
                        self.api = get_ths_http_api(access_token=self.access_token)
                    else:
                        self.api = get_ths_http_api(refresh_token=self.refresh_token)
                    logger.info("同花顺HTTP API实例创建成功")
                except ImportError as e:
                    logger.error(f"导入HTTP API模块失败: {str(e)}")
                    raise
                except Exception as e:
                    logger.error(f"创建HTTP API实例失败: {str(e)}")
                    raise
                
        return self.api
    
    def _get_cache_file_path(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> str:
        """
        获取缓存文件路径
        
        Args:
            symbol: 交易品种代码
            timeframe: 时间周期
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            缓存文件路径
        """
        filename = f"{symbol}_{timeframe}_{start_date}_{end_date}.csv"
        return os.path.join(self.cache_dir, filename)
    
    def _load_from_cache(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        从缓存加载数据
        
        Args:
            symbol: 交易品种代码
            timeframe: 时间周期
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            缓存的数据，如果缓存不存在则返回None
        """
        if not self.use_cache:
            return None
            
        cache_file = self._get_cache_file_path(symbol, timeframe, start_date, end_date)
        
        if os.path.exists(cache_file):
            try:
                df = pd.read_csv(cache_file)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                
                logger.info(f"从缓存加载数据: {cache_file}, 数据长度: {len(df)}")
                return df
            except Exception as e:
                logger.warning(f"读取缓存失败: {str(e)}")
                
        return None
    
    def _save_to_cache(self, df: pd.DataFrame, symbol: str, timeframe: str, start_date: str, end_date: str):
        """
        保存数据到缓存
        
        Args:
            df: 数据DataFrame
            symbol: 交易品种代码
            timeframe: 时间周期
            start_date: 开始日期
            end_date: 结束日期
        """
        if not self.use_cache:
            return
            
        cache_file = self._get_cache_file_path(symbol, timeframe, start_date, end_date)
        
        try:
            # 保存数据
            df.to_csv(cache_file)
            logger.info(f"保存数据到缓存: {cache_file}")
        except Exception as e:
            logger.warning(f"保存缓存失败: {str(e)}")
    
    def _convert_http_data_to_dataframe(self, kline_data: List[Dict]) -> pd.DataFrame:
        """
        将HTTP API返回的K线数据转换为DataFrame
        
        Args:
            kline_data: API返回的K线数据列表
            
        Returns:
            DataFrame格式的K线数据
        """
        if not kline_data:
            return pd.DataFrame()
            
        df = pd.DataFrame(kline_data)
        
        # 转换日期
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
        elif 'tradeDate' in df.columns:
            df['date'] = pd.to_datetime(df['tradeDate'])
            df.set_index('date', inplace=True)
            df = df.drop('tradeDate', axis=1)
            
        # 转换列名
        rename_dict = {
            'openPrice': 'open',
            'highPrice': 'high',
            'lowPrice': 'low',
            'closePrice': 'close',
            'turnoverVol': 'volume',
            'turnoverValue': 'amount'
        }
        
        df = df.rename(columns={k: v for k, v in rename_dict.items() if k in df.columns})
        
        # 转换数据类型
        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col])
        for col in ['volume', 'amount']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col])
        
        return df
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime] = None,
        timeframe: str = '1d',
        include_now: bool = False
    ) -> pd.DataFrame:
        """
        获取历史K线数据
        
        Args:
            symbol: 交易品种代码
            start_date: 开始日期
            end_date: 结束日期，默认为当前日期
            timeframe: 时间周期，如'1d'表示日线
            include_now: 是否包含当前最新数据
            
        Returns:
            包含OHLCV数据的DataFrame
        """
        # 转换日期格式
        if isinstance(start_date, datetime):
            start_date = start_date.strftime('%Y-%m-%d')
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        elif isinstance(end_date, datetime):
            end_date = end_date.strftime('%Y-%m-%d')
        
        # 首先尝试从数据库获取数据
        if self.db_manager:
            try:
                logger.info(f"尝试从数据库获取历史数据: {symbol}, {start_date} - {end_date}, {timeframe}")
                df = self.db_manager.get_kline_data(symbol, start_date, end_date, timeframe)
                if not df.empty:
                    logger.info(f"从数据库获取到{len(df)}条历史数据")
                    return df
            except Exception as e:
                logger.error(f"从数据库获取历史数据失败: {str(e)}")
        
        # 如果数据库中没有数据，尝试从缓存获取
        if self.use_cache:
            cache_df = self._load_from_cache(symbol, timeframe, start_date, end_date)
            if cache_df is not None:
                logger.info(f"从缓存获取历史数据: {symbol}, {timeframe}, {len(cache_df)}条记录")
                
                # 将缓存数据保存到数据库
                if self.db_manager:
                    try:
                        # 将DataFrame转换为列表字典
                        cache_df_copy = cache_df.copy()
                        cache_df_copy['date'] = cache_df_copy.index.strftime('%Y-%m-%d')
                        kline_data = cache_df_copy.reset_index(drop=True).to_dict('records')
                        
                        self.db_manager.insert_kline_data(
                            symbol=symbol,
                            kline_data=kline_data,
                            timeframe=timeframe,
                            source=f"ths_{self.api_type}_cache"
                        )
                        logger.info(f"成功将缓存数据保存到数据库: {symbol}, {len(kline_data)}条记录")
                    except Exception as e:
                        logger.error(f"保存缓存数据到数据库失败: {str(e)}")
                
                return cache_df
        
        # 从同花顺获取数据
        logger.info(f"从同花顺{self.api_type}获取历史数据: {symbol}, {start_date} - {end_date}")
        
        try:
            # 获取API实例
            api = self._get_api()
            
            if self.api_type == "sdk":
                # 使用SDK方式获取
                success, df, error_msg = api.get_daily_quotes(
                    symbol,
                    start_date,
                    end_date
                )
                
                if not success or df is None:
                    logger.error(f"获取历史数据失败: {error_msg}")
                    return pd.DataFrame()
                
            else:
                # 使用HTTP API方式获取
                if timeframe != '1d':
                    logger.warning(f"HTTP API暂不支持{timeframe}周期，将返回空DataFrame")
                    return pd.DataFrame()
                    
                success, kline_data = api.get_kline(
                    symbol,
                    start_date.replace('-', ''),
                    end_date.replace('-', ''),
                    adjust_type=1  # 前复权
                )
                
                if not success or not kline_data:
                    logger.error("获取历史数据失败")
                    return pd.DataFrame()
                
                # 转换为DataFrame
                df = self._convert_http_data_to_dataframe(kline_data)
            
            # 保存到缓存
            if self.use_cache and not df.empty:
                self._save_to_cache(df, symbol, timeframe, start_date, end_date)
            
            # 保存到数据库
            if self.db_manager and not df.empty:
                try:
                    # 将DataFrame转换为列表字典
                    df_copy = df.copy()
                    df_copy['date'] = df_copy.index.strftime('%Y-%m-%d')
                    kline_data = df_copy.reset_index(drop=True).to_dict('records')
                    
                    self.db_manager.insert_kline_data(
                        symbol=symbol,
                        kline_data=kline_data,
                        timeframe=timeframe,
                        source=f"ths_{self.api_type}"
                    )
                    logger.info(f"成功将API数据保存到数据库: {symbol}, {len(kline_data)}条记录")
                except Exception as e:
                    logger.error(f"保存API数据到数据库失败: {str(e)}")
            
            logger.info(f"获取历史数据成功: {symbol}, {timeframe}, {len(df)}条记录")
            return df
            
        except Exception as e:
            logger.error(f"获取历史数据异常: {str(e)}")
            return pd.DataFrame()
    
    def get_real_time_data(self, symbol: str) -> Dict:
        """
        获取实时行情数据
        
        Args:
            symbol: 交易品种代码
            
        Returns:
            实时行情数据字典
        """
        logger.info(f"获取实时行情: {symbol}")
        
        # 首先尝试从数据库获取最新行情
        if self.db_manager:
            try:
                logger.info(f"尝试从数据库获取实时行情: {symbol}")
                quote = self.db_manager.get_latest_quote(symbol)
                if quote:
                    logger.info(f"从数据库获取到实时行情: {symbol}")
                    return {
                        "symbol": symbol,
                        "price": quote.get("price"),
                        "change": quote.get("change_percent"),
                        "change_amount": quote.get("change_amount"),
                        "volume": quote.get("volume"),
                        "amount": quote.get("amount"),
                        "bid": quote.get("bid_price"),
                        "ask": quote.get("ask_price"),
                        "timestamp": quote.get("timestamp"),
                        "source": "database"
                    }
            except Exception as e:
                logger.error(f"从数据库获取实时行情失败: {str(e)}")
        
        # 从同花顺获取实时行情
        try:
            # 获取API实例
            api = self._get_api()
            
            if self.api_type == "sdk":
                # 使用SDK方式获取
                success, df_rt, error_msg = api.get_realtime_quotes(symbol)
                
                if not success or df_rt is None:
                    logger.error(f"获取实时行情失败: {error_msg}")
                    return {}
                
                # 解析数据
                row = df_rt.iloc[0] if not df_rt.empty else {}
                
                result = {
                    "symbol": symbol,
                    "price": row.get("now", None),
                    "change": None,  # 需要计算
                    "change_amount": None,  # 需要计算
                    "volume": row.get("volume", 0),
                    "amount": row.get("amount", 0),
                    "bid": None,  # iFinD API可能不提供
                    "ask": None,  # iFinD API可能不提供
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "ths_sdk",
                    "open": row.get("open", None),
                    "high": row.get("high", None),
                    "low": row.get("low", None),
                    "pe": row.get("pe", None),
                    "pb": row.get("pb", None),
                    "turnover": row.get("turnoverRatio", None)
                }
                
            else:
                # 使用HTTP API方式获取
                success, quote_data = api.get_quote(symbol)
                
                if not success or not quote_data:
                    logger.error(f"获取实时行情失败")
                    return {}
                
                # 解析数据
                result = {
                    "symbol": symbol,
                    "price": quote_data.get("lastPrice", None),
                    "change": quote_data.get("changePercent", None),
                    "change_amount": quote_data.get("change", None),
                    "volume": quote_data.get("volume", 0),
                    "amount": quote_data.get("amount", 0),
                    "bid": quote_data.get("bidPrice", None),
                    "ask": quote_data.get("askPrice", None),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "ths_http",
                    "open": quote_data.get("openPrice", None),
                    "high": quote_data.get("highPrice", None),
                    "low": quote_data.get("lowPrice", None),
                    "pe": quote_data.get("pe", None),
                    "pb": quote_data.get("pb", None),
                    "turnover": quote_data.get("turnoverRate", None)
                }
            
            # 保存到数据库
            if self.db_manager:
                try:
                    self.db_manager.update_real_time_quote(
                        symbol=symbol,
                        quote_data=result,
                        source=f"ths_{self.api_type}"
                    )
                    logger.info(f"成功将实时行情保存到数据库: {symbol}")
                except Exception as e:
                    logger.error(f"保存实时行情到数据库失败: {str(e)}")
            
            logger.info(f"获取实时行情成功: {symbol}")
            return result
            
        except Exception as e:
            logger.error(f"获取实时行情异常: {str(e)}")
            return {}
    
    def subscribe(self, symbols: List[str], callback: callable):
        """
        订阅行情
        
        Args:
            symbols: 交易品种代码列表
            callback: 回调函数，接收实时数据
        """
        logger.warning(f"同花顺{self.api_type}不支持WebSocket订阅，仅支持轮询")
        for symbol in symbols:
            self.callbacks[symbol] = callback
    
    def unsubscribe(self, symbols: List[str] = None):
        """
        取消订阅
        
        Args:
            symbols: 取消订阅的交易品种代码列表，如果为None则取消所有订阅
        """
        if symbols is None:
            self.callbacks.clear()
            logger.info("取消所有订阅")
        else:
            for symbol in symbols:
                if symbol in self.callbacks:
                    del self.callbacks[symbol]
            logger.info(f"取消订阅: {symbols}")

# 单例模式实现
_ths_data_feed_instance = None

def get_ths_data_feed(
    api_type: str = None, 
    username: str = None, 
    password: str = None,
    refresh_token: str = None,
    access_token: str = None,
    force_new: bool = False
) -> THSDataFeed:
    """
    获取THSDataFeed单例实例
    
    Args:
        api_type: API类型，'sdk'或'http'，如果为None则自动选择
        username: 同花顺SDK用户名
        password: 同花顺SDK密码
        refresh_token: 同花顺HTTP API的refresh_token
        access_token: 同花顺HTTP API的access_token（优先于refresh_token）
        force_new: 是否强制创建新实例
        
    Returns:
        THSDataFeed实例
    """
    global _ths_data_feed_instance
    
    # 如果实例已存在，但提供了新的access_token，则更新实例中的access_token
    if _ths_data_feed_instance is not None and access_token and not force_new:
        if _ths_data_feed_instance.api_type == "http":
            logger.info("更新现有实例的access_token")
            _ths_data_feed_instance.access_token = access_token
            # 确保下次调用时重新获取API实例
            _ths_data_feed_instance.api = None
            return _ths_data_feed_instance
    
    if _ths_data_feed_instance is None or force_new:
        # 自动选择API类型
        if api_type is None:
            api_type = "http" if get_config("ths_api", "use_http_api", False) else "sdk"
        
        _ths_data_feed_instance = THSDataFeed(
            api_type=api_type,
            username=username,
            password=password,
            refresh_token=refresh_token,
            access_token=access_token
        )
        
    return _ths_data_feed_instance 
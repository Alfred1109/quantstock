#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据获取模块
"""
import os
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union, Any
from src.utils.logger import get_logger
from src.utils.config import get_config

logger = get_logger("data_feed")

class DataFeed:
    """
    数据源基类
    定义数据获取接口
    """
    
    def __init__(self, name: str = "base"):
        """
        初始化数据源
        
        Args:
            name: 数据源名称
        """
        self.name = name
        logger.info(f"初始化数据源: {name}")
        
    def get_kline(self, symbol: str, start_date: str, end_date: str, period: str = "D", adjust_type: int = 1) -> pd.DataFrame:
        """
        获取K线数据
        
        Args:
            symbol: 证券代码
            start_date: 开始日期
            end_date: 结束日期
            period: K线周期，D=日线，W=周线，M=月线
            adjust_type: 复权类型，0=不复权，1=前复权，2=后复权
            
        Returns:
            K线数据DataFrame
        """
        raise NotImplementedError("子类必须实现get_kline方法")
    
    def get_quote(self, symbol: str) -> pd.DataFrame:
        """
        获取实时行情
        
        Args:
            symbol: 证券代码
            
        Returns:
            行情数据
        """
        raise NotImplementedError("子类必须实现get_quote方法")
    
    def get_index_stocks(self, index_code: str) -> List[Dict]:
        """
        获取指数成分股
        
        Args:
            index_code: 指数代码
            
        Returns:
            成分股列表
        """
        raise NotImplementedError("子类必须实现get_index_stocks方法")
    
    def get_industry_list(self, industry_type: str = "thi") -> List[Dict]:
        """
        获取行业列表
        
        Args:
            industry_type: 行业分类
            
        Returns:
            行业列表
        """
        raise NotImplementedError("子类必须实现get_industry_list方法")
    
    def get_industry_stocks(self, industry_code: str, industry_type: str = "thi") -> List[Dict]:
        """
        获取行业成分股
        
        Args:
            industry_code: 行业代码
            industry_type: 行业分类
            
        Returns:
            行业成分股列表
        """
        raise NotImplementedError("子类必须实现get_industry_stocks方法")


class THSSDKDataFeed(DataFeed):
    """
    同花顺SDK数据源
    使用同花顺SDK直接获取数据
    """
    
    def __init__(
        self,
        username: str = None,
        password: str = None,
        timeout: int = 10,
        retry_count: int = 3,
        use_cache: bool = True,
        cache_dir: str = "./output/data/cache"
    ):
        """
        初始化同花顺SDK数据源
        
        Args:
            username: 同花顺用户名
            password: 同花顺密码
            timeout: 请求超时时间
            retry_count: 请求失败重试次数
            use_cache: 是否使用缓存
            cache_dir: 缓存目录
        """
        super().__init__(name="ths_sdk")
        
        self.username = username
        self.password = password
        self.timeout = timeout
        self.retry_count = retry_count
        self.use_cache = use_cache
        self.cache_dir = cache_dir
        
        # 确保缓存目录存在
        if use_cache:
            os.makedirs(cache_dir, exist_ok=True)
        
        # 导入SDK API
        try:
            from api.ths_sdk_api import get_ths_sdk_api
            self.api = get_ths_sdk_api(username=username, password=password)
            logger.info("成功初始化同花顺SDK API")
        except Exception as e:
            logger.error(f"初始化同花顺SDK API失败: {e}")
            raise
    
    def get_kline(self, symbol: str, start_date: str, end_date: str, period: str = "D", adjust_type: int = 1) -> pd.DataFrame:
        """
        获取K线数据
        
        Args:
            symbol: 证券代码
            start_date: 开始日期
            end_date: 结束日期
            period: K线周期，D=日线，W=周线，M=月线
            adjust_type: 复权类型，0=不复权，1=前复权，2=后复权
            
        Returns:
            K线数据DataFrame
        """
        logger.info(f"获取K线数据: {symbol}, 周期: {period}, 时间: {start_date}至{end_date}")
        
        # 尝试从缓存加载
        if self.use_cache:
            cache_file = os.path.join(
                self.cache_dir, 
                f"kline_{symbol}_{period}_{adjust_type}_{start_date}_{end_date}.csv"
            )
            if os.path.exists(cache_file):
                try:
                    data = pd.read_csv(cache_file, index_col=0, parse_dates=True)
                    logger.info(f"从缓存加载K线数据: {cache_file}")
                    return data
                except Exception as e:
                    logger.warning(f"缓存加载失败: {e}")
        
        # 从API获取数据
        data = self.api.get_kline(symbol, start_date, end_date, period, adjust_type)
        
        # 保存到缓存
        if self.use_cache and data is not None and not data.empty:
            try:
                cache_file = os.path.join(
                    self.cache_dir, 
                    f"kline_{symbol}_{period}_{adjust_type}_{start_date}_{end_date}.csv"
                )
                data.to_csv(cache_file)
                logger.info(f"K线数据已缓存: {cache_file}")
            except Exception as e:
                logger.warning(f"缓存保存失败: {e}")
        
        return data
    
    def get_quote(self, symbol: str) -> pd.DataFrame:
        """
        获取实时行情
        
        Args:
            symbol: 证券代码
            
        Returns:
            行情数据
        """
        logger.info(f"获取实时行情: {symbol}")
        return self.api.get_realtime_quotes(symbol)
    
    def get_index_stocks(self, index_code: str) -> pd.DataFrame:
        """
        获取指数成分股
        
        Args:
            index_code: 指数代码
            
        Returns:
            成分股列表
        """
        logger.info(f"获取指数成分股: {index_code}")
        return self.api.get_index_stocks(index_code)
    
    def get_industry_list(self, industry_type: str = "THS") -> pd.DataFrame:
        """
        获取行业列表
        
        Args:
            industry_type: 行业分类，THS(同花顺行业)、SW(申万行业)等
            
        Returns:
            行业列表
        """
        logger.info(f"获取行业列表: {industry_type}")
        return self.api.get_industry_list(industry_type)
    
    def get_industry_stocks(self, industry_name: str, industry_type: str = "THS") -> pd.DataFrame:
        """
        获取行业成分股
        
        Args:
            industry_name: 行业名称
            industry_type: 行业分类
            
        Returns:
            行业成分股列表
        """
        logger.info(f"获取行业成分股: {industry_name}")
        return self.api.get_industry_stocks(industry_name)


class THSHTTPDataFeed(DataFeed):
    """
    从同花顺HTTP API获取数据的数据源
    """
    
    def __init__(
        self,
        refresh_token: str = None,
        access_token: str = None,
        api_url: str = None,
        timeout: int = 10,
        retry_count: int = 3,
        use_cache: bool = True,
        cache_dir: str = "./output/data/cache"
    ):
        """
        初始化同花顺HTTP数据源
        
        Args:
            refresh_token: 同花顺refresh_token
            access_token: 同花顺access_token
            api_url: 同花顺API地址
            timeout: 请求超时时间
            retry_count: 请求失败重试次数
            use_cache: 是否使用缓存
            cache_dir: 缓存目录
        """
        super().__init__(name="ths_http")
        
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.api_url = api_url
        self.timeout = timeout
        self.retry_count = retry_count
        self.use_cache = use_cache
        self.cache_dir = cache_dir
        
        # 确保缓存目录存在
        if use_cache:
            os.makedirs(cache_dir, exist_ok=True)
        
        # 导入HTTP API
        try:
            from api.ths_http_api import get_ths_http_api
            self.api = get_ths_http_api(
                refresh_token=refresh_token, 
                access_token=access_token
            )
            logger.info("成功初始化同花顺HTTP API")
        except Exception as e:
            logger.error(f"初始化同花顺HTTP API失败: {e}")
            raise
    
    def get_kline(self, symbol: str, start_date: str, end_date: str, period: str = "D", adjust_type: int = 1) -> pd.DataFrame:
        """
        获取K线数据
        
        Args:
            symbol: 证券代码
            start_date: 开始日期
            end_date: 结束日期
            period: K线周期，D=日线，W=周线，M=月线
            adjust_type: 复权类型，0=不复权，1=前复权，2=后复权
            
        Returns:
            K线数据DataFrame
        """
        logger.info(f"获取K线数据: {symbol}, 周期: {period}, 时间: {start_date}至{end_date}")
        
        # 日期格式转换，去除短横线
        start_date_fmt = start_date.replace("-", "")
        end_date_fmt = end_date.replace("-", "")
        
        # 尝试从缓存加载
        if self.use_cache:
            cache_file = os.path.join(
                self.cache_dir, 
                f"kline_{symbol}_{period}_{adjust_type}_{start_date_fmt}_{end_date_fmt}.csv"
            )
            if os.path.exists(cache_file):
                try:
                    data = pd.read_csv(cache_file, index_col=0, parse_dates=True)
                    logger.info(f"从缓存加载K线数据: {cache_file}")
                    return data
                except Exception as e:
                    logger.warning(f"缓存加载失败: {e}")
        
        # 从API获取数据
        success, result = self.api.get_kline(symbol, start_date_fmt, end_date_fmt, adjust_type)
        
        if success and result:
            # 转换为DataFrame
            df = pd.DataFrame(result)
            
            # 日期列转换为日期类型
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df.set_index("date", inplace=True)
            
            # 保存到缓存
            if self.use_cache:
                try:
                    cache_file = os.path.join(
                        self.cache_dir, 
                        f"kline_{symbol}_{period}_{adjust_type}_{start_date_fmt}_{end_date_fmt}.csv"
                    )
                    df.to_csv(cache_file)
                    logger.info(f"K线数据已缓存: {cache_file}")
                except Exception as e:
                    logger.warning(f"缓存保存失败: {e}")
                    
            return df
        else:
            logger.error(f"获取K线数据失败: {result}")
            return pd.DataFrame()
    
    def get_quote(self, symbol: str) -> pd.DataFrame:
        """
        获取实时行情
        
        Args:
            symbol: 证券代码
            
        Returns:
            行情数据
        """
        logger.info(f"获取实时行情: {symbol}")
        success, result = self.api.get_quote(symbol)
        
        if success and result:
            return pd.DataFrame([result])
        else:
            logger.error(f"获取实时行情失败: {result}")
            return pd.DataFrame()
    
    def get_index_stocks(self, index_code: str) -> pd.DataFrame:
        """
        获取指数成分股
        
        Args:
            index_code: 指数代码
            
        Returns:
            成分股列表
        """
        logger.info(f"获取指数成分股: {index_code}")
        success, result = self.api.get_index_stocks(index_code)
        
        if success and result:
            return pd.DataFrame(result)
        else:
            logger.error(f"获取指数成分股失败: {result}")
            return pd.DataFrame()
    
    def get_industry_list(self, industry_type: str = "thi") -> pd.DataFrame:
        """
        获取行业列表
        
        Args:
            industry_type: 行业分类
            
        Returns:
            行业列表
        """
        logger.info(f"获取行业列表: {industry_type}")
        success, result = self.api.get_industry_list(industry_type)
        
        if success and result:
            return pd.DataFrame(result)
        else:
            logger.error(f"获取行业列表失败: {result}")
            return pd.DataFrame()
    
    def get_industry_stocks(self, industry_code: str, industry_type: str = "thi") -> pd.DataFrame:
        """
        获取行业成分股
        
        Args:
            industry_code: 行业代码
            industry_type: 行业分类
            
        Returns:
            行业成分股列表
        """
        logger.info(f"获取行业成分股: {industry_code}")
        success, result = self.api.get_industry_stocks(industry_code, industry_type)
        
        if success and result:
            return pd.DataFrame(result)
        else:
            logger.error(f"获取行业成分股失败: {result}")
            return pd.DataFrame()


# 数据源工厂
def create_data_feed(data_source_type: str = None) -> DataFeed:
    """
    创建数据源
    
    Args:
        data_source_type: 数据源类型，不指定时从配置文件读取
        
    Returns:
        DataFeed对象
    """
    if data_source_type is None:
        data_source_type = get_config("system", "data_source", "ths_sdk")
        
    logger.info(f"创建数据源: {data_source_type}")
    
    if data_source_type == "ths_sdk":
        # 创建同花顺SDK数据源
        username = get_config("ths_api", "username", "")
        password = get_config("ths_api", "password", "")
        timeout = get_config("ths_api", "timeout", 10)
        retry_count = get_config("ths_api", "retry_count", 3)
        
        if not username or not password:
            logger.error("未配置同花顺用户名或密码")
            raise ValueError("必须配置同花顺用户名和密码")
            
        return THSSDKDataFeed(
            username=username,
            password=password,
            timeout=timeout,
            retry_count=retry_count
        )
        
    elif data_source_type == "ths_http":
        # 创建同花顺HTTP数据源
        refresh_token = get_config("ths_api", "refresh_token", "")
        access_token = get_config("ths_api", "access_token", "")
        api_url = get_config("ths_api", "api_url", "https://quantapi.10jqka.com.cn")
        timeout = get_config("ths_api", "timeout", 10)
        retry_count = get_config("ths_api", "retry_count", 3)
        
        if not refresh_token and not access_token:
            logger.error("未配置同花顺refresh_token或access_token")
            raise ValueError("必须配置同花顺refresh_token或access_token")
            
        return THSHTTPDataFeed(
            refresh_token=refresh_token,
            access_token=access_token,
            api_url=api_url,
            timeout=timeout,
            retry_count=retry_count
        )
        
    else:
        logger.error(f"不支持的数据源类型: {data_source_type}")
        raise ValueError(f"不支持的数据源类型: {data_source_type}")


# 单例模式，保持一个全局实例
_data_feed_instance = None

def get_data_feed(force_new: bool = False) -> DataFeed:
    """
    获取数据源实例（单例模式）
    
    Args:
        force_new: 是否强制创建新实例
        
    Returns:
        DataFeed实例
    """
    global _data_feed_instance
    
    if force_new or _data_feed_instance is None:
        _data_feed_instance = create_data_feed()
        
    return _data_feed_instance

if __name__ == "__main__":
    # 测试代码
    import pandas as pd
    from datetime import datetime, timedelta
    
    # 创建本地数据源
    local_data_feed = create_data_feed("local")
    
    # 创建模拟数据
    start_date = datetime.now() - timedelta(days=100)
    end_date = datetime.now()
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    
    data = {
        'date': dates,
        'open': np.random.normal(100, 1, len(dates)),
        'high': np.random.normal(101, 1, len(dates)),
        'low': np.random.normal(99, 1, len(dates)),
        'close': np.random.normal(100, 1, len(dates)),
        'volume': np.random.normal(1000000, 100000, len(dates))
    }
    
    df = pd.DataFrame(data)
    df.set_index('date', inplace=True)
    
    # 保存模拟数据
    local_data_feed.save_data(symbol="000001.SH", data=df)
    
    # 读取数据
    historical_data = local_data_feed.get_historical_data(
        symbol="000001.SH",
        start_date=start_date,
        end_date=end_date
    )
    
    print("获取的历史数据:")
    print(historical_data.head())
    
    # 创建同花顺数据源（仅测试接口）
    try:
        ths_data_feed = create_data_feed("ths")
        print("同花顺数据源创建成功")
    except Exception as e:
        print(f"创建同花顺数据源失败: {str(e)}") 
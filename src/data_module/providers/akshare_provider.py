import logging
import time
from typing import Dict, List, Optional, Any, Union
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import numpy as np
from .base_provider import BaseDataProvider

# 尝试导入akshare
try:
    import akshare as ak
except ImportError:
    logging.warning("无法导入akshare库，请确保已正确安装akshare")

# 设置日志
logger = logging.getLogger(__name__)

class AKShareDataProvider(BaseDataProvider):
    """
    AKShare数据提供器
    官方文档：https://akshare.akfamily.xyz/introduction.html
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.logger = logger
        
        # 从配置中读取设置
        self.use_cache = config.get('use_cache', True)
        self.cache_dir = config.get('cache_dir', 'output/cache/akshare')
        self.timeout_seconds = config.get('timeout_seconds', 30)
        self.retry_attempts = config.get('retry_attempts', 3)
        self.default_exchange = config.get('default_exchange', 'sh')
        
        # 确保缓存目录存在
        if self.use_cache and not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_cached_file_path(self, data_type: str, params: Dict[str, Any]) -> str:
        """获取缓存文件路径"""
        # 创建一个唯一的文件名
        param_str = "_".join([f"{k}_{v}" for k, v in sorted(params.items())])
        filename = f"{data_type}_{param_str}.csv"
        # 替换特殊字符
        filename = filename.replace("/", "_").replace(":", "_")
        return os.path.join(self.cache_dir, filename)
    
    def _save_to_cache(self, data: pd.DataFrame, file_path: str) -> None:
        """保存数据到缓存"""
        if self.use_cache and data is not None and not data.empty:
            try:
                data.to_csv(file_path, index=False)
                self.logger.debug(f"数据已缓存到: {file_path}")
            except Exception as e:
                self.logger.error(f"缓存数据时出错: {e}")
    
    def _load_from_cache(self, file_path: str) -> Optional[pd.DataFrame]:
        """从缓存加载数据"""
        if self.use_cache and os.path.exists(file_path):
            try:
                data = pd.read_csv(file_path)
                self.logger.debug(f"从缓存加载数据: {file_path}")
                return data
            except Exception as e:
                self.logger.error(f"从缓存加载数据时出错: {e}")
        return None
    
    def get_stock_list(self) -> pd.DataFrame:
        """
        获取A股股票列表
        
        返回:
            pd.DataFrame: 包含股票列表的DataFrame
        """
        cache_file = self._get_cached_file_path("stock_list", {})
        
        # 尝试从缓存加载
        cached_data = self._load_from_cache(cache_file)
        if cached_data is not None:
            return cached_data
        
        # 获取A股股票列表
        for attempt in range(self.retry_attempts):
            try:
                stock_list = ak.stock_info_a_code_name()
                
                # 缓存数据
                self._save_to_cache(stock_list, cache_file)
                
                return stock_list
            except Exception as e:
                self.logger.error(f"获取股票列表失败 (尝试 {attempt+1}/{self.retry_attempts}): {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(1)  # 重试前等待
        
        # 所有尝试都失败
        return pd.DataFrame()
    
    def get_historical_data(self, symbol: str, start_date: str = None, end_date: str = None, 
                          period: str = 'daily', adjust: str = 'qfq', timeframe: str = None) -> pd.DataFrame:
        """
        获取历史行情数据
        
        参数:
            symbol (str): 股票代码，例如 '600000' 或 '600000.SH'
            start_date (str, 可选): 开始日期，格式 'YYYY-MM-DD'
            end_date (str, 可选): 结束日期，格式 'YYYY-MM-DD'
            period (str, 可选): 数据周期，'daily'(日线)、'weekly'(周线)、'monthly'(月线)
            adjust (str, 可选): 复权类型，'qfq'(前复权)、'hfq'(后复权)、None(不复权)
            timeframe (str, 可选): 与backtesting_module兼容的时间周期参数，将被映射到period
                                  如 '1d' -> 'daily', '1w' -> 'weekly', '1mo' -> 'monthly'
            
        返回:
            pd.DataFrame: 历史行情数据
        """
        self.logger.info(f"正在获取股票 {symbol} 的历史数据，从 {start_date} 到 {end_date}，周期 {period}，复权 {adjust}")
        
        # 如果提供了timeframe参数，将其映射到period
        if timeframe:
            timeframe_map = {
                '1d': 'daily',
                '1h': 'daily',  # akshare没有小时级数据，暂时映射到日线
                '5m': 'daily',  # akshare没有分钟级数据，暂时映射到日线
                '1w': 'weekly',
                '1mo': 'monthly'
            }
            period = timeframe_map.get(timeframe, 'daily')
            
        # 处理股票代码，移除可能的后缀
        if '.' in symbol:
            pure_symbol = symbol.split('.')[0]
            market = symbol.split('.')[1].lower() if len(symbol.split('.')) > 1 else None
        else:
            pure_symbol = symbol
            market = None
            
        self.logger.debug(f"处理后的股票代码: {pure_symbol}, 市场: {market}")
            
        # 格式化日期
        if not start_date:
            start_date = '2000-01-01'
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
            
        # 缓存参数
        cache_params = {
            'symbol': pure_symbol,
            'start_date': start_date,
            'end_date': end_date,
            'period': period,
            'adjust': adjust
        }
        
        cache_file = self._get_cached_file_path("historical_data", cache_params)
        
        # 尝试从缓存加载
        cached_data = self._load_from_cache(cache_file)
        if cached_data is not None:
            self.logger.info(f"从缓存加载 {pure_symbol} 历史数据，共 {len(cached_data)} 条记录")
            return cached_data
            
        # 设置复权参数，在AKShare中：
        # 不复权: ""
        # 前复权: "qfq"
        # 后复权: "hfq"
        if adjust is None or adjust.lower() == 'none':
            adj = ""
        else:
            adj = adjust.lower()
            
        # 设置周期参数
        period_map = {
            'daily': 'daily',
            'weekly': 'weekly',
            'monthly': 'monthly'
        }
        freq = period_map.get(period, 'daily')
        
        # 增加重试次数和等待时间
        max_retries = self.retry_attempts * 2
        wait_time = 2  # 初始等待时间，秒
            
        for attempt in range(max_retries):
            try:
                self.logger.info(f"第 {attempt+1}/{max_retries} 次尝试获取 {pure_symbol} 的历史数据")
                
                # 判断是否是指数
                data = None
                is_index = False
                
                # 优先使用市场标识判断
                if market == 'sh' or market == 'sz':
                    market_code = market
                # 根据代码判断市场
                elif pure_symbol.startswith('6'):
                    market_code = 'sh'
                else:
                    market_code = 'sz'
                
                # 判断股票代码类型（指数或个股）
                if pure_symbol.startswith('0') and len(pure_symbol) == 6 and (pure_symbol.startswith('000') or pure_symbol.startswith('399')):  # 指数
                    is_index = True
                    self.logger.debug(f"识别 {pure_symbol} 为指数代码")
                    try:
                        if pure_symbol.startswith('000'):  # 上证系列指数
                            self.logger.debug(f"尝试获取上证指数 {pure_symbol} 数据")
                            data = ak.stock_zh_index_daily(symbol="sh" + pure_symbol)
                        else:
                            self.logger.debug(f"尝试获取深证指数 {pure_symbol} 数据")
                            data = ak.stock_zh_index_daily(symbol="sz" + pure_symbol)
                    except Exception as e:
                        self.logger.warning(f"获取指数数据失败: {e}，尝试使用股票接口")
                        is_index = False  # 如果指数接口失败，尝试用股票接口
                        
                # 如果不是指数或者指数接口失败
                if not is_index or data is None:
                    # 移除日期中的连字符，AKShare需要YYYYMMDD格式
                    start_date_clean = start_date.replace('-', '')
                    end_date_clean = end_date.replace('-', '')
                    
                    self.logger.debug(f"尝试获取股票 {pure_symbol} 数据，市场代码: {market_code}")
                    
                    # 首先尝试使用腾讯接口
                    try:
                        self.logger.debug("使用腾讯接口获取数据")
                        data = ak.stock_zh_a_hist_tx(
                            symbol=market_code + pure_symbol,
                            # 只传递腾讯接口支持的参数
                            start_date=start_date,
                            end_date=end_date,
                            adjust=adj
                        )
                        self.logger.info(f"腾讯接口成功获取 {pure_symbol} 数据，共 {len(data) if data is not None else 0} 条记录")
                    except Exception as tx_error:
                        self.logger.warning(f"腾讯接口获取失败: {tx_error}，尝试东方财富接口")
                        try:
                            # 然后尝试东方财富接口
                            self.logger.debug("使用东方财富接口获取数据")
                            data = ak.stock_zh_a_hist(
                                symbol=pure_symbol, 
                                period=freq, 
                                start_date=start_date_clean,
                                end_date=end_date_clean,
                                adjust=adj
                            )
                            self.logger.info(f"东方财富接口成功获取 {pure_symbol} 数据，共 {len(data) if data is not None else 0} 条记录")
                        except Exception as em_error:
                            self.logger.warning(f"东方财富接口获取失败: {em_error}，已尝试所有可用接口")
                            raise ValueError(f"无法通过任何可用接口获取 {pure_symbol} 的历史数据")
                
                # 检查数据是否为空
                if data is None or data.empty:
                    self.logger.warning(f"获取到的 {pure_symbol} 数据为空")
                    raise ValueError(f"获取到的 {pure_symbol} 数据为空")
                
                self.logger.info(f"成功获取 {pure_symbol} 历史数据，共 {len(data)} 条记录")
                
                # 规范化列名
                data = self._normalize_columns(data)
                
                # 确保日期列是datetime类型
                if 'date' in data.columns:
                    data['date'] = pd.to_datetime(data['date'])
                
                # 缓存数据
                self._save_to_cache(data, cache_file)
                
                return data
            except Exception as e:
                self.logger.error(f"获取历史数据失败 (尝试 {attempt+1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    # 使用指数增长的等待时间
                    wait_seconds = wait_time * (2 ** attempt)
                    if wait_seconds > 30:
                        wait_seconds = 30  # 最长等待30秒
                    self.logger.info(f"等待 {wait_seconds} 秒后重试...")
                    time.sleep(wait_seconds)  # 重试前等待
        
        # 所有尝试都失败
        self.logger.error(f"获取 {pure_symbol} 历史数据失败，已尝试 {max_retries} 次")
        return pd.DataFrame()
        
    def _normalize_columns(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        统一规范化列名，处理不同接口返回的不同列名
        
        参数:
            data (pd.DataFrame): 原始数据
            
        返回:
            pd.DataFrame: 规范化后的数据
        """
        if data is None or data.empty:
            return pd.DataFrame()
            
        # 列名映射字典
        column_maps = [
            # 中文列名映射
            {
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
                '振幅': 'amplitude',
                '涨跌幅': 'change_pct',
                '涨跌额': 'change',
                '换手率': 'turnover'
            },
            # 英文列名映射（可能的变种）
            {
                'date': 'date',
                'open': 'open',
                'close': 'close',
                'high': 'high',
                'low': 'low',
                'volume': 'volume',
                'amount': 'amount',
                'amp': 'amplitude',
                'pct_chg': 'change_pct',
                'change': 'change',
                'turn': 'turnover'
            }
        ]
        
        # 尝试每种映射
        for column_map in column_maps:
            rename_dict = {}
            for src, dst in column_map.items():
                if src in data.columns:
                    rename_dict[src] = dst
            if rename_dict:
                data = data.rename(columns=rename_dict)
                
        self.logger.debug(f"规范化后的列名: {list(data.columns)}")
        return data
    
    def get_current_price(self, symbols: Union[str, List[str]]) -> pd.DataFrame:
        """
        获取实时行情数据
        
        参数:
            symbols (str 或 List[str]): 单个股票代码或股票代码列表
            
        返回:
            pd.DataFrame: 实时行情数据
        """
        self.logger.info(f"正在获取实时行情数据: {symbols}")
        
        # 转换单个股票为列表
        if isinstance(symbols, str):
            symbols = [symbols]
            
        # 处理股票代码，移除可能的后缀
        pure_symbols = []
        market_info = {}  # 保存市场信息，用于备选接口
        
        for symbol in symbols:
            if '.' in symbol:
                parts = symbol.split('.')
                pure_symbol = parts[0]
                pure_symbols.append(pure_symbol)
                if len(parts) > 1:
                    market_info[pure_symbol] = parts[1].lower()
            else:
                pure_symbols.append(symbol)
                # 根据代码判断市场
                if symbol.startswith('6'):
                    market_info[symbol] = 'sh'
                else:
                    market_info[symbol] = 'sz'
        
        self.logger.debug(f"处理后的股票代码: {pure_symbols}, 市场信息: {market_info}")
        
        # 增加重试次数和等待时间
        max_retries = self.retry_attempts * 2
        wait_time = 1  # 初始等待时间，秒
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"第 {attempt+1}/{max_retries} 次尝试获取实时行情")
                
                # 尝试不同的数据源获取实时行情
                data = None
                
                # 1. 首先尝试东方财富接口
                try:
                    self.logger.debug("使用东方财富接口获取实时行情")
                    data = ak.stock_zh_a_spot_em()
                    
                    if data is None or data.empty:
                        raise ValueError("东方财富接口返回空数据")
                        
                except Exception as em_error:
                    self.logger.warning(f"东方财富接口获取失败: {em_error}")
                    data = None
                
                # 2. 如果东方财富失败，尝试新浪接口
                if data is None:
                    try:
                        self.logger.debug("使用新浪接口获取实时行情")
                        # 新浪不支持批量查询，需要拼接代码
                        symbols_with_market = []
                        for s in pure_symbols:
                            market = market_info.get(s, 'sh' if s.startswith('6') else 'sz')
                            symbols_with_market.append(f"{market}{s}")
                        
                        data_list = []
                        for ms in symbols_with_market:
                            try:
                                single_data = ak.stock_zh_a_minute(symbol=ms, period="1", adjust="qfq")
                                if not single_data.empty:
                                    # 取最新一条数据作为实时行情
                                    latest = single_data.iloc[-1:].copy()
                                    latest['symbol'] = ms[2:]  # 去掉市场前缀
                                    data_list.append(latest)
                            except Exception as e:
                                self.logger.warning(f"获取 {ms} 分钟线数据失败: {e}")
                        
                        if data_list:
                            data = pd.concat(data_list, ignore_index=True)
                        else:
                            data = None
                    
                    except Exception as sina_error:
                        self.logger.warning(f"新浪接口获取失败: {sina_error}")
                        data = None
                
                # 3. 如果还是失败，尝试腾讯接口
                if data is None:
                    try:
                        self.logger.debug("使用腾讯接口获取实时行情")
                        # 腾讯接口
                        data_list = []
                        for s in pure_symbols:
                            market = market_info.get(s, 'sh' if s.startswith('6') else 'sz')
                            try:
                                single_data = ak.stock_zh_a_hist_tx(symbol=f"{market}{s}", start_date=(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'), end_date=datetime.now().strftime('%Y-%m-%d'))
                                if not single_data.empty:
                                    latest = single_data.iloc[-1:].copy()
                                    latest['symbol'] = s
                                    data_list.append(latest)
                            except Exception as e:
                                self.logger.warning(f"获取 {s} 腾讯历史数据失败: {e}")
                        
                        if data_list:
                            data = pd.concat(data_list, ignore_index=True)
                        else:
                            data = None
                    
                    except Exception as tx_error:
                        self.logger.warning(f"腾讯接口获取失败: {tx_error}")
                        data = None
                
                # 检查是否获取到数据
                if data is None:
                    self.logger.error("所有实时行情接口均失败，无法获取数据")
                    raise ValueError("无法通过任何接口获取实时行情数据")
                
                # 过滤出需要的股票
                if not data.empty:
                    # 处理东方财富数据
                    if '代码' in data.columns:
                        # 规范化代码格式，移除市场后缀
                        data['代码'] = data['代码'].astype(str).str.replace(r'\.\w+$', '', regex=True)
                        
                        # 过滤股票
                        filtered_data = data[data['代码'].isin(pure_symbols)]
                        
                        # 规范化列名
                        filtered_data = filtered_data.rename(columns={
                            '代码': 'symbol',
                            '名称': 'name',
                            '最新价': 'price',
                            '涨跌幅': 'change_pct',
                            '涨跌额': 'change',
                            '成交量': 'volume',
                            '成交额': 'amount',
                            '振幅': 'amplitude',
                            '最高': 'high',
                            '最低': 'low',
                            '今开': 'open',
                            '昨收': 'pre_close'
                        })
                    else:
                        # 已经是处理过的其他接口数据
                        filtered_data = data
                        # 统一列名
                        filtered_data = self._normalize_columns(filtered_data)
                    
                    if not filtered_data.empty:
                        self.logger.info(f"成功获取 {len(filtered_data)} 条实时行情数据")
                        return filtered_data
                    else:
                        self.logger.warning("过滤后没有匹配的股票数据")
                        raise ValueError("过滤后没有符合条件的股票数据")
                
                self.logger.error("获取到的数据为空")
                return pd.DataFrame()
                
            except Exception as e:
                self.logger.error(f"获取实时行情失败 (尝试 {attempt+1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    # 使用指数增长的等待时间
                    wait_seconds = wait_time * (2 ** attempt)
                    if wait_seconds > 15:
                        wait_seconds = 15  # 最长等待15秒，实时行情不宜等待太久
                    self.logger.info(f"等待 {wait_seconds} 秒后重试...")
                    time.sleep(wait_seconds)  # 重试前等待
        
        # 所有尝试都失败，尝试从历史数据中获取最近数据作为备用
        self.logger.warning(f"实时行情获取失败，尝试获取最近历史数据作为替代")
        try:
            result_data = []
            for symbol in symbols:
                try:
                    end_date = datetime.now().strftime('%Y-%m-%d')
                    start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
                    hist_data = self.get_historical_data(symbol=symbol, start_date=start_date, end_date=end_date)
                    if not hist_data.empty:
                        latest_data = hist_data.iloc[-1:].copy()
                        if 'date' in latest_data.columns:
                            latest_data['fetch_time'] = datetime.now().isoformat()
                        
                        # 确保有symbol列
                        if '.' in symbol:
                            pure_symbol = symbol.split('.')[0]
                        else:
                            pure_symbol = symbol
                            
                        latest_data['symbol'] = pure_symbol
                        result_data.append(latest_data)
                except Exception as hist_err:
                    self.logger.error(f"获取 {symbol} 历史数据作为替代也失败: {hist_err}")
                    
            if result_data:
                final_data = pd.concat(result_data, ignore_index=True)
                self.logger.info(f"使用历史数据作为实时行情替代，共 {len(final_data)} 条数据")
                return final_data
        except Exception as backup_err:
            self.logger.error(f"备用方案也失败: {backup_err}")
        
        # 一切尝试都失败
        self.logger.error("所有获取实时行情的尝试均已失败")
        return pd.DataFrame()
    
    def get_index_components(self, index_code: str) -> pd.DataFrame:
        """
        获取指数成分股
        
        参数:
            index_code (str): 指数代码，例如 '000300' 或 '000300.SH'（沪深300）
            
        返回:
            pd.DataFrame: 成分股数据
        """
        # 处理指数代码，移除可能的后缀
        if '.' in index_code:
            pure_index = index_code.split('.')[0]
        else:
            pure_index = index_code
            
        # 缓存参数
        cache_params = {'index_code': pure_index}
        cache_file = self._get_cached_file_path("index_components", cache_params)
        
        # 尝试从缓存加载
        cached_data = self._load_from_cache(cache_file)
        if cached_data is not None:
            return cached_data
            
        for attempt in range(self.retry_attempts):
            try:
                # 根据指数代码选择适当的API
                if pure_index == '000300':  # 沪深300
                    data = ak.index_stock_cons_weight_csindex(symbol="000300")
                elif pure_index == '000016':  # 上证50
                    data = ak.index_stock_cons_weight_csindex(symbol="000016")
                elif pure_index == '000905':  # 中证500
                    data = ak.index_stock_cons_weight_csindex(symbol="000905")
                elif pure_index == '000010':  # 上证180
                    data = ak.index_stock_cons_weight_csindex(symbol="000010")
                elif pure_index == '000688':  # 科创50
                    data = ak.index_stock_cons_weight_csindex(symbol="000688")
                else:
                    # 默认尝试通过成分股API获取
                    data = ak.index_stock_cons(symbol=pure_index)
                
                # 缓存数据
                self._save_to_cache(data, cache_file)
                
                return data
            except Exception as e:
                self.logger.error(f"获取指数成分股失败 (尝试 {attempt+1}/{self.retry_attempts}): {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(1)  # 重试前等待
        
        # 所有尝试都失败
        return pd.DataFrame()
    
    def get_financial_data(self, symbol: str, report_type: str = 'income') -> pd.DataFrame:
        """
        获取财务数据
        
        参数:
            symbol (str): 股票代码，例如 '600000' 或 '600000.SH'
            report_type (str, 可选): 报表类型，'income'(利润表)、'balance'(资产负债表)、'cash'(现金流量表)
            
        返回:
            pd.DataFrame: 财务数据
        """
        # 处理股票代码，移除可能的后缀
        if '.' in symbol:
            pure_symbol = symbol.split('.')[0]
        else:
            pure_symbol = symbol
            
        # 缓存参数
        cache_params = {'symbol': pure_symbol, 'report_type': report_type}
        cache_file = self._get_cached_file_path("financial_data", cache_params)
        
        # 尝试从缓存加载
        cached_data = self._load_from_cache(cache_file)
        if cached_data is not None:
            return cached_data
            
        for attempt in range(self.retry_attempts):
            try:
                # 根据报表类型选择适当的API
                if report_type == 'income':
                    data = ak.stock_financial_report_sina(symbol=pure_symbol, symbol_type="利润表")
                elif report_type == 'balance':
                    data = ak.stock_financial_report_sina(symbol=pure_symbol, symbol_type="资产负债表")
                elif report_type == 'cash':
                    data = ak.stock_financial_report_sina(symbol=pure_symbol, symbol_type="现金流量表")
                else:
                    data = ak.stock_financial_report_sina(symbol=pure_symbol, symbol_type="利润表")
                
                # 缓存数据
                self._save_to_cache(data, cache_file)
                
                return data
            except Exception as e:
                self.logger.error(f"获取财务数据失败 (尝试 {attempt+1}/{self.retry_attempts}): {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(1)  # 重试前等待
        
        # 所有尝试都失败
        return pd.DataFrame()
    
    def get_macro_data(self, indicator: str) -> pd.DataFrame:
        """
        获取宏观经济数据
        
        参数:
            indicator (str): 指标名称，例如 'cpi', 'pmi', 'gdp'
            
        返回:
            pd.DataFrame: 宏观经济数据
        """
        # 缓存参数
        cache_params = {'indicator': indicator}
        cache_file = self._get_cached_file_path("macro_data", cache_params)
        
        # 尝试从缓存加载
        cached_data = self._load_from_cache(cache_file)
        if cached_data is not None:
            return cached_data
            
        for attempt in range(self.retry_attempts):
            try:
                # 根据指标选择适当的API
                if indicator == 'cpi':
                    data = ak.macro_china_cpi_yearly()
                elif indicator == 'pmi':
                    data = ak.macro_china_pmi_yearly()
                elif indicator == 'gdp':
                    data = ak.macro_china_gdp_yearly()
                elif indicator == 'interest_rate':
                    data = ak.interest_rate_data()
                else:
                    raise ValueError(f"不支持的宏观指标: {indicator}")
                
                # 缓存数据
                self._save_to_cache(data, cache_file)
                
                return data
            except Exception as e:
                self.logger.error(f"获取宏观经济数据失败 (尝试 {attempt+1}/{self.retry_attempts}): {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(1)  # 重试前等待
        
        # 所有尝试都失败
        return pd.DataFrame()
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            Dict[str, Any]: 健康状态信息
        """
        return {"status": "ok", "provider": "AKShareDataProvider"}
        
    def get_stock_news(self, symbol: str, count: int = 10) -> pd.DataFrame:
        """
        获取特定股票的相关新闻
        
        参数:
            symbol (str): 股票代码
            count (int): 获取的新闻条数
            
        返回:
            pd.DataFrame: 包含新闻标题、日期、链接等信息的DataFrame
        """
        cache_params = {
            'symbol': symbol,
            'count': count,
            'date': datetime.now().strftime('%Y-%m-%d')  # 每日更新
        }
        
        cache_file = self._get_cached_file_path("stock_news", cache_params)
        
        # 尝试从缓存加载
        cached_data = self._load_from_cache(cache_file)
        if cached_data is not None:
            return cached_data
            
        try:
            # 移除可能的后缀
            if '.' in symbol:
                pure_symbol = symbol.split('.')[0]
            else:
                pure_symbol = symbol
                
            # 使用AKShare获取新闻
            # 注意：akshare的新闻接口可能有变化，需要根据实际情况调整
            news_data = None
            
            # 尝试获取个股新闻
            for attempt in range(self.retry_attempts):
                try:
                    # 尝试不同的新闻接口
                    try:
                        # 上市公司公告
                        if pure_symbol.startswith('6'):  # 上交所
                            news_data = ak.stock_notice_report(symbol=pure_symbol)
                        else:  # 深交所
                            news_data = ak.stock_notice_report(symbol=pure_symbol)
                    except Exception:
                        # 如果上市公司公告接口失败，尝试其他新闻接口
                        pass
                        
                    # 如果公司公告接口失败，可以尝试行业新闻
                    if news_data is None or news_data.empty:
                        # 可以替换为其他行业新闻接口
                        news_data = ak.stock_news_em()
                        
                    # 如果获取到数据
                    if news_data is not None and not news_data.empty:
                        # 限制条数
                        news_data = news_data.head(count)
                        # 添加获取时间
                        news_data['fetch_time'] = datetime.now().isoformat()
                        
                        # 缓存数据
                        self._save_to_cache(news_data, cache_file)
                        
                        return news_data
                        
                except Exception as e:
                    self.logger.error(f"获取股票新闻失败 (尝试 {attempt+1}/{self.retry_attempts}): {e}")
                    if attempt < self.retry_attempts - 1:
                        time.sleep(1)  # 重试前等待
            
            # 所有尝试都失败，返回空DataFrame
            return pd.DataFrame(columns=['date', 'title', 'link'])
                
        except Exception as e:
            self.logger.error(f"获取股票新闻时发生错误: {e}")
            # 返回空DataFrame
            return pd.DataFrame(columns=['date', 'title', 'link'])
            
    def get_market_news(self, count: int = 10) -> pd.DataFrame:
        """
        获取市场综合新闻
        
        参数:
            count (int): 获取的新闻条数
            
        返回:
            pd.DataFrame: 包含新闻标题、日期、链接等信息的DataFrame
        """
        cache_params = {
            'count': count,
            'date': datetime.now().strftime('%Y-%m-%d')  # 每日更新
        }
        
        cache_file = self._get_cached_file_path("market_news", cache_params)
        
        # 尝试从缓存加载
        cached_data = self._load_from_cache(cache_file)
        if cached_data is not None:
            return cached_data
            
        try:
            news_data = None
            
            # 尝试获取市场新闻
            for attempt in range(self.retry_attempts):
                try:
                    # 尝试东方财富网新闻
                    news_data = ak.stock_news_em()
                    
                    # 如果获取到数据
                    if news_data is not None and not news_data.empty:
                        # 限制条数
                        news_data = news_data.head(count)
                        # 添加获取时间
                        news_data['fetch_time'] = datetime.now().isoformat()
                        
                        # 缓存数据
                        self._save_to_cache(news_data, cache_file)
                        
                        return news_data
                        
                except Exception as e:
                    self.logger.error(f"获取市场新闻失败 (尝试 {attempt+1}/{self.retry_attempts}): {e}")
                    if attempt < self.retry_attempts - 1:
                        time.sleep(1)  # 重试前等待
            
            # 所有尝试都失败，返回空DataFrame
            return pd.DataFrame(columns=['date', 'title', 'link'])
                
        except Exception as e:
            self.logger.error(f"获取市场新闻时发生错误: {e}")
            # 返回空DataFrame
            return pd.DataFrame(columns=['date', 'title', 'link']) 
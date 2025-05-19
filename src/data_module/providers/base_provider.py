# Base class for all data providers
class BaseDataProvider:
    def __init__(self, config):
        self.config = config

    def get_market_data(self, symbol, start_date, end_date, timeframe='1d', **kwargs):
        raise NotImplementedError

    def get_historical_data(self, symbol, start_date=None, end_date=None, period='daily', adjust='qfq', timeframe=None):
        """
        获取历史行情数据
        
        参数:
            symbol (str): 股票代码
            start_date (str, 可选): 开始日期，格式 'YYYY-MM-DD'
            end_date (str, 可选): 结束日期，格式 'YYYY-MM-DD'
            period (str, 可选): 数据周期，'daily'(日线)、'weekly'(周线)、'monthly'(月线)
            adjust (str, 可选): 复权类型，'qfq'(前复权)、'hfq'(后复权)、None(不复权)
            timeframe (str, 可选): 与backtesting_module兼容的时间周期参数，将被映射到period
        """
        raise NotImplementedError

    def get_financial_data(self, symbol, report_type, period):
        raise NotImplementedError 
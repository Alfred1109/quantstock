from .base_provider import BaseDataProvider
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import random
import logging
import pandas as pd

logger = logging.getLogger(__name__) # Changed to __name__ for module-specific logger

class SimulatedDataProvider(BaseDataProvider):
    """
    模拟数据提供者。
    为回测生成或提供预定义的模拟市场数据。
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.start_date = datetime.strptime(config.get('start_date', '2023-01-01'), '%Y-%m-%d')
        self.end_date = datetime.strptime(config.get('end_date', '2024-01-01'), '%Y-%m-%d')
        self.symbols: List[str] = config.get('symbols', ['SIM_AAPL'])
        # Further config for data generation or loading path can be added here
        logger.info(f"SimulatedDataProvider initialized for symbols: {self.symbols}, period: {self.start_date} to {self.end_date}")

    def get_historical_data(self, 
                            symbol: str, 
                            start_date: str, 
                            end_date: str, 
                            timeframe: str = '1d', 
                            **kwargs) -> pd.DataFrame:
        """生成指定时间范围内的模拟历史K线数据。"""
        if symbol not in self.symbols:
            logger.warning(f"Symbol {symbol} not configured for SimulatedDataProvider.")
            return pd.DataFrame()

        historical_data_list = []
        current_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt_obj = datetime.strptime(end_date, '%Y-%m-%d')
        last_close = random.uniform(100, 200) # Initial random price

        while current_dt <= end_dt_obj:
            if timeframe == '1d' and current_dt.weekday() >= 5: # Skip weekends for daily data
                current_dt += timedelta(days=1)
                continue
            
            open_price = last_close * random.uniform(0.99, 1.01)
            high_price = open_price * random.uniform(1.0, 1.03)
            low_price = open_price * random.uniform(0.97, 1.0)
            close_price = random.uniform(low_price, high_price)
            volume = random.randint(100000, 2000000)
            last_close = close_price

            historical_data_list.append({
                'timestamp': current_dt, # Store as datetime object
                'symbol': symbol,
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': round(close_price, 2),
                'volume': volume
            })
            
            if timeframe == '1d':
                current_dt += timedelta(days=1)
            elif timeframe == '1h': # Simplified hourly, no market hours logic
                current_dt += timedelta(hours=1)
            else:
                logger.warning(f"Unsupported timeframe '{timeframe}' for simulated data generation. Defaulting to daily step.")
                current_dt += timedelta(days=1)
        
        logger.info(f"Generated {len(historical_data_list)} data points for {symbol} from {start_date} to {end_date}")
        
        if not historical_data_list:
            return pd.DataFrame()
            
        df = pd.DataFrame(historical_data_list)
        df['timestamp'] = pd.to_datetime(df['timestamp']) # Ensure datetime type
        return df

    def get_market_data(self, symbol: str, start_date: str, end_date: str, timeframe: str = '1d', **kwargs) -> pd.DataFrame:
        """获取市场数据，实际调用get_historical_data方法，确保接口一致性"""
        return self.get_historical_data(symbol, start_date, end_date, timeframe, **kwargs)

    def get_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取当前模拟价格 (简单实现，返回一个随机价格或最后一个生成的价格)。"""
        # This is a very basic mock. In a real simulation, you might want to fetch based on current backtest time.
        if symbol not in self.symbols:
            return None
        price = random.uniform(100,500) # Placeholder
        return {'symbol': symbol, 'price': price, 'close': price, 'timestamp': datetime.now().isoformat()}

    def health_check(self) -> Dict[str, Any]:
        return {"status": "ok", "provider": "SimulatedDataProvider"} 
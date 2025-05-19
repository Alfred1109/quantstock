import logging
import math
from typing import List, Dict, Any, Optional
import numpy as np # For more complex calculations if needed in future
from datetime import datetime

logger = logging.getLogger('app')

class PerformanceCalculator:
    """
    投资组合绩效计算器。

    根据投资组合历史价值和交易日志计算常用的绩效指标。
    """

    def __init__(self, portfolio_history: List[Dict[str, Any]], trade_log: List[Dict[str, Any]], initial_capital: float):
        """
        初始化绩效计算器。

        Args:
            portfolio_history: 投资组合每日或定期价值记录列表。
                                [{'timestamp': '...', 'total_value': ...}, ...]
            trade_log: 交易日志列表。
            initial_capital: 初始投入资本。
        """
        self.portfolio_history = sorted(portfolio_history, key=lambda x: x['timestamp'])
        self.trade_log = trade_log
        self.initial_capital = initial_capital
        self.returns_series: Optional[List[float]] = None
        self.timestamps: Optional[List[datetime]] = None

        if self.portfolio_history:
            self._calculate_returns_series()
        else:
            logger.warning("PerformanceCalculator: Portfolio history is empty. Some metrics will not be available.")

    def _calculate_returns_series(self):
        """从投资组合历史价值计算收益率序列。"""
        if not self.portfolio_history or len(self.portfolio_history) < 2:
            self.returns_series = []
            self.timestamps = []
            return

        values = np.array([item['total_value'] for item in self.portfolio_history])
        # Calculate simple returns: (current_value - previous_value) / previous_value
        # Using log returns: np.log(values[1:] / values[:-1]) is also an option for easier aggregation
        self.returns_series = (values[1:] - values[:-1]) / values[:-1]
        self.timestamps = [datetime.fromisoformat(item['timestamp']) for item in self.portfolio_history[1:]]
        
        # Ensure no NaN or Inf values if values[:-1] had zeros (should not happen with positive portfolio value)
        self.returns_series = np.nan_to_num(self.returns_series, nan=0.0, posinf=0.0, neginf=0.0).tolist()

    def get_total_return(self) -> float:
        """计算总回报率。"""
        if not self.portfolio_history:
            return 0.0
        final_value = self.portfolio_history[-1]['total_value']
        return (final_value - self.initial_capital) / self.initial_capital if self.initial_capital > 0 else 0.0

    def get_annualized_return(self, trading_days_per_year: int = 252) -> float:
        """计算年化回报率。"""
        if not self.returns_series or not self.timestamps or len(self.timestamps) < 1:
            return 0.0
        
        total_return_overall = self.get_total_return()
        num_days = (self.timestamps[-1] - datetime.fromisoformat(self.portfolio_history[0]['timestamp'])).days
        if num_days == 0: # Avoid division by zero if only one history point or same day
            return 0.0 
            
        num_years = num_days / 365.25 # More precise than trading_days_per_year for period length
        if num_years == 0: return 0.0 # Avoid issues with very short periods

        annualized_return = (1 + total_return_overall) ** (1 / num_years) - 1
        return annualized_return

    def get_sharpe_ratio(self, risk_free_rate: float = 0.0, trading_days_per_year: int = 252) -> float:
        """计算夏普比率。"""
        if not self.returns_series or len(self.returns_series) < 2:
            return 0.0
        
        mean_daily_return = np.mean(self.returns_series)
        std_daily_return = np.std(self.returns_series)
        
        if std_daily_return == 0: # Avoid division by zero if no volatility
            return 0.0 

        # Adjust risk-free rate to daily if provided as annual
        daily_risk_free_rate = (1 + risk_free_rate)**(1/trading_days_per_year) - 1
        
        excess_return = mean_daily_return - daily_risk_free_rate
        sharpe_ratio = excess_return / std_daily_return * np.sqrt(trading_days_per_year)
        return sharpe_ratio

    def get_sortino_ratio(self, risk_free_rate: float = 0.0, target_return: float = 0.0, trading_days_per_year: int = 252) -> float:
        """计算索提诺比率 (使用目标收益率作为下行偏差的基准)。"""
        if not self.returns_series or len(self.returns_series) < 2:
            return 0.0

        mean_daily_return = np.mean(self.returns_series)
        # Adjust risk-free rate to daily if provided as annual
        daily_risk_free_rate = (1 + risk_free_rate)**(1/trading_days_per_year) - 1
        daily_target_return = (1 + target_return)**(1/trading_days_per_year) - 1

        excess_return = mean_daily_return - daily_risk_free_rate

        # Calculate downside deviation
        downside_returns = [r for r in self.returns_series if r < daily_target_return]
        if not downside_returns:
            return float('inf') if excess_return > 0 else 0.0 # Or handle as very high if no downside risk

        downside_deviation = np.std([r - daily_target_return for r in downside_returns])
        
        if downside_deviation == 0: 
            return float('inf') if excess_return > 0 else 0.0

        sortino_ratio = excess_return / downside_deviation * np.sqrt(trading_days_per_year)
        return sortino_ratio

    def get_max_drawdown(self) -> float:
        """计算最大回撤。"""
        if not self.portfolio_history:
            return 0.0
        
        values = np.array([item['total_value'] for item in self.portfolio_history])
        if len(values) < 2:
            return 0.0

        peak = values[0]
        max_drawdown = 0.0
        for value in values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        return max_drawdown

    def get_volatility(self, trading_days_per_year: int = 252) -> float:
        """计算年化波动率。"""
        if not self.returns_series or len(self.returns_series) < 2:
            return 0.0
        std_daily_return = np.std(self.returns_series)
        annualized_volatility = std_daily_return * np.sqrt(trading_days_per_year)
        return annualized_volatility
    
    def get_calmar_ratio(self, risk_free_rate: float = 0.0, trading_days_per_year: int = 252) -> float:
        """计算卡玛比率 (年化收益率 / 最大回撤)。"""
        annual_return = self.get_annualized_return(trading_days_per_year=trading_days_per_year)
        # Note: annualized return used here is often taken as the geometric mean of returns over the period.
        # The self.get_annualized_return() is one way to compute this.
        
        max_dd = self.get_max_drawdown()
        if max_dd == 0:
            return float('inf') if annual_return > 0 else 0.0 # Or handle as appropriate
        
        calmar_ratio = annual_return / max_dd
        return calmar_ratio

    def get_trade_statistics(self) -> Dict[str, Any]:
        """计算交易相关的统计数据。"""
        if not self.trade_log:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'average_win_amount': 0,
                'average_loss_amount': 0,
                'profit_factor': 0,
                'average_trade_pnl': 0
            }

        total_trades = len(self.trade_log)
        winning_trades = 0
        losing_trades = 0
        total_profit_from_wins = 0
        total_loss_from_losses = 0

        # Simplified: assumes trade_log has 'realized_pnl_trade' for each SELL that closes/reduces a position
        # More accurate PnL per trade requires matching buys and sells, which is complex.
        # This approach uses PnL recorded at the time of SELL fill events.
        trade_pnls = [t.get('realized_pnl_trade', 0.0) for t in self.trade_log if t.get('action', '').upper() == 'SELL' and 'realized_pnl_trade' in t]
        
        if not trade_pnls: # No sell trades with PnL logged means we can't calculate these stats
            return {
                'total_trades': total_trades, # Still show total BUY/SELL operations
                'winning_trades': 0, 'losing_trades': 0, 'win_rate': 0,
                'average_win_amount': 0, 'average_loss_amount': 0, 'profit_factor': 0, 'average_trade_pnl':0
            }

        for pnl in trade_pnls:
            if pnl > 0:
                winning_trades += 1
                total_profit_from_wins += pnl
            elif pnl < 0:
                losing_trades += 1
                total_loss_from_losses += abs(pnl)
        
        num_closed_trades = winning_trades + losing_trades
        win_rate = winning_trades / num_closed_trades if num_closed_trades > 0 else 0
        avg_win = total_profit_from_wins / winning_trades if winning_trades > 0 else 0
        avg_loss = total_loss_from_losses / losing_trades if losing_trades > 0 else 0
        profit_factor = total_profit_from_wins / total_loss_from_losses if total_loss_from_losses > 0 else float('inf')
        avg_trade_pnl = sum(trade_pnls) / num_closed_trades if num_closed_trades > 0 else 0

        return {
            'total_trades': total_trades, # Number of all BUY/SELL operations processed
            'num_closed_trades_with_pnl': num_closed_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'average_win_amount': avg_win,
            'average_loss_amount': avg_loss,
            'profit_factor': profit_factor,
            'average_trade_pnl': avg_trade_pnl
        }

    def get_all_metrics(self, risk_free_rate: float = 0.0, trading_days_per_year: int = 252) -> Dict[str, Any]:
        """获取所有计算出的绩效指标。"""
        if not self.portfolio_history:
            return {"error": "Portfolio history is empty, cannot calculate metrics."}
            
        final_portfolio_summary = self.portfolio_history[-1] if self.portfolio_history else {}
        initial_portfolio_summary = self.portfolio_history[0] if self.portfolio_history else {}
        
        metrics = {
            'start_date': initial_portfolio_summary.get('timestamp'),
            'end_date': final_portfolio_summary.get('timestamp'),
            'initial_capital': self.initial_capital,
            'final_portfolio_value': final_portfolio_summary.get('total_value'),
            'total_return_pct': self.get_total_return() * 100,
            'annualized_return_pct': self.get_annualized_return(trading_days_per_year) * 100,
            'annualized_volatility_pct': self.get_volatility(trading_days_per_year) * 100,
            'sharpe_ratio': self.get_sharpe_ratio(risk_free_rate, trading_days_per_year),
            'sortino_ratio': self.get_sortino_ratio(risk_free_rate, 0.0, trading_days_per_year),
            'max_drawdown_pct': self.get_max_drawdown() * 100,
            'calmar_ratio': self.get_calmar_ratio(risk_free_rate, trading_days_per_year),
            'trade_statistics': self.get_trade_statistics(),
        }
        return metrics 
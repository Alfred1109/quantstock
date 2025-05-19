import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import os

logger = logging.getLogger('app')

class BacktestReporter:
    """
    回测报告生成器。
    负责将回测结果格式化为可读的报告，并生成可视化图表。
    """

    def __init__(self, results: Dict[str, Any], plots_output_dir: Optional[str] = "output/plots"):
        """
        初始化报告生成器。

        Args:
            results: BacktestingEngine._calculate_performance_metrics() 返回的结果字典。
                     This dictionary is expected to contain:
                     - Summary statistics (e.g., 'total_return_pct', 'sharpe_ratio').
                     - 'portfolio_history': pd.DataFrame with columns ['timestamp', 'total_value']
                                          (and potentially 'drawdown' if pre-calculated).
                     - 'trade_log': pd.DataFrame containing trade details (optional, for future plots).
            plots_output_dir: Directory to save generated plot images. Will be created if it doesn't exist.
        """
        self.results = results
        self.portfolio_history_df = self.results.get('portfolio_history')
        self.trade_log_df = self.results.get('trade_log') # For future use
        self.plots_output_dir = plots_output_dir

        if self.plots_output_dir:
            os.makedirs(self.plots_output_dir, exist_ok=True)
        
        # Set a default style for plots
        plt.style.use('seaborn-v0_8-darkgrid')

    def _calculate_drawdowns(self) -> Optional[pd.Series]:
        """Calculates drawdown series from portfolio history."""
        if self.portfolio_history_df is None or 'total_value' not in self.portfolio_history_df.columns:
            logger.warning("Portfolio history with 'total_value' is needed to calculate drawdowns.")
            return None
        
        # Ensure timestamp is datetime type for proper plotting
        if not pd.api.types.is_datetime64_any_dtype(self.portfolio_history_df['timestamp']):
            self.portfolio_history_df['timestamp'] = pd.to_datetime(self.portfolio_history_df['timestamp'], errors='coerce')

        df = self.portfolio_history_df.sort_values(by='timestamp').set_index('timestamp')
        
        cumulative_max = df['total_value'].cummax()
        drawdown = (df['total_value'] - cumulative_max) / cumulative_max
        return drawdown # This is a pd.Series with timestamp index

    def plot_equity_curve(self, filename: str = "equity_curve.png") -> Optional[str]:
        """Generates and saves the equity curve plot."""
        if self.portfolio_history_df is None or self.portfolio_history_df.empty:
            logger.warning("Cannot generate equity curve: portfolio_history is missing or empty.")
            return None

        df = self.portfolio_history_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
             df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.sort_values(by='timestamp')

        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(df['timestamp'], df['total_value'], label='Portfolio Value', color='blue')
        ax.set_title('Equity Curve')
        ax.set_xlabel('Time')
        ax.set_ylabel('Portfolio Value')
        ax.legend()
        ax.grid(True)
        fig.autofmt_xdate() # Auto-formats the x-axis labels (dates)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

        if self.plots_output_dir and filename:
            output_path = os.path.join(self.plots_output_dir, filename)
            try:
                plt.savefig(output_path)
                logger.info(f"Equity curve plot saved to {output_path}")
                plt.close(fig) # Close the figure to free memory
                return output_path
            except Exception as e:
                logger.error(f"Failed to save equity curve plot: {e}")
                plt.close(fig)
                return None
        else:
            # If no output path, one might want to display it (e.g., in Jupyter)
            # For now, we just log and don't save if dir is None
            logger.info("Equity curve plot generated but not saved (no output directory specified).")
            plt.show() # Or return fig for inline display
            return None 

    def plot_drawdown_curve(self, filename: str = "drawdown_curve.png") -> Optional[str]:
        """Generates and saves the drawdown curve plot."""
        drawdown_series = self._calculate_drawdowns()
        if drawdown_series is None or drawdown_series.empty:
            logger.warning("Cannot generate drawdown curve: drawdown series could not be calculated or is empty.")
            return None

        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(drawdown_series.index, drawdown_series * 100, label='Drawdown', color='red') # Plot as percentage
        ax.fill_between(drawdown_series.index, drawdown_series * 100, 0, color='red', alpha=0.3)
        ax.set_title('Portfolio Drawdown Curve')
        ax.set_xlabel('Time')
        ax.set_ylabel('Drawdown (%)')
        ax.legend()
        ax.grid(True)
        fig.autofmt_xdate()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.2f}%'))

        if self.plots_output_dir and filename:
            output_path = os.path.join(self.plots_output_dir, filename)
            try:
                plt.savefig(output_path)
                logger.info(f"Drawdown curve plot saved to {output_path}")
                plt.close(fig)
                return output_path
            except Exception as e:
                logger.error(f"Failed to save drawdown curve plot: {e}")
                plt.close(fig)
                return None
        else:
            logger.info("Drawdown curve plot generated but not saved (no output directory specified).")
            plt.show()
            return None

    def plot_trades_for_asset(self, symbol: str, filename: Optional[str] = None) -> Optional[str]:
        """
        为特定资产生成交易点图表，显示买入和卖出时机。
        
        Args:
            symbol: 要绘制的资产代码/名称
            filename: 输出文件名，如果为None则自动生成
            
        Returns:
            Optional[str]: 保存的图表文件路径，如果未保存则返回None
        """
        if self.trade_log_df is None or self.trade_log_df.empty:
            logger.warning(f"Cannot generate trade plot for {symbol}: trade_log is missing or empty.")
            return None
            
        # 确保trade_log_df有必要的列
        required_columns = ['timestamp', 'symbol', 'action', 'price']
        missing_columns = [col for col in required_columns if col not in self.trade_log_df.columns]
        if missing_columns:
            logger.warning(f"Cannot generate trade plot for {symbol}: missing columns in trade_log: {missing_columns}")
            return None
            
        # 提取该资产的交易记录
        asset_trades = self.trade_log_df[self.trade_log_df['symbol'] == symbol].copy()
        if asset_trades.empty:
            logger.warning(f"No trades found for {symbol}")
            return None
            
        # 确保时间戳是datetime类型
        if not pd.api.types.is_datetime64_any_dtype(asset_trades['timestamp']):
            asset_trades['timestamp'] = pd.to_datetime(asset_trades['timestamp'], errors='coerce')
            
        # 按时间排序
        asset_trades = asset_trades.sort_values(by='timestamp')
        
        # 创建图表
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # 绘制买入点（绿色上三角）
        buy_trades = asset_trades[asset_trades['action'].str.upper() == 'BUY']
        if not buy_trades.empty:
            ax.scatter(buy_trades['timestamp'], buy_trades['price'], 
                      color='green', marker='^', s=100, label='Buy')
                      
        # 绘制卖出点（红色下三角）
        sell_trades = asset_trades[asset_trades['action'].str.upper() == 'SELL']
        if not sell_trades.empty:
            ax.scatter(sell_trades['timestamp'], sell_trades['price'], 
                      color='red', marker='v', s=100, label='Sell')
        
        # 绘制持仓期间的连线
        # 这部分假设交易记录包含足够信息来匹配买卖对
        # 在实际应用中，可能需要更复杂的匹配逻辑
        if 'trade_id' in asset_trades.columns:
            # 如果有trade_id可以直接匹配买卖对
            for trade_id in asset_trades['trade_id'].unique():
                trade_group = asset_trades[asset_trades['trade_id'] == trade_id]
                if len(trade_group) >= 2:  # 至少有买入和卖出
                    ax.plot(trade_group['timestamp'], trade_group['price'], 
                           color='gray', linestyle='--', alpha=0.7)
        else:
            # 简化处理：假设买卖交替进行，按时间顺序连接
            if len(asset_trades) >= 2:
                ax.plot(asset_trades['timestamp'], asset_trades['price'], 
                       color='gray', linestyle='--', alpha=0.7)
        
        # 美化图表
        ax.set_title(f'交易记录: {symbol}')
        ax.set_xlabel('时间')
        ax.set_ylabel('价格')
        ax.legend()
        ax.grid(True)
        fig.autofmt_xdate()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        
        # 如果没有提供文件名，则自动生成
        if filename is None:
            filename = f"trades_{symbol.replace('/', '_').replace(':', '_')}.png"
            
        # 保存图表
        if self.plots_output_dir:
            output_path = os.path.join(self.plots_output_dir, filename)
            try:
                plt.savefig(output_path)
                logger.info(f"Trade plot for {symbol} saved to {output_path}")
                plt.close(fig)
                return output_path
            except Exception as e:
                logger.error(f"Failed to save trade plot for {symbol}: {e}")
                plt.close(fig)
                return None
        else:
            logger.info(f"Trade plot for {symbol} generated but not saved (no output directory specified).")
            plt.show()
            plt.close(fig)
            return None
            
    def plot_all_asset_trades(self) -> List[str]:
        """
        为交易日志中的所有资产生成交易点图表。
        
        Returns:
            List[str]: 成功生成的图表文件路径列表
        """
        if self.trade_log_df is None or self.trade_log_df.empty or 'symbol' not in self.trade_log_df.columns:
            logger.warning("Cannot generate asset trade plots: trade_log is missing, empty, or doesn't have 'symbol' column.")
            return []
            
        plot_paths = []
        for symbol in self.trade_log_df['symbol'].unique():
            plot_path = self.plot_trades_for_asset(symbol)
            if plot_path:
                plot_paths.append(plot_path)
                
        return plot_paths

    def generate_text_report(self, include_plot_paths: bool = True) -> str:
        """
        生成文本格式的回测报告。
        Args:
            include_plot_paths: If True, attempts to generate plots and includes their paths in the report.
        """
        if not self.results or self.results.get("error"):
            return f"无法生成报告: {self.results.get('error', '未知错误，结果为空')}"

        report_lines = []
        rp = report_lines.append

        rp("========== 量化回测报告 ==========")
        rp(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        rp("-----------------------------------")
        rp("回测周期:")
        rp(f"  开始日期: {self.results.get('start_date', 'N/A')}")
        rp(f"  结束日期: {self.results.get('end_date', 'N/A')}")
        rp("-----------------------------------")
        rp("核心绩效指标:")
        rp(f"  初始资本: {self.results.get('initial_capital', 0.0):,.2f}")
        rp(f"  期末总资产: {self.results.get('final_portfolio_value', 0.0):,.2f}")
        rp(f"  总收益率: {self.results.get('total_return_pct', 0.0):.2f}%")
        rp(f"  年化收益率: {self.results.get('annualized_return_pct', 0.0):.2f}%")
        rp(f"  年化波动率: {self.results.get('annualized_volatility_pct', 0.0):.2f}%")
        rp(f"  夏普比率: {self.results.get('sharpe_ratio', 0.0):.3f}")
        rp(f"  索提诺比率: {self.results.get('sortino_ratio', 0.0):.3f}")
        rp(f"  最大回撤: {self.results.get('max_drawdown_pct', 0.0):.2f}%")
        rp(f"  卡玛比率: {self.results.get('calmar_ratio', 0.0):.3f}")
        rp("-----------------------------------")
        
        trade_stats = self.results.get('trade_statistics', {})
        rp("交易统计:")
        rp(f"  总交易次数 (买/卖操作): {trade_stats.get('total_trades', 0)}")
        rp(f"  产生盈亏的平仓交易数: {trade_stats.get('num_closed_trades_with_pnl', 0)}")
        rp(f"  盈利交易次数: {trade_stats.get('winning_trades', 0)}")
        rp(f"  亏损交易次数: {trade_stats.get('losing_trades', 0)}")
        rp(f"  胜率: {trade_stats.get('win_rate', 0.0) * 100:.2f}%")
        rp(f"  平均盈利金额: {trade_stats.get('average_win_amount', 0.0):,.2f}")
        rp(f"  平均亏损金额: {trade_stats.get('average_loss_amount', 0.0):,.2f}")
        rp(f"  盈亏比 (平均盈利/平均亏损): {(trade_stats.get('average_win_amount', 0) / abs(trade_stats.get('average_loss_amount', -1)) if trade_stats.get('average_loss_amount') else 'N/A'):.2f}")
        rp(f"  利润因子 (总盈利/总亏损): {trade_stats.get('profit_factor', 0.0):.2f}")
        rp(f"  平均每笔交易盈亏: {trade_stats.get('average_trade_pnl', 0.0):,.2f}")
        rp("===================================")

        if include_plot_paths and self.plots_output_dir:
            rp("\n--- 生成的图表 ---")
            equity_plot_path = self.plot_equity_curve()
            if equity_plot_path:
                rp(f"  资金曲线图: {equity_plot_path}")
            else:
                rp("  资金曲线图: 未能生成或保存")
            
            drawdown_plot_path = self.plot_drawdown_curve()
            if drawdown_plot_path:
                rp(f"  回撤曲线图: {drawdown_plot_path}")
            else:
                rp("  回撤曲线图: 未能生成或保存")
            
            # 为每个交易的资产生成交易点图
            if self.trade_log_df is not None and not self.trade_log_df.empty and 'symbol' in self.trade_log_df.columns:
                asset_plot_paths = self.plot_all_asset_trades()
                if asset_plot_paths:
                    rp("\n  个股交易图:")
                    for path in asset_plot_paths:
                        rp(f"    {path}")
                else:
                    rp("  个股交易图: 未能生成或保存")
            
            rp("===================================")

        return "\n".join(report_lines)

    def save_text_report(self, filepath: str, include_plot_paths: bool = True) -> None:
        """
        将文本报告保存到文件。
        """
        report_content = self.generate_text_report(include_plot_paths)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            logger.info(f"回测报告已保存到: {filepath}")
        except IOError as e:
            logger.error(f"保存回测报告失败: {e}")

# Example Usage (Illustrative)
if __name__ == '__main__':
    # Dummy results for testing the reporter
    sample_results = {
        'start_date': '2023-01-01T00:00:00',
        'end_date': '2023-12-31T23:59:59',
        'initial_capital': 100000.0,
        'final_portfolio_value': 125000.0,
        'total_return_pct': 25.0,
        'annualized_return_pct': 25.0, # Simplified for example
        'annualized_volatility_pct': 15.0,
        'sharpe_ratio': 1.5,
        'sortino_ratio': 2.0,
        'max_drawdown_pct': 10.0,
        'calmar_ratio': 2.5,
        'trade_statistics': {
            'total_trades': 50,
            'num_closed_trades_with_pnl': 45,
            'winning_trades': 30,
            'losing_trades': 15,
            'win_rate': 30/45 if 45 else 0,
            'average_win_amount': 1200.0,
            'average_loss_amount': -800.0,  # 注意这里使用负值表示损失
            'profit_factor': (30*1200)/(15*800) if (15*800) else float('inf'),
            'average_trade_pnl': ( (30*1200) - (15*800) ) / 45 if 45 else 0
        }
    }

    # Updated example to include portfolio_history for plotting
    sample_timestamps = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(10)]
    sample_values = [100000, 101000, 100500, 102000, 103000, 102500, 104000, 105000, 103500, 106000]
    sample_portfolio_history = pd.DataFrame({
        'timestamp': sample_timestamps,
        'total_value': sample_values
    })

    # 添加示例交易日志用于测试个股交易图
    sample_trades = [
        # 股票A的交易
        {'timestamp': datetime(2023, 1, 3), 'symbol': 'Stock_A', 'action': 'BUY', 'price': 100.0, 'quantity': 100},
        {'timestamp': datetime(2023, 1, 5), 'symbol': 'Stock_A', 'action': 'SELL', 'price': 110.0, 'quantity': 100},
        {'timestamp': datetime(2023, 1, 8), 'symbol': 'Stock_A', 'action': 'BUY', 'price': 105.0, 'quantity': 150},
        {'timestamp': datetime(2023, 1, 9), 'symbol': 'Stock_A', 'action': 'SELL', 'price': 95.0, 'quantity': 150},
        
        # 股票B的交易
        {'timestamp': datetime(2023, 1, 2), 'symbol': 'Stock_B', 'action': 'BUY', 'price': 50.0, 'quantity': 200},
        {'timestamp': datetime(2023, 1, 6), 'symbol': 'Stock_B', 'action': 'SELL', 'price': 60.0, 'quantity': 200},
    ]
    sample_trade_log = pd.DataFrame(sample_trades)

    sample_results_with_history = sample_results.copy()
    sample_results_with_history['portfolio_history'] = sample_portfolio_history
    sample_results_with_history['trade_log'] = sample_trade_log

    reporter = BacktestReporter(sample_results_with_history)
    text_report = reporter.generate_text_report()
    print(text_report)

    # reporter.save_text_report("sample_backtest_report.txt") 
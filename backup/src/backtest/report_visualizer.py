"""
回测报告可视化模块 - 用于生成回测结果图表
"""
import os
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from typing import Dict, List, Optional, Union
from datetime import datetime

from utils.logger import get_logger

logger = get_logger("report_visualizer")

class ReportVisualizer:
    """
    回测报告可视化类，用于生成回测结果图表
    """
    
    def __init__(self, output_dir: str = "./output/results"):
        """
        初始化回测报告可视化器
        
        Args:
            output_dir: 图表输出目录
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 设置全局图表样式
        plt.style.use('seaborn-darkgrid')
        
        logger.info(f"回测报告可视化器初始化完成, 输出目录: {output_dir}")
    
    def _prepare_equity_curve(self, report: Dict) -> pd.DataFrame:
        """
        准备资金曲线数据
        
        Args:
            report: 回测报告字典
            
        Returns:
            资金曲线DataFrame
        """
        equity_data = report.get("equity_curve", {})
        if not equity_data:
            logger.error("回测报告中缺少资金曲线数据")
            return pd.DataFrame()
            
        # 转换字典为DataFrame
        df = pd.DataFrame(equity_data)
        
        # 处理日期索引
        if 'index' in df.columns:
            df['date'] = pd.to_datetime(df['index'])
            df.set_index('date', inplace=True)
            df.drop('index', axis=1, inplace=True)
        
        return df
    
    def _prepare_trades(self, report: Dict) -> pd.DataFrame:
        """
        准备交易记录数据
        
        Args:
            report: 回测报告字典
            
        Returns:
            交易记录DataFrame
        """
        trades = report.get("trades", [])
        if not trades:
            logger.warning("回测报告中缺少交易记录数据")
            return pd.DataFrame()
            
        # 转换列表为DataFrame
        df = pd.DataFrame(trades)
        
        # 处理日期时间
        if 'entry_time' in df.columns:
            df['entry_time'] = pd.to_datetime(df['entry_time'])
        if 'exit_time' in df.columns:
            df['exit_time'] = pd.to_datetime(df['exit_time'])
        
        return df
    
    def visualize(self, report: Dict, filename_prefix: str = None) -> str:
        """
        生成回测报告可视化图表
        
        Args:
            report: 回测报告字典
            filename_prefix: 文件名前缀，如果为None则使用时间戳
            
        Returns:
            保存的图表文件路径
        """
        if not report:
            logger.error("回测报告为空，无法生成可视化图表")
            return ""
            
        # 创建保存文件名
        if filename_prefix is None:
            filename_prefix = f"backtest_{time.strftime('%Y%m%d_%H%M%S')}"
            
        # 创建图表文件路径
        chart_path = os.path.join(self.output_dir, f"{filename_prefix}_report.png")
            
        # 准备数据
        equity_df = self._prepare_equity_curve(report)
        trades_df = self._prepare_trades(report)
        
        if equity_df.empty:
            logger.error("无法获取资金曲线数据，取消可视化")
            return ""
            
        # 获取绩效指标
        performance = report.get("performance", {})
        summary = report.get("summary", {})
        
        # 创建多子图
        fig = plt.figure(figsize=(15, 12))
        gs = fig.add_gridspec(4, 2)
        
        # 资金曲线图
        ax1 = fig.add_subplot(gs[0, :])
        equity_df['equity'].plot(ax=ax1, label='净值')
        ax1.set_title('资金曲线')
        ax1.set_ylabel('净值')
        ax1.set_xlabel('日期')
        ax1.legend()
        
        # 持仓价值与现金曲线
        ax2 = fig.add_subplot(gs[1, :])
        equity_df['position_value'].plot(ax=ax2, label='持仓价值')
        equity_df['cash'].plot(ax=ax2, label='现金')
        ax2.set_title('持仓价值与现金曲线')
        ax2.set_ylabel('价值')
        ax2.set_xlabel('日期')
        ax2.legend()
        
        # 月度收益热图
        ax3 = fig.add_subplot(gs[2, 0])
        if not equity_df.empty and 'return' in equity_df:
            monthly_returns = equity_df['return'].resample('M').apply(
                lambda x: (1 + x).prod() - 1
            )
            
            # 创建月度收益热图
            monthly_returns_matrix = monthly_returns.to_frame().reset_index()
            monthly_returns_matrix['Year'] = monthly_returns_matrix['date'].dt.year
            monthly_returns_matrix['Month'] = monthly_returns_matrix['date'].dt.month
            monthly_returns_matrix = monthly_returns_matrix.pivot(
                index='Year', columns='Month', values='return'
            )
            
            # 绘制热图
            sns.heatmap(
                monthly_returns_matrix, 
                annot=True, 
                fmt=".2%", 
                cmap='RdYlGn', 
                center=0, 
                ax=ax3
            )
            ax3.set_title('月度收益热图')
            ax3.set_xlabel('月份')
            ax3.set_ylabel('年份')
        else:
            ax3.text(0.5, 0.5, "无月度收益数据", ha='center', va='center')
            ax3.set_title('月度收益热图')
        
        # 回撤图
        ax4 = fig.add_subplot(gs[2, 1])
        if 'drawdown' in equity_df.columns:
            equity_df['drawdown'].plot(ax=ax4, color='red')
            ax4.set_title('回撤曲线')
            ax4.set_ylabel('回撤率')
            ax4.set_xlabel('日期')
            
            # 标记最大回撤
            max_dd_idx = equity_df['drawdown'].idxmax()
            if not pd.isna(max_dd_idx):
                max_dd = equity_df.loc[max_dd_idx, 'drawdown']
                ax4.axhline(y=max_dd, color='black', linestyle='--', label=f'最大回撤: {max_dd:.2%}')
                ax4.legend()
        else:
            ax4.text(0.5, 0.5, "无回撤数据", ha='center', va='center')
            ax4.set_title('回撤曲线')
        
        # 绩效指标表格
        ax5 = fig.add_subplot(gs[3, 0])
        ax5.axis('off')
        
        metrics = [
            ("初始资金", f"${summary.get('initial_capital', 0):,.2f}"),
            ("最终资金", f"${performance.get('final_capital', 0):,.2f}"),
            ("总收益率", f"{performance.get('total_return', 0):.2%}"),
            ("年化收益率", f"{performance.get('annual_return', 0):.2%}"),
            ("最大回撤", f"{performance.get('max_drawdown', 0):.2%}"),
            ("夏普比率", f"{performance.get('sharpe_ratio', 0):.2f}"),
            ("索提诺比率", f"{performance.get('sortino_ratio', 0):.2f}"),
            ("总交易次数", f"{performance.get('total_trades', 0)}"),
            ("胜率", f"{performance.get('win_rate', 0):.2%}"),
            ("盈亏比", f"{performance.get('profit_factor', 0):.2f}"),
            ("平均盈利", f"${performance.get('avg_win', 0):,.2f}"),
            ("平均亏损", f"${performance.get('avg_loss', 0):,.2f}")
        ]
        
        table_text = []
        for name, value in metrics:
            table_text.append([name, value])
            
        ax5.table(
            cellText=table_text,
            loc='center',
            cellLoc='left',
            colWidths=[0.5, 0.5]
        )
        ax5.set_title('绩效指标')
        
        # 交易统计图
        ax6 = fig.add_subplot(gs[3, 1])
        if not trades_df.empty and 'profit' in trades_df.columns:
            ax6.hist(
                trades_df['profit'],
                bins=20,
                color='green' if trades_df['profit'].mean() > 0 else 'red'
            )
            ax6.set_title('交易盈亏分布')
            ax6.set_xlabel('盈亏金额')
            ax6.set_ylabel('交易次数')
            
            # 添加均值线
            avg_profit = trades_df['profit'].mean()
            ax6.axvline(x=avg_profit, color='black', linestyle='--', label=f'平均盈亏: ${avg_profit:.2f}')
            ax6.legend()
        else:
            ax6.text(0.5, 0.5, "无交易数据", ha='center', va='center')
            ax6.set_title('交易盈亏分布')
        
        # 调整布局并保存
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()
        
        logger.info(f"回测报告可视化图表已保存至 {chart_path}")
        return chart_path
    
    def create_trade_chart(self, report: Dict, symbol: str, filename_prefix: str = None) -> str:
        """
        创建单品种交易图表，显示买卖点位
        
        Args:
            report: 回测报告字典
            symbol: 交易品种代码
            filename_prefix: 文件名前缀，如果为None则使用时间戳
            
        Returns:
            保存的图表文件路径
        """
        if not report:
            logger.error("回测报告为空，无法生成交易图表")
            return ""
            
        # 准备交易数据
        trades_df = self._prepare_trades(report)
        if trades_df.empty:
            logger.error("无交易记录数据，无法生成交易图表")
            return ""
            
        # 过滤指定品种的交易
        symbol_trades = trades_df[trades_df['symbol'] == symbol]
        if symbol_trades.empty:
            logger.error(f"未找到品种 {symbol} 的交易记录")
            return ""
            
        # 创建保存文件名
        if filename_prefix is None:
            filename_prefix = f"trades_{symbol}_{time.strftime('%Y%m%d_%H%M%S')}"
            
        # 创建图表文件路径
        chart_path = os.path.join(self.output_dir, f"{filename_prefix}_trades.png")
        
        # 创建图表
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # 绘制价格曲线和交易点
        # 注意：这里需要价格数据，可能需要从额外提供的数据中获取
        # 这部分代码假设报告中有价格数据，实际使用时可能需要调整
        
        # 绘制买入点
        for _, trade in symbol_trades[symbol_trades['direction'] == 'LONG'].iterrows():
            ax.plot(
                trade['entry_time'],
                trade['entry_price'],
                '^',
                color='green',
                markersize=10,
                label='买入'
            )
            
            if 'exit_time' in trade and 'exit_price' in trade:
                ax.plot(
                    trade['exit_time'],
                    trade['exit_price'],
                    'v',
                    color='red',
                    markersize=10,
                    label='卖出'
                )
        
        # 绘制卖出点
        for _, trade in symbol_trades[symbol_trades['direction'] == 'SHORT'].iterrows():
            ax.plot(
                trade['entry_time'],
                trade['entry_price'],
                'v',
                color='red',
                markersize=10,
                label='卖出'
            )
            
            if 'exit_time' in trade and 'exit_price' in trade:
                ax.plot(
                    trade['exit_time'],
                    trade['exit_price'],
                    '^',
                    color='green',
                    markersize=10,
                    label='买入'
                )
        
        # 添加图例（去除重复）
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys())
        
        # 设置标题和轴标签
        ax.set_title(f"{symbol} 交易图表")
        ax.set_xlabel("日期")
        ax.set_ylabel("价格")
        
        # 格式化x轴日期
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate()
        
        # 保存图表
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()
        
        logger.info(f"{symbol} 交易图表已保存至 {chart_path}")
        return chart_path
    
    def create_performance_comparison(self, reports: List[Dict], labels: List[str], filename: str = None) -> str:
        """
        创建多策略绩效对比图表
        
        Args:
            reports: 回测报告字典列表
            labels: 对应的策略标签列表
            filename: 文件名，如果为None则使用默认文件名
            
        Returns:
            保存的图表文件路径
        """
        if not reports or len(reports) < 2:
            logger.error("至少需要两份回测报告进行比较")
            return ""
            
        if len(reports) != len(labels):
            logger.error("报告数量与标签数量不匹配")
            return ""
            
        # 创建保存文件名
        if filename is None:
            filename = f"strategy_comparison_{time.strftime('%Y%m%d_%H%M%S')}.png"
            
        # 创建图表文件路径
        chart_path = os.path.join(self.output_dir, filename)
        
        # 创建图表
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 15))
        
        # 绘制资金曲线对比
        for report, label in zip(reports, labels):
            equity_df = self._prepare_equity_curve(report)
            if not equity_df.empty and 'equity' in equity_df.columns:
                # 标准化资金曲线，以便比较
                normalized_equity = equity_df['equity'] / equity_df['equity'].iloc[0]
                normalized_equity.plot(ax=ax1, label=label)
        
        ax1.set_title('策略资金曲线对比 (标准化)')
        ax1.set_ylabel('标准化净值')
        ax1.set_xlabel('日期')
        ax1.legend()
        
        # 绘制绩效指标对比柱状图
        metrics = ['annual_return', 'max_drawdown', 'sharpe_ratio']
        metric_labels = ['年化收益率', '最大回撤', '夏普比率']
        
        data = []
        for report, label in zip(reports, labels):
            performance = report.get("performance", {})
            data.append([
                performance.get('annual_return', 0),
                performance.get('max_drawdown', 0),
                performance.get('sharpe_ratio', 0)
            ])
            
        df = pd.DataFrame(data, index=labels, columns=metric_labels)
        
        # 绘制年化收益率和最大回撤对比
        df[['年化收益率', '最大回撤']].plot(kind='bar', ax=ax2)
        ax2.set_title('年化收益率与最大回撤对比')
        ax2.set_ylabel('百分比')
        ax2.set_xlabel('策略')
        
        # 绘制夏普比率对比
        df[['夏普比率']].plot(kind='bar', ax=ax3)
        ax3.set_title('夏普比率对比')
        ax3.set_ylabel('夏普比率')
        ax3.set_xlabel('策略')
        
        # 保存图表
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()
        
        logger.info(f"策略绩效对比图表已保存至 {chart_path}")
        return chart_path


def create_report_visualizer(output_dir: str = None) -> ReportVisualizer:
    """
    创建回测报告可视化器
    
    Args:
        output_dir: 输出目录，如果为None则使用默认目录
        
    Returns:
        回测报告可视化器实例
    """
    from utils.config import get_config
    
    if output_dir is None:
        output_dir = get_config("results", "output_dir", "./output/results")
        
    return ReportVisualizer(output_dir=output_dir)


if __name__ == "__main__":
    # 测试代码
    import json
    
    # 读取样例回测报告
    try:
        with open("./results/sample_report.json", "r") as f:
            report = json.load(f)
            
        # 创建可视化器
        visualizer = create_report_visualizer()
        
        # 生成回测报告图表
        visualizer.visualize(report, "sample_report")
        
    except Exception as e:
        print(f"测试失败: {str(e)}") 
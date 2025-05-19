"""
参数优化模块 - 负责策略参数优化
"""
import os
import time
import itertools
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Callable, Union, Optional
from multiprocessing import Pool, cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm

from backtest.backtest_engine import BacktestEngine
from core.pyramid import PyramidStrategy
from utils.logger import get_logger
from utils.config import get_config

logger = get_logger("param_optimizer")

class OptimizationResult:
    """参数优化结果类"""
    
    def __init__(self, params: Dict[str, Any], metrics: Dict[str, Any]):
        """
        初始化参数优化结果
        
        Args:
            params: 策略参数
            metrics: 性能指标
        """
        self.params = params
        self.metrics = metrics
    
    def __lt__(self, other):
        """比较两个优化结果的优劣"""
        # 默认按照夏普比率排序
        return self.metrics.get("sharpe_ratio", 0) < other.metrics.get("sharpe_ratio", 0)
    
    def __str__(self):
        """字符串表示"""
        return f"参数: {self.params}, 夏普比率: {self.metrics.get('sharpe_ratio', 0):.4f}, 总收益: {self.metrics.get('total_return', 0):.4f}"


class ParamOptimizer:
    """
    参数优化器
    
    支持网格搜索和随机搜索两种优化方法
    """
    
    def __init__(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        timeframe: str = '1d',
        initial_capital: float = 100000.0,
        parallel: bool = True,
        max_workers: int = None
    ):
        """
        初始化参数优化器
        
        Args:
            symbols: 交易品种列表
            start_date: 回测开始日期
            end_date: 回测结束日期
            timeframe: 时间周期
            initial_capital: 初始资金
            parallel: 是否并行优化
            max_workers: 最大并行工作进程数
        """
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.parallel = parallel
        self.max_workers = max_workers if max_workers else max(1, cpu_count() - 1)
        
        logger.info(f"参数优化器初始化完成, 并行: {parallel}, 最大进程数: {self.max_workers}")
    
    def _run_backtest(self, params: Dict[str, Any]) -> OptimizationResult:
        """
        使用指定参数运行回测
        
        Args:
            params: 策略参数
            
        Returns:
            优化结果对象
        """
        try:
            # 创建策略实例
            strategy = PyramidStrategy(**params)
            
            # 创建回测引擎
            backtest_engine = BacktestEngine(
                strategy_instance=strategy,
                symbols=self.symbols,
                start_date=self.start_date,
                end_date=self.end_date,
                timeframe=self.timeframe,
                initial_capital=self.initial_capital
            )
            
            # 运行回测
            report = backtest_engine.run_backtest()
            
            # 提取性能指标
            if not report:
                logger.warning(f"回测未返回报告, 参数: {params}")
                return OptimizationResult(params, {"sharpe_ratio": -999, "total_return": -999})
                
            metrics = report.get("performance", {})
            return OptimizationResult(params, metrics)
            
        except Exception as e:
            logger.error(f"回测异常: {str(e)}, 参数: {params}")
            return OptimizationResult(params, {"sharpe_ratio": -999, "total_return": -999})
    
    def grid_search(self, param_grid: Dict[str, List[Any]], sort_key: str = "sharpe_ratio") -> List[OptimizationResult]:
        """
        网格搜索优化
        
        Args:
            param_grid: 参数网格，字典形式，键为参数名，值为参数可能值列表
            sort_key: 排序指标，默认为夏普比率
            
        Returns:
            优化结果列表，按指定指标降序排序
        """
        # 生成参数组合
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        param_combinations = list(itertools.product(*param_values))
        
        total_combinations = len(param_combinations)
        logger.info(f"开始网格搜索, 参数组合数: {total_combinations}")
        
        results = []
        
        # 进度条
        progress_bar = tqdm(total=total_combinations, desc="参数优化进度")
        
        if self.parallel and total_combinations > 1:
            # 并行优化
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                
                for combination in param_combinations:
                    params = dict(zip(param_names, combination))
                    futures.append(executor.submit(self._run_backtest, params))
                
                for future in as_completed(futures):
                    results.append(future.result())
                    progress_bar.update(1)
        else:
            # 串行优化
            for combination in param_combinations:
                params = dict(zip(param_names, combination))
                result = self._run_backtest(params)
                results.append(result)
                progress_bar.update(1)
        
        progress_bar.close()
        
        # 按指定指标降序排序
        results.sort(key=lambda x: x.metrics.get(sort_key, 0), reverse=True)
        
        logger.info(f"网格搜索完成, 最佳参数: {results[0].params}, 最佳{sort_key}: {results[0].metrics.get(sort_key, 0)}")
        return results
    
    def random_search(
        self,
        param_ranges: Dict[str, Tuple[Any, Any]],
        param_types: Dict[str, type],
        n_iterations: int = 100,
        sort_key: str = "sharpe_ratio"
    ) -> List[OptimizationResult]:
        """
        随机搜索优化
        
        Args:
            param_ranges: 参数范围，字典形式，键为参数名，值为(最小值, 最大值)元组
            param_types: 参数类型，字典形式，键为参数名，值为类型(int, float等)
            n_iterations: 迭代次数
            sort_key: 排序指标，默认为夏普比率
            
        Returns:
            优化结果列表，按指定指标降序排序
        """
        logger.info(f"开始随机搜索, 迭代次数: {n_iterations}")
        
        # 进度条
        progress_bar = tqdm(total=n_iterations, desc="参数优化进度")
        
        results = []
        param_names = list(param_ranges.keys())
        
        if self.parallel and n_iterations > 1:
            # 并行优化
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                
                for _ in range(n_iterations):
                    # 随机生成参数
                    params = {}
                    for name in param_names:
                        min_val, max_val = param_ranges[name]
                        param_type = param_types[name]
                        
                        if param_type == int:
                            params[name] = np.random.randint(min_val, max_val + 1)
                        elif param_type == float:
                            params[name] = np.random.uniform(min_val, max_val)
                        elif param_type == bool:
                            params[name] = np.random.choice([True, False])
                        else:
                            params[name] = min_val  # 默认使用最小值
                    
                    futures.append(executor.submit(self._run_backtest, params))
                
                for future in as_completed(futures):
                    results.append(future.result())
                    progress_bar.update(1)
        else:
            # 串行优化
            for _ in range(n_iterations):
                # 随机生成参数
                params = {}
                for name in param_names:
                    min_val, max_val = param_ranges[name]
                    param_type = param_types[name]
                    
                    if param_type == int:
                        params[name] = np.random.randint(min_val, max_val + 1)
                    elif param_type == float:
                        params[name] = np.random.uniform(min_val, max_val)
                    elif param_type == bool:
                        params[name] = np.random.choice([True, False])
                    else:
                        params[name] = min_val  # 默认使用最小值
                
                result = self._run_backtest(params)
                results.append(result)
                progress_bar.update(1)
        
        progress_bar.close()
        
        # 按指定指标降序排序
        results.sort(key=lambda x: x.metrics.get(sort_key, 0), reverse=True)
        
        logger.info(f"随机搜索完成, 最佳参数: {results[0].params}, 最佳{sort_key}: {results[0].metrics.get(sort_key, 0)}")
        return results
    
    def visualize_results(self, results: List[OptimizationResult], top_n: int = 20, metric: str = "sharpe_ratio"):
        """
        可视化优化结果
        
        Args:
            results: 优化结果列表
            top_n: 展示前N个结果
            metric: 性能指标名称
        """
        # 限制结果数量
        results = results[:min(top_n, len(results))]
        
        # 提取参数和指标
        param_df = pd.DataFrame([r.params for r in results])
        metrics = [r.metrics.get(metric, 0) for r in results]
        
        # 创建结果表格
        result_df = pd.DataFrame({
            **{f"param_{k}": param_df[k] for k in param_df.columns},
            metric: metrics
        })
        
        # 设置图表风格
        plt.style.use('seaborn-darkgrid')
        
        # 创建图表
        fig, axes = plt.subplots(len(param_df.columns), 1, figsize=(10, 4 * len(param_df.columns)))
        
        for i, param in enumerate(param_df.columns):
            ax = axes[i] if len(param_df.columns) > 1 else axes
            ax.scatter(param_df[param], metrics)
            ax.set_xlabel(param)
            ax.set_ylabel(metric)
            ax.set_title(f"{param} vs {metric}")
            
        plt.tight_layout()
        
        # 保存图表
        results_dir = "./output/results"
        os.makedirs(results_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        plt.savefig(f"{results_dir}/optimization_{timestamp}.png")
        
        # 保存结果表格
        result_df.to_csv(f"{results_dir}/optimization_{timestamp}.csv", index=False)
        
        logger.info(f"优化结果已保存至 {results_dir}/optimization_{timestamp}.png 和 .csv")
        
        return result_df


# 创建参数优化器
def create_param_optimizer(
    symbols: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    timeframe: str = '1d',
    initial_capital: float = None,
    parallel: bool = True,
    max_workers: int = None
) -> ParamOptimizer:
    """
    创建参数优化器
    
    从配置文件加载参数，如果有指定参数则使用指定参数
    
    Args:
        symbols: 交易品种列表
        start_date: 回测开始日期
        end_date: 回测结束日期
        timeframe: 时间周期
        initial_capital: 初始资金
        parallel: 是否并行优化
        max_workers: 最大并行工作进程数
        
    Returns:
        参数优化器实例
    """
    # 从配置文件加载参数
    if symbols is None:
        symbols = get_config("backtest", "symbols", [])
    if start_date is None:
        start_date = get_config("backtest", "start_date", "")
    if end_date is None:
        end_date = get_config("backtest", "end_date", "")
    if initial_capital is None:
        initial_capital = get_config("account", "initial_capital", 100000.0)
    
    return ParamOptimizer(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe,
        initial_capital=initial_capital,
        parallel=parallel,
        max_workers=max_workers
    )


if __name__ == "__main__":
    # 测试代码
    optimizer = create_param_optimizer()
    
    # 定义参数网格
    param_grid = {
        "ma_short_period": [10, 20, 30],
        "ma_long_period": [50, 60, 70],
        "atr_period": [10, 14, 18],
        "breakout_periods": [15, 20, 25],
        "trail_stop_atr": [1.5, 2.0, 2.5]
    }
    
    # 运行网格搜索
    results = optimizer.grid_search(param_grid)
    
    # 打印前10个最佳结果
    for i, result in enumerate(results[:10]):
        print(f"#{i+1}: {result}")
    
    # 可视化结果
    optimizer.visualize_results(results) 
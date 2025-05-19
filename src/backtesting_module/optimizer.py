import logging
import itertools
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional, Union, Callable
from datetime import datetime
import multiprocessing
import json
import os
from pathlib import Path

from .engine import BacktestingEngine

logger = logging.getLogger('app')

class Optimizer:
    """
    策略参数优化器。
    
    支持对策略参数进行网格搜索(Grid Search)，找出最优参数组合。
    """
    
    def __init__(self, 
                 backtest_engine: BacktestingEngine,
                 symbols: List[str],
                 output_dir: Optional[str] = "output/results"):
        """
        初始化优化器。
        
        Args:
            backtest_engine: 已配置好的回测引擎实例。
            symbols: 需要回测的资产代码列表。
            output_dir: 优化结果输出目录。
        """
        self.backtest_engine = backtest_engine
        self.symbols = symbols
        self.output_dir = output_dir
        self.param_grid = {}  # 参数网格
        self.optimization_results = []  # 优化结果列表
        self.best_params = None  # 最佳参数组合
        
        # 创建输出目录
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
    
    def set_param_grid(self, param_grid: Dict[str, List[Any]]) -> None:
        """
        设置参数网格。
        
        Args:
            param_grid: 参数网格字典，键为参数名，值为参数可能值列表。
                例如: {'ma_short': [5, 10, 15], 'ma_long': [30, 50, 100]}
        """
        self.param_grid = param_grid
        logger.info(f"Parameter grid set with {len(param_grid)} parameters.")
        
        # 计算总共需要测试的参数组合数
        total_combinations = 1
        for param_values in param_grid.values():
            total_combinations *= len(param_values)
        logger.info(f"Total number of parameter combinations to test: {total_combinations}")
    
    def _run_single_backtest(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单次回测。
        
        Args:
            params: 策略参数字典。
            
        Returns:
            Dict[str, Any]: 回测结果，包含性能指标和使用的参数。
        """
        try:
            # 运行回测
            results = self.backtest_engine.run_backtest(
                symbols=self.symbols,
                strategy_params=params
            )
            
            # 添加参数信息到结果中
            results.update({
                'strategy_params': params
            })
            
            return results
        except Exception as e:
            logger.error(f"Error during backtest with params {params}: {str(e)}", exc_info=True)
            return {
                'error': str(e),
                'strategy_params': params
            }
    
    def run_optimization(self, 
                        metric_to_optimize: str = 'sharpe_ratio',
                        maximize: bool = True,
                        max_workers: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        运行参数优化。
        
        Args:
            metric_to_optimize: 用于优化的性能指标名称。
            maximize: 如果为True，则寻找最大化指标的参数；否则寻找最小化指标的参数。
            max_workers: 最大并行工作进程数。如果为None，则使用CPU核心数。
            
        Returns:
            List[Dict[str, Any]]: 按优化指标排序的参数组合及其性能结果列表。
        """
        if not self.param_grid:
            logger.error("Parameter grid is empty. Call set_param_grid() first.")
            return []
        
        # 生成所有可能的参数组合
        param_names = list(self.param_grid.keys())
        param_values = list(self.param_grid.values())
        param_combinations = list(itertools.product(*param_values))
        
        logger.info(f"Starting optimization with {len(param_combinations)} parameter combinations.")
        logger.info(f"Optimizing for {'maximum' if maximize else 'minimum'} {metric_to_optimize}.")
        
        # 执行回测（可以并行）
        results = []
        
        # 根据max_workers决定是否使用并行处理
        if max_workers is not None and max_workers > 1:
            # 使用进程池并行处理
            with multiprocessing.Pool(processes=max_workers) as pool:
                # 为每个参数组合准备参数字典
                param_dicts = [dict(zip(param_names, combo)) for combo in param_combinations]
                
                # 并行执行回测
                results = pool.map(self._run_single_backtest, param_dicts)
        else:
            # 串行执行
            for combo in param_combinations:
                param_dict = dict(zip(param_names, combo))
                logger.info(f"Testing parameters: {param_dict}")
                result = self._run_single_backtest(param_dict)
                results.append(result)
        
        # 过滤出成功的回测结果
        valid_results = [r for r in results if 'error' not in r]
        
        if not valid_results:
            logger.warning("No valid optimization results. All backtests failed.")
            return []
        
        # 根据指定的性能指标排序
        try:
            valid_results.sort(
                key=lambda x: x.get(metric_to_optimize, float('-inf' if maximize else 'inf')),
                reverse=maximize
            )
            
            # 保存所有结果
            self.optimization_results = valid_results
            
            # 保存最佳参数组合
            self.best_params = valid_results[0]['strategy_params'] if valid_results else None
            
            # 输出优化结果
            logger.info(f"Optimization complete. Best {metric_to_optimize}: "
                        f"{valid_results[0].get(metric_to_optimize) if valid_results else 'N/A'}")
            
            # 保存结果到文件
            self._save_results()
            
            return valid_results
        except Exception as e:
            logger.error(f"Error during results sorting: {str(e)}", exc_info=True)
            return valid_results  # 返回未排序的结果
    
    def _save_results(self) -> None:
        """保存优化结果到文件"""
        if not self.output_dir or not self.optimization_results:
            return
            
        try:
            # 创建时间戳文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            results_file = os.path.join(self.output_dir, f"optimization_results_{timestamp}.json")
            
            # 将结果转换为可序列化格式
            serializable_results = []
            for result in self.optimization_results:
                serializable_result = {}
                for k, v in result.items():
                    # 处理不可直接序列化的类型
                    if isinstance(v, (datetime, pd.DataFrame)):
                        continue
                    elif isinstance(v, dict):
                        # 递归处理嵌套字典
                        serializable_result[k] = {
                            sk: str(sv) if isinstance(sv, (datetime, pd.DataFrame)) else sv 
                            for sk, sv in v.items()
                        }
                    else:
                        serializable_result[k] = v
                serializable_results.append(serializable_result)
            
            # 保存为JSON文件
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_results, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Optimization results saved to {results_file}")
            
            # 同时保存最佳参数组合
            if self.best_params:
                best_params_file = os.path.join(self.output_dir, f"best_params_{timestamp}.json")
                with open(best_params_file, 'w', encoding='utf-8') as f:
                    json.dump(self.best_params, f, indent=2, ensure_ascii=False)
                logger.info(f"Best parameters saved to {best_params_file}")
                
            # 生成优化结果摘要
            self._generate_summary(timestamp)
            
        except Exception as e:
            logger.error(f"Error saving optimization results: {str(e)}", exc_info=True)
    
    def _generate_summary(self, timestamp: str) -> None:
        """生成优化结果摘要"""
        if not self.optimization_results:
            return
            
        try:
            # 创建DataFrame来展示结果
            results_data = []
            
            for result in self.optimization_results:
                row = {}
                
                # 添加参数值
                params = result.get('strategy_params', {})
                for param_name, param_value in params.items():
                    row[f"param_{param_name}"] = param_value
                
                # 添加关键性能指标
                key_metrics = [
                    'total_return_pct', 'annualized_return_pct', 'sharpe_ratio', 
                    'sortino_ratio', 'max_drawdown_pct', 'calmar_ratio'
                ]
                
                for metric in key_metrics:
                    row[metric] = result.get(metric, "N/A")
                
                results_data.append(row)
            
            # 创建DataFrame
            df = pd.DataFrame(results_data)
            
            # 保存为CSV文件
            summary_file = os.path.join(self.output_dir, f"optimization_summary_{timestamp}.csv")
            df.to_csv(summary_file, index=False)
            logger.info(f"Optimization summary saved to {summary_file}")
            
        except Exception as e:
            logger.error(f"Error generating optimization summary: {str(e)}", exc_info=True)
    
    def get_best_params(self) -> Optional[Dict[str, Any]]:
        """获取最佳参数组合"""
        return self.best_params
    
    def get_results_df(self) -> Optional[pd.DataFrame]:
        """获取优化结果的DataFrame表示"""
        if not self.optimization_results:
            return None
            
        results_data = []
        
        for result in self.optimization_results:
            row = {}
            
            # 添加参数值
            params = result.get('strategy_params', {})
            for param_name, param_value in params.items():
                row[f"param_{param_name}"] = param_value
            
            # 添加关键性能指标
            key_metrics = [
                'total_return_pct', 'annualized_return_pct', 'sharpe_ratio', 
                'sortino_ratio', 'max_drawdown_pct', 'calmar_ratio'
            ]
            
            for metric in key_metrics:
                row[metric] = result.get(metric, "N/A")
            
            results_data.append(row)
        
        return pd.DataFrame(results_data)

# Example Usage
if __name__ == "__main__":
    # 此代码块展示如何使用Optimizer类
    # 实际使用时，需要根据实际情况创建和配置BacktestingEngine
    
    from datetime import datetime, timedelta
    from ..data_module.providers.simulated_data_provider import SimulatedDataProvider
    from ..strategy_module.pyramid_llm_strategy import PyramidLLMStrategy
    from ..llm_module.clients.simulated_llm_client import SimulatedLLMClient
    from ..portfolio_module.portfolio import Portfolio
    from ..execution_module.brokers.simulated_broker import SimulatedBroker
    from ..execution_module.order_handler import OrderHandler
    from ..risk_module.simple_risk_manager import SimpleRiskManager
    
    # 示例：设置回测环境
    start_dt = datetime(2023, 1, 1)
    end_dt = datetime(2023, 12, 31)
    initial_capital = 100000.0
    test_symbols = ['AAPL', 'MSFT']
    
    # 创建组件实例
    data_provider = SimulatedDataProvider(config={})
    llm_client = SimulatedLLMClient(config={})
    strategy = PyramidLLMStrategy(config={'llm_client': llm_client})
    portfolio = Portfolio(initial_cash=initial_capital, market_data_provider=data_provider)
    broker = SimulatedBroker(config={'initial_cash': initial_capital})
    risk_manager = SimpleRiskManager(config={})
    order_handler = OrderHandler(broker=broker, risk_manager=risk_manager)
    
    # 创建回测引擎
    engine = BacktestingEngine(
        start_date=start_dt,
        end_date=end_dt,
        data_provider=data_provider,
        strategy=strategy,
        portfolio=portfolio,
        broker=broker,
        order_handler=order_handler,
        initial_capital=initial_capital,
        risk_manager=risk_manager
    )
    
    # 创建优化器
    optimizer = Optimizer(
        backtest_engine=engine,
        symbols=test_symbols
    )
    
    # 设置要优化的参数网格
    optimizer.set_param_grid({
        'ma_short': [5, 10, 15, 20],
        'ma_long': [30, 40, 50, 60],
        'stop_loss_pct': [0.02, 0.03, 0.05]
    })
    
    # 运行优化
    results = optimizer.run_optimization(
        metric_to_optimize='sharpe_ratio', 
        maximize=True
    )
    
    # 获取最佳参数
    best_params = optimizer.get_best_params()
    print(f"Best Parameters: {best_params}")
    
    # 获取结果DataFrame并输出
    results_df = optimizer.get_results_df()
    if results_df is not None:
        print(results_df.head()) 
"""
LLM响应解析工具函数

用于解析大模型返回的各类分析结果，如趋势分析、入场点分析、仓位管理建议等。
"""

import re
import logging
from typing import Dict, Any, List, Optional, Union

# 获取logger
logger = logging.getLogger('app')

def parse_trend_analysis(llm_response: str) -> Dict[str, Any]:
    """
    解析LLM趋势分析响应
    
    Args:
        llm_response: LLM返回的趋势分析文本
        
    Returns:
        解析后的趋势分析结果字典
    """
    result = {
        'trend': None,        # 趋势方向: 上升趋势/下降趋势/横盘整理
        'strength': None,     # 趋势强度: 1-10
        'duration': None,     # 趋势持续性: 短期/中期/长期
        'support_levels': [], # 支撑位列表
        'resistance_levels': [], # 阻力位列表
        'analysis': None      # 分析依据
    }
    
    try:
        # 提取趋势方向
        trend_match = re.search(r'趋势: *(上升趋势|下降趋势|横盘整理)', llm_response, re.IGNORECASE)
        if trend_match:
            result['trend'] = trend_match.group(1)
            
        # 提取趋势强度
        strength_match = re.search(r'强度评分: *([1-9]|10)', llm_response)
        if strength_match:
            result['strength'] = int(strength_match.group(1))
            
        # 提取趋势持续性
        duration_match = re.search(r'趋势持续性: *(短期|中期|长期) *- *([^\n]+)', llm_response)
        if duration_match:
            duration_type = duration_match.group(1)
            duration_time = duration_match.group(2)
            result['duration'] = f"{duration_type} - {duration_time}"
            
        # 提取支撑位
        support_match = re.search(r'关键支撑位: *([^\n]+)', llm_response)
        if support_match:
            support_str = support_match.group(1)
            # 尝试提取数字作为支撑位
            supports = re.findall(r'(\d+\.?\d*)', support_str)
            result['support_levels'] = [float(s) for s in supports]
            
        # 提取阻力位
        resistance_match = re.search(r'关键阻力位: *([^\n]+)', llm_response)
        if resistance_match:
            resistance_str = resistance_match.group(1)
            # 尝试提取数字作为阻力位
            resistances = re.findall(r'(\d+\.?\d*)', resistance_str)
            result['resistance_levels'] = [float(r) for r in resistances]
            
        # 提取分析依据
        analysis_match = re.search(r'分析依据:\s*(.+?)(?=\n\n|\Z)', llm_response, re.DOTALL)
        if analysis_match:
            result['analysis'] = analysis_match.group(1).strip()
            
    except Exception as e:
        logger.error(f"解析趋势分析响应时出错: {str(e)}")
    
    # 验证是否成功提取了基本信息
    if not result['trend'] or result['strength'] is None:
        logger.warning(f"未能成功解析趋势分析的核心信息，原始响应: {llm_response[:200]}...")
        
    return result

def parse_entry_analysis(llm_response: str) -> Dict[str, Any]:
    """
    解析LLM入场点分析响应
    
    Args:
        llm_response: LLM返回的入场点分析文本
        
    Returns:
        解析后的入场分析结果字典
    """
    result = {
        'entry_decision': None,  # 入场决策: 是/否
        'price_range': None,     # 入场价格区间
        'initial_position': None, # 初始仓位大小
        'stop_loss': None,       # 止损位
        'confidence': None,      # 信号可信度
        'reason': None           # 入场理由
    }
    
    try:
        # 提取入场决策
        decision_match = re.search(r'入场决策: *(是|否)', llm_response, re.IGNORECASE)
        if decision_match:
            result['entry_decision'] = decision_match.group(1).lower()
            
        # 提取价格区间
        price_match = re.search(r'入场价格区间: *(\d+\.?\d*)-(\d+\.?\d*)', llm_response)
        if price_match:
            price_lower = float(price_match.group(1))
            price_upper = float(price_match.group(2))
            result['price_range'] = (price_lower, price_upper)
            
        # 提取初始仓位
        position_match = re.search(r'初始仓位: *(\d+\.?\d*)%', llm_response)
        if position_match:
            result['initial_position'] = float(position_match.group(1)) / 100.0
            
        # 提取止损位
        stop_loss_match = re.search(r'止损位: *(\d+\.?\d*)', llm_response)
        if stop_loss_match:
            result['stop_loss'] = float(stop_loss_match.group(1))
            
        # 提取信号可信度
        confidence_match = re.search(r'信号可信度: *([1-9]|10)', llm_response)
        if confidence_match:
            result['confidence'] = int(confidence_match.group(1))
            
        # 提取入场理由
        reason_match = re.search(r'入场理由:\s*(.+?)(?=\n\n|\Z)', llm_response, re.DOTALL)
        if reason_match:
            result['reason'] = reason_match.group(1).strip()
            
    except Exception as e:
        logger.error(f"解析入场分析响应时出错: {str(e)}")
    
    # 验证是否成功提取了基本信息
    if result['entry_decision'] is None:
        logger.warning(f"未能成功解析入场决策，原始响应: {llm_response[:200]}...")
        
    return result

def parse_position_advice(llm_response: str) -> Dict[str, Any]:
    """
    解析LLM仓位管理建议响应
    
    Args:
        llm_response: LLM返回的仓位管理建议文本
        
    Returns:
        解析后的仓位管理建议字典
    """
    result = {
        'action': None,           # 建议操作: 加仓/减仓/维持/清仓
        'percentage': None,       # 操作百分比
        'total_position': None,   # 操作后总仓位
        'stop_loss': None,        # 新止损位
        'reason': None            # 操作理由
    }
    
    try:
        # 提取建议操作
        action_match = re.search(r'建议操作: *(加仓|减仓|维持|清仓)', llm_response, re.IGNORECASE)
        if action_match:
            action = action_match.group(1).lower()
            # 将中文操作转换为英文代码
            action_map = {
                '加仓': 'add',
                '减仓': 'reduce',
                '维持': 'maintain',
                '清仓': 'exit'
            }
            result['action'] = action_map.get(action, 'maintain')
            
        # 提取操作百分比
        percentage_match = re.search(r'操作百分比: *(\d+\.?\d*)%', llm_response)
        if percentage_match:
            result['percentage'] = float(percentage_match.group(1)) / 100.0
            
        # 提取操作后总仓位
        total_match = re.search(r'操作后总仓位: *(\d+\.?\d*)%', llm_response)
        if total_match:
            result['total_position'] = float(total_match.group(1)) / 100.0
            
        # 提取新止损位
        stop_loss_match = re.search(r'新止损位: *(\d+\.?\d*)', llm_response)
        if stop_loss_match:
            result['stop_loss'] = float(stop_loss_match.group(1))
            
        # 提取操作理由
        reason_match = re.search(r'操作理由:\s*(.+?)(?=\n\n|\Z)', llm_response, re.DOTALL)
        if reason_match:
            result['reason'] = reason_match.group(1).strip()
            
    except Exception as e:
        logger.error(f"解析仓位管理建议响应时出错: {str(e)}")
    
    # 验证是否成功提取了基本信息
    if result['action'] is None:
        logger.warning(f"未能成功解析仓位管理建议的核心信息，原始响应: {llm_response[:200]}...")
        # 默认为维持现状
        result['action'] = 'maintain'
        
    return result

def parse_exit_strategy(llm_response: str) -> Dict[str, Any]:
    """
    解析LLM退出策略响应
    
    Args:
        llm_response: LLM返回的退出策略文本
        
    Returns:
        解析后的退出策略字典
    """
    result = {
        'exit_decision': None,    # 退出决策: 是/否
        'exit_percentage': None,  # 退出比例
        'exit_price_range': None, # 退出价格区间
        'new_stop_loss': None,    # 新止损位
        'trigger_condition': None, # 触发条件
        'confidence': None,       # 置信度
        'reason': None            # 建议理由
    }
    
    try:
        # 提取退出决策
        decision_match = re.search(r'退出决策: *(是|否)', llm_response, re.IGNORECASE)
        if decision_match:
            result['exit_decision'] = decision_match.group(1).lower()
            
        # 提取退出比例
        percentage_match = re.search(r'退出比例: *(\d+\.?\d*)%', llm_response)
        if percentage_match:
            result['exit_percentage'] = float(percentage_match.group(1)) / 100.0
            
        # 提取退出价格区间
        price_match = re.search(r'退出价格区间: *(\d+\.?\d*)-(\d+\.?\d*)', llm_response)
        if price_match:
            price_lower = float(price_match.group(1))
            price_upper = float(price_match.group(2))
            result['exit_price_range'] = (price_lower, price_upper)
            
        # 提取新止损位
        stop_loss_match = re.search(r'新止损位: *(\d+\.?\d*)', llm_response)
        if stop_loss_match:
            result['new_stop_loss'] = float(stop_loss_match.group(1))
            
        # 提取触发条件 - 这可能是多行文本
        condition_match = re.search(r'触发条件:\s*(.+?)(?=置信度:|建议理由:|\n\n|\Z)', llm_response, re.DOTALL)
        if condition_match:
            result['trigger_condition'] = condition_match.group(1).strip()
            
        # 提取置信度
        confidence_match = re.search(r'置信度: *([1-9]|10)', llm_response)
        if confidence_match:
            result['confidence'] = int(confidence_match.group(1))
            
        # 提取建议理由
        reason_match = re.search(r'建议理由:\s*(.+?)(?=\n\n|\Z)', llm_response, re.DOTALL)
        if reason_match:
            result['reason'] = reason_match.group(1).strip()
            
    except Exception as e:
        logger.error(f"解析退出策略响应时出错: {str(e)}")
    
    # 验证是否成功提取了基本信息
    if result['exit_decision'] is None:
        logger.warning(f"未能成功解析退出策略的核心信息，原始响应: {llm_response[:200]}...")
        
    return result 
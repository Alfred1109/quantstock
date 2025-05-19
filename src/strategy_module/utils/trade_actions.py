"""
交易操作工具函数

实现金字塔交易策略中的加仓、减仓、清仓等核心交易操作。
"""

import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

# 获取logger
logger = logging.getLogger('app')

def add_to_position(
    symbol: str, 
    position_advice: Dict[str, Any], 
    market_data: Dict[str, Any],
    current_positions: Dict[str, Dict[str, Any]],
    pyramid_status: Dict[str, Dict[str, Any]],
    account_value: float,
    execute_signal_func: callable
) -> Dict[str, Any]:
    """
    执行加仓操作
    
    根据仓位建议和市场数据，计算加仓数量并执行加仓
    
    Args:
        symbol: 资产代码
        position_advice: 仓位管理建议
        market_data: 市场数据
        current_positions: 当前持仓状态
        pyramid_status: 金字塔状态
        account_value: 账户总价值
        execute_signal_func: 执行信号的函数
        
    Returns:
        执行结果字典
    """
    # 获取当前持仓信息
    position = current_positions.get(symbol, {})
    pyramid = pyramid_status.get(symbol, {
        'level': 0,
        'entries': [],
        'stop_loss': None,
        'take_profit': None
    })
    
    # 获取加仓比例和当前价格
    add_percentage = position_advice.get('percentage', 0.1)  # 默认10%
    current_price = market_data.get('current', {}).get('close')
    
    if not current_price:
        logger.error(f"加仓失败: {symbol}当前价格不可用")
        return {'status': 'failed', 'reason': '当前价格不可用'}
    
    # 计算加仓数量
    add_amount = account_value * add_percentage
    add_quantity = int(add_amount / current_price)
    
    if add_quantity <= 0:
        logger.warning(f"{symbol}计算的加仓数量为0，跳过加仓")
        return {'status': 'skipped', 'reason': '计算的加仓数量为0'}
    
    # 检查是否达到最大金字塔层级
    if pyramid.get('level', 0) >= 3:  # 假设最大层级为3
        logger.warning(f"{symbol}已达到最大金字塔层级，不再加仓")
        return {'status': 'skipped', 'reason': '已达到最大金字塔层级'}
    
    # 创建加仓信号
    signal = {
        'action': 'BUY',
        'symbol': symbol,
        'quantity': add_quantity,
        'price': current_price,
        'reason': position_advice.get('reason', '金字塔策略加仓')
    }
    
    # 执行信号
    result = execute_signal_func(signal)
    
    # 如果执行成功，更新金字塔状态
    if result.get('status') == 'success':
        # 增加金字塔层级
        pyramid['level'] = pyramid.get('level', 0) + 1
        
        # 记录新的入场
        entry = {
            'price': current_price,
            'quantity': add_quantity,
            'timestamp': datetime.now().isoformat(),
            'type': 'pyramid_add'
        }
        pyramid['entries'].append(entry)
        
        # 更新止损位（如果提供了新的止损位）
        new_stop_loss = position_advice.get('stop_loss')
        if new_stop_loss:
            pyramid['stop_loss'] = new_stop_loss
            
        # 更新金字塔状态
        pyramid_status[symbol] = pyramid
        
        logger.info(f"{symbol}加仓成功: {add_quantity}@{current_price}, 新金字塔层级: {pyramid['level']}")
    
    return result

def reduce_position(
    symbol: str, 
    position_advice: Dict[str, Any], 
    market_data: Dict[str, Any],
    current_positions: Dict[str, Dict[str, Any]],
    pyramid_status: Dict[str, Dict[str, Any]],
    execute_signal_func: callable
) -> Dict[str, Any]:
    """
    执行减仓操作
    
    根据仓位建议和市场数据，计算减仓数量并执行减仓
    
    Args:
        symbol: 资产代码
        position_advice: 仓位管理建议
        market_data: 市场数据
        current_positions: 当前持仓状态
        pyramid_status: 金字塔状态
        execute_signal_func: 执行信号的函数
        
    Returns:
        执行结果字典
    """
    # 获取当前持仓信息
    position = current_positions.get(symbol, {})
    current_quantity = position.get('quantity', 0)
    
    if current_quantity <= 0:
        logger.warning(f"减仓失败: {symbol}无持仓")
        return {'status': 'failed', 'reason': '无持仓'}
    
    pyramid = pyramid_status.get(symbol, {
        'level': 1,
        'entries': [],
        'stop_loss': None,
        'take_profit': None
    })
    
    # 获取减仓比例和当前价格
    reduce_percentage = position_advice.get('percentage', 0.5)  # 默认减仓50%
    current_price = market_data.get('current', {}).get('close')
    
    if not current_price:
        logger.error(f"减仓失败: {symbol}当前价格不可用")
        return {'status': 'failed', 'reason': '当前价格不可用'}
    
    # 计算减仓数量
    reduce_quantity = int(current_quantity * reduce_percentage)
    
    if reduce_quantity <= 0:
        logger.warning(f"{symbol}计算的减仓数量为0，跳过减仓")
        return {'status': 'skipped', 'reason': '计算的减仓数量为0'}
    
    # 创建减仓信号
    signal = {
        'action': 'SELL',
        'symbol': symbol,
        'quantity': reduce_quantity,
        'price': current_price,
        'reason': position_advice.get('reason', '金字塔策略减仓')
    }
    
    # 执行信号
    result = execute_signal_func(signal)
    
    # 如果执行成功，更新金字塔状态
    if result.get('status') == 'success':
        # 减少金字塔层级
        new_level = max(1, pyramid.get('level', 1) - 1)
        pyramid['level'] = new_level
        
        # 记录减仓
        exit_record = {
            'price': current_price,
            'quantity': reduce_quantity,
            'timestamp': datetime.now().isoformat(),
            'type': 'pyramid_reduce'
        }
        
        # 添加到退出记录（如果没有，则创建）
        if 'exits' not in pyramid:
            pyramid['exits'] = []
        pyramid['exits'].append(exit_record)
        
        # 更新止损位（如果提供了新的止损位）
        new_stop_loss = position_advice.get('stop_loss')
        if new_stop_loss:
            pyramid['stop_loss'] = new_stop_loss
            
        # 更新金字塔状态
        pyramid_status[symbol] = pyramid
        
        logger.info(f"{symbol}减仓成功: {reduce_quantity}@{current_price}, 新金字塔层级: {pyramid['level']}")
    
    return result

def exit_position(
    symbol: str, 
    position_advice: Dict[str, Any], 
    market_data: Dict[str, Any],
    current_positions: Dict[str, Dict[str, Any]],
    pyramid_status: Dict[str, Dict[str, Any]],
    execute_signal_func: callable
) -> Dict[str, Any]:
    """
    执行清仓操作
    
    根据仓位建议和市场数据，执行全部清仓
    
    Args:
        symbol: 资产代码
        position_advice: 仓位管理建议
        market_data: 市场数据
        current_positions: 当前持仓状态
        pyramid_status: 金字塔状态
        execute_signal_func: 执行信号的函数
        
    Returns:
        执行结果字典
    """
    # 获取当前持仓信息
    position = current_positions.get(symbol, {})
    current_quantity = position.get('quantity', 0)
    
    if current_quantity <= 0:
        logger.warning(f"清仓失败: {symbol}无持仓")
        return {'status': 'failed', 'reason': '无持仓'}
    
    # 获取当前价格
    current_price = market_data.get('current', {}).get('close')
    
    if not current_price:
        logger.error(f"清仓失败: {symbol}当前价格不可用")
        return {'status': 'failed', 'reason': '当前价格不可用'}
    
    # 创建清仓信号
    signal = {
        'action': 'SELL',
        'symbol': symbol,
        'quantity': current_quantity,  # 全部数量
        'price': current_price,
        'reason': position_advice.get('reason', '金字塔策略清仓')
    }
    
    # 执行信号
    result = execute_signal_func(signal)
    
    # 如果执行成功，重置金字塔状态
    if result.get('status') == 'success':
        # 记录清仓
        exit_record = {
            'price': current_price,
            'quantity': current_quantity,
            'timestamp': datetime.now().isoformat(),
            'type': 'full_exit'
        }
        
        # 添加到退出记录（如果没有，则创建）
        if symbol in pyramid_status:
            pyramid = pyramid_status[symbol]
            if 'exits' not in pyramid:
                pyramid['exits'] = []
            pyramid['exits'].append(exit_record)
            
            # 重置金字塔状态
            pyramid['level'] = 0
            pyramid['stop_loss'] = None
            pyramid['take_profit'] = None
            
            # 更新金字塔状态
            pyramid_status[symbol] = pyramid
        
        logger.info(f"{symbol}清仓成功: {current_quantity}@{current_price}")
    
    return result 
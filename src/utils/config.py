#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
配置工具模块
提供统一的配置访问功能
"""

import os
import yaml
from typing import Any, Dict, Optional

# 默认配置目录
DEFAULT_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'config')

# 配置缓存
_config_cache: Dict[str, Dict] = {}

def get_config(section: str, key: Optional[str] = None, default: Any = None) -> Any:
    """
    获取配置项
    
    Args:
        section: 配置文件名（不含扩展名）或配置节名称
        key: 配置项键名，如果为None则返回整个配置节
        default: 如果配置项不存在，返回的默认值
        
    Returns:
        配置项值或默认值
    """
    # 尝试加载配置
    config = _load_config(section)
    
    # 如果找不到配置，返回默认值
    if config is None:
        return default
    
    # 如果未指定键名，返回整个配置节
    if key is None:
        return config
    
    # 返回指定键名的配置项，如果不存在则返回默认值
    return config.get(key, default)

def _load_config(section: str) -> Optional[Dict]:
    """
    加载配置文件
    
    Args:
        section: 配置文件名（不含扩展名）或配置节名称
        
    Returns:
        配置字典，如果加载失败则返回None
    """
    # 如果已经缓存，直接返回
    if section in _config_cache:
        return _config_cache[section]
    
    # 尝试作为文件名加载
    config_path = os.path.join(DEFAULT_CONFIG_DIR, f"{section}.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                _config_cache[section] = config
                return config
        except Exception:
            # 加载失败，尝试其他方式
            pass
    
    # 尝试从settings.yaml中加载指定节
    settings_path = os.path.join(DEFAULT_CONFIG_DIR, "settings.yaml")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = yaml.safe_load(f)
                if isinstance(settings, dict) and section in settings:
                    _config_cache[section] = settings[section]
                    return settings[section]
        except Exception:
            # 加载失败，返回None
            pass
    
    # 所有尝试都失败，返回None
    return None 
import os
import logging
import yaml
from typing import Dict, Any, Optional

from .providers import (
    BaseDataProvider,
    SimulatedDataProvider,
    AKShareDataProvider
)

logger = logging.getLogger(__name__)

def load_config(provider_type: str) -> Dict[str, Any]:
    """
    加载指定数据提供器的配置文件
    
    参数:
        provider_type: 数据提供器类型
        
    返回:
        配置字典
    """
    # 确定配置文件路径
    config_path = os.path.join('config', f'{provider_type.lower()}_config.yaml')
    
    # 尝试加载配置文件
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        logger.warning(f"配置文件未找到: {config_path}，将使用默认配置")
        return {}
    except Exception as e:
        logger.error(f"加载配置文件出错: {e}")
        return {}

class DataProviderFactory:
    """
    数据提供器工厂类
    负责创建和管理各种数据提供器实例
    """
    
    _instances = {}  # 单例模式存储不同类型的数据提供器实例
    
    @classmethod
    def get_provider(cls, provider_type: str = "akshare", force_new: bool = False) -> BaseDataProvider:
        """
        获取指定类型的数据提供器实例
        
        参数:
            provider_type: 数据提供器类型 (akshare, simulated)
            force_new: 是否强制创建新实例
            
        返回:
            数据提供器实例
        """
        # 转换为小写以忽略大小写差异
        provider_type = provider_type.lower()
        
        # 如果不是强制创建新实例且已有缓存实例，则返回缓存的实例
        if not force_new and provider_type in cls._instances:
            return cls._instances[provider_type]
        
        # 加载配置
        config = load_config(provider_type)
        
        # 根据类型创建数据提供器
        provider = None
        
        if provider_type == 'akshare':
            provider = AKShareDataProvider(config)
            logger.info("创建AKShare数据提供器")
        elif provider_type == 'simulated':
            provider = SimulatedDataProvider(config)
            logger.info("创建模拟数据提供器")
        else:
            # 默认使用AKShare
            logger.warning(f"未知的数据提供器类型: {provider_type}，将使用AKShare作为默认值")
            provider = AKShareDataProvider(load_config('akshare'))
        
        # 缓存实例
        cls._instances[provider_type] = provider
        
        return provider
    
    @classmethod
    def clear_instance(cls, provider_type: str = None):
        """
        清除指定类型或所有数据提供器实例缓存
        
        参数:
            provider_type: 数据提供器类型，为None时清除所有实例
        """
        if provider_type:
            if provider_type.lower() in cls._instances:
                del cls._instances[provider_type.lower()]
                logger.info(f"清除{provider_type}数据提供器实例缓存")
        else:
            cls._instances.clear()
            logger.info("清除所有数据提供器实例缓存")

# 提供便捷的全局访问函数
def get_data_provider(provider_type: str = "akshare", force_new: bool = False) -> BaseDataProvider:
    """
    获取数据提供器实例
    
    参数:
        provider_type: 数据提供器类型 (akshare, simulated)
        force_new: 是否强制创建新实例
        
    返回:
        数据提供器实例
    """
    return DataProviderFactory.get_provider(provider_type, force_new) 
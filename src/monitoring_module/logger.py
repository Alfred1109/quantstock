"""
日志模块，提供统一的日志记录功能。
支持多级别日志（DEBUG, INFO, WARNING, ERROR, CRITICAL）
支持输出到文件和控制台
支持通过配置文件设置日志级别和输出方式
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import yaml
from datetime import datetime
import traceback

class Logger:
    """
    日志类，提供统一的日志记录接口
    """
    # 日志级别映射
    LEVELS = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }
    
    # 单例实例
    _instance = None
    
    @classmethod
    def get_instance(cls, config_path=None):
        """
        获取Logger单例实例
        
        Args:
            config_path: 日志配置文件路径，默认为None使用默认配置
            
        Returns:
            Logger实例
        """
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance
    
    @classmethod
    def configure(cls, log_level='INFO', log_file=None, console_logging=True, max_bytes=10*1024*1024, backup_count=5):
        """
        配置全局日志记录器
        
        Args:
            log_level: 日志级别，可以是'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
            log_file: 日志文件路径，如果为None，则不写入文件
            console_logging: 是否输出到控制台
            max_bytes: 单个日志文件最大字节数
            backup_count: 备份文件数量
            
        Returns:
            配置好的logger对象
        """
        # 设置日志级别
        level = cls.LEVELS.get(log_level.lower(), logging.INFO)
        
        # 创建根logger
        logger = logging.getLogger('app')
        logger.setLevel(level)
        
        # 清除已有处理器
        logger.handlers.clear()
        
        # 创建格式化器
        console_formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')
        file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s')
        
        # 添加控制台处理器
        if console_logging:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        # 添加文件处理器
        if log_file:
            # 确保日志目录存在
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
                
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    @classmethod
    def get_logger(cls, name='app'):
        """
        获取指定名称的logger
        
        Args:
            name: logger名称
            
        Returns:
            logger对象
        """
        return logging.getLogger(name)
    
    def __init__(self, config_path=None):
        """
        初始化日志记录器
        
        Args:
            config_path: 日志配置文件路径，如果为None则使用默认配置
        """
        # 默认配置
        self.config = {
            'log_level': 'info',
            'log_to_console': True,
            'log_to_file': True,
            'log_dir': 'logs',
            'log_file_prefix': 'app',
            'max_file_size_mb': 10,
            'backup_count': 5,
            'use_rotating_file': True
        }
        
        # 如果提供了配置文件，则加载配置
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f)
                    if isinstance(file_config, dict) and 'logging' in file_config:
                        self.config.update(file_config['logging'])
            except Exception as e:
                print(f"加载日志配置文件失败: {str(e)}")
                
        # 创建日志目录
        if self.config['log_to_file']:
            os.makedirs(self.config['log_dir'], exist_ok=True)
        
        # 创建日志记录器
        self.logger = logging.getLogger('app')
        self.logger.setLevel(self.LEVELS.get(self.config['log_level'].lower(), logging.INFO))
        
        # 清除现有处理器
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # 添加控制台处理器
        if self.config['log_to_console']:
            console_handler = logging.StreamHandler(sys.stdout)
            console_format = logging.Formatter(
                '%(asctime)s [%(levelname)s] - %(message)s'
            )
            console_handler.setFormatter(console_format)
            self.logger.addHandler(console_handler)
        
        # 添加文件处理器
        if self.config['log_to_file']:
            # 生成日志文件名
            today = datetime.now().strftime('%Y%m%d')
            log_file = os.path.join(
                self.config['log_dir'], 
                f"{self.config['log_file_prefix']}_{today}.log"
            )
            
            file_format = logging.Formatter(
                '%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s'
            )
            
            # 根据配置选择文件处理器类型
            if self.config['use_rotating_file']:
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=self.config['max_file_size_mb'] * 1024 * 1024,
                    backupCount=self.config['backup_count'],
                    encoding='utf-8'
                )
            else:
                file_handler = TimedRotatingFileHandler(
                    log_file,
                    when='midnight',
                    interval=1,
                    backupCount=self.config['backup_count'],
                    encoding='utf-8'
                )
                
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
    
    def debug(self, message, *args, **kwargs):
        """记录调试级别日志"""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message, *args, **kwargs):
        """记录信息级别日志"""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message, *args, **kwargs):
        """记录警告级别日志"""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message, *args, **kwargs):
        """记录错误级别日志"""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message, *args, **kwargs):
        """记录严重错误级别日志"""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message, *args, exc_info=True, **kwargs):
        """记录异常信息，包含堆栈跟踪"""
        self.logger.exception(message, *args, exc_info=exc_info, **kwargs)
    
    def log_exception(self, exception, message="发生异常:"):
        """记录完整的异常信息"""
        trace = traceback.format_exc()
        self.error(f"{message} {str(exception)}\n{trace}")

# 便于直接导入使用的函数
def get_logger(config_path=None):
    """
    获取日志实例的便捷函数
    
    Args:
        config_path: 日志配置文件路径
        
    Returns:
        Logger实例
    """
    return Logger.get_instance(config_path)

# 使用示例
if __name__ == "__main__":
    # 获取日志实例
    logger = get_logger()
    
    # 记录不同级别的日志
    logger.debug("这是一条调试日志")
    logger.info("这是一条信息日志")
    logger.warning("这是一条警告日志")
    logger.error("这是一条错误日志")
    
    # 记录异常
    try:
        1 / 0
    except Exception as e:
        logger.log_exception(e, "除零错误:") 
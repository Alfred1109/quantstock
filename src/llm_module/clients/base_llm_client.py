"""
LLM客户端基类，定义了与大模型交互的通用接口。
所有具体的LLM客户端实现都应继承此类。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union

class BaseLLMClient(ABC):
    """
    大语言模型(LLM)客户端的抽象基类。
    
    定义了与LLM交互的标准接口，包括文本生成、嵌入向量获取等功能。
    具体的API实现（如DeepSeek、OpenAI等）需要继承此类并实现抽象方法。
    """

    def __init__(self, api_key: str, model_name: str, base_url: Optional[str] = None):
        """
        初始化LLM客户端
        
        Args:
            api_key: API密钥
            model_name: 模型名称
            base_url: API基础URL，如果为None则使用默认URL
        """
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url

    @abstractmethod
    def generate_text(self, prompt: str, **kwargs) -> str:
        """
        根据提示生成文本
        
        Args:
            prompt: 提示文本
            **kwargs: 其他可选参数，如温度、最大token数等
            
        Returns:
            生成的文本内容
        """
        raise NotImplementedError("子类必须实现generate_text方法")

    @abstractmethod
    def get_embeddings(self, text_list: List[str]) -> List[List[float]]:
        """
        获取文本列表的嵌入向量表示
        
        Args:
            text_list: 文本列表
            
        Returns:
            嵌入向量列表，每个文本对应一个向量
        """
        raise NotImplementedError("子类必须实现get_embeddings方法")
    
    def health_check(self) -> bool:
        """
        检查API连接状态
        
        Returns:
            如果API连接正常则返回True，否则返回False
        """
        try:
            # 基本实现：尝试生成一个简单的文本
            self.generate_text("Hello", max_tokens=5)
            return True
        except Exception as e:
            print(f"API健康检查失败: {str(e)}")
            return False 
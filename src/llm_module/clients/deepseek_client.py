"""
与火山引擎上的DeepSeek大模型API交互的客户端
"""

import json
import requests
from typing import List, Dict, Any, Optional
import logging
import os

# 添加OpenAI客户端支持
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from .base_llm_client import BaseLLMClient

# 获取logger
logger = logging.getLogger('app')

class DeepSeekClient(BaseLLMClient):
    """
    火山引擎DeepSeek大模型客户端实现
    
    该客户端用于与火山引擎提供的DeepSeek大模型API进行交互，
    支持文本生成和向量嵌入功能。
    可以使用原生requests方式调用，也可以使用OpenAI客户端库。
    """
    
    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
    
    def __init__(self, 
                 api_key: str, 
                 model_name: str = "deepseek-v3-250324",
                 base_url: Optional[str] = None,
                 use_openai_client: bool = True):
        """
        初始化DeepSeek客户端
        
        Args:
            api_key: 火山引擎API密钥
            model_name: 模型名称，默认为"deepseek-v3-250324"
            base_url: API基础URL，如未指定则使用默认值
            use_openai_client: 是否使用OpenAI客户端库，默认为True
        """
        base_url = base_url or self.DEFAULT_BASE_URL
        super().__init__(api_key, model_name, base_url)
        
        self.use_openai_client = use_openai_client and OPENAI_AVAILABLE
        
        if self.use_openai_client:
            if not OPENAI_AVAILABLE:
                logger.warning("OpenAI客户端库不可用，将使用requests直接调用API")
                self.use_openai_client = False
            else:
                # 初始化OpenAI客户端
                self.openai_client = OpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key
                )
                logger.info(f"DeepSeekClient已初始化(OpenAI客户端)，模型: {model_name}, URL: {base_url}")
        else:
            logger.info(f"DeepSeekClient已初始化(直接请求)，模型: {model_name}, URL: {base_url}")
    
    def generate_text(self, 
                     prompt: str, 
                     temperature: float = 0.7, 
                     max_tokens: int = 2048,
                     top_p: float = 0.95,
                     stream: bool = False,
                     **kwargs) -> str:
        """
        使用DeepSeek生成文本
        
        Args:
            prompt: 提示文本
            temperature: 温度参数，控制生成文本的随机性，默认0.7
            max_tokens: 生成的最大token数，默认2048
            top_p: 用于nucleus sampling的概率阈值，默认0.95
            stream: 是否启用流式输出，默认False
            **kwargs: 其他传递给API的参数
            
        Returns:
            生成的文本内容
            
        Raises:
            Exception: 当API调用失败时抛出异常
        """
        logger.debug(f"向DeepSeek发送请求，提示长度: {len(prompt)}")
        
        if self.use_openai_client:
            return self._generate_text_openai(
                prompt, temperature, max_tokens, top_p, stream, **kwargs
            )
        else:
            return self._generate_text_requests(
                prompt, temperature, max_tokens, top_p, stream, **kwargs
            )
    
    def _generate_text_openai(self, 
                             prompt: str, 
                             temperature: float = 0.7, 
                             max_tokens: int = 2048,
                             top_p: float = 0.95,
                             stream: bool = False,
                             **kwargs) -> str:
        """使用OpenAI客户端生成文本"""
        try:
            # 使用OpenAI客户端API格式
            response = self.openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是人工智能助手"},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                stream=stream,
                **kwargs
            )
            
            if stream:
                # 处理流式响应
                chunks = []
                for chunk in response:
                    if not chunk.choices:
                        continue
                    chunk_content = chunk.choices[0].delta.content
                    if chunk_content:
                        chunks.append(chunk_content)
                return "".join(chunks)
            else:
                # 处理普通响应
                return response.choices[0].message.content
                
        except Exception as e:
            error_msg = f"DeepSeek API(OpenAI客户端)请求失败: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def _generate_text_requests(self, 
                               prompt: str, 
                               temperature: float = 0.7, 
                               max_tokens: int = 2048,
                               top_p: float = 0.95,
                               stream: bool = False,
                               **kwargs) -> str:
        """使用requests直接调用API生成文本"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 构建API请求体
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "你是人工智能助手"},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": stream
        }
        
        # 添加其他参数
        payload.update({k: v for k, v in kwargs.items() if k not in payload})
        
        try:
            response = requests.post(
                f"{self.base_url}/completions",
                headers=headers,
                json=payload,
                timeout=60  # 60秒超时
            )
            
            # 检查是否有HTTP错误
            response.raise_for_status()
            
            # 解析返回结果
            result = response.json()
            
            if "error" in result:
                error_msg = f"DeepSeek API错误: {result['error']}"
                logger.error(error_msg)
                raise Exception(error_msg)
            
            # 从结果中提取生成的文本
            if stream:
                # 处理流式输出
                return self._handle_streaming_response(response)
            else:
                # 处理普通响应
                text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                logger.debug(f"DeepSeek返回文本，长度: {len(text)}")
                return text
            
        except requests.exceptions.RequestException as e:
            error_msg = f"DeepSeek API请求失败: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def _handle_streaming_response(self, response):
        """处理流式API响应"""
        # 此处实现需要根据火山引擎实际的流式响应格式调整
        chunks = []
        
        for line in response.iter_lines():
            if line:
                try:
                    chunk = json.loads(line.decode('utf-8').replace('data: ', ''))
                    text_chunk = chunk.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if text_chunk:
                        chunks.append(text_chunk)
                except Exception as e:
                    logger.warning(f"解析流式响应失败: {str(e)}")
        
        return "".join(chunks)
    
    def get_embeddings(self, text_list: List[str]) -> List[List[float]]:
        """
        获取文本的嵌入向量表示
        
        Args:
            text_list: 文本列表
            
        Returns:
            嵌入向量列表，每个文本对应一个向量
            
        Raises:
            Exception: 当API调用失败时抛出异常
        """
        # 注意：如果需要使用OpenAI客户端获取嵌入向量，需要实现相应代码
        # 这里暂时保留原来的实现
        
        logger.debug(f"请求DeepSeek嵌入向量，文本数量: {len(text_list)}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": f"{self.model_name}-embedding",  # 通常嵌入模型名称会有区别
            "input": text_list
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            response.raise_for_status()
            result = response.json()
            
            if "error" in result:
                error_msg = f"DeepSeek Embedding API错误: {result['error']}"
                logger.error(error_msg)
                raise Exception(error_msg)
            
            # 从结果中提取嵌入向量
            # 注意：实际实现需要根据火山引擎API的具体返回格式调整
            embeddings = [item.get("embedding", []) for item in result.get("data", [])]
            
            if len(embeddings) != len(text_list):
                logger.warning(f"获取的嵌入向量数量({len(embeddings)})与请求文本数量({len(text_list)})不匹配")
            
            return embeddings
            
        except requests.exceptions.RequestException as e:
            error_msg = f"DeepSeek Embedding API请求失败: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

# 使用示例
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    # 加载环境变量
    load_dotenv()
    
    # 从环境变量获取API密钥
    api_key = os.getenv("DEEPSEEK_API_KEY", "3470059d-f774-4302-81e0-50fa017fea38")
    
    # 初始化客户端 - 使用OpenAI客户端
    client = DeepSeekClient(
        api_key=api_key,
        model_name="deepseek-v3-250324",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        use_openai_client=True
    )
    
    # 测试文本生成
    prompt = "请简要分析中国股市近期趋势。"
    try:
        response = client.generate_text(prompt, temperature=0.7, max_tokens=500)
        print(f"生成的文本:\n{response}")
    except Exception as e:
        print(f"文本生成失败: {str(e)}")
    
    # 测试嵌入向量
    try:
        texts = ["中国股市", "美国股市", "日本股市"]
        embeddings = client.get_embeddings(texts)
        print(f"嵌入向量维度: {len(embeddings)}x{len(embeddings[0]) if embeddings else 0}")
    except Exception as e:
        print(f"获取嵌入向量失败: {str(e)}") 
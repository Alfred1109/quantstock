from .base_llm_client import BaseLLMClient
from typing import Dict, Any, List, Optional
import logging
import json # For parsing structured responses if needed
import random

logger = logging.getLogger(__name__) # Changed to __name__ for module-specific logger

class SimulatedLLMClient(BaseLLMClient):
    """
    模拟LLM客户端。
    返回预定义的或基于简单规则的模拟LLM响应，用于测试。
    """
    def __init__(self, config: Dict[str, Any]):
        api_key = config.get('api_key', 'simulated_api_key')
        model_name = config.get('model_name', 'simulated_model')
        base_url = config.get('base_url', None)
        super().__init__(api_key=api_key, model_name=model_name, base_url=base_url)
        self.simulated_responses = config.get('simulated_responses', {})
        logger.info("SimulatedLLMClient initialized.")

    def generate_text(self, prompt: str, **kwargs) -> str:
        """模拟生成文本。会尝试根据prompt中的关键词返回预设答案。"""
        logger.debug(f"SimulatedLLMClient received prompt (first 100 chars): {prompt[:100]}")
        # Simple keyword matching for different prompt types
        if "市场趋势分析" in prompt or "Market Trend Analysis" in prompt:
            response = {
                "trend": random.choice(["上升趋势", "下降趋势", "横盘震荡"]),
                "strength": random.randint(3, 8),
                "confidence": random.uniform(0.6, 0.95),
                "analysis": "这是一个基于模拟数据的趋势判断。",
                "suggestion": random.choice(["建议观察", "考虑逢低做多", "考虑逢高做空"])
            }
            return json.dumps(response, ensure_ascii=False)
        
        elif "入场点分析" in prompt or "Entry Point Analysis" in prompt:
            response = {
                "entry_decision": random.choice(["是", "否"]),
                "price_range": [round(random.uniform(90,100),2), round(random.uniform(101,110),2)],
                "confidence": random.randint(5,9),
                "reason": "模拟入场点分析结果。",
                "stop_loss": round(random.uniform(80,89),2),
                "take_profit": round(random.uniform(115,125),2),
                "initial_position": round(random.uniform(0.05, 0.15),3)
            }
            return json.dumps(response, ensure_ascii=False)

        elif "仓位管理建议" in prompt or "Position Sizing Advice" in prompt:
            response = {
                "action": random.choice(["add", "reduce", "maintain", "exit"]),
                "percentage": round(random.uniform(0.05, 0.2),3), # For add/reduce
                "confidence": random.uniform(0.5, 0.9),
                "reason": "模拟仓位管理建议。",
                "target_price": round(random.uniform(100,120),2),
                 'stop_loss': round(random.uniform(80,89),2)
            }
            return json.dumps(response, ensure_ascii=False)

        # Default fallback response
        return json.dumps({"response": "This is a default simulated LLM response.", "status": "simulated"})

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """模拟生成嵌入向量。"""
        logger.debug(f"SimulatedLLMClient generating embeddings for {len(texts)} texts.")
        # Return fixed-size random embeddings
        return [[random.uniform(-1, 1) for _ in range(1536)] for _ in texts] # Example dim size

    def health_check(self) -> Dict[str, Any]:
        return {"status": "ok", "client": "SimulatedLLMClient"}

    # Add a dummy stream_generate_text if BaseLLMClient expects it or if used by strategy
    def stream_generate_text(self, prompt: str, **kwargs):
        logger.debug(f"SimulatedLLMClient stream_generate_text called for prompt: {prompt[:100]}")
        # Simulate streaming by yielding parts of a generated text response
        full_response = self.generate_text(prompt, **kwargs)
        # Yield in chunks
        chunk_size = 10
        for i in range(0, len(full_response), chunk_size):
            yield {"text_chunk": full_response[i:i+chunk_size], "is_final": False}
        yield {"text_chunk": "", "is_final": True} # Signal end of stream 
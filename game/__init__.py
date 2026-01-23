"""
游戏相关webhook处理模块
支持通过 AI 分析推送内容并提取错误信息
"""

import json
from astrbot.api import logger

class GameHandler:
    """游戏Webhook处理器"""
    
    def __init__(self, context, config: dict = None):
        """初始化游戏处理器"""
        self.context = context
        self.config = config or {}
    
    async def process_game_webhook(self, payload: dict, headers: dict = None) -> dict:
        """
        处理游戏相关的Webhook推送，并调用 AI 进行分析
        
        Args:
            payload: Webhook负载数据
            headers: HTTP请求头
            
        Returns:
            处理结果字典
        """
        source = self.detect_game_source(payload, headers)
        
        # 提取基础消息
        game_name = payload.get("game_name") or payload.get("game") or "未知游戏"
        event_type = payload.get("event") or payload.get("action") or "更新"
        content = payload.get("content") or payload.get("message") or str(payload)
        
        message_text = f"🎮 游戏通知: {game_name}\n事件: {event_type}\n详情: {content}"
        
        # AI 分析逻辑
        if self.config.get("game_ai_analyze", False):
            try:
                ai_analysis = await self._analyze_with_ai(payload)
                if ai_analysis:
                    message_text += f"\n\n🤖 AI 运行分析:\n{ai_analysis}"
            except Exception as e:
                logger.error(f"AI 分析游戏推送失败: {e}")
        
        return {
            "status": "success",
            "message_text": message_text,
            "source": source,
            "game_data": payload
        }
    
    async def _analyze_with_ai(self, payload: dict) -> str:
        """使用 AstrBot LLM 分析推送内容中的错误信息"""
        max_tokens = self.config.get("game_ai_max_tokens", 150)
        
        prompt = (
            f"你是一个资深的游戏运维专家。请分析以下 Webhook 推送的 JSON 数据，"
            f"特别是检查其中是否包含任何错误、警告或运行异常。如果发现错误，请简要说明原因及可能的解决办法。"
            f"如果没有发现明显错误，请总结该条推送的核心内容。\n"
            f"要求：回答尽量简练，字数严格控制在 {max_tokens} 字以内。\n\n"
            f"数据内容：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        
        try:
            # 根据 AstrBot AI 逻辑调用 LLM
            llm = self.context.get_llm_chain()
            if not llm:
                return "未配置 AI 模型，无法分析。"
            
            # 使用 LLM 进行推理
            response = await llm.generate_response(prompt)
            result = response.completion
            
            # 截断处理 (虽然 prompt 要求了，但还是做一层兜底)
            if len(result) > max_tokens:
                result = result[:max_tokens] + "..."
                
            return result
        except Exception as e:
            logger.error(f"LLM 请求出错: {e}")
            return f"分析过程出错: {str(e)}"

    def detect_game_source(self, payload: dict, headers: dict = None) -> str:
        """
        检测游戏推送来源
        """
        if "source" in payload:
            return payload["source"]
        if headers and "user-agent" in headers:
            ua = headers["user-agent"].lower()
            if "steam" in ua: return "steam"
            if "discord" in ua: return "discord"
        return "generic_game"


__all__ = ["GameHandler"]

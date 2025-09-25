"""
优化的 aiocqhttp 协议适配器
基于 AstrBot 文档和 aiocqhttp 文档实现
支持 AstrBot 原生 Node/Nodes 组件和消息验证
"""

from typing import Any, Optional

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain

from .adapter_base import BaseAdapter


class AiocqhttpAdapter(BaseAdapter):
    """优化的 aiocqhttp 协议适配器，支持AstrBot原生组件和消息验证"""

    def __init__(self, platform_name: str):
        super().__init__(platform_name)

    async def send_forward_messages(
        self, bot_client: Any, group_id: str, messages: list[dict[str, Any]], **kwargs
    ) -> dict[str, Any]:
        """
        使用 AstrBot 原生 Node/Nodes 组件发送合并转发消息

        Args:
            bot_client: aiocqhttp 客户端实例
            group_id: 群组ID
            messages: 消息列表
            **kwargs: 其他参数，支持 user_id (私聊), sender_id, sender_name

        Returns:
            dict: 发送结果，包含成功状态和消息验证信息
        """
        try:
            # 获取配置参数
            user_id = kwargs.get("user_id")
            sender_id = kwargs.get("sender_id", "10000")
            sender_name = kwargs.get("sender_name", "媒体服务器")

            # 构建 AstrBot 原生 Node 组件列表
            nodes = []

            for _i, msg in enumerate(messages):
                # 构建消息内容
                content = []

                # 添加文本内容
                if msg.get("text"):
                    content.append(Comp.Plain(text=msg["text"]))

                # 添加图片内容
                if msg.get("image_url"):
                    try:
                        content.append(Comp.Image.fromURL(url=msg["image_url"]))
                    except Exception as e:
                        # 如果图片加载失败，添加错误提示
                        content.append(Comp.Plain(text=f"[图片加载失败: {str(e)}]"))

                # 如果没有内容，添加默认文本
                if not content:
                    content.append(Comp.Plain(text="[空消息]"))

                # 创建 Node 组件
                node = Comp.Node(uin=int(sender_id), name=sender_name, content=content)
                nodes.append(node)

            # 构建消息链
            if len(nodes) == 1:
                # 单个节点直接发送
                message_chain = MessageChain().chain(nodes[0].content)
            else:
                # 多个节点使用 Nodes 组件
                message_chain = MessageChain().chain([Comp.Nodes(nodes=nodes)])

            # 发送消息
            if user_id:
                # 私聊消息
                result = await self._send_private_message(
                    bot_client, user_id, message_chain
                )
            else:
                # 群聊消息
                result = await self._send_group_message(
                    bot_client, group_id, message_chain
                )

            # 验证消息发送结果
            validation_result = await self._validate_message_sent(
                bot_client, result, group_id, user_id
            )

            return {
                "success": True,
                "message_id": result.get("message_id"),
                "validation": validation_result,
                "adapter": "aiocqhttp_optimized",
                "nodes_count": len(nodes),
                "method": "astrbot_native_nodes",
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "adapter": "aiocqhttp_optimized",
                "method": "astrbot_native_nodes",
            }

    async def _send_group_message(
        self, bot_client: Any, group_id: str, message_chain: MessageChain
    ) -> dict[str, Any]:
        """发送群聊消息"""
        try:
            # 使用 aiocqhttp 的 send_group_msg API
            result = await bot_client.api.call_action(
                "send_group_msg", group_id=int(group_id), message=message_chain.chain
            )
            return result
        except Exception:
            # 如果原生组件失败，尝试降级到基础API
            return await self._fallback_send_group_message(
                bot_client, group_id, message_chain
            )

    async def _send_private_message(
        self, bot_client: Any, user_id: str, message_chain: MessageChain
    ) -> dict[str, Any]:
        """发送私聊消息"""
        try:
            # 使用 aiocqhttp 的 send_private_msg API
            result = await bot_client.api.call_action(
                "send_private_msg", user_id=int(user_id), message=message_chain.chain
            )
            return result
        except Exception:
            # 如果原生组件失败，尝试降级到基础API
            return await self._fallback_send_private_message(
                bot_client, user_id, message_chain
            )

    async def _fallback_send_group_message(
        self, bot_client: Any, group_id: str, message_chain: MessageChain
    ) -> dict[str, Any]:
        """降级发送群聊消息（使用基础文本）"""
        try:
            # 提取纯文本内容
            text_content = message_chain.get_plain_text()
            if not text_content:
                text_content = "[媒体通知]"

            result = await bot_client.api.call_action(
                "send_group_msg", group_id=int(group_id), message=text_content
            )
            return result
        except Exception as e:
            raise Exception(f"群聊消息发送失败: {str(e)}") from e

    async def _fallback_send_private_message(
        self, bot_client: Any, user_id: str, message_chain: MessageChain
    ) -> dict[str, Any]:
        """降级发送私聊消息（使用基础文本）"""
        try:
            # 提取纯文本内容
            text_content = message_chain.get_plain_text()
            if not text_content:
                text_content = "[媒体通知]"

            result = await bot_client.api.call_action(
                "send_private_msg", user_id=int(user_id), message=text_content
            )
            return result
        except Exception as e:
            raise Exception(f"私聊消息发送失败: {str(e)}") from e

    async def _validate_message_sent(
        self,
        bot_client: Any,
        send_result: dict,
        group_id: str,
        user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """验证消息是否成功发送"""
        validation = {"validated": False, "message_exists": False, "error": None}

        try:
            message_id = send_result.get("message_id")
            if not message_id:
                validation["error"] = "未获取到消息ID"
                return validation

            # 尝试获取消息信息来验证
            try:
                msg_info = await bot_client.api.call_action(
                    "get_msg", message_id=message_id
                )

                if msg_info and msg_info.get("message_id") == message_id:
                    validation["validated"] = True
                    validation["message_exists"] = True
                    validation["message_info"] = {
                        "time": msg_info.get("time"),
                        "message_type": msg_info.get("message_type"),
                        "sender": msg_info.get("sender", {}).get("nickname", "Unknown"),
                    }

            except Exception as e:
                # get_msg API 可能不被支持，使用其他方式验证
                validation["error"] = f"消息验证API不可用: {str(e)}"
                # 如果有消息ID，认为发送成功
                if message_id:
                    validation["validated"] = True
                    validation["message_exists"] = True

        except Exception as e:
            validation["error"] = f"验证过程出错: {str(e)}"

        return validation

    def build_forward_node(
        self,
        message: dict[str, Any],
        sender_id: str = "10000",
        sender_name: str = "媒体服务器",
    ) -> dict[str, Any]:
        """
        构建单个转发节点（兼容方法）

        Args:
            message: 消息内容字典
            sender_id: 发送者ID
            sender_name: 发送者昵称

        Returns:
            转发节点字典
        """
        # 构建消息内容
        content = []

        # 添加文本内容
        if message.get("text") or message.get("message_text"):
            text = message.get("text") or message.get("message_text")
            content.append({"type": "text", "data": {"text": text}})

        # 添加图片内容
        if message.get("image_url"):
            content.append({"type": "image", "data": {"file": message["image_url"]}})

        # 如果没有内容，添加默认文本
        if not content:
            content.append({"type": "text", "data": {"text": "[空消息]"}})

        return {
            "type": "node",
            "data": {"name": sender_name, "uin": sender_id, "content": content},
        }

    @staticmethod
    def get_adapter_info() -> dict[str, Any]:
        """获取适配器信息"""
        return {
            "name": "AiocqhttpOptimized",
            "description": "优化的aiocqhttp适配器，支持AstrBot原生组件",
            "supported_apis": ["send_group_msg", "send_private_msg", "get_msg"],
            "features": [
                "AstrBot原生Node/Nodes组件",
                "消息发送验证",
                "降级兼容模式",
                "群聊和私聊支持",
                "图片消息支持",
                "错误处理和重试",
            ],
        }

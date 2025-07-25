"""
Ani-RSS 处理模块
提供 Ani-RSS 数据检测、解析和处理功能
"""

import json
from typing import Optional

from astrbot.api import logger


class AniRSSHandler:
    """Ani-RSS 处理器"""

    def __init__(self):
        # Ani-RSS 模板变量列表
        self.ani_rss_template_patterns = [
            "${emoji}",
            "${action}",
            "${title}",
            "${score}",
            "${tmdburl}",
            "${themoviedbName}",
            "${bgmUrl}",
            "${season}",
            "${episode}",
            "${subgroup}",
            "${currentEpisodeNumber}",
            "${totalEpisodeNumber}",
            "${year}",
            "${month}",
            "${date}",
            "${text}",
            "${downloadPath}",
            "${episodeTitle}",
        ]

    def try_fix_ani_rss_json(self, body_text: str) -> str:
        """尝试修复不完整的 ani-rss JSON"""
        try:
            # 检查是否包含 ani-rss 特征
            if "meassage" not in body_text:
                return ""

            # 尝试修复常见的不完整 JSON 问题
            fixed_text = body_text.strip()

            # 计算需要的闭合括号数量
            open_braces = fixed_text.count("{")
            close_braces = fixed_text.count("}")
            open_brackets = fixed_text.count("[")
            close_brackets = fixed_text.count("]")

            # 添加缺失的闭合括号
            if open_braces > close_braces:
                fixed_text += "}" * (open_braces - close_braces)
            if open_brackets > close_brackets:
                fixed_text += "]" * (open_brackets - close_brackets)

            # 验证修复后的 JSON
            json.loads(fixed_text)
            logger.info("成功修复 ani-rss JSON")
            return fixed_text

        except Exception as e:
            logger.debug(f"修复 ani-rss JSON 失败: {e}")
            return ""

    def is_ani_rss_text_template(self, text: str) -> bool:
        """检查是否为 ani-rss 文本模板"""
        # 检查是否包含至少一个模板变量
        return any(pattern in text for pattern in self.ani_rss_template_patterns)

    def detect_ani_rss_format(self, body_text: str) -> tuple[bool, Optional[dict], str]:
        """
        检测 Ani-RSS 格式
        返回: (是否为 Ani-RSS, 解析后的数据, 格式类型)
        """
        try:
            # 尝试解析 JSON
            try:
                raw_data = json.loads(body_text)
                is_text_template = False
                logger.debug("成功解析为 JSON 格式")
            except json.JSONDecodeError as e:
                logger.debug(f"JSON 解析失败: {e}")

                # 尝试修复不完整的 ani-rss JSON
                fixed_json = self.try_fix_ani_rss_json(body_text)
                if fixed_json:
                    try:
                        raw_data = json.loads(fixed_json)
                        is_text_template = False
                        logger.info("成功修复并解析 ani-rss 不完整 JSON")
                    except json.JSONDecodeError:
                        fixed_json = None

                if not fixed_json:
                    # 检查是否为 Ani-RSS 文本模板
                    if self.is_ani_rss_text_template(body_text):
                        raw_data = {"text_template": body_text}
                        is_text_template = True
                        logger.info("检测到 ani-rss 文本模板格式")
                        return True, raw_data, "text_template"
                    return False, None, "unknown"

            # 检查是否为 Ani-RSS 数据
            if self.is_ani_rss_data(raw_data):
                format_type = "text_template" if is_text_template else "message"
                return True, raw_data, format_type
            return False, None, "not_ani_rss"

        except Exception as e:
            logger.error(f"Ani-RSS 格式检测失败: {e}")
            return False, None, "error"

    def is_ani_rss_data(self, data: dict) -> bool:
        """判断是否为 Ani-RSS 数据"""
        return "meassage" in data or "text_template" in data

    def extract_ani_rss_content(self, data: dict) -> dict:
        """提取 Ani-RSS 的内容（包括图片和文本）"""
        try:
            result = {"text": "", "image_url": ""}

            # 检查是否为 Ani-RSS 真实消息格式
            if "meassage" in data:
                messages = data.get("meassage", [])
                for msg in messages:
                    if isinstance(msg, dict):
                        msg_type = msg.get("type", "")
                        msg_data = msg.get("data", {})

                        if msg_type == "text":
                            result["text"] = msg_data.get("text", "")
                        elif msg_type == "image":
                            # 修复图片 URL 提取
                            image_url = msg_data.get("url", "") or msg_data.get(
                                "file", ""
                            )
                            if image_url:
                                result["image_url"] = image_url
                                logger.debug(f"提取到 Ani-RSS 图片: {image_url}")

            # 检查是否为文本模板格式
            elif "text_template" in data:
                result["text"] = data.get("text_template", "")

            # 验证提取结果
            if result["text"]:
                logger.info(
                    f"成功提取 Ani-RSS 内容: 文本长度={len(result['text'])}, 图片={'有' if result['image_url'] else '无'}"
                )
            else:
                logger.warning("Ani-RSS 内容提取失败: 未找到文本内容")

            return result

        except Exception as e:
            logger.error(f"提取 Ani-RSS 内容失败: {e}")
            return {"text": "", "image_url": ""}

    def generate_ani_rss_raw_message(self, data: dict) -> str:
        """为 Ani-RSS 生成原始格式消息（仅返回文本部分）"""
        content = self.extract_ani_rss_content(data)
        text = content["text"]

        if not text:
            logger.warning("Ani-RSS 消息文本为空，使用默认消息")
            return "来自 Ani-RSS 的通知"

        return text

    def process_ani_rss_data(self, data: dict, format_type: str) -> dict:
        """
        处理 Ani-RSS 数据，返回标准化的消息载荷
        """
        try:
            # 提取内容
            content = self.extract_ani_rss_content(data)

            # 生成消息文本
            message_text = content["text"] if content["text"] else "来自 Ani-RSS 的通知"

            # 获取图片 URL
            image_url = content["image_url"]

            # 创建消息载荷
            message_payload = {
                "image_url": image_url,
                "message_text": message_text,
                "source": "ani-rss",
                "format_type": format_type,
                "raw_data": data,
            }

            logger.info(
                f"Ani-RSS 数据处理完成: 格式={format_type}, 图片={'有' if image_url else '无'}"
            )

            return message_payload

        except Exception as e:
            logger.error(f"Ani-RSS 数据处理失败: {e}")
            return {
                "image_url": "",
                "message_text": "Ani-RSS 数据处理失败",
                "source": "ani-rss",
                "format_type": "error",
                "raw_data": data,
            }

    def validate_ani_rss_message(self, message_payload: dict) -> bool:
        """验证 Ani-RSS 消息载荷"""
        try:
            # 检查必要字段
            required_fields = ["message_text", "source"]
            for field in required_fields:
                if field not in message_payload:
                    logger.error(f"Ani-RSS 消息载荷缺少必要字段: {field}")
                    return False

            # 检查消息文本
            if not message_payload["message_text"].strip():
                logger.error("Ani-RSS 消息文本为空")
                return False

            # 检查来源
            if message_payload["source"] != "ani-rss":
                logger.error(f"Ani-RSS 消息来源错误: {message_payload['source']}")
                return False

            return True

        except Exception as e:
            logger.error(f"Ani-RSS 消息验证失败: {e}")
            return False

    def get_debug_info(self, data: dict) -> dict:
        """获取调试信息"""
        try:
            debug_info = {
                "is_ani_rss": self.is_ani_rss_data(data),
                "has_meassage": "meassage" in data,
                "has_text_template": "text_template" in data,
                "data_keys": list(data.keys()) if isinstance(data, dict) else [],
            }

            if "meassage" in data:
                messages = data.get("meassage", [])
                debug_info["message_count"] = len(messages)
                debug_info["message_types"] = []

                for msg in messages:
                    if isinstance(msg, dict):
                        msg_type = msg.get("type", "unknown")
                        debug_info["message_types"].append(msg_type)

            return debug_info

        except Exception as e:
            logger.error(f"获取 Ani-RSS 调试信息失败: {e}")
            return {"error": str(e)}

    def extract_image_from_message(self, msg_data: dict) -> str:
        """从消息数据中提取图片 URL"""
        try:
            # 尝试多种可能的图片字段
            image_fields = ["url", "file", "path", "src", "image", "picture"]

            for field in image_fields:
                if msg_data.get(field):
                    image_url = str(msg_data[field]).strip()
                    if image_url:
                        logger.debug(f"从字段 '{field}' 提取到图片: {image_url}")
                        return image_url

            logger.debug("未找到图片 URL")
            return ""

        except Exception as e:
            logger.error(f"提取图片 URL 失败: {e}")
            return ""

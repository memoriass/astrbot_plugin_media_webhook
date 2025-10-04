import asyncio
import hashlib
import json
import time

from aiohttp import web
from aiohttp.web import Request, Response

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

from .adapters import AdapterFactory
from .media_handler import MediaHandler
from .processors import AniRSSHandler

# 常量定义
DEFAULT_SENDER_ID = "2659908767"
DEFAULT_SENDER_NAME = "媒体通知"
DEFAULT_WEBHOOK_PORT = 60071
DEFAULT_BATCH_MIN_SIZE = 3
DEFAULT_CACHE_TTL = 300
DEFAULT_BATCH_INTERVAL = 300


@register(
    "media_webhook",
    "Assistant",
    "媒体通知 Webhook 插件",
    "2.0.0",
    "https://github.com/example/astrbot_plugin_media_webhook",
)
class MediaWebhookPlugin(Star):
    """媒体通知 Webhook 插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # 核心配置
        self.webhook_port = config.get("webhook_port", DEFAULT_WEBHOOK_PORT)
        self.group_id = config.get("group_id", "")
        self.platform_name = config.get("platform_name", "auto")
        self.batch_min_size = config.get("batch_min_size", DEFAULT_BATCH_MIN_SIZE)
        self.batch_interval_seconds = config.get(
            "batch_interval_seconds", DEFAULT_BATCH_INTERVAL
        )
        self.cache_ttl_seconds = config.get("cache_ttl_seconds", DEFAULT_CACHE_TTL)

        # 适配器配置
        self.sender_id = config.get("sender_id", DEFAULT_SENDER_ID)
        self.sender_name = config.get("sender_name", DEFAULT_SENDER_NAME)

        # API 配置
        self.tmdb_api_key = config.get("tmdb_api_key", "")
        self.fanart_api_key = config.get("fanart_api_key", "")

        # 初始化子模块
        self.ani_rss_handler = AniRSSHandler()
        self.media_handler = MediaHandler(self.tmdb_api_key, self.fanart_api_key)

        # 打印工作正常的子模块
        working_modules = []

        # 检查 Ani-RSS 处理器
        if self.ani_rss_handler:
            working_modules.append("Ani-RSS 处理器")

        # 检查媒体处理器
        if self.media_handler:
            tmdb_status = "TMDB: 已启用" if self.tmdb_api_key else "TMDB: 未配置"
            fanart_status = "Fanart: 已启用" if self.fanart_api_key else "Fanart: 未配置"
            working_modules.append(f"媒体处理器 ({tmdb_status}, {fanart_status})")

            # 详细日志
            if self.tmdb_api_key:
                logger.info(f"[OK] TMDB API 密钥已配置: {self.tmdb_api_key[:8]}...")
            else:
                logger.warning("[WARN] TMDB API 密钥未配置，将使用媒体服务器原始图片")

        logger.info("媒体 Webhook 插件子模块初始化完成:")
        for module in working_modules:
            logger.info(f"  [OK] {module}: 工作正常")

        # 消息队列和缓存
        self.message_queue: list[dict] = []
        self.request_cache: dict[str, float] = {}
        self.last_batch_time = time.time()

        # 媒体类型映射
        self.media_type_map = {
            "Movie": "电影",
            "Series": "剧集",
            "Season": "剧季",
            "Episode": "剧集",
            "Album": "专辑",
            "Song": "歌曲",
            "Video": "视频",
        }

        self.type_emoji_map = {
            "Movie": "🎬",
            "Series": "📺",
            "Season": "📺",
            "Episode": "📺",
            "Album": "🎵",
            "Song": "🎶",
            "Video": "📹",
            "Default": "🌟",
        }

        # HTTP 服务器
        self.app = None
        self.runner = None
        self.site = None

        # 启动服务
        asyncio.create_task(self.start_webhook_server())
        asyncio.create_task(self.start_batch_processor())

    async def start_webhook_server(self):
        """启动 Webhook 服务器"""
        try:
            self.app = web.Application()
            self.app.router.add_post("/media-webhook", self.handle_webhook)

            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, "0.0.0.0", self.webhook_port)
            await self.site.start()

            logger.info(f"Media Webhook 服务已启动，监听端口: {self.webhook_port}")

        except Exception as e:
            logger.error(f"启动 Webhook 服务失败: {e}")

    async def handle_webhook(self, request: Request) -> Response:
        """处理 Webhook 请求"""
        try:
            # 解析请求体
            body_text = await request.text()
            if not body_text:
                return Response(text="请求体为空", status=400)

            # 记录请求信息
            headers = dict(request.headers)
            logger.info("收到 Webhook 请求:")
            logger.info(f"  User-Agent: {headers.get('user-agent', 'N/A')}")
            logger.info(f"  Content-Type: {headers.get('content-type', 'N/A')}")
            logger.info(f"  请求体长度: {len(body_text)} 字符")

            # 调试：打印原始数据的关键字段
            try:
                data_preview = json.loads(body_text)
                logger.debug(f"原始数据键: {list(data_preview.keys())}")
                if "Item" in data_preview:
                    item = data_preview["Item"]
                    logger.debug(f"Item键: {list(item.keys())}")
                    logger.debug(f"ImageTags: {item.get('ImageTags', {})}")
                    logger.debug(f"Server: {data_preview.get('Server', {})}")
            except Exception:
                pass

            # 将所有数据交由批量处理器检测和处理
            await self.add_raw_data_to_queue(body_text, headers)
            return Response(text="数据已加入队列", status=200)

        except Exception as e:
            logger.error(f"Webhook 处理出错: {e}")
            return Response(text="处理消息时发生内部错误", status=500)

    def is_duplicate_request(self, media_data: dict) -> bool:
        """检查是否为重复请求 - 使用哈希校验，排除图片以保持更高准确率"""
        request_hash = self.calculate_request_hash(media_data)
        if not request_hash:
            return False

        current_time = time.time()

        # 清理过期缓存
        self.cleanup_expired_cache(current_time)

        # 检查是否重复
        if request_hash in self.request_cache:
            cached_time = self.request_cache[request_hash]
            logger.debug(
                f"检测到重复请求，哈希: {request_hash[:8]}..., 缓存时间: {cached_time}"
            )
            return True

        # 缓存新请求
        self.request_cache[request_hash] = current_time + self.cache_ttl_seconds
        logger.debug(
            f"缓存新请求，哈希: {request_hash[:8]}..., 过期时间: {current_time + self.cache_ttl_seconds}"
        )
        return False

    def calculate_request_hash(self, media_data: dict) -> str:
        """计算请求哈希值 - 排除图片和不稳定字段以提高准确率"""
        try:
            # 根据数据来源选择不同的哈希策略
            if self.is_ani_rss_data(media_data):
                return self.calculate_ani_rss_hash(media_data)
            return self.calculate_standard_hash(media_data)
        except Exception as e:
            logger.error(f"计算请求哈希失败: {e}")
            return ""

    def is_ani_rss_data(self, media_data: dict) -> bool:
        """判断是否为 Ani-RSS 数据"""
        return "meassage" in media_data or "text_template" in media_data

    def calculate_ani_rss_hash(self, media_data: dict) -> str:
        """计算 Ani-RSS 数据的哈希值"""
        # 对于 Ani-RSS，提取关键信息进行哈希
        if "meassage" in media_data:
            messages = media_data.get("meassage", [])
            text_content = ""
            for msg in messages:
                if isinstance(msg, dict) and msg.get("type") == "text":
                    text_data = msg.get("data", {})
                    text_content = text_data.get("text", "")
                    break

            # 从文本中提取关键信息
            hash_data = {
                "content_hash": hashlib.md5(text_content.encode()).hexdigest()[:16],
                "data_type": "ani_rss_message",
            }
        elif "text_template" in media_data:
            template = media_data.get("text_template", "")
            hash_data = {
                "content_hash": hashlib.md5(template.encode()).hexdigest()[:16],
                "data_type": "ani_rss_template",
            }
        else:
            hash_data = {"data_type": "ani_rss_unknown"}

        hash_string = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(hash_string.encode()).hexdigest()

    def calculate_standard_hash(self, media_data: dict) -> str:
        """计算标准媒体数据的哈希值"""
        # 排除不稳定字段
        stable_fields = {
            k: v
            for k, v in media_data.items()
            if k not in ["image_url", "timestamp", "runtime_ticks"]
        }
        hash_string = json.dumps(stable_fields, sort_keys=True)
        return hashlib.sha256(hash_string.encode()).hexdigest()

    def cleanup_expired_cache(self, current_time: float):
        """清理过期缓存"""
        expired_keys = [
            key
            for key, expire_time in self.request_cache.items()
            if current_time > expire_time
        ]
        for key in expired_keys:
            del self.request_cache[key]

        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 个过期缓存条目")

    async def add_to_queue(self, message_payload: dict):
        """添加标准媒体消息到队列"""
        try:
            # 标记为标准媒体消息，使用批量发送逻辑
            message_payload["message_type"] = "media"

            # 添加时间戳（如果没有）
            if "timestamp" not in message_payload:
                message_payload["timestamp"] = time.time()

            # 添加到队列
            self.message_queue.append(message_payload)

            # 记录日志
            source = message_payload.get("source", "unknown")
            has_image = bool(message_payload.get("image_url"))
            logger.info(
                f"消息已加入队列 [来源: {source}] {'(含图片)' if has_image else '(无图片)'}"
            )

        except Exception as e:
            logger.error(f"添加消息到队列失败: {e}")

    async def add_raw_data_to_queue(self, body_text: str, headers: dict):
        """添加原始数据到队列，由批量处理器检测和处理"""
        try:
            # 创建原始数据载荷
            raw_payload = {
                "raw_data": body_text,
                "headers": headers,
                "timestamp": time.time(),
                "message_type": "raw",  # 标记为原始数据，需要检测
            }

            # 添加到队列
            self.message_queue.append(raw_payload)

            logger.info("原始数据已加入队列，等待批量处理器检测")

        except Exception as e:
            logger.error(f"添加原始数据到队列失败: {e}")

    async def add_ani_rss_to_queue(self, message_payload: dict):
        """添加 Ani-RSS 消息到队列（标记为独立发送）"""
        try:
            # 标记为 ani-rss 消息，使用独立发送逻辑
            message_payload["message_type"] = "ani-rss"

            # 添加时间戳
            message_payload["timestamp"] = time.time()

            # 添加到队列
            self.message_queue.append(message_payload)

            # 记录日志
            has_image = bool(message_payload.get("image_url"))
            format_type = message_payload.get("format_type", "unknown")
            logger.info(
                f"Ani-RSS 消息已加入队列 [格式: {format_type}] {'(含图片)' if has_image else '(无图片)'}"
            )

        except Exception as e:
            logger.error(f"添加 Ani-RSS 消息到队列失败: {e}")

    async def send_ani_rss_message_directly(self, message_payload: dict):
        """直接发送 Ani-RSS 消息（独立处理，不进入批量处理器）"""
        try:
            group_id = str(self.group_id).replace(":", "_")
            unified_msg_origin = (
                f"{self.get_effective_platform_name()}:GroupMessage:{group_id}"
            )

            # 记录日志
            has_image = bool(message_payload.get("image_url"))
            format_type = message_payload.get("format_type", "unknown")
            logger.info(
                f"直接发送 Ani-RSS 消息 [格式: {format_type}] {'(含图片)' if has_image else '(无图片)'}"
            )

            content_list = []

            # 添加图片（如果有）
            if message_payload.get("image_url"):
                content_list.append(Comp.Image.fromURL(message_payload["image_url"]))

            # 添加文本
            content_list.append(Comp.Plain(message_payload["message_text"]))

            # 创建消息链
            message_chain = MessageChain(content_list)

            # 直接发送消息
            await self.context.send_message(unified_msg_origin, message_chain)
            logger.info("✅ Ani-RSS 消息发送成功")

        except Exception as e:
            logger.error(f"❌ Ani-RSS 消息发送失败: {e}")
            logger.debug(f"Ani-RSS 发送失败详情: {e}", exc_info=True)

    async def send_ani_rss_message_individually(self, message_payload: dict):
        """在批量处理器中独立发送单条 Ani-RSS 消息"""
        try:
            group_id = str(self.group_id).replace(":", "_")
            unified_msg_origin = (
                f"{self.get_effective_platform_name()}:GroupMessage:{group_id}"
            )

            # 记录日志
            has_image = bool(message_payload.get("image_url"))
            format_type = message_payload.get("format_type", "unknown")
            logger.debug(
                f"独立发送 Ani-RSS 消息 [格式: {format_type}] {'(含图片)' if has_image else '(无图片)'}"
            )

            content_list = []

            # 添加图片（如果有）
            if message_payload.get("image_url"):
                content_list.append(Comp.Image.fromURL(message_payload["image_url"]))

            # 添加文本
            content_list.append(Comp.Plain(message_payload["message_text"]))

            # 创建消息链
            message_chain = MessageChain(content_list)

            # 发送消息
            await self.context.send_message(unified_msg_origin, message_chain)
            logger.debug("✅ Ani-RSS 消息发送成功")

        except Exception as e:
            logger.error(f"❌ Ani-RSS 消息发送失败: {e}")
            logger.debug(f"Ani-RSS 发送失败详情: {e}", exc_info=True)

    async def detect_and_process_raw_data(self, raw_msg: dict) -> dict:
        """检测和处理原始数据"""
        try:
            body_text = raw_msg.get("raw_data", "")
            headers = raw_msg.get("headers", {})

            # 首先检测是否为 Ani-RSS 格式
            is_ani_rss, ani_rss_data, format_type = (
                self.ani_rss_handler.detect_ani_rss_format(body_text)
            )

            if is_ani_rss:
                logger.info(f"检测到 Ani-RSS 数据，格式类型: {format_type}")

                # 处理 Ani-RSS 数据
                message_payload = self.ani_rss_handler.process_ani_rss_data(
                    ani_rss_data, format_type
                )

                # 验证消息载荷
                if not self.ani_rss_handler.validate_ani_rss_message(message_payload):
                    logger.error("Ani-RSS 消息验证失败")
                    return None

                # 检查重复请求
                if self.is_duplicate_request(ani_rss_data):
                    logger.info("检测到重复的 Ani-RSS 请求，忽略")
                    return None

                # 标记为 ani-rss 消息
                message_payload["message_type"] = "ani-rss"
                return message_payload

            # 处理标准媒体数据
            try:
                raw_data = json.loads(body_text)
                logger.info("检测为标准媒体数据")
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失败: {e}")
                return None

            # 检测媒体来源
            detected_source = self.media_handler.detect_media_source(raw_data, headers)
            if not detected_source:
                logger.warning("未识别的媒体数据格式")
                return None

            logger.info(f"检测到媒体来源: {detected_source}")

            # 使用媒体处理器处理数据
            media_data = await self.media_handler.process_media_data(
                raw_data, detected_source, headers
            )

            # 验证处理结果
            if not self.media_handler.validate_media_data(
                media_data.get("media_data", {})
            ):
                logger.error("媒体数据验证失败")
                return None

            # 检查重复请求
            if self.is_duplicate_request(media_data):
                logger.info("检测到重复请求，忽略")
                return None

            # 标记为媒体消息
            media_data["message_type"] = "media"
            return media_data

        except Exception as e:
            logger.error(f"原始数据检测和处理失败: {e}")
            return None

    async def send_media_messages_intelligently(self, media_messages: list):
        """智能发送标准媒体消息（根据协议端选择最优发送模式）"""
        try:
            effective_platform = self.get_effective_platform_name()
            message_count = len(media_messages)

            logger.info(
                f"智能发送 {message_count} 条媒体消息 [平台: {effective_platform}]"
            )

            # 根据消息数量选择发送模式（所有协议端统一使用 AstrBot pipeline）
            if message_count >= self.batch_min_size:
                logger.info(f"使用 {effective_platform} 批量发送模式（合并转发）")
                await self.send_batch_messages(media_messages)
            else:
                logger.info(f"使用 {effective_platform} 单独发送模式")
                await self.send_individual_messages(media_messages)

        except Exception as e:
            logger.error(f"智能发送媒体消息失败: {e}")

    async def start_batch_processor(self):
        """启动批量处理器（智能检测和发送所有消息类型）"""
        logger.info("[OK] 批量处理器: 工作正常")
        while True:
            try:
                await asyncio.sleep(self.batch_interval_seconds)
                await self.process_message_queue()
            except Exception as e:
                logger.error(f"批量处理器出错: {e}")
                await asyncio.sleep(10)

    async def process_message_queue(self):
        """处理消息队列（根据消息类型使用不同发送逻辑）"""
        if not self.message_queue:
            return

        if not self.group_id:
            logger.warning("未配置群组ID，无法发送消息")
            return

        messages = self.message_queue.copy()
        self.message_queue.clear()

        logger.info(f"从队列中取出 {len(messages)} 条待发消息")

        try:
            # 分离不同类型的消息
            raw_data_messages = []
            ani_rss_messages = []
            media_messages = []

            for msg in messages:
                msg_type = msg.get("message_type", "media")
                if msg_type == "raw":
                    raw_data_messages.append(msg)
                elif msg_type == "ani-rss":
                    ani_rss_messages.append(msg)
                else:
                    media_messages.append(msg)

            # 处理原始数据（检测和转换）
            if raw_data_messages:
                logger.info(f"检测和处理 {len(raw_data_messages)} 条原始数据")
                for raw_msg in raw_data_messages:
                    processed_msg = await self.detect_and_process_raw_data(raw_msg)
                    if processed_msg:
                        # 根据检测结果分类
                        if processed_msg.get("message_type") == "ani-rss":
                            ani_rss_messages.append(processed_msg)
                        else:
                            media_messages.append(processed_msg)

            # 处理 Ani-RSS 消息（独立发送）
            if ani_rss_messages:
                logger.info(f"处理 {len(ani_rss_messages)} 条 Ani-RSS 消息（独立发送）")
                for msg in ani_rss_messages:
                    await self.send_ani_rss_message_individually(msg)

            # 处理标准媒体消息（智能发送）
            if media_messages:
                logger.info(f"处理 {len(media_messages)} 条标准媒体消息（智能发送）")
                await self.send_media_messages_intelligently(media_messages)

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
        finally:
            self.last_batch_time = time.time()

    async def send_batch_messages(self, messages: list[dict]):
        """发送合并转发消息（使用 AstrBot pipeline）"""
        group_id = str(self.group_id).replace(":", "_")

        logger.info(f"发送合并转发: {len(messages)} 条消息 [使用 LLOneBot 兼容模式]")

        try:
            # 使用自定义节点构建，避免 LLOneBot 的 base64 图片 bug
            # LLOneBot 在处理合并转发中的 base64 图片时会报错：
            # "Cannot read properties of undefined (reading 'result')"
            # 解决方案：直接构建使用 URL 的节点字典，绕过 AstrBot 的 base64 转换

            nodes_data = []
            for i, msg in enumerate(messages, 1):
                # 调试：打印消息数据结构
                logger.debug(f"  消息 {i} 数据键: {list(msg.keys())}")

                # 构建节点内容 - 使用CQ码字符串格式（LLOneBot兼容）
                content_parts = []

                # 添加图片（如果有）- 使用 CQ 码格式
                image_url = msg.get("image_url")
                if image_url:
                    logger.info(f"  消息 {i}: 添加图片")
                    logger.info(f"    图片URL: {image_url}")
                    logger.info(f"    URL类型: {'TMDB' if 'tmdb.org' in image_url else 'Fanart' if 'fanart.tv' in image_url else 'Emby/Jellyfin' if '/Items/' in image_url else '其他'}")
                    # 使用CQ码格式
                    content_parts.append(f"[CQ:image,file={image_url}]")
                else:
                    logger.warning(f"  消息 {i}: [WARN] 无图片URL")
                    # 检查media_data中是否有图片信息
                    media_data = msg.get("media_data", {})
                    if media_data:
                        alt_image_url = media_data.get("image_url")
                        logger.debug(f"    media_data中的image_url: {alt_image_url}")
                        tmdb_enriched = media_data.get("tmdb_enriched", False)
                        logger.debug(f"    TMDB丰富状态: {tmdb_enriched}")

                # 添加文本
                message_text = msg["message_text"]
                logger.info(f"  消息 {i}: 添加文本 (长度={len(message_text)})")
                content_parts.append(message_text)

                # 合并为CQ码字符串
                content_str = "".join(content_parts)

                # 构建节点 - content使用字符串格式
                node_data = {
                    "type": "node",
                    "data": {
                        "name": self.sender_name,
                        "uin": str(self.sender_id),
                        "content": content_str
                    }
                }
                logger.info(f"  消息 {i}: 节点创建完成，content长度={len(content_str)}")
                nodes_data.append(node_data)

            # 直接调用协议端 API，绕过 AstrBot 的消息组件转换
            platform = self.context.get_platform_inst(self.get_effective_platform_name())
            if platform:
                bot = platform.get_client()
                if bot is None:
                    raise Exception("Bot 客户端未连接")

                payload = {
                    "group_id": int(group_id),
                    "messages": nodes_data
                }
                logger.debug(f"发送合并转发 payload: {payload}")
                await bot.call_action("send_group_forward_msg", **payload)
                logger.info("[OK] 合并转发发送成功 [LLOneBot 兼容模式]")
            else:
                raise Exception(f"未找到平台: {self.get_effective_platform_name()}")

        except Exception as e:
            logger.error(f"发送合并转发失败: {e}")
            logger.debug(f"合并转发失败详情: {e}", exc_info=True)
            # 回退到单独发送
            logger.info("回退到单独发送模式")
            await self.send_individual_messages(messages)

    async def send_individual_messages(self, messages: list[dict]):
        """发送单独消息"""
        group_id = str(self.group_id).replace(":", "_")
        unified_msg_origin = (
            f"{self.get_effective_platform_name()}:GroupMessage:{group_id}"
        )

        logger.info(f"发送单独消息: {len(messages)} 条消息")
        logger.info(f"目标群组ID: {group_id}")
        logger.info(f"统一消息来源: {unified_msg_origin}")

        for i, msg in enumerate(messages, 1):
            try:
                content_list = []

                # 添加图片
                if msg.get("image_url"):
                    content_list.append(Comp.Image.fromURL(msg["image_url"]))

                # 添加文本
                content_list.append(Comp.Plain(msg["message_text"]))

                # 创建消息链
                message_chain = MessageChain(content_list)

                logger.info(f"准备发送消息 {i}: {msg.get('message_text', '')[:50]}...")
                await self.context.send_message(unified_msg_origin, message_chain)
                logger.info(f"✅ 消息 {i}/{len(messages)} 发送成功")

                # 添加延迟避免频率限制
                if i < len(messages):
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"❌ 消息 {i} 发送失败: {e}")
                logger.error(f"错误详情: {e}", exc_info=True)

    @filter.command("webhook status")
    async def webhook_status(self, event: AstrMessageEvent):
        """查看 Webhook 状态"""
        queue_size = len(self.message_queue)
        cache_size = len(self.request_cache)

        # 获取子模块状态
        media_stats = self.media_handler.get_processing_stats()

        # 获取适配器信息
        try:
            adapter = AdapterFactory.create_adapter(self.get_effective_platform_name())
            adapter_info = adapter.get_adapter_info()
            adapter_name = adapter_info.get("name", "Unknown")
            adapter_features = ", ".join(adapter_info.get("features", []))
        except Exception as e:
            adapter_name = f"Error: {str(e)}"
            adapter_features = "N/A"

        status_text = f"""📊 Media Webhook 状态

🌐 服务状态: {"运行中" if self.site else "未启动"}
📡 监听端口: {self.webhook_port}
📋 队列消息: {queue_size} 条
🗂️ 缓存条目: {cache_size} 条
⚙️ 批量阈值: {self.batch_min_size} 条
⏱️ 批量间隔: {self.batch_interval_seconds} 秒
🎯 目标群组: {self.group_id or "未配置"}
🤖 协议平台: {self.platform_name} {"(自动检测: " + self.get_effective_platform_name() + ")" if self.platform_name == "auto" else ""}

🔧 适配器状态:
  📡 当前适配器: {adapter_name}
  🎛️ 配置类型: 自动推断
  👤 发送者: {self.sender_name} ({self.sender_id})
  ✨ 支持功能: {adapter_features}

📂 子模块状态:
  🎬 媒体处理器: 已启用
    - TMDB 丰富: {"启用" if media_stats.get("tmdb_enabled") else "禁用"}
    - 支持来源: {", ".join(media_stats.get("supported_sources", []))}
    - TMDB 缓存: {media_stats.get("cache_size", 0)} 条
  📺 Ani-RSS 处理器: 已启用"""

        yield event.plain_result(status_text)

    async def terminate(self):
        """插件卸载时的清理工作"""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            logger.info("Media Webhook 服务已停止")
        except Exception as e:
            logger.error(f"停止 Webhook 服务时出错: {e}")

    def get_available_platforms(self) -> list[dict]:
        """获取当前可用的平台列表"""
        platforms = []
        for platform_inst in self.context.platform_manager.platform_insts:
            platform_meta = platform_inst.meta()
            platforms.append(
                {
                    "id": platform_meta.id,
                    "name": platform_meta.name,
                    "description": platform_meta.description,
                }
            )
        return platforms

    def auto_detect_platform(self) -> str:
        """自动检测最合适的平台"""
        available_platforms = self.get_available_platforms()

        if not available_platforms:
            logger.warning("未找到任何可用平台，使用默认值 llonebot")
            return "llonebot"

        # 优先级顺序：llonebot > napcat > aiocqhttp > 其他
        priority_order = ["llonebot", "napcat", "aiocqhttp"]

        # 按优先级查找
        for priority_name in priority_order:
            for platform in available_platforms:
                if (
                    priority_name in platform["name"].lower()
                    or priority_name in platform["id"].lower()
                ):
                    logger.info(
                        f"自动检测到平台: {platform['id']} ({platform['name']})"
                    )
                    return platform["id"]

        # 如果没有找到优先级平台，使用第一个可用平台
        first_platform = available_platforms[0]
        logger.info(
            f"使用第一个可用平台: {first_platform['id']} ({first_platform['name']})"
        )
        return first_platform["id"]

    def get_effective_platform_name(self) -> str:
        """获取有效的平台名称（处理auto模式）"""
        if self.platform_name == "auto":
            return self.auto_detect_platform()
        return self.platform_name

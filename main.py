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

from .ani_rss_handler import AniRSSHandler
from .media_handler import MediaHandler


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
        self.webhook_port = config.get("webhook_port", 60071)
        self.group_id = config.get("group_id", "")
        self.platform_name = config.get("platform_name", "aiocqhttp")
        self.batch_min_size = config.get("batch_min_size", 3)
        self.batch_interval_seconds = config.get("batch_interval_seconds", 300)
        self.cache_ttl_seconds = config.get("cache_ttl_seconds", 300)

        # API 配置
        self.tmdb_api_key = config.get("tmdb_api_key", "")
        self.fanart_api_key = config.get("fanart_api_key", "")

        # 初始化子模块
        self.ani_rss_handler = AniRSSHandler()
        self.media_handler = MediaHandler(self.tmdb_api_key, self.fanart_api_key)

        logger.info("媒体 Webhook 插件子模块初始化完成:")
        logger.info("  - Ani-RSS 处理器: 已启用")
        logger.info(
            f"  - 媒体处理器: 已启用 (TMDB: {'是' if self.tmdb_api_key else '否'})"
        )

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
                    return Response(text="Ani-RSS 消息格式错误", status=400)

                # 检查重复请求
                if self.is_duplicate_request(ani_rss_data):
                    logger.info("检测到重复的 Ani-RSS 请求，忽略")
                    return Response(text="重复请求", status=200)

                # 直接添加到队列（不进行 TMDB 丰富）
                await self.add_ani_rss_to_queue(message_payload)
                return Response(text="Ani-RSS 消息已加入队列", status=200)

            # 处理非 Ani-RSS 数据（媒体服务器数据）
            try:
                raw_data = json.loads(body_text)
                logger.info("成功解析为标准 JSON 格式")
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失败: {e}")
                return Response(text="无效的 JSON 格式", status=400)

            # 使用媒体处理器处理数据（自动检测来源、转换格式、TMDB 丰富）
            logger.info("分发到媒体处理器...")
            media_data = await self.media_handler.process_media_data(
                raw_data, "unknown", headers
            )

            # 验证处理结果
            if not self.media_handler.validate_media_data(
                media_data.get("media_data", {})
            ):
                logger.error("媒体数据验证失败")
                return Response(text="媒体数据格式错误", status=400)

            # 检查重复请求
            if self.is_duplicate_request(media_data):
                logger.info("检测到重复请求，忽略")
                return Response(text="重复请求", status=200)

            # 添加到队列
            await self.add_to_queue(media_data)
            return Response(text="媒体消息已加入队列", status=200)

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
        """添加消息载荷到队列（通用方法）"""
        try:
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

    async def add_ani_rss_to_queue(self, message_payload: dict):
        """添加 Ani-RSS 消息到队列"""
        try:
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

    async def start_batch_processor(self):
        """启动批量处理器"""
        logger.info("启动批量处理器")
        while True:
            try:
                await asyncio.sleep(self.batch_interval_seconds)
                await self.process_message_queue()
            except Exception as e:
                logger.error(f"批量处理器出错: {e}")
                await asyncio.sleep(10)

    async def process_message_queue(self):
        """处理消息队列"""
        if not self.message_queue:
            return

        if not self.group_id:
            logger.warning("未配置群组ID，无法发送消息")
            return

        messages = self.message_queue.copy()
        self.message_queue.clear()

        logger.info(f"从队列中取出 {len(messages)} 条待发消息")

        try:
            # 根据消息数量和平台能力选择发送方式
            if (
                len(messages) >= self.batch_min_size
                and self.platform_name.lower() == "aiocqhttp"
            ):
                await self.send_batch_messages(messages)
            else:
                await self.send_individual_messages(messages)

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
        finally:
            self.last_batch_time = time.time()

    async def send_batch_messages(self, messages: list[dict]):
        """发送合并转发消息（仅 aiocqhttp）"""
        group_id = str(self.group_id).replace(":", "_")
        unified_msg_origin = f"{self.platform_name}:GroupMessage:{group_id}"

        logger.info(f"发送合并转发: {len(messages)} 条消息")

        try:
            # 构建合并转发节点
            forward_nodes = []
            for msg in messages:
                content_list = []

                # 添加图片
                if msg.get("image_url"):
                    content_list.append(Comp.Image.fromURL(msg["image_url"]))

                # 添加文本
                content_list.append(Comp.Plain(msg["message_text"]))

                # 创建转发节点
                node = Comp.Node(
                    uin="2659908767",
                    name="媒体通知",
                    content=content_list,  # 可配置
                )
                forward_nodes.append(node)

            # 创建合并转发消息链
            forward_chain = MessageChain(forward_nodes)
            await self.context.send_message(unified_msg_origin, forward_chain)
            logger.info(f"✅ 成功发送 {len(forward_nodes)} 条合并转发消息")

        except Exception as e:
            logger.error(f"发送合并转发失败: {e}")
            # 回退到单独发送
            await self.send_individual_messages(messages)

    async def send_individual_messages(self, messages: list[dict]):
        """发送单独消息"""
        group_id = str(self.group_id).replace(":", "_")
        unified_msg_origin = f"{self.platform_name}:GroupMessage:{group_id}"

        logger.info(f"发送单独消息: {len(messages)} 条消息")

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

                await self.context.send_message(unified_msg_origin, message_chain)
                logger.debug(f"✅ 消息 {i}/{len(messages)} 发送成功")

                # 添加延迟避免频率限制
                if i < len(messages):
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"❌ 消息 {i} 发送失败: {e}")

    @filter.command("webhook status")
    async def webhook_status(self, event: AstrMessageEvent):
        """查看 Webhook 状态"""
        queue_size = len(self.message_queue)
        cache_size = len(self.request_cache)

        # 获取子模块状态
        media_stats = self.media_handler.get_processing_stats()

        status_text = f"""📊 Media Webhook 状态

🌐 服务状态: {"运行中" if self.site else "未启动"}
📡 监听端口: {self.webhook_port}
📋 队列消息: {queue_size} 条
🗂️ 缓存条目: {cache_size} 条
⚙️ 批量阈值: {self.batch_min_size} 条
⏱️ 批量间隔: {self.batch_interval_seconds} 秒
🎯 目标群组: {self.group_id or "未配置"}
🤖 协议平台: {self.platform_name}

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

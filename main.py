import asyncio
import json
import time

from aiohttp import web
from aiohttp.web import Request, Response

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

from .adapters import AdapterFactory
from .media import MediaHandler, MediaDataProcessor
from .game import GameHandler

# 常量定义
DEFAULT_SENDER_ID = "2659908767"
DEFAULT_SENDER_NAME = "媒体通知"
DEFAULT_WEBHOOK_PORT = 60071
DEFAULT_BATCH_MIN_SIZE = 3
DEFAULT_CACHE_TTL = 300
DEFAULT_BATCH_INTERVAL = 300


@register(
    "media_webhook",
    "memoriass",
    "媒体通知 Webhook 插件，接收媒体服务器的通知并发送到群聊",
    "1.1.0",
    "https://github.com/memoriass/astrbot_plugin_media_webhook",
)
class MediaWebhookPlugin(Star):
    """媒体通知 Webhook 插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # 配置验证
        self._validate_config()

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

        # 自定义路由配置 - 细分处理器
        media_routes = config.get("media_routes", ["/media-webhook"])
        if isinstance(media_routes, str):
            media_routes = [r.strip() for r in media_routes.split(",")]
        elif not isinstance(media_routes, list):
            media_routes = ["/media-webhook"]
        self.media_routes = media_routes
        
        game_routes = config.get("game_routes", ["/game-webhook"])
        if isinstance(game_routes, str):
            game_routes = [r.strip() for r in game_routes.split(",")]
        elif not isinstance(game_routes, list):
            game_routes = []
        self.game_routes = game_routes
        
        # 调试：记录路由配置
        logger.info(f"[DEBUG] media_routes: {self.media_routes}")
        logger.info(f"[DEBUG] game_routes: {self.game_routes}")

        # API 配置
        self.tmdb_api_key = config.get("tmdb_api_key", "")
        self.fanart_api_key = config.get("fanart_api_key", "")
        self.tvdb_api_key = config.get("tvdb_api_key", "")
        self.bgm_app_id = config.get("bgm_app_id", "")
        self.bgm_app_secret = config.get("bgm_app_secret", "")

        # 构建丰富配置
        enrichment_config = {
            "tmdb_api_key": self.tmdb_api_key,
            "fanart_api_key": self.fanart_api_key,
            "tvdb_api_key": self.tvdb_api_key,
            "bgm_app_id": self.bgm_app_id,
            "bgm_app_secret": self.bgm_app_secret,
        }

        # 初始化子模块
        try:
            self.media_handler = MediaHandler(enrichment_config)
            self.data_processor = MediaDataProcessor(self.media_handler, self.cache_ttl_seconds)
            self.game_handler = GameHandler(enrichment_config)
        except Exception as e:
            logger.error(f"初始化处理器失败: {e}")
            raise

        # 显示初始化状态
        self._log_initialization_status()

        # 初始化运行时数据
        self.message_queue: list[dict] = []
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

        # HTTP 服务器
        self.app = None
        self.runner = None
        self.site = None
        self.batch_processor_task = None

    async def initialize(self):
        """初始化插件，启动 Webhook 服务器和批处理器"""
        try:
            # 启动 Webhook 服务器
            await self.start_webhook_server()
            # 启动批处理任务
            self.batch_processor_task = asyncio.create_task(self.start_batch_processor())
        except Exception as e:
            logger.error(f"插件初始化失败: {e}", exc_info=True)

    def _validate_config(self):
        """验证配置参数"""
        errors = []

        # 验证端口
        port = self.config.get("webhook_port", DEFAULT_WEBHOOK_PORT)
        if not isinstance(port, int) or port < 1 or port > 65535:
            errors.append(f"webhook_port 必须是 1-65535 之间的整数，当前值: {port}")

        # 验证批处理大小
        batch_size = self.config.get("batch_min_size", DEFAULT_BATCH_MIN_SIZE)
        if not isinstance(batch_size, int) or batch_size < 1:
            errors.append(f"batch_min_size 必须是大于 0 的整数，当前值: {batch_size}")

        # 验证时间间隔
        intervals = [
            ("batch_interval_seconds", self.config.get("batch_interval_seconds", DEFAULT_BATCH_INTERVAL)),
            ("cache_ttl_seconds", self.config.get("cache_ttl_seconds", DEFAULT_CACHE_TTL)),
        ]
        for name, value in intervals:
            if not isinstance(value, int) or value < 0:
                errors.append(f"{name} 必须是非负整数，当前值: {value}")

        # 验证平台名称
        platform = self.config.get("platform_name", "auto")
        if platform != "auto" and not isinstance(platform, str):
            errors.append(f"platform_name 必须是字符串或 'auto'，当前值: {platform}")

        # 验证 API 密钥格式（如果提供）
        api_keys = [
            ("tmdb_api_key", self.config.get("tmdb_api_key", "")),
            ("fanart_api_key", self.config.get("fanart_api_key", "")),
            ("tvdb_api_key", self.config.get("tvdb_api_key", "")),
        ]
        for name, value in api_keys:
            if value and not isinstance(value, str):
                errors.append(f"{name} 必须是字符串，当前值: {value}")

        # 验证媒体路由
        media_routes = self.config.get("media_routes", ["/media-webhook"])
        if isinstance(media_routes, str):
            media_routes = [r.strip() for r in media_routes.split(",")]
        if isinstance(media_routes, list) and media_routes:
            for route in media_routes:
                if not isinstance(route, str) or not route.strip():
                    errors.append(f"media_routes 必须是非空字符串列表，当前值: {media_routes}")
                    break
        elif not isinstance(media_routes, (list, str)) or (isinstance(media_routes, list) and not media_routes):
            errors.append(f"media_routes 必须是列表或逗号分隔的字符串，当前值: {media_routes}")

        # 验证游戏路由
        game_routes = self.config.get("game_routes", ["/game-webhook"])
        if isinstance(game_routes, str):
            game_routes = [r.strip() for r in game_routes.split(",")]
        if isinstance(game_routes, list):
            for route in game_routes:
                if route and (not isinstance(route, str) or not route.strip()):
                    errors.append(f"game_routes 必须是非空字符串列表，当前值: {game_routes}")
                    break
        elif not isinstance(game_routes, (list, str)):
            errors.append(f"game_routes 必须是列表或逗号分隔的字符串，当前值: {game_routes}")

        # 验证 BGM 配置
        bgm_id = self.config.get("bgm_app_id", "")
        bgm_secret = self.config.get("bgm_app_secret", "")
        if (bgm_id and not bgm_secret) or (not bgm_id and bgm_secret):
            errors.append("bgm_app_id 和 bgm_app_secret 必须同时提供或同时为空")

        if errors:
            error_msg = "配置验证失败:\n" + "\n".join(f"  - {error}" for error in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _log_initialization_status(self):
        """记录初始化状态"""
        try:
            # 检查媒体处理器
            if not self.media_handler:
                logger.error("媒体处理器初始化失败")
                return

            logger.info("[OK] 插件初始化完成 - 所有模块已启用")

        except Exception as e:
            logger.error(f"记录初始化状态时出错: {e}")

    async def handle_status(self, request: Request) -> Response:
        """处理状态查询请求"""
        try:
            queue_size = len(self.message_queue)
            cache_size = len(self.data_processor.request_cache) if hasattr(self.data_processor, 'request_cache') else 0
            
            status_info = {
                "server_running": bool(self.site),
                "listen_port": self.webhook_port,
                "queue_messages": queue_size,
                "cache_entries": cache_size,
                "batch_threshold": self.batch_min_size,
                "batch_interval": self.batch_interval_seconds,
                "target_group": self.group_id or "not_configured",
                "platform": self.get_effective_platform_name(),
            }
            
            return Response(text=json.dumps(status_info, indent=2), status=200, content_type="application/json")
        except Exception as e:
            logger.error(f"处理状态查询失败: {e}")
            return Response(text=json.dumps({"error": str(e)}), status=500, content_type="application/json")

    async def start_webhook_server(self):
        """启动 Webhook 服务器"""
        try:
            self.app = web.Application()
            
            logger.info(f"[DEBUG] Registering routes - media_routes: {self.media_routes}, game_routes: {self.game_routes}")
            
            # 注册媒体相关路由
            for route in self.media_routes:
                if not route.startswith("/"):
                    route = "/" + route
                self.app.router.add_post(route, self.handle_media_webhook)
                logger.info(f"注册媒体Webhook路由: POST {route}")
            
            # 注册游戏相关路由
            for route in self.game_routes:
                if not route.startswith("/"):
                    route = "/" + route
                self.app.router.add_post(route, self.handle_game_webhook)
                logger.info(f"注册游戏Webhook路由: POST {route}")
            
            # 注册状态查询路由
            self.app.router.add_get("/status", self.handle_status)
            logger.info("注册状态查询路由: GET /status")

            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, "0.0.0.0", self.webhook_port)
            await self.site.start()

            logger.info(f"Webhook 服务器已启动在端口 {self.webhook_port}")
            if self.media_routes:
                logger.info(f"媒体路由: {', '.join(self.media_routes)}")
            if self.game_routes:
                logger.info(f"游戏路由: {', '.join(self.game_routes)}")

        except Exception as e:
            logger.error(f"启动 Webhook 服务器失败: {e}")
            raise

    async def start_batch_processor(self):
        """启动批处理器"""
        try:
            self.batch_processor_task = asyncio.create_task(self.batch_processor())
            logger.info("批处理器已启动")

        except Exception as e:
            logger.error(f"启动批处理器失败: {e}")
            raise

    async def handle_media_webhook(self, request: Request) -> Response:
        """处理媒体相关 Webhook 请求"""
        try:
            # 解析请求体
            try:
                body_text = await request.text()
            except Exception as e:
                logger.error(f"读取请求体失败: {e}")
                return Response(text="无法读取请求体", status=400)

            if not body_text:
                logger.warning("收到空的请求体")
                return Response(text="请求体为空", status=400)

            # 记录请求信息
            headers = dict(request.headers)
            logger.info(f"[媒体] 收到 Webhook 请求: {request.path}")
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
            except json.JSONDecodeError:
                logger.debug("请求体不是有效的JSON格式")
            except Exception as e:
                logger.debug(f"解析请求体预览失败: {e}")

            # 将所有数据交由批量处理器检测和处理
            try:
                await self.add_raw_data_to_queue(body_text, headers)
                logger.info("媒体数据已成功加入队列")
                return Response(text="数据已加入队列", status=200)
            except Exception as e:
                logger.error(f"添加数据到队列失败: {e}")
                return Response(text="队列处理失败", status=500)

        except Exception as e:
            logger.error(f"媒体Webhook 处理出错: {e}", exc_info=True)
            return Response(text="处理消息时发生内部错误", status=500)

    async def handle_game_webhook(self, request: Request) -> Response:
        """处理游戏相关 Webhook 请求"""
        try:
            # 解析请求体
            try:
                body_text = await request.text()
            except Exception as e:
                logger.error(f"读取请求体失败: {e}")
                return Response(text="无法读取请求体", status=400)

            if not body_text:
                logger.warning("收到空的请求体")
                return Response(text="请求体为空", status=400)

            # 记录请求信息
            headers = dict(request.headers)
            logger.info(f"[游戏] 收到 Webhook 请求: {request.path}")
            logger.info(f"  User-Agent: {headers.get('user-agent', 'N/A')}")
            logger.info(f"  Content-Type: {headers.get('content-type', 'N/A')}")
            logger.info(f"  请求体长度: {len(body_text)} 字符")

            # 游戏处理器处理
            try:
                payload = json.loads(body_text)
                result = await self.game_handler.process_game_webhook(payload, headers)
                logger.info(f"游戏数据处理结果: {result}")
                return Response(text=json.dumps(result), status=200, content_type="application/json")
            except json.JSONDecodeError:
                logger.error("请求体不是有效的JSON格式")
                return Response(text="请求体不是有效的JSON格式", status=400)
            except Exception as e:
                logger.error(f"处理游戏数据失败: {e}", exc_info=True)
                return Response(text="处理游戏数据失败", status=500)

        except Exception as e:
            logger.error(f"游戏Webhook 处理出错: {e}", exc_info=True)
            return Response(text="处理消息时发生内部错误", status=500)

    async def add_raw_data_to_queue(self, body_text: str, headers: dict):
        """添加原始数据到队列，等待批量处理器检测"""
        try:
            if not isinstance(body_text, str):
                raise ValueError(f"body_text 必须是字符串类型，当前类型: {type(body_text)}")

            if not isinstance(headers, dict):
                raise ValueError(f"headers 必须是字典类型，当前类型: {type(headers)}")

            # 创建原始数据载荷
            raw_payload = {
                "raw_data": body_text,
                "headers": headers,
                "timestamp": time.time(),
                "message_type": "raw",  # 标记为原始数据，需要检测
            }

            # 添加到队列
            self.message_queue.append(raw_payload)

            logger.info(f"原始数据已加入队列，等待批量处理器检测 (队列长度: {len(self.message_queue)})")

        except ValueError as e:
            logger.error(f"参数验证失败: {e}")
            raise
        except Exception as e:
            logger.error(f"添加原始数据到队列失败: {e}", exc_info=True)
            raise

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

            logger.info(f"标准媒体消息已加入队列 (队列长度: {len(self.message_queue)})")

        except Exception as e:
            logger.error(f"添加消息到队列失败: {e}", exc_info=True)
            raise

    async def detect_and_process_raw_data(self, raw_msg: dict) -> dict:
        """检测和处理原始数据"""
        try:
            if not isinstance(raw_msg, dict):
                logger.error(f"raw_msg 必须是字典类型，当前类型: {type(raw_msg)}")
                return None

            body_text = raw_msg.get("raw_data", "")
            headers = raw_msg.get("headers", {})

            if not body_text:
                logger.warning("原始数据为空")
                return None

            # 处理标准媒体数据
            try:
                raw_data = json.loads(body_text)
                logger.info("检测为标准媒体数据")
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失败: {e}")
                return None
            except Exception as e:
                logger.error(f"解析JSON时发生意外错误: {e}")
                return None

            # 检测媒体来源
            try:
                detected_source = self.media_handler.detect_media_source(raw_data, headers)
                if not detected_source:
                    logger.warning("未识别的媒体数据格式")
                    return None

                logger.info(f"检测到媒体来源: {detected_source}")
            except Exception as e:
                logger.error(f"检测媒体来源失败: {e}")
                return None

            # 使用媒体处理器处理数据
            try:
                media_data = await self.media_handler.process_media_data(
                    raw_data, detected_source, headers
                )
            except Exception as e:
                logger.error(f"处理媒体数据失败: {e}")
                return None

            # 验证处理结果
            try:
                if not self.media_handler.validate_media_data(
                    media_data.get("media_data", {})
                ):
                    logger.error("媒体数据验证失败")
                    return None
            except Exception as e:
                logger.error(f"验证媒体数据失败: {e}")
                return None

            # 检查重复请求
            try:
                if self.is_duplicate_request(media_data):
                    logger.info("检测到重复请求，忽略")
                    return None
            except Exception as e:
                logger.warning(f"检查重复请求失败，继续处理: {e}")

            # 标记为媒体消息
            media_data["message_type"] = "media"
            logger.info("原始数据处理完成")
            return media_data

        except Exception as e:
            logger.error(f"原始数据检测和处理失败: {e}", exc_info=True)
            return None


    async def send_media_messages_intelligently(self, media_messages: list):
        """智能发送标准媒体消息（根据协议端选择最优发送模式）"""
        try:
            if not isinstance(media_messages, list):
                raise ValueError(f"media_messages 必须是列表类型，当前类型: {type(media_messages)}")

            if not media_messages:
                logger.warning("没有媒体消息需要发送")
                return

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

        except ValueError as e:
            logger.error(f"参数验证失败: {e}")
            raise
        except Exception as e:
            logger.error(f"智能发送媒体消息失败: {e}", exc_info=True)
            raise

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
            media_messages = []

            for msg in messages:
                msg_type = msg.get("message_type", "media")
                if msg_type == "raw":
                    raw_data_messages.append(msg)
                else:
                    media_messages.append(msg)

            # 处理原始数据（检测和转换）
            if raw_data_messages:
                logger.info(f"检测和处理 {len(raw_data_messages)} 条原始数据")
                for raw_msg in raw_data_messages:
                    processed_msg = await self.data_processor.detect_and_process_raw_data(raw_msg)
                    if processed_msg:
                        media_messages.append(processed_msg)

            # 处理标准媒体消息（智能发送）
            if media_messages:
                logger.info(f"处理 {len(media_messages)} 条标准媒体消息（智能发送）")
                await self.send_media_messages_intelligently(media_messages)

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
        finally:
            self.last_batch_time = time.time()

    async def send_batch_messages(self, messages: list[dict]):
        """发送合并转发消息（使用适配器）"""
        group_id = str(self.group_id).replace(":", "_")

        logger.info(f"发送合并转发: {len(messages)} 条消息")

        try:
            # 获取平台实例和bot客户端
            platform = self.context.get_platform_inst(
                self.get_effective_platform_name()
            )
            if not platform:
                raise Exception(f"未找到平台: {self.get_effective_platform_name()}")

            bot = platform.get_client()
            if bot is None:
                raise Exception("Bot 客户端未连接")

            # 使用适配器发送消息
            adapter = AdapterFactory.create_adapter(self.get_effective_platform_name())
            result = await adapter.send_forward_messages(
                bot_client=bot,
                group_id=group_id,
                messages=messages,
                sender_id=self.sender_id,
                sender_name=self.sender_name,
            )

            if result.get("success"):
                logger.info(
                    f"[OK] 合并转发发送成功 [适配器: {adapter.get_adapter_info()['name']}]"
                )
            else:
                raise Exception(result.get("error", "未知错误"))

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
        cache_size = len(self.data_processor.request_cache)

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
  媒体处理器: 已启用
    - 处理器就绪: ✓
    - 丰富提供者: 已配置
    - 缓存体系: 活跃"""

        yield event.plain_result(status_text)

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("正在停止媒体 Webhook 插件...")

        try:
            # 停止批处理器任务
            if hasattr(self, 'batch_processor_task') and self.batch_processor_task:
                if not self.batch_processor_task.done():
                    logger.info("正在取消批处理器任务...")
                    self.batch_processor_task.cancel()
                    try:
                        await asyncio.wait_for(self.batch_processor_task, timeout=5.0)
                        logger.info("批处理器任务已停止")
                    except asyncio.TimeoutError:
                        logger.warning("批处理器任务停止超时")
                    except asyncio.CancelledError:
                        logger.info("批处理器任务已取消")
                else:
                    logger.info("批处理器任务已完成")

            # 停止 Webhook 服务器
            if hasattr(self, 'site') and self.site:
                try:
                    logger.info("正在停止 Webhook 服务器...")
                    await self.site.stop()
                    logger.info("Webhook 服务器已停止")
                except Exception as e:
                    logger.error(f"停止 Webhook 服务器失败: {e}")

            if hasattr(self, 'runner') and self.runner:
                try:
                    logger.info("正在清理 HTTP runner...")
                    await self.runner.cleanup()
                    logger.info("HTTP runner 已清理")
                except Exception as e:
                    logger.error(f"清理 HTTP runner 失败: {e}")

            # 清空消息队列
            if hasattr(self, 'message_queue'):
                queue_size = len(self.message_queue)
                self.message_queue.clear()
                logger.info(f"消息队列已清空 (处理了 {queue_size} 条消息)")

            logger.info("媒体 Webhook 插件已完全停止")

        except Exception as e:
            logger.error(f"插件终止时发生错误: {e}", exc_info=True)

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

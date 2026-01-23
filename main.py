import asyncio
import json
import time
import uuid
import aiohttp
import requests

from aiohttp import web
from aiohttp.web import Request, Response

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

from .adapters import AdapterFactory
from .media import MediaHandler, MediaDataProcessor
from .game import GameHandler
from .common import CommonHandler
from .utils.html_renderer import HtmlRenderer
from .utils.browser import BrowserManager
from concurrent.futures import ThreadPoolExecutor

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
    "通用 Webhook 推送插件，支持媒体、游戏及自定义消息推送",
    "1.3.0",
    "https://github.com/memoriass/astrbot_plugin_media_webhook",
)
class WebhookPushPlugin(Star):
    """通用 Webhook 推送插件"""

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
        self.webhook_token = config.get("webhook_token", "")

        # 路由配置
        self.media_routes = self._parse_routes(config.get("media_routes", ["/media-webhook"]))
        self.game_routes = self._parse_routes(config.get("game_routes", ["/game-webhook"]))
        self.common_routes = self._parse_routes(config.get("common_routes", ["/webhook"]))
        
        # 初始化子模块
        # 获取标准数据路径
        base_data_path = self.get_astrbot_data_path()
        
        enrichment_config = {
            "tmdb_api_key": config.get("tmdb_api_key", ""),
            "fanart_api_key": config.get("fanart_api_key", ""),
            "tvdb_api_key": config.get("tvdb_api_key", ""),
            "bgm_app_id": config.get("bgm_app_id", ""),
            "bgm_app_secret": config.get("bgm_app_secret", ""),
            "enable_translation": config.get("enable_translation", False),
            "preferred_translator": config.get("preferred_translator", "tencent"),
            "tencent_secret_id": config.get("tencent_secret_id", ""),
            "tencent_secret_key": config.get("tencent_secret_key", ""),
            "baidu_app_id": config.get("baidu_app_id", ""),
            "baidu_secret_key": config.get("baidu_secret_key", ""),
            "cache_persistence_days": config.get("cache_persistence_days", 7),
            "data_path": base_data_path, # 传入数据路径
        }

        try:
            self.media_handler = MediaHandler(enrichment_config)
            self.data_processor = MediaDataProcessor(self.media_handler, self.cache_ttl_seconds)
            self.game_handler = GameHandler(self.context, config)
            self.common_handler = CommonHandler(config)
            self.image_renderer = HtmlRenderer()
        except Exception as e:
            logger.error(f"初始化处理器失败: {e}")
            raise

        # 初始化运行时数据
        self.message_queue: list[dict] = []
        self.last_batch_time = time.time()

        # HTTP 服务器组件
        self.app = None
        self.runner = None
        self.site = None
        self.batch_processor_task = None

    def _parse_routes(self, routes) -> list:
        if isinstance(routes, str):
            return [r.strip() for r in routes.split(",") if r.strip()]
        elif isinstance(routes, list):
            return [r for r in routes if isinstance(r, str) and r.strip()]
        return []

    async def initialize(self):
        """初始化插件，启动 Webhook 服务器和批处理器"""
        try:
            # 恢复持久化队列
            saved_queue = await self.context.get_kv_data("persistent_msg_queue", [])
            if saved_queue:
                self.message_queue.extend(saved_queue)
                logger.info(f"已恢复 {len(saved_queue)} 条未处理消息")
            
            await BrowserManager.init()
            await self.start_webhook_server()
            self.batch_processor_task = asyncio.create_task(self.start_batch_processor())
            logger.info("[OK] 插件初始化完成 - 所有模块已启用")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}", exc_info=True)

    async def _save_queue(self):
        """持久化队列到 KV"""
        try:
            await self.context.put_kv_data("persistent_msg_queue", self.message_queue)
        except Exception as e:
            logger.error(f"保存队列失败: {e}")

    async def _enqueue(self, msg: dict):
        """入队并保存"""
        self.message_queue.append(msg)
        await self._save_queue()

    def _validate_config(self):
        """验证配置参数"""
        errors = []
        port = self.config.get("webhook_port", DEFAULT_WEBHOOK_PORT)
        if not isinstance(port, int) or port < 1 or port > 65535:
            errors.append(f"webhook_port 必须是 1-65535 之间的整数，当前值: {port}")
        
        batch_size = self.config.get("batch_min_size", DEFAULT_BATCH_MIN_SIZE)
        if not isinstance(batch_size, int) or batch_size < 1:
            errors.append(f"batch_min_size 必须是大于 0 的整数，当前值: {batch_size}")

        if errors:
            error_msg = "配置验证失败:\n" + "\n".join(f"  - {error}" for error in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

    async def start_webhook_server(self):
        """启动 Webhook 服务器"""
        try:
            self.app = web.Application()
            
            # 注册媒体相关路由
            for route in self.media_routes:
                self.app.router.add_post(self._normalize_route(route), self.handle_media_webhook)
                logger.info(f"注册媒体Webhook路由: POST {route}")
            
            # 注册游戏相关路由
            for route in self.game_routes:
                self.app.router.add_post(self._normalize_route(route), self.handle_game_webhook)
                logger.info(f"注册游戏Webhook路由: POST {route}")

            # 注册通用路由
            for route in self.common_routes:
                self.app.router.add_post(self._normalize_route(route), self.handle_common_webhook)
                logger.info(f"注册通用Webhook路由: POST {route}")
            
            self.app.router.add_get("/status", self.handle_status)

            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, "0.0.0.0", self.webhook_port)
            await self.site.start()

            logger.info(f"Webhook 服务器已启动在端口 {self.webhook_port}")
        except Exception as e:
            logger.error(f"启动 Webhook 服务器失败: {e}")
            raise

    def _check_auth(self, request: Request) -> bool:
        """检查 Webhook 鉴权 Token"""
        if not self.webhook_token:
            return True
        token = request.headers.get("X-Webhook-Token")
        return token == self.webhook_token

    def _normalize_route(self, route: str) -> str:
        if not route.startswith("/"):
            return "/" + route
        return route

    async def start_batch_processor(self):
        """启动批量处理器周期任务"""
        while True:
            try:
                await asyncio.sleep(self.batch_interval_seconds)
                await self.process_message_queue()
            except Exception as e:
                logger.error(f"批量处理器出错: {e}")
                await asyncio.sleep(10)

    # --- Webhook 处理方法 (只负责分流) ---

    async def handle_media_webhook(self, request: Request) -> Response:
        """处理媒体相关 Webhook 请求"""
        trace_id = str(uuid.uuid4())[:8]
        if not self._check_auth(request):
            logger.warning(f"[{trace_id}] {t('unauthorized')}: {request.remote}")
            return Response(text="Unauthorized", status=401)
        try:
            body_text = await request.text()
            headers = dict(request.headers)
            logger.info(f"[{trace_id}][{t('media_webhook')}] 收到 Webhook 请求: {request.path}")
            
            # 加入队列，标记为需要媒体检测
            raw_payload = {
                "raw_data": body_text,
                "headers": headers,
                "timestamp": time.time(),
                "message_type": "raw_media",
                "trace_id": trace_id,
            }
            await self._enqueue(raw_payload)
            return Response(text=f"{t('queue_success')} (ID: {trace_id})", status=200)
        except Exception as e:
            logger.error(f"[{trace_id}] Webhook 处理出错: {e}")
            return Response(text="Internal Error", status=500)

    async def handle_game_webhook(self, request: Request) -> Response:
        """处理游戏相关 Webhook 请求"""
        trace_id = str(uuid.uuid4())[:8]
        if not self._check_auth(request):
            logger.warning(f"[{trace_id}] {t('unauthorized')}: {request.remote}")
            return Response(text="Unauthorized", status=401)
        try:
            body_text = await request.text()
            headers = dict(request.headers)
            logger.info(f"[{trace_id}][{t('game_webhook')}] 收到 Webhook 请求: {request.path}")
            
            payload = json.loads(body_text)
            result = await self.game_handler.process_game_webhook(payload, headers)
            
            if result and "message_text" in result:
                result["message_type"] = "game"
                result["timestamp"] = time.time()
                result["trace_id"] = trace_id
                await self._enqueue(result)
                return Response(text=f"{t('queue_success')} (ID: {trace_id})", status=200)

            return Response(text=f"{t('invalid_data')}", status=400)
        except Exception as e:
            logger.error(f"[{trace_id}] Webhook 处理出错: {e}")
            return Response(text="Internal Error", status=500)

    async def handle_common_webhook(self, request: Request) -> Response:
        """处理通用相关 Webhook 请求"""
        trace_id = str(uuid.uuid4())[:8]
        if not self._check_auth(request):
            logger.warning(f"[{trace_id}] {t('unauthorized')}: {request.remote}")
            return Response(text="Unauthorized", status=401)
        try:
            body_text = await request.text()
            headers = dict(request.headers)
            logger.info(f"[{trace_id}][{t('common_webhook')}] 收到 Webhook 请求: {request.path}")
            
            result = await self.common_handler.process_common_webhook(body_text, headers)
            
            if result and "message_text" in result:
                result["timestamp"] = time.time()
                result["trace_id"] = trace_id
                await self._enqueue(result)
                return Response(text=f"{t('queue_success')} (ID: {trace_id})", status=200)
            
            return Response(text=f"{t('invalid_data')}", status=400)
        except Exception as e:
            logger.error(f"[{trace_id}] Webhook 处理出错: {e}")
            return Response(text="Internal Error", status=500)

    async def handle_status(self, request: Request) -> Response:
        """HTTP 状态查询"""
        status_info = {
            "server_running": bool(self.site),
            "listen_port": self.webhook_port,
            "queue_messages": len(self.message_queue),
            "target_group": self.group_id or "not_configured",
        }
        return Response(text=json.dumps(status_info, indent=2), status=200, content_type="application/json")

    # --- 消息分发与队列处理 (只负责最终发送) ---

    async def process_message_queue(self):
        """处理消息队列"""
        if not self.message_queue or not self.group_id:
            return

        messages_to_process = self.message_queue.copy()
        self.message_queue.clear()
        await self._save_queue()
        
        final_messages = []
        for msg in messages_to_process:
            trace_id = msg.get("trace_id", "Unknown")
            m_type = msg.get("message_type")
            if m_type == "raw_media":
                logger.debug(f"[{trace_id}] 开始处理媒体元数据...")
                # 交给媒体处理器进行识别和数据富化
                processed = await self.data_processor.detect_and_process_raw_data(msg)
                if processed:
                    processed["trace_id"] = trace_id
                    final_messages.append(processed)
            else:
                # 已经是标准格式 (game 或 common)
                final_messages.append(msg)

        if final_messages:
            logger.info(t("batch_start").format(len(final_messages)))
            await self.send_intelligently(final_messages)
        
        self.last_batch_time = time.time()

    async def send_intelligently(self, messages: list):
        """智能发送逻辑"""
        count = len(messages)
        if count >= self.batch_min_size:
            await self.send_batch_messages(messages)
        else:
            await self.send_individual_messages(messages)

    async def send_batch_messages(self, messages: list):
        """批量发送 (渲染为多张合并转发图片)"""
        try:
            rendered_messages = []
            for msg in messages:
                trace_id = msg.get("trace_id", "Unknown")
                logger.info(f"[{trace_id}] {t('rendering')}")
                # 使用 HtmlRenderer 异步渲染
                img = await self.image_renderer.render(
                    msg["message_text"],
                    msg.get("image_url")
                )
                if img:
                    rendered_messages.append({
                        "message_text": "[图片通知]",
                        "rendered_image": img,
                        "sender_name": self.sender_name
                    })
            
            if not rendered_messages: return

            platform = self.context.get_platform_inst(self.get_effective_platform_name())
            bot = platform.get_client() if platform else None
            if not bot: return

            adapter = AdapterFactory.create_adapter(self.get_effective_platform_name())
            await adapter.send_forward_messages(
                bot_client=bot,
                group_id=str(self.group_id).replace(":", "_"),
                messages=rendered_messages,
                sender_id=self.sender_id,
                sender_name=self.sender_name,
            )
        except Exception as e:
            logger.error(f"批量发送失败，回退到单独发送: {e}")
            await self.send_individual_messages(messages)

    async def send_individual_messages(self, messages: list):
        """单独发送 (每条消息渲染一张图片)"""
        group_id = str(self.group_id).replace(":", "_")
        origin = f"{self.get_effective_platform_name()}:GroupMessage:{group_id}"

        for msg in messages:
            trace_id = msg.get("trace_id", "Unknown")
            try:
                logger.info(f"[{trace_id}] {t('rendering')}")
                # 使用 HtmlRenderer 异步渲染
                img = await self.image_renderer.render(
                    msg["message_text"],
                    msg.get("image_url")
                )
                if img:
                    chain = MessageChain([Comp.Image.fromBytes(img)])
                    await self.context.send_message(origin, chain)
                    logger.info(f"[{trace_id}] {t('send_success')}")
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"单条消息发送失败: {e}")

    @filter.command("webhook status")
    async def webhook_status(self, event: AstrMessageEvent):
        """查看 Webhook 状态 (AstrBot 命令)"""
        status_text = f"📊 Webhook 状态\n\n🌐 端口: {self.webhook_port}\n📋 待发: {len(self.message_queue)}\n🎯 目标: {self.group_id}"
        yield event.plain_result(status_text)

    async def terminate(self):
        """卸载清理"""
        if self.batch_processor_task: self.batch_processor_task.cancel()
        if self.site: await self.site.stop()
        if self.runner: await self.runner.cleanup()
        await BrowserManager.close()

    def get_effective_platform_name(self) -> str:
        if self.platform_name == "auto":
            # 简化版自动检测逻辑
            available = [p.meta().id for p in self.context.platform_manager.platform_insts]
            for p in ["llonebot", "napcat", "aiocqhttp"]:
                if any(p in name.lower() for name in available): return p
            return available[0] if available else "llonebot"
        return self.platform_name

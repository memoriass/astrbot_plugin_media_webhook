import asyncio
import hashlib
import html
import json
import time
from typing import Dict, List, Optional

from aiohttp import web
from aiohttp.web import Request, Response

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

from .ani_rss_handler import AniRSSHandler
from .tmdb_enricher import TMDBEnricher


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

        # 初始化 TMDB 丰富器
        if self.tmdb_api_key:
            self.tmdb_enricher = TMDBEnricher(self.tmdb_api_key, self.fanart_api_key)
            logger.info("TMDB 丰富器已初始化")
        else:
            self.tmdb_enricher = None
            logger.info("未配置 TMDB API 密钥，跳过 TMDB 丰富器初始化")

        # 初始化 Ani-RSS 处理器
        self.ani_rss_handler = AniRSSHandler()
        logger.info("Ani-RSS 处理器已初始化")

        # 消息队列和缓存
        self.message_queue: List[Dict] = []
        self.request_cache: Dict[str, float] = {}
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
            logger.info(f"收到 Webhook 请求:")
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

            # 处理非 Ani-RSS 数据
            try:
                raw_data = json.loads(body_text)
                logger.info("成功解析为标准 JSON 格式")
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失败: {e}")
                return Response(text="无效的 JSON 格式", status=400)

            # 检测通知来源
            source = self.detect_notification_source(raw_data, headers)
            logger.info(f"检测到数据来源: {source}")

            # 处理不同来源的数据格式
            if source == "emby":
                media_data = self.convert_emby_to_media_data(raw_data)
                logger.info("Emby 数据已转换为标准格式")
            elif source in ["jellyfin", "plex"]:
                media_data = self.convert_generic_media_data(raw_data)
                logger.info(f"{source.title()} 数据已转换为标准格式")
            else:
                media_data = raw_data
                logger.info("使用原始数据格式")

            # 检查重复请求
            if self.is_duplicate_request(media_data):
                logger.info("检测到重复请求，忽略")
                return Response(text="重复请求", status=200)

            # 使用 TMDB 丰富数据
            if self.tmdb_enricher:
                media_data = await self.tmdb_enricher.enrich_media_data(media_data)

            # 添加到队列
            await self.add_to_queue(media_data, source)
            return Response(text="消息已加入队列", status=200)

        except Exception as e:
            logger.error(f"Webhook 处理出错: {e}")
            return Response(text="处理消息时发生内部错误", status=500)

    def detect_notification_source(self, data: Dict, headers: Dict) -> str:
        """检测通知来源"""
        # 检查 User-Agent 中的特征
        user_agent = headers.get("user-agent", "").lower()

        # 优先检查 User-Agent
        if "emby server" in user_agent:
            return "emby"
        elif "jellyfin" in user_agent:
            return "jellyfin"
        elif "plex" in user_agent:
            return "plex"

        # 检查数据结构特征
        if "Item" in data and "Server" in data:
            return "emby"
        elif "ItemType" in data or "SeriesName" in data:
            return "jellyfin"
        elif "Metadata" in data or "Player" in data:
            return "plex"

        return "unknown"

    def convert_emby_to_media_data(self, data: Dict) -> Dict:
        """将 Emby 数据转换为标准媒体数据格式"""
        try:
            item = data.get("Item", {})

            # 提取基本信息
            item_type = item.get("Type", "Unknown")
            item_name = item.get("Name", "")

            # 处理剧集信息
            series_name = ""
            season_number = ""
            episode_number = ""

            if item_type == "Episode":
                series_name = item.get("SeriesName", "")
                season_number = item.get("ParentIndexNumber", "")
                episode_number = item.get("IndexNumber", "")
            elif item_type == "Season":
                series_name = item.get("SeriesName", "")
                season_number = item.get("IndexNumber", "")
            elif item_type == "Series":
                series_name = item_name

            # 提取其他信息
            year = item.get("ProductionYear", "")
            overview = item.get("Overview", "")
            runtime_ticks = item.get("RunTimeTicks", 0)
            runtime = f"{runtime_ticks // 600000000}分钟" if runtime_ticks > 0 else ""

            return {
                "item_type": item_type,
                "series_name": series_name,
                "item_name": item_name,
                "season_number": str(season_number) if season_number else "",
                "episode_number": str(episode_number) if episode_number else "",
                "year": str(year) if year else "",
                "overview": overview,
                "runtime": runtime,
                "image_url": "",
            }

        except Exception as e:
            logger.error(f"转换 Emby 数据失败: {e}")
            return {}

    def convert_generic_media_data(self, data: Dict) -> Dict:
        """将通用媒体数据转换为标准格式（适用于 Jellyfin、Plex 等）"""
        try:
            # 提取基本信息
            item_type = (
                data.get("ItemType")
                or data.get("Type")
                or data.get("item_type", "Episode")
            )

            # 处理剧集名称
            series_name = (
                data.get("SeriesName")
                or data.get("series_name")
                or data.get("Name")
                or data.get("name", "")
            )

            # 处理集名称
            item_name = (
                data.get("Name")
                or data.get("name")
                or data.get("ItemName")
                or data.get("item_name", "")
            )

            # 处理季集号
            season_number = str(
                data.get("SeasonNumber") or data.get("season_number", "")
            )
            episode_number = str(
                data.get("EpisodeNumber") or data.get("episode_number", "")
            )

            # 处理年份
            year = str(
                data.get("Year") or data.get("year") or data.get("ProductionYear", "")
            )

            # 处理简介
            overview = (
                data.get("Overview")
                or data.get("overview")
                or data.get("Description", "")
            )

            # 处理时长
            runtime = data.get("Runtime") or data.get("runtime", "")
            if not runtime and data.get("RunTimeTicks"):
                runtime_ticks = data.get("RunTimeTicks", 0)
                runtime = (
                    f"{runtime_ticks // 600000000}分钟" if runtime_ticks > 0 else ""
                )

            return {
                "item_type": item_type,
                "series_name": series_name,
                "item_name": item_name,
                "season_number": season_number,
                "episode_number": episode_number,
                "year": year,
                "overview": overview,
                "runtime": runtime,
                "image_url": data.get("image_url", ""),
            }

        except Exception as e:
            logger.error(f"转换通用媒体数据失败: {e}")
            return {}

    def is_duplicate_request(self, media_data: Dict) -> bool:
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

    def calculate_request_hash(self, media_data: Dict) -> str:
        """计算请求哈希值 - 排除图片和不稳定字段以提高准确率"""
        try:
            # 根据数据来源选择不同的哈希策略
            if self.is_ani_rss_data(media_data):
                return self.calculate_ani_rss_hash(media_data)
            else:
                return self.calculate_standard_hash(media_data)
        except Exception as e:
            logger.error(f"计算请求哈希失败: {e}")
            return ""

    def is_ani_rss_data(self, media_data: Dict) -> bool:
        """判断是否为 Ani-RSS 数据"""
        return "meassage" in media_data or "text_template" in media_data

    def calculate_ani_rss_hash(self, media_data: Dict) -> str:
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

    def calculate_standard_hash(self, media_data: Dict) -> str:
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

    async def add_to_queue(self, media_data: Dict, source: str):
        """添加消息到队列（非 Ani-RSS 数据）"""
        try:
            # 注意：Ani-RSS 数据应该使用 add_ani_rss_to_queue 方法
            if source == "ani-rss":
                logger.warning("Ani-RSS 数据应该使用 add_ani_rss_to_queue 方法")
                return

            image_url = media_data.get("image_url", "")
            message_text = self.generate_message_text(media_data)

            message_payload = {
                "image_url": image_url,
                "message_text": message_text,
                "timestamp": time.time(),
                "source": source,
            }

            self.message_queue.append(message_payload)

            item_type = media_data.get("item_type", "Unknown")
            logger.info(
                f"新 {item_type} 通知已加入队列 [来源: {source}] {'(含图片)' if image_url else '(无图片)'}"
            )

        except Exception as e:
            logger.error(f"添加消息到队列失败: {e}")

    async def add_ani_rss_to_queue(self, message_payload: Dict):
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

    def generate_title_by_type(
        self, item_type: str, cn_type: str, emoji: str, action: str, data: Dict
    ) -> str:
        """根据媒体类型生成合适的标题"""
        if item_type == "Movie":
            return f"{emoji} 新电影{action}"
        elif item_type in ["Series", "Season"]:
            return f"{emoji} 剧集{action}"
        elif item_type == "Episode":
            # 对于剧集，显示更具体的信息
            season_num = data.get("season_number", "")
            episode_num = data.get("episode_number", "")
            if season_num and episode_num:
                return f"{emoji} 新剧集{action}"
            else:
                return f"{emoji} 剧集{action}"
        elif item_type == "Album":
            return f"{emoji} 新专辑{action}"
        elif item_type == "Song":
            return f"{emoji} 新歌曲{action}"
        elif item_type == "Video":
            return f"{emoji} 新视频{action}"
        elif item_type in ["Audio", "AudioBook"]:
            return f"{emoji} 新音频{action}"
        elif item_type == "Book":
            return f"{emoji} 新图书{action}"
        else:
            # 默认格式
            return f"{emoji} 新{cn_type}{action}"

    def get_first_paragraph(self, text: str) -> str:
        """获取文本的第一段"""
        if not text:
            return ""

        # 按句号分割
        sentences = text.split("。")
        if len(sentences) > 1 and sentences[0]:
            first_sentence = sentences[0].strip() + "。"
            # 限制长度
            if len(first_sentence) > 100:
                return first_sentence[:97] + "..."
            return first_sentence

        # 按换行符分割
        lines = text.split("\n")
        first_line = lines[0].strip()
        if first_line:
            # 限制长度
            if len(first_line) > 100:
                return first_line[:97] + "..."
            return first_line

        # 如果都没有，直接截取前100个字符
        if len(text) > 100:
            return text[:97] + "..."
        return text.strip()

    def generate_message_text(self, data: Dict) -> str:
        """生成消息文本（紧凑排列优化）"""
        item_type = data.get("item_type", "")
        cn_type = self.media_type_map.get(item_type, item_type)
        emoji = self.type_emoji_map.get(item_type, self.type_emoji_map["Default"])

        # 生成标题
        title = self.generate_title_by_type(item_type, cn_type, emoji, "上线", data)
        message_parts = [title]

        # 主要信息（紧凑排列）
        main_section = self.generate_main_section(data)
        if main_section:
            message_parts.append(main_section)

        # 只显示第一段剧情简介
        overview = data.get("overview", "")
        if overview:
            decoded_overview = html.unescape(overview)
            # 只取第一段（以句号、换行符或长度为界）
            first_paragraph = self.get_first_paragraph(decoded_overview)
            if first_paragraph:
                if item_type == "Movie":
                    message_parts.append(f"剧情简介: {first_paragraph}")
                elif item_type in ["Series", "Season", "Episode"]:
                    message_parts.append(f"剧情简介: {first_paragraph}")
                elif item_type == "Album":
                    message_parts.append(f"专辑介绍: {first_paragraph}")
                elif item_type == "Song":
                    message_parts.append(f"歌曲介绍: {first_paragraph}")
                elif item_type == "Book":
                    message_parts.append(f"内容简介: {first_paragraph}")
                else:
                    message_parts.append(f"内容简介: {first_paragraph}")

        # 时长信息
        runtime = data.get("runtime", "")
        if runtime:
            if item_type == "Movie":
                message_parts.append(f"片长: {runtime}")
            elif item_type in ["Episode", "Video"]:
                message_parts.append(f"时长: {runtime}")
            elif item_type == "Song":
                message_parts.append(f"时长: {runtime}")
            else:
                message_parts.append(f"时长: {runtime}")

        # 数据来源标记
        if data.get("tmdb_enriched"):
            message_parts.append("✨ 数据来源: TMDB")
        elif data.get("bgm_enriched"):
            message_parts.append("✨ 数据来源: BGM.TV")

        return "\n".join(message_parts)

    def generate_main_section(self, data: Dict) -> str:
        """生成主要信息部分"""
        sections = []

        # 剧集名称
        if data.get("series_name"):
            name_part = data["series_name"]
            if data.get("year"):
                name_part += f" ({data['year']})"
            sections.append(f"剧集名称: {name_part}")

        # 根据类型生成不同信息
        item_type = data.get("item_type", "")

        if item_type == "Episode":
            # 集号
            season_num = data.get("season_number", "")
            episode_num = data.get("episode_number", "")
            if season_num and episode_num:
                season_str = str(season_num).zfill(2)
                episode_str = str(episode_num).zfill(2)
                sections.append(f"集号: S{season_str}E{episode_str}")

            # 集名称
            if data.get("item_name"):
                sections.append(f"集名称: {data['item_name']}")

        elif item_type == "Season":
            # 季名称
            if data.get("item_name"):
                sections.append(f"季名称: {data['item_name']}")
            if data.get("season_number"):
                sections.append(f"季号: {data['season_number']}")

        else:
            # 其他类型
            if data.get("item_name"):
                sections.append(f"名称: {data['item_name']}")
            if data.get("year") and not data.get("series_name"):
                sections.append(f"年份: {data['year']}")

        return "\n".join(sections)

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

    async def send_batch_messages(self, messages: List[Dict]):
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

                # 创建消息链
                message_chain = MessageChain(content_list)

                # 创建转发节点
                node = Comp.Node(
                    uin="2659908767", name="媒体通知", content=content_list  # 可配置
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

    async def send_individual_messages(self, messages: List[Dict]):
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

        status_text = f"""📊 Webhook 状态

🌐 服务状态: {'运行中' if self.site else '未启动'}
📡 监听端口: {self.webhook_port}
📋 队列消息: {queue_size} 条
🗂️ 缓存条目: {cache_size} 条
⚙️ 批量阈值: {self.batch_min_size} 条
⏱️ 批量间隔: {self.batch_interval_seconds} 秒
🎯 目标群组: {self.group_id or '未配置'}
🤖 协议平台: {self.platform_name}"""

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

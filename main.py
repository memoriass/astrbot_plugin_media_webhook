import asyncio
import hashlib
import html
import json
import random
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

import astrbot.api.message_components as Comp
import aiohttp
from aiohttp import web
from aiohttp.web import Request, Response
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register


class MediaSource(Enum):
    """媒体来源枚举"""
    JELLYFIN = "jellyfin"
    EMBY = "emby"
    PLEX = "plex"
    ANI_RSS = "ani-rss"
    SONARR = "sonarr"
    RADARR = "radarr"
    DEFAULT = "default"


class DataSource(Enum):
    """数据来源枚举"""
    TMDB = "tmdb"
    BGM_TV = "bgm"
    ORIGINAL = "original"


@dataclass
class MediaData:
    """媒体数据结构"""
    item_type: str = "Episode"
    series_name: str = ""
    item_name: str = ""
    season_number: str = ""
    episode_number: str = ""
    overview: str = ""
    runtime: str = ""
    year: str = ""
    image_url: str = ""
    event_type: str = ""
    data_source: Optional[DataSource] = None

    def to_dict(self) -> Dict:
        """转换为字典格式"""
        result = {
            "item_type": self.item_type,
            "series_name": self.series_name,
            "item_name": self.item_name,
            "season_number": self.season_number,
            "episode_number": self.episode_number,
            "overview": self.overview,
            "runtime": self.runtime,
            "year": self.year,
            "event_type": self.event_type,
        }
        if self.image_url:
            result["image_url"] = self.image_url
        if self.data_source:
            result[f"{self.data_source.value}_enriched"] = True
        return result


@register(
    "media_webhook",
    "Assistant",
    "媒体通知 Webhook 插件",
    "1.0.0",
    "https://github.com/example/astrbot_plugin_media_webhook",
)
class MediaWebhookPlugin(Star):
    """媒体通知 Webhook 插件主类"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # HTTP 服务器相关
        self.app = None
        self.runner = None
        self.site = None

        # 核心配置
        self._init_core_config()

        # 缓存和队列
        self._init_cache_and_queue()

    def _init_core_config(self):
        """初始化核心配置 - 优化配置获取性能"""
        # 一次性获取所有配置，避免重复调用 config.get()
        config = self.config
        self.webhook_port = config.get("webhook_port", 60071)
        self.webhook_path = config.get("webhook_path", "/media-webhook")
        self.group_id = config.get("group_id", "")
        self.platform_name = config.get("platform_name", "aiocqhttp")

        # 批量处理配置
        self.batch_min_size = config.get("batch_min_size", 3)
        self.batch_interval_seconds = config.get("batch_interval_seconds", 300)
        self.cache_ttl_seconds = config.get("cache_ttl_seconds", 300)
        self.force_individual_send = config.get("force_individual_send", False)

        # 显示配置
        self.show_platform_prefix = config.get("show_platform_prefix", True)
        self.show_source_info = config.get("show_source_info", True)

        # API 配置
        self.tmdb_api_key = config.get("tmdb_api_key", "")
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.bgm_base_url = "https://api.bgm.tv"

    def _init_cache_and_queue(self):
        """初始化缓存和队列"""
        self.message_queue: List[Dict] = []
        self.request_cache: Dict[str, float] = {}
        self.tmdb_cache: Dict[str, Dict] = {}
        self.bgm_cache: Dict[str, Dict] = {}
        self.last_batch_time = time.time()

        # 配置缓存，避免重复调用 config.get()
        self._config_cache: Dict[str, any] = {}

        # 映射表
        self._init_mappings()

    def _get_config(self, key: str, default=None):
        """获取配置值，带缓存优化"""
        if key not in self._config_cache:
            self._config_cache[key] = self.config.get(key, default)
        return self._config_cache[key]

    def _init_mappings(self):
        """初始化映射表"""
        self.media_type_map = {
            "Movie": "电影", "Series": "剧集", "Season": "剧季", "Episode": "剧集",
            "Album": "专辑", "Song": "歌曲", "Video": "视频", "Audio": "音频",
            "Book": "图书", "AudioBook": "有声书",
        }

        self.type_emoji_map = {
            "Movie": "🎬", "Series": "📺", "Season": "📺", "Episode": "📺",
            "Album": "🎵", "Song": "🎶", "Video": "📹", "Audio": "🎧",
            "Book": "📚", "AudioBook": "🎧", "Default": "🌟"
        }

        self.media_action_map = {
            "Movie": "上映", "Series": "更新", "Season": "开播", "Episode": "更新",
            "Album": "发布", "Song": "发布", "Video": "发布", "Audio": "发布",
            "Book": "上架", "AudioBook": "上架",
        }

        self.source_map = {
            MediaSource.JELLYFIN.value: "Jellyfin",
            MediaSource.EMBY.value: "Emby",
            MediaSource.PLEX.value: "Plex",
            MediaSource.SONARR.value: "Sonarr",
            MediaSource.RADARR.value: "Radarr",
            MediaSource.ANI_RSS.value: "Ani-RSS",
            MediaSource.DEFAULT.value: "媒体服务器"
        }

        # 平台前缀映射
        self.platform_prefix_map = {
            "aiocqhttp": "🤖",
            "telegram": "✈️",
            "gewechat": "💬",
            "qqofficial": "🤖",
            "lark": "🚀",
            "dingtalk": "📱",
            "discord": "🎮",
            "wecom": "💼",
            "default": "📢"
        }

        # 验证配置
        self.validate_config()

        # 启动HTTP服务器和定时任务
        asyncio.create_task(self.start_webhook_server())
        asyncio.create_task(self.start_batch_processor())

    def validate_config(self):
        """验证配置参数 - 优化配置验证逻辑"""
        # 配置验证规则
        validation_rules = [
            ("webhook_port", 60071, lambda x: isinstance(x, int) and 1 <= x <= 65535, "无效的端口号"),
            ("batch_interval_seconds", 300, lambda x: isinstance(x, int) and x >= 10, "批量处理间隔过短", 10),
            ("cache_ttl_seconds", 300, lambda x: isinstance(x, int) and x >= 60, "缓存TTL过短", 60),
            ("batch_min_size", 3, lambda x: isinstance(x, int) and x >= 1, "批量发送阈值无效", 1),
        ]

        for rule in validation_rules:
            key, default, validator, error_msg = rule[:4]
            min_value = rule[4] if len(rule) > 4 else default

            value = self.config.get(key, default)
            if not validator(value):
                logger.warning(f"{error_msg}: {value}，设置为 {min_value}")
                self.config[key] = min_value
                # 清除缓存中的旧值
                self._config_cache.pop(key, None)

    async def start_webhook_server(self):
        """启动HTTP Webhook服务器"""
        try:
            self.app = web.Application()
            self.app.router.add_post(
                self.webhook_path, self.handle_webhook
            )

            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, "0.0.0.0", self.webhook_port)
            await self.site.start()

            logger.info(f"Media Webhook 服务已启动，监听端口: {self.webhook_port}")
            logger.info(
                f"访问地址: http://localhost:{self.webhook_port}{self.webhook_path}"
            )

        except OSError as e:
            error_msg = (
                f"端口 {self.webhook_port} 已被占用，请更换端口"
                if "Address already in use" in str(e) or "Only one usage" in str(e)
                else f"网络错误: {e}"
            )
            logger.error(error_msg)
        except Exception as e:
            logger.error(f"启动 Webhook 服务器失败: {e}")

    async def handle_webhook(self, request: Request) -> Response:
        """处理Webhook请求"""
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

            # 尝试解析 JSON，如果失败则尝试修复或检查其他格式
            try:
                raw_data = json.loads(body_text)
                is_text_template = False
                logger.info("成功解析为 JSON 格式")
            except json.JSONDecodeError as e:
                logger.info(f"JSON 解析失败: {e}")

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
                    else:
                        logger.error("Webhook 请求体解析失败: 无效的JSON格式且不是已知的文本模板")
                        logger.error(f"完整请求体内容:\n{body_text}")
                        # 保存失败的请求到文件以供分析
                        import datetime
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"failed_webhook_{timestamp}.txt"
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(f"时间: {timestamp}\n")
                            f.write(f"User-Agent: {headers.get('user-agent', 'N/A')}\n")
                            f.write(f"Content-Type: {headers.get('content-type', 'N/A')}\n")
                            f.write(f"请求体:\n{body_text}")
                        logger.error(f"失败的请求已保存到: {filename}")
                        return Response(text="无效的数据格式", status=400)

            # 检测通知来源
            headers = dict(request.headers)
            if is_text_template:
                source = "ani-rss"
            else:
                source = self.detect_notification_source(raw_data, headers)

            # 处理不同来源的数据格式
            if source == "ani-rss":
                # Ani-RSS 消息保持原始格式，不进行数据转换或丰富
                media_data = raw_data
                logger.info("检测到 ani-rss 数据，保持原始格式直接发送")
            elif source == "emby":
                media_data = self.convert_emby_to_media_data(raw_data)
                logger.info("检测到 Emby 数据，已转换为标准格式")

                # 使用外部 API 丰富数据（TMDB → BGM.TV → 原始数据）
                media_data = await self.enrich_media_data_with_external_apis(media_data)
            elif source in ["jellyfin", "plex"]:
                # Jellyfin 和 Plex 使用通用的媒体数据处理
                media_data = self.convert_generic_media_data(raw_data)
                logger.info(f"检测到 {source.title()} 数据，已转换为标准格式")

                # 使用外部 API 丰富数据（TMDB → BGM.TV → 原始数据）
                media_data = await self.enrich_media_data_with_external_apis(media_data)
            else:
                media_data = raw_data

            # 检查重复请求
            if self._is_duplicate_request(media_data):
                logger.info("检测到重复请求，忽略")
                return Response(text="重复请求", status=200)

            # 添加到消息队列
            self._add_to_queue(media_data, source)
            return Response(text="消息已加入队列", status=200)

        except json.JSONDecodeError:
            logger.error("Webhook 请求体解析失败: 无效的JSON格式")
            return Response(text="无效的JSON格式", status=400)
        except Exception as e:
            logger.error(f"Webhook 处理出错: {e}")
            return Response(text="处理消息时发生内部错误", status=500)

    def _is_duplicate_request(self, media_data: Dict) -> bool:
        """检查是否为重复请求 - 使用哈希校验，排除图片以保持更高准确率"""
        request_hash = self._calculate_request_hash(media_data)
        if not request_hash:
            return False

        current_time = time.time()

        # 清理过期缓存
        self._cleanup_expired_cache(current_time)

        # 检查是否重复
        if request_hash in self.request_cache:
            cached_time = self.request_cache[request_hash]
            logger.debug(f"检测到重复请求，哈希: {request_hash[:8]}..., 缓存时间: {cached_time}")
            return True

        # 缓存新请求
        cache_ttl = self.cache_ttl_seconds
        self.request_cache[request_hash] = current_time + cache_ttl
        logger.debug(f"缓存新请求，哈希: {request_hash[:8]}..., 过期时间: {current_time + cache_ttl}")
        return False

    def _calculate_request_hash(self, media_data: Dict) -> Optional[str]:
        """计算请求哈希值 - 排除图片和不稳定字段以提高准确率"""
        try:
            # 根据数据来源选择不同的哈希策略
            if self._is_ani_rss_data(media_data):
                return self._calculate_ani_rss_hash(media_data)
            else:
                return self._calculate_standard_hash(media_data)
        except Exception as e:
            logger.error(f"计算请求哈希失败: {e}")
            return None

    def _is_ani_rss_data(self, media_data: Dict) -> bool:
        """判断是否为 Ani-RSS 数据"""
        return "meassage" in media_data or "text_template" in media_data

    def _calculate_ani_rss_hash(self, media_data: Dict) -> str:
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
                "data_type": "ani_rss_message"
            }
        elif "text_template" in media_data:
            template = media_data.get("text_template", "")
            hash_data = {
                "content_hash": hashlib.md5(template.encode()).hexdigest()[:16],
                "data_type": "ani_rss_template"
            }
        else:
            # 其他 Ani-RSS 格式
            content_str = json.dumps(media_data, sort_keys=True)
            hash_data = {
                "content_hash": hashlib.md5(content_str.encode()).hexdigest()[:16],
                "data_type": "ani_rss_other"
            }

        hash_string = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(hash_string.encode()).hexdigest()

    def _calculate_standard_hash(self, media_data: Dict) -> str:
        """计算标准媒体数据的哈希值 - 排除图片和时间戳等不稳定字段"""
        # 提取核心标识字段，排除图片URL、时间戳等不稳定字段
        hash_data = {
            "series_name": media_data.get("series_name", "").strip(),
            "item_name": media_data.get("item_name", "").strip(),
            "season_number": str(media_data.get("season_number", "")).strip(),
            "episode_number": str(media_data.get("episode_number", "")).strip(),
            "item_type": media_data.get("item_type", "").strip(),
            "year": str(media_data.get("year", "")).strip(),
        }

        # 移除空值以提高匹配准确率
        hash_data = {k: v for k, v in hash_data.items() if v}

        # 如果关键字段都为空，使用原始数据的部分内容
        if not hash_data:
            # 排除图片URL和时间戳等字段
            excluded_fields = {
                "image_url", "timestamp", "raw_message", "headers",
                "request_time", "processed_time", "cache_time"
            }
            filtered_data = {
                k: v for k, v in media_data.items()
                if k not in excluded_fields and not k.endswith("_url")
            }
            hash_data = {"fallback_content": str(filtered_data)}

        hash_string = json.dumps(hash_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(hash_string.encode()).hexdigest()

    def _cleanup_expired_cache(self, current_time: float):
        """清理过期缓存"""
        expired_keys = [
            key for key, expire_time in self.request_cache.items()
            if expire_time < current_time
        ]
        if expired_keys:
            logger.debug(f"清理 {len(expired_keys)} 个过期缓存项")
            for key in expired_keys:
                del self.request_cache[key]

    async def _add_to_queue(self, media_data: Dict, source: str):
        """添加消息到队列并智能发送 - 支持图片降级获取"""

        # 对于 Ani-RSS，需要特殊处理图片提取
        if source == "ani-rss":
            ani_rss_content = self.extract_ani_rss_content(media_data)
            image_url = ani_rss_content.get("image_url", "")
            message_text = ani_rss_content.get("text", "")
        else:
            image_url = media_data.get("image_url", "")
            message_text = self.generate_message_text(media_data, source)

            # 如果没有图片，尝试获取降级图片
            if not image_url:
                logger.info("通知没有图片，尝试获取降级图片...")
                fallback_image = await self.get_fallback_image(media_data)
                if fallback_image:
                    image_url = fallback_image
                    logger.info("成功获取降级图片")
                else:
                    logger.info("降级图片获取失败，将不发送图片")

        message_payload = {
            "image_url": image_url,
            "message_text": message_text,
            "timestamp": time.time(),
            "source": source,
        }

        self.message_queue.append(message_payload)

        source_name = self.source_map.get(source, source)
        item_type = media_data.get('item_type', 'Unknown') if source != "ani-rss" else "Ani-RSS"
        logger.info(f"新 {item_type} 通知已加入队列 [来源: {source_name}] {'(含图片)' if image_url else '(无图片)'}")

        # 智能发送逻辑：立即检查是否需要发送
        await self._check_and_send_messages()

    def _save_failed_request(self, body_text: str, headers: Dict):
        """保存失败的请求到文件"""
        try:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"failed_webhook_{timestamp}.txt"

            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"时间: {timestamp}\n")
                f.write(f"User-Agent: {headers.get('user-agent', 'N/A')}\n")
                f.write(f"Content-Type: {headers.get('content-type', 'N/A')}\n")
                f.write(f"请求体:\n{body_text}")

            logger.error(f"失败的请求已保存到: {filename}")
        except Exception as e:
            logger.error(f"保存失败请求时出错: {e}")

    def decode_html_entities(self, text: str) -> str:
        """解码HTML实体"""
        if not text:
            return ""
        return html.unescape(text)

    def try_fix_ani_rss_json(self, body_text: str) -> str:
        """尝试修复不完整的 ani-rss JSON"""
        try:
            # 检查是否包含 ani-rss 特征
            if "meassage" not in body_text:
                return ""

            # 尝试修复常见的不完整 JSON 问题
            fixed_text = body_text.strip()

            # 计算需要的闭合括号数量
            open_braces = fixed_text.count('{')
            close_braces = fixed_text.count('}')
            open_brackets = fixed_text.count('[')
            close_brackets = fixed_text.count(']')

            # 记录修复前的状态
            logger.info(f"JSON 修复分析: 开放括号 {{{open_braces}, [{open_brackets}, 闭合括号 }}{close_braces}, ]{close_brackets}")

            # 添加缺失的闭合符号（先添加中括号，再添加大括号）
            brackets_needed = open_brackets - close_brackets
            braces_needed = open_braces - close_braces

            if brackets_needed > 0:
                fixed_text += ']' * brackets_needed

            if braces_needed > 0:
                fixed_text += '}' * braces_needed

            # 验证修复后的 JSON
            try:
                parsed_data = json.loads(fixed_text)
                logger.info(f"成功修复 JSON，添加了 {braces_needed} 个 '}}' 和 {brackets_needed} 个 ']]'")

                # 验证数据结构
                if "meassage" in parsed_data:
                    messages = parsed_data["meassage"]
                    logger.info(f"修复后的 JSON 包含 {len(messages)} 条消息")

                return fixed_text
            except json.JSONDecodeError as e:
                logger.warning(f"修复后的 JSON 仍然无效: {e}")
                return ""

        except Exception as e:
            logger.warning(f"修复 JSON 时出错: {e}")
            return ""



    def is_emby_data(self, data: Dict) -> bool:
        """检查是否为 Emby 数据格式"""
        # 检查 Emby 特有的字段组合
        emby_fields = ["Title", "Description", "Date", "Event", "Item", "Server"]

        # 检查基本字段
        basic_match = sum(1 for field in emby_fields if field in data) >= 4

        # 检查 Item 字段的 Emby 特征
        item_data = data.get("Item", {})
        if isinstance(item_data, dict):
            emby_item_fields = ["ServerId", "Id", "Type", "Name"]
            item_match = sum(1 for field in emby_item_fields if field in item_data) >= 3
            return basic_match and item_match

        return basic_match

    def is_ani_rss_data(self, data: Dict) -> bool:
        """检查是否为 ani-rss 数据格式"""
        # 检查 ani-rss 特有的字段组合
        ani_rss_fields = [
            "notificationTemplate", "notificationType", "webHookMethod",
            "webHookUrl", "webHookBody", "statusList"
        ]

        # 如果包含多个 ani-rss 特有字段，则认为是 ani-rss 数据
        found_fields = sum(1 for field in ani_rss_fields if field in data)
        return found_fields >= 3

    def is_ani_rss_message_format(self, data: Dict) -> bool:
        """检查是否为 ani-rss 消息格式"""
        # 检查是否有 meassage 字段（注意拼写）
        if "meassage" in data:
            messages = data.get("meassage", [])
            if isinstance(messages, list) and len(messages) > 0:
                # 检查消息格式
                for msg in messages:
                    if isinstance(msg, dict) and "type" in msg and "data" in msg:
                        msg_type = msg.get("type")
                        if msg_type in ["image", "text"]:
                            return True
        return False

    def is_ani_rss_text_template(self, text: str) -> bool:
        """检查是否为 ani-rss 文本模板"""
        # 检查 ani-rss 文本模板的特征
        ani_rss_template_patterns = [
            "${emoji}", "${action}", "${title}", "${score}", "${tmdburl}",
            "${themoviedbName}", "${bgmUrl}", "${season}", "${episode}",
            "${subgroup}", "${currentEpisodeNumber}", "${totalEpisodeNumber}",
            "${year}", "${month}", "${date}", "${text}", "${downloadPath}",
            "${episodeTitle}"
        ]

        # 如果包含多个模板变量，则认为是 ani-rss 文本模板
        found_patterns = sum(1 for pattern in ani_rss_template_patterns if pattern in text)
        return found_patterns >= 3

    def parse_ani_rss_webhook_body(self, webhook_body: str) -> Dict:
        """解析 ani-rss 的 webHookBody 字段"""
        try:
            # ani-rss 的 webHookBody 可能包含模板变量
            # 尝试提取其中的结构信息
            if not webhook_body:
                return {}

            # 检查是否包含图片和文本信息
            has_image = "${image}" in webhook_body or "image" in webhook_body.lower()
            has_text = "${message}" in webhook_body or "text" in webhook_body.lower()

            return {
                "has_image": has_image,
                "has_text": has_text,
                "raw_body": webhook_body
            }
        except Exception as e:
            logger.warning(f"解析 ani-rss webHookBody 失败: {e}")
            return {}

    def convert_ani_rss_to_media_data(self, data: Dict) -> Dict:
        """将 ani-rss 数据转换为标准媒体数据格式"""
        try:
            # 解析 webHookBody
            webhook_body = data.get("webHookBody", "")
            body_info = self.parse_ani_rss_webhook_body(webhook_body)

            # 构建标准格式的媒体数据
            media_data = {
                "item_type": "Episode",  # ani-rss 主要处理动画剧集
                "series_name": "Ani-RSS 通知",
                "item_name": "动画更新通知",
                "overview": "来自 Ani-RSS 的动画更新通知",
                "runtime": "",
                "year": "",
                "season_number": "",
                "episode_number": "",
            }

            # 如果支持图片，添加默认图片
            if body_info.get("has_image"):
                media_data["image_url"] = "https://picsum.photos/300/450"

            return media_data

        except Exception as e:
            logger.error(f"转换 ani-rss 数据失败: {e}")
            # 返回基本的媒体数据
            return {
                "item_type": "Episode",
                "series_name": "Ani-RSS 通知",
                "item_name": "动画更新通知",
                "overview": "来自 Ani-RSS 的动画更新通知"
            }

    def parse_ani_rss_text_template(self, template_text: str) -> Dict:
        """解析 ani-rss 文本模板，提取变量信息"""
        import re

        # 提取模板变量的值（这里是模拟，实际值由 ani-rss 填充）
        template_vars = {}

        # 查找所有模板变量
        pattern = r'\$\{([^}]+)\}'
        matches = re.findall(pattern, template_text)

        for var in matches:
            template_vars[var] = f"${{{var}}}"  # 保留模板格式

        return template_vars

    def convert_ani_rss_text_template_to_media_data(self, template_text: str) -> Dict:
        """将 ani-rss 文本模板转换为标准媒体数据格式"""
        try:
            # 解析模板变量
            template_vars = self.parse_ani_rss_text_template(template_text)

            # 构建标准格式的媒体数据
            media_data = {
                "item_type": "Episode",
                "series_name": template_vars.get("title", "Ani-RSS 通知"),
                "item_name": template_vars.get("episodeTitle", "动画更新通知"),
                "overview": f"来自 Ani-RSS 的动画更新通知\n\n原始模板:\n{template_text[:200]}...",
                "runtime": "",
                "year": template_vars.get("year", ""),
                "season_number": template_vars.get("season", ""),
                "episode_number": template_vars.get("episode", ""),
            }

            # 添加额外信息到 overview
            extra_info = []
            if "score" in template_vars:
                extra_info.append(f"评分: {template_vars['score']}")
            if "subgroup" in template_vars:
                extra_info.append(f"字幕组: {template_vars['subgroup']}")
            if "currentEpisodeNumber" in template_vars and "totalEpisodeNumber" in template_vars:
                extra_info.append(f"进度: {template_vars['currentEpisodeNumber']}/{template_vars['totalEpisodeNumber']}")

            if extra_info:
                media_data["overview"] += "\n\n" + "\n".join(extra_info)

            # 检查是否有图片相关信息（虽然模板中没有直接的图片URL）
            # 可以根据需要添加默认图片
            if any(var in template_vars for var in ["tmdburl", "bgmUrl"]):
                media_data["image_url"] = "https://picsum.photos/300/450"

            return media_data

        except Exception as e:
            logger.error(f"转换 ani-rss 文本模板失败: {e}")
            # 返回基本的媒体数据
            return {
                "item_type": "Episode",
                "series_name": "Ani-RSS 通知",
                "item_name": "动画更新通知",
                "overview": f"来自 Ani-RSS 的动画更新通知\n\n{template_text[:100]}..."
            }

    def convert_ani_rss_message_to_media_data(self, data: Dict) -> Dict:
        """将 ani-rss 消息格式转换为标准媒体数据格式"""
        try:
            messages = data.get("meassage", [])

            # 提取图片和文本信息
            image_url = ""
            text_content = ""

            for msg in messages:
                if isinstance(msg, dict):
                    msg_type = msg.get("type")
                    msg_data = msg.get("data", {})

                    if msg_type == "image":
                        image_url = msg_data.get("file", "")
                    elif msg_type == "text":
                        text_content = msg_data.get("text", "")

            # 解析文本内容中的信息
            media_data = self.parse_ani_rss_text_content(text_content)

            # 添加图片URL
            if image_url:
                media_data["image_url"] = image_url

            return media_data

        except Exception as e:
            logger.error(f"转换 ani-rss 消息格式失败: {e}")
            return {
                "item_type": "Episode",
                "series_name": "Ani-RSS 通知",
                "item_name": "动画更新通知",
                "overview": "来自 Ani-RSS 的动画更新通知"
            }

    def parse_ani_rss_text_content(self, text_content: str) -> Dict:
        """解析 ani-rss 文本内容，提取媒体信息"""
        try:
            # 初始化媒体数据
            media_data = {
                "item_type": "Episode",
                "series_name": "Ani-RSS 通知",
                "item_name": "动画更新通知",
                "overview": text_content,
                "runtime": "",
                "year": "",
                "season_number": "",
                "episode_number": "",
            }

            # 解析文本中的信息
            lines = text_content.split('\n')
            for line in lines:
                line = line.strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    if key == "标题":
                        media_data["series_name"] = value
                    elif key == "季":
                        media_data["season_number"] = value
                    elif key == "集":
                        media_data["episode_number"] = value
                    elif key == "TMDB集标题":
                        media_data["item_name"] = value
                    elif key == "首播":
                        # 提取年份
                        import re
                        year_match = re.search(r'(\d{4})', value)
                        if year_match:
                            media_data["year"] = year_match.group(1)

            return media_data

        except Exception as e:
            logger.error(f"解析 ani-rss 文本内容失败: {e}")
            return {
                "item_type": "Episode",
                "series_name": "Ani-RSS 通知",
                "item_name": "动画更新通知",
                "overview": text_content
            }

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
                # 从 Title 中提取剧集名称
                title = data.get("Title", "")
                if " - " in title:
                    # 格式: "新 - S1, Ep3 - Tsuihousha Shokudou e Youkoso! - 03 在 AFXS-210103060"
                    parts = title.split(" - ")
                    if len(parts) >= 3:
                        series_name = parts[2].strip()

                # 如果从 Title 提取失败，使用 Item.Name
                if not series_name:
                    series_name = item_name

                # 提取季集信息
                season_number = str(item.get("ParentIndexNumber", ""))
                episode_number = str(item.get("IndexNumber", ""))

            # 构建媒体数据（移除剧情简介、服务器、集名称）
            media_data = {
                "item_type": item_type,
                "series_name": series_name,
                "season_number": season_number,
                "episode_number": episode_number,
                "runtime": "",
                "year": "",
                "event_type": data.get("Event", ""),
                # 保留原始数据用于 TMDB 匹配
                "emby_item_id": item.get("Id", ""),
                "emby_path": item.get("Path", ""),
                "emby_original_name": item_name,
            }

            # 处理运行时间
            runtime_ticks = item.get("RunTimeTicks")
            if runtime_ticks:
                # Emby 使用 ticks (1 tick = 100 nanoseconds)
                # 转换为分钟
                minutes = int(runtime_ticks / 10000000 / 60)
                media_data["runtime"] = f"{minutes}分钟"

            logger.info(f"Emby 数据转换完成，准备 TMDB 匹配: {media_data}")
            return media_data

        except Exception as e:
            logger.error(f"转换 Emby 数据失败: {e}")
            return {
                "item_type": "Episode",
                "series_name": "Emby 通知",
                "season_number": "",
                "episode_number": "",
                "overview": f"来自 Emby 的媒体更新通知"
            }

    def convert_generic_media_data(self, data: Dict) -> Dict:
        """将通用媒体数据转换为标准格式（适用于 Jellyfin、Plex 等）"""
        try:
            # 提取基本信息
            item_type = data.get("ItemType") or data.get("Type") or data.get("item_type", "Episode")

            # 处理剧集名称
            series_name = (
                data.get("SeriesName") or
                data.get("series_name") or
                data.get("Name") or
                data.get("Title") or
                ""
            )

            # 处理集名称
            item_name = (
                data.get("Name") or
                data.get("item_name") or
                data.get("EpisodeName") or
                ""
            )

            # 处理季集信息
            season_number = str(data.get("SeasonNumber") or data.get("season_number") or "")
            episode_number = str(data.get("IndexNumber") or data.get("episode_number") or "")

            # 处理年份
            year = ""
            if data.get("Year"):
                year = str(data.get("Year"))
            elif data.get("ProductionYear"):
                year = str(data.get("ProductionYear"))

            # 构建媒体数据
            media_data = {
                "item_type": item_type,
                "series_name": series_name,
                "item_name": item_name,
                "season_number": season_number,
                "episode_number": episode_number,
                "overview": data.get("Overview") or data.get("overview", ""),
                "runtime": "",
                "year": year,
                "event_type": data.get("Event") or data.get("event_type", ""),
            }

            # 处理运行时间
            runtime_ticks = data.get("RunTimeTicks")
            if runtime_ticks:
                # 转换为分钟
                minutes = int(runtime_ticks / 10000000 / 60)
                media_data["runtime"] = f"{minutes}分钟"
            elif data.get("runtime"):
                media_data["runtime"] = data.get("runtime")

            logger.info(f"通用媒体数据转换完成，准备数据丰富: {media_data}")
            return media_data

        except Exception as e:
            logger.error(f"转换通用媒体数据失败: {e}")
            return {
                "item_type": "Episode",
                "series_name": "媒体通知",
                "season_number": "",
                "episode_number": "",
                "overview": f"来自媒体服务器的更新通知"
            }

    async def search_tmdb_tv_show(self, series_name: str) -> Optional[Dict]:
        """搜索 TMDB TV 节目"""
        if not self.tmdb_api_key:
            logger.warning("TMDB API Key 未配置，跳过 TMDB 查询")
            return None

        try:
            # 检查缓存
            cache_key = f"tv_search_{series_name}"
            if cache_key in self.tmdb_cache:
                logger.info(f"使用 TMDB 缓存: {series_name}")
                return self.tmdb_cache[cache_key]

            # 搜索 TV 节目
            search_url = f"{self.tmdb_base_url}/search/tv"
            params = {
                "api_key": self.tmdb_api_key,
                "query": series_name,
                "language": "zh-CN"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        if results:
                            # 返回第一个匹配结果
                            tv_show = results[0]
                            self.tmdb_cache[cache_key] = tv_show
                            logger.info(f"TMDB TV 搜索成功: {series_name} -> {tv_show.get('name')}")
                            return tv_show
                    else:
                        logger.warning(f"TMDB TV 搜索失败: {response.status}")

            return None

        except Exception as e:
            logger.error(f"TMDB TV 搜索出错: {e}")
            return None

    async def get_tmdb_episode_details(self, tv_id: int, season_number: int, episode_number: int) -> Optional[Dict]:
        """获取 TMDB 剧集详情"""
        if not self.tmdb_api_key:
            return None

        try:
            # 检查缓存
            cache_key = f"episode_{tv_id}_{season_number}_{episode_number}"
            if cache_key in self.tmdb_cache:
                logger.info(f"使用 TMDB 剧集缓存: {cache_key}")
                return self.tmdb_cache[cache_key]

            # 获取剧集详情
            episode_url = f"{self.tmdb_base_url}/tv/{tv_id}/season/{season_number}/episode/{episode_number}"
            params = {
                "api_key": self.tmdb_api_key,
                "language": "zh-CN"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(episode_url, params=params) as response:
                    if response.status == 200:
                        episode_data = await response.json()
                        self.tmdb_cache[cache_key] = episode_data
                        logger.info(f"TMDB 剧集详情获取成功: {cache_key}")
                        return episode_data
                    else:
                        logger.warning(f"TMDB 剧集详情获取失败: {response.status}")

            return None

        except Exception as e:
            logger.error(f"TMDB 剧集详情获取出错: {e}")
            return None

    async def enrich_media_data_with_external_apis(self, media_data: Dict) -> Dict:
        """使用外部 API 丰富媒体信息（TMDB → BGM.TV → 原始数据）"""
        try:
            if media_data.get("item_type") != "Episode":
                return media_data

            series_name = media_data.get("series_name", "")
            season_number = media_data.get("season_number", "")
            episode_number = media_data.get("episode_number", "")

            if not all([series_name, episode_number]):
                logger.warning("缺少必要信息，跳过外部 API 查询")
                return media_data

            logger.info(f"开始数据丰富流程: {series_name} 第{episode_number}集")

            # 第一步：尝试 TMDB
            if self.tmdb_api_key and season_number:
                logger.info("尝试使用 TMDB 获取数据...")
                enriched_data = await self.try_tmdb_enrichment(media_data)
                if enriched_data.get("tmdb_enriched"):
                    logger.info("TMDB 数据获取成功")
                    return enriched_data
                else:
                    logger.info("TMDB 数据获取失败，尝试 BGM.TV")
            else:
                logger.info("TMDB API Key 未配置或缺少季数信息，跳过 TMDB，尝试 BGM.TV")

            # 第二步：尝试 BGM.TV
            logger.info("尝试使用 BGM.TV 获取数据...")
            enriched_data = await self.enrich_media_data_with_bgm(media_data)
            if enriched_data.get("bgm_enriched"):
                logger.info("BGM.TV 数据获取成功")
                return enriched_data
            else:
                logger.info("BGM.TV 数据获取失败")

            # 第三步：尝试补全图片（如果没有图片）
            if not media_data.get("image_url"):
                logger.info("尝试补全图片信息...")
                image_url = await self.get_fallback_image(media_data)
                if image_url:
                    media_data["image_url"] = image_url
                    logger.info("成功获取降级图片")

            # 第四步：返回原始数据
            logger.info("所有外部 API 获取失败，使用原始数据")
            return media_data

        except Exception as e:
            logger.error(f"数据丰富流程失败: {e}")
            return media_data

    async def get_fallback_image(self, media_data: Dict) -> str:
        """获取降级图片 - TMDB → BGM.TV → 无图片"""
        try:
            series_name = media_data.get("series_name", "")
            if not series_name:
                return ""

            # 尝试从 TMDB 获取图片
            if self.tmdb_api_key:
                logger.info("尝试从 TMDB 获取图片...")
                image_url = await self.get_tmdb_image(series_name)
                if image_url:
                    logger.info("TMDB 图片获取成功")
                    return image_url

            # 尝试从 BGM.TV 获取图片
            logger.info("尝试从 BGM.TV 获取图片...")
            image_url = await self.get_bgm_image(series_name)
            if image_url:
                logger.info("BGM.TV 图片获取成功")
                return image_url

            logger.info("所有图片源获取失败")
            return ""

        except Exception as e:
            logger.error(f"获取降级图片失败: {e}")
            return ""

    async def get_tmdb_image(self, series_name: str) -> str:
        """从 TMDB 获取图片"""
        try:
            tv_show = await self.search_tmdb_tv_show(series_name)
            if tv_show and tv_show.get("poster_path"):
                poster_path = tv_show["poster_path"]
                return f"https://image.tmdb.org/t/p/w500{poster_path}"
            return ""
        except Exception as e:
            logger.error(f"TMDB 图片获取失败: {e}")
            return ""

    async def get_bgm_image(self, series_name: str) -> str:
        """从 BGM.TV 获取图片"""
        try:
            subject = await self.search_bgm_tv_show(series_name)
            if subject and subject.get("images"):
                images = subject["images"]
                # 优先使用大图
                return images.get("large", images.get("medium", images.get("small", "")))
            return ""
        except Exception as e:
            logger.error(f"BGM.TV 图片获取失败: {e}")
            return ""

    async def try_tmdb_enrichment(self, media_data: Dict) -> Dict:
        """尝试使用 TMDB 丰富数据"""
        try:
            series_name = media_data.get("series_name", "")
            season_number = media_data.get("season_number", "")
            episode_number = media_data.get("episode_number", "")

            # 搜索 TV 节目
            tv_show = await self.search_tmdb_tv_show(series_name)
            if not tv_show:
                return media_data

            tv_id = tv_show.get("id")
            if not tv_id:
                return media_data

            # 获取剧集详情
            episode_details = await self.get_tmdb_episode_details(
                tv_id, int(season_number), int(episode_number)
            )

            if episode_details:
                # 更新媒体数据
                enriched_data = media_data.copy()

                # 更新剧集名称
                episode_name = episode_details.get("name")
                if episode_name:
                    enriched_data["item_name"] = episode_name

                # 更新剧情简介
                overview = episode_details.get("overview")
                if overview:
                    enriched_data["overview"] = overview

                # 更新年份
                air_date = episode_details.get("air_date")
                if air_date:
                    enriched_data["year"] = air_date[:4]

                # 添加 TMDB 信息标记
                enriched_data["tmdb_enriched"] = True
                enriched_data["tmdb_tv_id"] = tv_id
                enriched_data["tmdb_episode_id"] = episode_details.get("id")

                return enriched_data

            return media_data

        except Exception as e:
            logger.error(f"TMDB 数据丰富失败: {e}")
            return media_data

    async def search_bgm_tv_show(self, series_name: str) -> Optional[Dict]:
        """搜索 BGM.TV 节目"""
        try:
            # 检查缓存
            cache_key = f"bgm_search_{series_name}"
            if cache_key in self.bgm_cache:
                logger.info(f"使用 BGM.TV 缓存: {series_name}")
                return self.bgm_cache[cache_key]

            # 搜索节目
            search_url = f"{self.bgm_base_url}/search/subject/{series_name}"
            params = {
                "type": 2,  # 动画类型
                "responseGroup": "large"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("list", [])
                        if results:
                            # 返回第一个匹配结果
                            subject = results[0]
                            self.bgm_cache[cache_key] = subject
                            logger.info(f"BGM.TV 搜索成功: {series_name} -> {subject.get('name_cn') or subject.get('name')}")
                            return subject
                    else:
                        logger.warning(f"BGM.TV 搜索失败: {response.status}")

            return None

        except Exception as e:
            logger.error(f"BGM.TV 搜索出错: {e}")
            return None

    async def get_bgm_episode_details(self, subject_id: int, episode_number: int) -> Optional[Dict]:
        """获取 BGM.TV 剧集详情"""
        try:
            # 检查缓存
            cache_key = f"bgm_episode_{subject_id}_{episode_number}"
            if cache_key in self.bgm_cache:
                logger.info(f"使用 BGM.TV 剧集缓存: {cache_key}")
                return self.bgm_cache[cache_key]

            # 获取剧集列表
            episodes_url = f"{self.bgm_base_url}/subject/{subject_id}/ep"

            async with aiohttp.ClientSession() as session:
                async with session.get(episodes_url) as response:
                    if response.status == 200:
                        episodes_data = await response.json()
                        episodes = episodes_data.get("data", [])

                        # 查找对应集数
                        for episode in episodes:
                            if episode.get("sort") == episode_number:
                                self.bgm_cache[cache_key] = episode
                                logger.info(f"BGM.TV 剧集详情获取成功: {cache_key}")
                                return episode
                    else:
                        logger.warning(f"BGM.TV 剧集详情获取失败: {response.status}")

            return None

        except Exception as e:
            logger.error(f"BGM.TV 剧集详情获取出错: {e}")
            return None

    async def enrich_media_data_with_bgm(self, media_data: Dict) -> Dict:
        """使用 BGM.TV 数据丰富媒体信息"""
        try:
            if media_data.get("item_type") != "Episode":
                return media_data

            series_name = media_data.get("series_name", "")
            episode_number = media_data.get("episode_number", "")

            if not all([series_name, episode_number]):
                logger.warning("缺少必要信息，跳过 BGM.TV 查询")
                return media_data

            # 搜索节目
            subject = await self.search_bgm_tv_show(series_name)
            if not subject:
                logger.info(f"BGM.TV 未找到匹配的节目: {series_name}")
                return media_data

            subject_id = subject.get("id")
            if not subject_id:
                return media_data

            # 获取剧集详情
            episode_details = await self.get_bgm_episode_details(subject_id, int(episode_number))

            if episode_details:
                # 更新媒体数据
                enriched_data = media_data.copy()

                # 更新剧集名称
                episode_name = episode_details.get("name_cn") or episode_details.get("name")
                if episode_name:
                    enriched_data["item_name"] = episode_name

                # 更新剧情简介
                episode_desc = episode_details.get("desc")
                if episode_desc:
                    enriched_data["overview"] = episode_desc

                # 更新播出日期
                air_date = episode_details.get("airdate")
                if air_date:
                    enriched_data["year"] = air_date[:4]

                # 添加 BGM.TV 信息标记
                enriched_data["bgm_enriched"] = True
                enriched_data["bgm_subject_id"] = subject_id
                enriched_data["bgm_episode_id"] = episode_details.get("id")

                logger.info(f"BGM.TV 数据丰富完成: {series_name} 第{episode_number}集")
                return enriched_data

            return media_data

        except Exception as e:
            logger.error(f"BGM.TV 数据丰富失败: {e}")
            return media_data

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
        elif "ani-rss" in user_agent:
            return "ani-rss"

        # 检查 Emby 数据格式特征
        if self.is_emby_data(data):
            return "emby"

        # 检查 ani-rss 数据格式特征
        if self.is_ani_rss_message_format(data):
            return "ani-rss"

        # 检查传统 ani-rss 配置格式
        if self.is_ani_rss_data(data):
            return "ani-rss"

        # 检查数据字段特征
        if "jellyfin" in str(data).lower():
            return "jellyfin"
        elif "emby" in str(data).lower():
            return "emby"
        elif "plex" in str(data).lower():
            return "plex"
        elif "sonarr" in str(data).lower():
            return "sonarr"
        elif "radarr" in str(data).lower():
            return "radarr"
        elif "overseerr" in str(data).lower():
            return "overseerr"
        elif "tautulli" in str(data).lower():
            return "tautulli"

        # 检查特定字段
        if data.get("server_name") or data.get("server_version"):
            return "jellyfin"  # 常见于Jellyfin
        elif data.get("application") == "Emby":
            return "emby"
        elif data.get("product") == "Plex":
            return "plex"

        return "default"

    def get_platform_prefix(self) -> str:
        """获取平台前缀"""
        platform_name = self.config.get("platform_name", "aiocqhttp")
        return self.platform_prefix_map.get(platform_name.lower(), self.platform_prefix_map["default"])

    def generate_main_section(self, data: Dict) -> str:
        """生成消息主要部分"""
        sections = []
        item_type = data.get("item_type", "")
        series_name = data.get("series_name", "")
        item_name = data.get("item_name", "")
        year = data.get("year", "")
        season_number = data.get("season_number", "")
        episode_number = data.get("episode_number", "")

        # 根据媒体类型生成不同的信息结构
        if item_type == "Movie":
            # 电影信息
            if item_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"电影名称: {item_name}{year_text}")
            elif series_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"电影名称: {series_name}{year_text}")

        elif item_type in ["Series", "Season"]:
            # 剧集/剧季信息
            if series_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"剧集名称: {series_name}{year_text}")
            if item_type == "Season" and season_number:
                sections.append(f"季号: 第{season_number}季")
            if item_name and item_name != series_name:
                sections.append(f"季名称: {item_name}")

        elif item_type == "Episode":
            # 剧集单集信息
            if series_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"剧集名称: {series_name}{year_text}")
            if season_number and episode_number:
                s_num = str(season_number).zfill(2)
                e_num = str(episode_number).zfill(2)
                sections.append(f"集号: S{s_num}E{e_num}")
            if item_name:
                sections.append(f"集名称: {item_name}")

        elif item_type == "Album":
            # 专辑信息
            if item_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"专辑名称: {item_name}{year_text}")
            if series_name and series_name != item_name:
                sections.append(f"艺术家: {series_name}")

        elif item_type == "Song":
            # 歌曲信息
            if item_name:
                sections.append(f"歌曲名称: {item_name}")
            if series_name:
                sections.append(f"艺术家: {series_name}")
            if year:
                sections.append(f"发行年份: {year}")

        elif item_type == "Book":
            # 图书信息
            if item_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"书名: {item_name}{year_text}")
            if series_name and series_name != item_name:
                sections.append(f"作者: {series_name}")

        elif item_type in ["Video", "Audio", "AudioBook"]:
            # 视频/音频信息
            if item_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"标题: {item_name}{year_text}")
            if series_name and series_name != item_name:
                sections.append(f"创作者: {series_name}")

        else:
            # 默认格式
            if series_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"名称: {series_name}{year_text}")
            elif item_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"名称: {item_name}{year_text}")

        return "\n".join(sections)

    def generate_message_text(self, data: Dict, source: str = "default") -> str:
        """生成消息文本"""

        # 对于 Ani-RSS，直接使用原始数据格式
        if source == "ani-rss":
            return self.generate_ani_rss_raw_message(data)

        item_type = data.get("item_type", "")
        cn_type = self.media_type_map.get(item_type, item_type)
        emoji = self.type_emoji_map.get(item_type, self.type_emoji_map["Default"])
        action = self.media_action_map.get(item_type, "上线")

        # 检查配置选项
        show_platform_prefix = self.config.get("show_platform_prefix", True)
        show_source_info = self.config.get("show_source_info", True)

        # 构建标题
        title_parts = []

        # 添加平台前缀
        if show_platform_prefix:
            platform_prefix = self.get_platform_prefix()
            title_parts.append(platform_prefix)

        # 根据媒体类型生成合适的标题
        title_text = self.generate_title_by_type(item_type, cn_type, emoji, action, data)
        title_parts.append(title_text)

        # 添加来源信息
        if show_source_info and source != "default":
            source_name = self.source_map.get(source.lower(), self.source_map["default"])
            title_parts.append(f"[{source_name}]")

        title = " ".join(title_parts)
        message_parts = [title, self.generate_main_section(data)]

        # 添加详细信息
        self.add_detail_sections(message_parts, data, item_type)

        return "\n\n".join(message_parts)

    def extract_ani_rss_content(self, data: Dict) -> Dict:
        """提取 Ani-RSS 的内容（包括图片和文本）"""
        try:
            result = {
                "text": "",
                "image_url": ""
            }

            # 检查是否为 Ani-RSS 真实消息格式
            if "meassage" in data:
                messages = data.get("meassage", [])

                for msg in messages:
                    if isinstance(msg, dict):
                        msg_type = msg.get("type")
                        msg_data = msg.get("data", {})

                        if msg_type == "text":
                            result["text"] = msg_data.get("text", "")
                        elif msg_type == "image":
                            result["image_url"] = msg_data.get("file", "")

                return result

            # 检查是否为文本模板格式
            if "text_template" in data:
                result["text"] = data.get("text_template", "")
                return result

            # 其他格式，尝试提取文本内容
            if isinstance(data, dict):
                # 查找可能的文本字段
                for key in ["text", "message", "content", "body"]:
                    if key in data and isinstance(data[key], str):
                        result["text"] = data[key]
                        break

                # 查找可能的图片字段
                for key in ["image", "image_url", "picture", "cover"]:
                    if key in data and isinstance(data[key], str):
                        result["image_url"] = data[key]
                        break

                # 如果没有找到文本字段，返回 JSON 字符串
                if not result["text"]:
                    import json
                    result["text"] = json.dumps(data, ensure_ascii=False, indent=2)

                return result

            # 如果是字符串，直接返回
            if isinstance(data, str):
                result["text"] = data
                return result

            # 默认情况
            result["text"] = "来自 Ani-RSS 的通知"
            return result

        except Exception as e:
            logger.error(f"提取 Ani-RSS 内容失败: {e}")
            return {
                "text": "来自 Ani-RSS 的通知",
                "image_url": ""
            }

    def generate_ani_rss_raw_message(self, data: Dict) -> str:
        """为 Ani-RSS 生成原始格式消息（仅返回文本部分）"""
        content = self.extract_ani_rss_content(data)
        return content["text"]

    def generate_title_by_type(self, item_type: str, cn_type: str, emoji: str, action: str, data: Dict) -> str:
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

    def add_detail_sections(self, message_parts: List, data: Dict, item_type: str) -> None:
        """添加详细信息部分"""
        # 剧情简介/内容描述
        overview = data.get("overview", "")
        if overview:
            decoded_overview = self.decode_html_entities(overview)
            if item_type == "Movie":
                message_parts.append(f"\n剧情简介:\n{decoded_overview}")
            elif item_type in ["Series", "Season", "Episode"]:
                message_parts.append(f"\n剧情简介:\n{decoded_overview}")
            elif item_type == "Album":
                message_parts.append(f"\n专辑介绍:\n{decoded_overview}")
            elif item_type == "Song":
                message_parts.append(f"\n歌曲介绍:\n{decoded_overview}")
            elif item_type == "Book":
                message_parts.append(f"\n内容简介:\n{decoded_overview}")
            else:
                message_parts.append(f"\n内容简介:\n{decoded_overview}")

        # 时长信息
        runtime = data.get("runtime", "")
        if runtime:
            if item_type == "Movie":
                message_parts.append(f"\n片长: {runtime}")
            elif item_type in ["Episode", "Video"]:
                message_parts.append(f"\n时长: {runtime}")
            elif item_type == "Song":
                message_parts.append(f"\n时长: {runtime}")
            else:
                message_parts.append(f"\n时长: {runtime}")

        # 数据来源标记
        if data.get("tmdb_enriched"):
            message_parts.append("\n✨ 数据来源: TMDB")
        elif data.get("bgm_enriched"):
            message_parts.append("\n✨ 数据来源: BGM.TV")

    def supports_forward_messages(self, platform_name: str) -> bool:
        """检查平台是否支持合并转发功能"""
        # 支持合并转发的平台列表
        forward_supported_platforms = {
            "aiocqhttp",  # OneBot V11 标准，支持 Node 组件
            # 其他支持合并转发的平台可以在这里添加
        }

        return platform_name.lower() in forward_supported_platforms

    async def fetch_bgm_data(self) -> Optional[Dict]:
        """从 bgm.tv 获取随机剧集数据"""
        try:
            # BGM.TV API 端点
            # 获取热门动画列表
            api_url = "https://api.bgm.tv/search/subject/动画"

            headers = {
                'User-Agent': 'AstrBot-MediaWebhook/1.0.0 (https://github.com/Soulter/AstrBot)',
                'Accept': 'application/json'
            }

            async with aiohttp.ClientSession() as session:
                # 获取搜索结果
                async with session.get(api_url, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        logger.warning(f"BGM.TV API 请求失败: {resp.status}")
                        return None

                    data = await resp.json()

                    if not data.get('list'):
                        logger.warning("BGM.TV API 返回空列表")
                        return None

                    # 随机选择一个条目
                    subjects = data['list']
                    if not subjects:
                        return None

                    subject = random.choice(subjects)

                    # 获取详细信息
                    subject_id = subject.get('id')
                    if subject_id:
                        detail_url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
                        async with session.get(detail_url, headers=headers, timeout=10) as detail_resp:
                            if detail_resp.status == 200:
                                detail_data = await detail_resp.json()

                                # 转换为插件需要的格式
                                return self.convert_bgm_to_test_data(detail_data)

                    # 如果获取详细信息失败，使用基本信息
                    return self.convert_bgm_to_test_data(subject)

        except asyncio.TimeoutError:
            logger.warning("BGM.TV API 请求超时")
            return None
        except Exception as e:
            logger.warning(f"获取 BGM.TV 数据失败: {e}")
            return None

    def convert_bgm_to_test_data(self, bgm_data: Dict) -> Dict:
        """将 BGM.TV 数据转换为测试数据格式"""
        try:
            # 提取基本信息
            name = bgm_data.get('name', '未知作品')
            name_cn = bgm_data.get('name_cn', name)

            # 使用中文名称，如果没有则使用原名
            series_name = name_cn if name_cn else name

            # 提取年份
            year = ""
            air_date = bgm_data.get('air_date', '')
            if air_date:
                try:
                    year = air_date.split('-')[0]
                except:
                    pass

            # 提取简介
            summary = bgm_data.get('summary', '')
            if len(summary) > 200:
                summary = summary[:200] + "..."

            # 提取图片
            image_url = ""
            images = bgm_data.get('images', {})
            if images:
                # 优先使用大图
                image_url = images.get('large', images.get('medium', images.get('small', '')))

            # 随机生成集数信息
            season_number = random.randint(1, 3)
            episode_number = random.randint(1, 24)

            return {
                "item_type": "Episode",
                "series_name": series_name,
                "year": year,
                "item_name": f"第{episode_number}话",
                "season_number": season_number,
                "episode_number": episode_number,
                "overview": summary or "暂无剧情简介",
                "runtime": f"{random.randint(20, 30)}分钟",
                "image_url": image_url
            }

        except Exception as e:
            logger.warning(f"转换 BGM.TV 数据失败: {e}")
            # 返回默认数据
            return {
                "item_type": "Episode",
                "series_name": "数据转换失败",
                "year": "2024",
                "item_name": "测试集名称",
                "season_number": 1,
                "episode_number": 1,
                "overview": "无法获取剧情简介",
                "runtime": "24分钟",
            }

    async def start_batch_processor(self):
        """启动批量处理任务"""
        while True:
            try:
                interval = self.config.get("batch_interval_seconds", 300)
                await asyncio.sleep(interval)
                await self.process_message_queue()
            except Exception as e:
                logger.error(f"批量处理任务出错: {e}")

    async def process_message_queue(self):
        """处理消息队列 - 优化配置获取"""
        if not self.message_queue:
            return

        if not self.group_id:
            logger.warning("未配置群组ID，无法发送消息")
            return

        # 清理 group_id，移除可能的冒号
        group_id = str(self.group_id).replace(":", "_")
        logger.debug(f"使用群组ID: {group_id}")

        messages = self.message_queue.copy()
        self.message_queue.clear()

        logger.info(f"从队列中取出 {len(messages)} 条待发消息")

        try:
            # 使用缓存的配置值
            batch_min_size = self.batch_min_size
            platform_name = self.platform_name
            force_individual = self.force_individual_send

            # 根据 aiocqhttp 文档优化的发送逻辑
            if len(messages) < batch_min_size:
                # 低于 batch_min_size 阈值，使用单独发送（符合 aiocqhttp 文档建议）
                logger.info(f"消息数量 {len(messages)} 低于批量发送阈值 {batch_min_size}，使用单独发送")
                await self.send_individual_messages(group_id, messages)
            elif force_individual:
                # 强制单独发送
                logger.info(f"配置强制单独发送，将 {len(messages)} 条消息逐个发送")
                await self.send_individual_messages(group_id, messages)
            elif self.supports_forward_messages(platform_name):
                # 达到或超过 batch_min_size 阈值，使用合并转发
                logger.info(f"消息数量 {len(messages)} 达到阈值 {batch_min_size}，平台 {platform_name} 支持合并转发，使用合并发送")
                await self.send_batch_messages(group_id, messages)
            else:
                # 平台不支持合并转发，回退到单独发送
                logger.info(f"平台 {platform_name} 不支持合并转发，将 {len(messages)} 条消息逐个发送")
                await self.send_individual_messages(group_id, messages)

        except Exception as e:
            logger.error(f"发送消息时出错: {e}")

    async def send_batch_messages(self, group_id: str, messages: List[Dict]):
        """发送批量合并转发消息（仅支持 aiocqhttp 等平台）- 优化配置获取"""
        logger.info(f"使用合并转发发送 {len(messages)} 条消息")

        # 根据 aiocqhttp 文档，低于 batch_min_size 使用单独发送
        if len(messages) < self.batch_min_size:
            logger.info(f"消息数量 {len(messages)} 低于批量阈值 {self.batch_min_size}，改为单独发送")
            await self.send_individual_messages(group_id, messages)
            return

        # 构建合并转发节点
        forward_nodes = []

        for msg in messages:
            try:
                content = []

                # 添加图片（如果有）
                if msg.get("image_url"):
                    content.append(Comp.Image.fromURL(msg["image_url"]))

                # 处理消息文本
                message_text = msg["message_text"]

                # 对于合并转发，也使用相同的文本处理
                if self.platform_name.lower() == "aiocqhttp":
                    processed_text = self._process_text_for_aiocqhttp(message_text)
                    content.append(Comp.Plain(processed_text))
                else:
                    content.append(Comp.Plain(message_text))

                # 根据 AstrBot 文档，使用正确的 Node 格式
                node = Comp.Node(
                    uin="2659908767",  # 可以配置化
                    name="媒体通知",
                    content=content
                )
                forward_nodes.append(node)

            except Exception as e:
                logger.error(f"构建转发节点失败: {e}")
                logger.error(f"消息内容: {msg}")

        if forward_nodes:
            try:
                # 发送合并转发消息
                unified_msg_origin = f"{self.platform_name}:GroupMessage:{group_id}"
                logger.debug(f"发送合并转发消息，unified_msg_origin: {unified_msg_origin}")

                # 根据 AstrBot 文档，直接发送 Node 列表
                message_chain = MessageChain(chain=forward_nodes)
                await self.context.send_message(unified_msg_origin, message_chain)

                logger.info(f"成功发送 {len(forward_nodes)} 条合并转发消息")
            except Exception as e:
                logger.error(f"发送合并转发消息失败: {e}")
                logger.info("回退到单独发送模式")
                await self.send_individual_messages(group_id, messages)
        else:
            logger.warning("没有有效的转发节点，改为单独发送")
            await self.send_individual_messages(group_id, messages)

    async def send_individual_messages(self, group_id: str, messages: List[Dict]):
        """发送单独消息（适用于所有平台）"""
        logger.info(f"逐个发送 {len(messages)} 条消息")

        unified_msg_origin = f"{self.platform_name}:GroupMessage:{group_id}"
        logger.debug(f"发送单独消息，unified_msg_origin: {unified_msg_origin}")

        # 预计算是否为 aiocqhttp 平台，避免重复判断
        is_aiocqhttp = self.platform_name.lower() == "aiocqhttp"

        for msg in messages:
            try:
                content = []

                # 添加图片（如果有）
                if msg.get("image_url"):
                    content.append(Comp.Image.fromURL(msg["image_url"]))

                # 处理消息文本，确保换行符正确处理
                message_text = msg["message_text"]

                # 对于 aiocqhttp，使用特殊的换行符处理
                if is_aiocqhttp:
                    # 尝试不同的换行符处理方式
                    processed_text = self._process_text_for_aiocqhttp(message_text)
                    content.append(Comp.Plain(processed_text))
                else:
                    # 其他平台直接使用完整消息
                    content.append(Comp.Plain(message_text))

                message_chain = MessageChain(chain=content)
                await self.context.send_message(unified_msg_origin, message_chain)

                # 添加短暂延迟，避免消息发送过快
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"发送单条消息失败: {e}")
                logger.error(f"消息内容: {msg}")

        logger.info(f"成功逐个发送 {len(messages)} 条消息")

    def _process_text_for_aiocqhttp(self, message_text: str) -> str:
        """为 aiocqhttp 处理消息文本"""
        # 基于测试结果，使用最佳的修复方案

        # 首先标准化换行符
        processed_text = message_text.replace('\r\n', '\n').replace('\r', '\n')

        # 对于 Emby/Plex/Jellyfin 的消息，应用格式清理
        if any(platform in message_text for platform in ['[Emby]', '[Plex]', '[Jellyfin]']):
            # 方案3+5组合：移除双换行符并移除空行
            lines = processed_text.split('\n')
            # 移除空行，保持紧凑格式
            non_empty_lines = [line for line in lines if line.strip()]
            processed_text = '\n'.join(non_empty_lines)

            logger.debug(f"aiocqhttp 消息处理: {len(lines)} 行 -> {len(non_empty_lines)} 行")

        return processed_text

    def _split_message_for_aiocqhttp(self, message_text: str) -> List[str]:
        """为 aiocqhttp 拆分消息文本（备用方案）"""
        # 将消息按双换行符拆分为段落
        paragraphs = message_text.split('\n\n')

        result = []
        for paragraph in paragraphs:
            if paragraph.strip():
                # 保持段落内的单换行符
                result.append(paragraph.strip())

        return result

    @filter.command("webhook status")
    async def webhook_status(self, event: AstrMessageEvent):
        """查看Webhook状态"""
        port = self.config.get("webhook_port", 60071)
        path = self.config.get("webhook_path", "/media-webhook")
        queue_size = len(self.message_queue)
        cache_size = len(self.request_cache)

        platform_name = self.config.get("platform_name", "aiocqhttp")
        supports_forward = self.supports_forward_messages(platform_name)
        force_individual = self.config.get("force_individual_send", False)

        # 确定发送策略
        if force_individual:
            send_strategy = "强制单独发送"
        elif supports_forward:
            send_strategy = f"智能发送（支持合并转发）"
        else:
            send_strategy = f"单独发送（平台不支持合并转发）"

        status_text = f"""📊 Media Webhook 状态
🌐 服务地址: http://localhost:{port}{path}
🎯 目标群组: {self.config.get('group_id', '未配置')}
🔗 消息平台: {platform_name}
📤 发送策略: {send_strategy}
🔀 合并转发支持: {'✅' if supports_forward else '❌'}

📋 队列消息数: {queue_size}
🗂️ 缓存请求数: {cache_size}
⚙️ 批量发送阈值: {self.config.get('batch_min_size', 3)}
⏰ 处理间隔: {self.config.get('batch_interval_seconds', 300)}秒"""

        yield event.plain_result(status_text)

    @filter.command("webhook test")
    async def webhook_test(self, event: AstrMessageEvent, source: str = "bgm"):
        """测试Webhook功能

        Args:
            source: 数据源 (bgm/static)，默认为 bgm
        """
        if source.lower() in ["bgm", "bangumi"]:
            yield event.plain_result("🔄 获取 BGM.TV 数据...")
            test_data = await self.fetch_bgm_data()
            if not test_data:
                test_data = self.get_default_test_data()
                yield event.plain_result("❌ BGM.TV 获取失败，使用静态数据")
            else:
                yield event.plain_result("✅ BGM.TV 数据获取成功")
        else:
            test_data = self.get_default_test_data()

        # 生成消息
        test_source = "jellyfin" if source.lower() in ["bgm", "bangumi"] else "default"
        message_text = self.generate_message_text(test_data, test_source)

        content = []
        image_url = test_data.get("image_url")
        if image_url:
            try:
                content.append(Comp.Image.fromURL(str(image_url)))
            except Exception as e:
                logger.warning(f"图片加载失败: {e}")
                content.append(Comp.Plain(f"[图片加载失败]\n\n"))
        content.append(Comp.Plain(message_text))

        yield event.chain_result(content)

    def get_default_test_data(self) -> Dict:
        """获取默认测试数据"""
        return {
            "item_type": "Episode",
            "series_name": "测试剧集",
            "year": "2024",
            "item_name": "测试集名称",
            "season_number": 1,
            "episode_number": 1,
            "overview": "这是一个测试剧情简介",
            "runtime": "45分钟",
        }

    @filter.command("webhook test simple")
    async def webhook_test_simple(self, event: AstrMessageEvent):
        """简单测试Webhook功能（不包含图片）"""
        test_data = {
            "item_type": "Episode",
            "series_name": "测试剧集",
            "year": "2024",
            "item_name": "测试集名称",
            "season_number": 1,
            "episode_number": 1,
            "overview": "这是一个测试剧情简介",
            "runtime": "45分钟",
        }

        message_text = self.generate_message_text(test_data, "default")
        yield event.plain_result(message_text)

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

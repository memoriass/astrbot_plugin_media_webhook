import asyncio
import hashlib
import html
import json
import random
import time
from typing import Dict, List, Optional

import astrbot.api.message_components as Comp
import aiohttp
from aiohttp import web
from aiohttp.web import Request, Response
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register


@register(
    "media_webhook",
    "Assistant",
    "媒体通知 Webhook 插件",
    "1.0.0",
    "https://github.com/example/astrbot_plugin_media_webhook",
)
class MediaWebhookPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.app = None
        self.runner = None
        self.site = None

        # 消息队列和缓存
        self.message_queue: List[Dict] = []
        self.request_cache: Dict[str, float] = {}  # hash -> timestamp

        # 媒体类型映射
        self.media_type_map = {
            "Movie": "电影",
            "Series": "剧集",
            "Season": "剧季",
            "Episode": "单集",
            "Album": "专辑",
            "Song": "歌曲",
            "Video": "视频",
        }
        self.type_emoji_map = {"Season": "🎬", "Episode": "📺", "Default": "🌟"}

        # 验证配置
        self.validate_config()

        # 启动HTTP服务器和定时任务
        asyncio.create_task(self.start_webhook_server())
        asyncio.create_task(self.start_batch_processor())

    def validate_config(self):
        """验证配置参数"""
        port = self.config.get("webhook_port", 60071)
        if not isinstance(port, int) or port < 1 or port > 65535:
            logger.warning(f"无效的端口号: {port}，使用默认端口 60071")
            self.config["webhook_port"] = 60071

        batch_interval = self.config.get("batch_interval_seconds", 300)
        if not isinstance(batch_interval, int) or batch_interval < 10:
            logger.warning(f"批量处理间隔过短: {batch_interval}秒，设置为最小值 10秒")
            self.config["batch_interval_seconds"] = max(10, batch_interval)

        cache_ttl = self.config.get("cache_ttl_seconds", 300)
        if not isinstance(cache_ttl, int) or cache_ttl < 60:
            logger.warning(f"缓存TTL过短: {cache_ttl}秒，设置为最小值 60秒")
            self.config["cache_ttl_seconds"] = max(60, cache_ttl)

    async def start_webhook_server(self):
        """启动HTTP Webhook服务器"""
        try:
            self.app = web.Application()
            self.app.router.add_post(
                self.config.get("webhook_path", "/media-webhook"), self.handle_webhook
            )

            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            port = self.config.get("webhook_port", 60071)
            self.site = web.TCPSite(self.runner, "0.0.0.0", port)
            await self.site.start()

            logger.info(f"Media Webhook 服务已启动，监听端口: {port}")
            logger.info(
                f"访问地址: http://localhost:{port}{self.config.get('webhook_path', '/media-webhook')}"
            )

        except OSError as e:
            if "Address already in use" in str(e) or "Only one usage" in str(e):
                logger.error(
                    f"端口 {self.config.get('webhook_port', 60071)} 已被占用，请更换端口"
                )
            else:
                logger.error(f"网络错误: {e}")
        except Exception as e:
            logger.error(f"启动 Webhook 服务器失败: {e}")

    async def handle_webhook(self, request: Request) -> Response:
        """处理Webhook请求"""
        try:
            # 解析请求体
            body_text = await request.text()
            if not body_text:
                return Response(text="请求体为空", status=400)

            media_data = json.loads(body_text)

            # 计算请求哈希值
            request_hash = self.calculate_body_hash(media_data)

            # 检查重复请求
            if request_hash and self.is_duplicate_request(request_hash):
                logger.warning(f"检测到重复请求，已忽略。[hash: {request_hash}]")
                return Response(text="重复请求已被忽略", status=202)

            # 缓存请求哈希
            if request_hash:
                cache_ttl = self.config.get("cache_ttl_seconds", 300)
                self.request_cache[request_hash] = time.time() + cache_ttl

            # 生成消息内容
            message_payload = {
                "image_url": media_data.get("image_url", ""),
                "message_text": self.generate_message_text(media_data),
                "timestamp": time.time(),
            }

            # 添加到消息队列
            self.message_queue.append(message_payload)

            logger.info(
                f"新 {media_data.get('item_type', 'Unknown')} 通知已加入队列。[hash: {request_hash}]"
            )
            return Response(text="消息已加入队列", status=200)

        except json.JSONDecodeError:
            logger.error("Webhook 请求体解析失败: 无效的JSON格式")
            return Response(text="无效的JSON格式", status=400)
        except Exception as e:
            logger.error(f"Webhook 处理出错: {e}")
            return Response(text="处理消息时发生内部错误", status=500)

    def calculate_body_hash(self, body: Dict) -> Optional[str]:
        """计算请求体哈希值"""
        try:
            body_for_hash = body.copy()
            body_for_hash.pop("image_url", None)  # 排除图片URL
            body_string = json.dumps(body_for_hash, sort_keys=True)
            return hashlib.md5(body_string.encode()).hexdigest()
        except Exception as e:
            logger.error(f"MD5 哈希计算失败: {e}")
            return None

    def is_duplicate_request(self, request_hash: str) -> bool:
        """检查是否为重复请求"""
        current_time = time.time()

        # 清理过期缓存
        expired_keys = [k for k, v in self.request_cache.items() if v < current_time]
        for key in expired_keys:
            del self.request_cache[key]

        return request_hash in self.request_cache

    def decode_html_entities(self, text: str) -> str:
        """解码HTML实体"""
        if not text:
            return ""
        return html.unescape(text)

    def generate_main_section(self, data: Dict) -> str:
        """生成消息主要部分"""
        sections = []
        series_name = data.get("series_name", "")
        year = data.get("year", "")
        item_type = data.get("item_type", "")
        item_name = data.get("item_name", "")
        season_number = data.get("season_number", "")
        episode_number = data.get("episode_number", "")

        if series_name:
            year_text = f" ({year})" if year else ""
            sections.append(f"剧集名称: {series_name}{year_text}")

        if item_type == "Season":
            if item_name:
                sections.append(f"季名称: {item_name}")
            if season_number:
                sections.append(f"季号: {season_number}")
        elif item_type == "Episode":
            if season_number and episode_number:
                s_num = str(season_number).zfill(2)
                e_num = str(episode_number).zfill(2)
                sections.append(f"集号: S{s_num}E{e_num}")
            if item_name:
                sections.append(f"集名称: {item_name}")
        else:
            if item_name:
                sections.append(f"名称: {item_name}")
            if year:
                sections.append(f"年份: {year}")

        return "\n".join(sections)

    def generate_message_text(self, data: Dict) -> str:
        """生成消息文本"""
        item_type = data.get("item_type", "")
        cn_type = self.media_type_map.get(item_type, item_type)
        emoji = self.type_emoji_map.get(item_type, self.type_emoji_map["Default"])

        message_parts = [f"{emoji} 新{cn_type}上线", self.generate_main_section(data)]

        overview = data.get("overview", "")
        if overview:
            decoded_overview = self.decode_html_entities(overview)
            message_parts.append(f"\n剧情简介:\n{decoded_overview}")

        runtime = data.get("runtime", "")
        if runtime:
            message_parts.append(f"\n时长: {runtime}")

        return "\n\n".join(message_parts)

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
        """处理消息队列"""
        if not self.message_queue:
            return

        group_id = self.config.get("group_id", "")
        if not group_id:
            logger.warning("未配置群组ID，无法发送消息")
            return

        # 清理 group_id，移除可能的冒号
        group_id = str(group_id).replace(":", "_")
        logger.debug(f"使用群组ID: {group_id}")

        messages = self.message_queue.copy()
        self.message_queue.clear()

        logger.info(f"从队列中取出 {len(messages)} 条待发消息")

        try:
            batch_min_size = self.config.get("batch_min_size", 3)
            platform_name = self.config.get("platform_name", "aiocqhttp")
            force_individual = self.config.get("force_individual_send", False)

            # 智能发送逻辑
            if len(messages) < batch_min_size:
                # 消息数量不足，直接单独发送
                logger.info(f"消息数量 {len(messages)} 低于批量发送阈值 {batch_min_size}，使用单独发送")
                await self.send_individual_messages(group_id, messages)
            elif force_individual:
                # 强制单独发送
                logger.info(f"配置强制单独发送，将 {len(messages)} 条消息逐个发送")
                await self.send_individual_messages(group_id, messages)
            elif self.supports_forward_messages(platform_name):
                # 平台支持合并转发，使用合并发送
                logger.info(f"平台 {platform_name} 支持合并转发，将 {len(messages)} 条消息合并发送")
                await self.send_batch_messages(group_id, messages)
            else:
                # 平台不支持合并转发，回退到单独发送
                logger.info(f"平台 {platform_name} 不支持合并转发，将 {len(messages)} 条消息逐个发送")
                await self.send_individual_messages(group_id, messages)

        except Exception as e:
            logger.error(f"发送消息时出错: {e}")

    async def send_batch_messages(self, group_id: str, messages: List[Dict]):
        """发送批量合并转发消息（仅支持 aiocqhttp 等平台）"""
        logger.info(f"使用合并转发发送 {len(messages)} 条消息")

        # 构建合并转发节点
        forward_nodes = []
        for msg in messages:
            content = []
            if msg.get("image_url"):
                content.append(Comp.Image.fromURL(msg["image_url"]))
            content.append(Comp.Plain(msg["message_text"]))

            node = Comp.Node(
                content=content, uin="2659908767", name="媒体通知"  # 可以配置化
            )
            forward_nodes.append(node)

        # 发送合并转发消息
        platform_name = self.config.get("platform_name", "aiocqhttp")
        unified_msg_origin = f"{platform_name}:GroupMessage:{group_id}"
        logger.debug(f"发送合并转发消息，unified_msg_origin: {unified_msg_origin}")
        message_chain = MessageChain(chain=forward_nodes)
        await self.context.send_message(unified_msg_origin, message_chain)

        logger.info(f"成功发送 {len(messages)} 条合并转发消息")

    async def send_individual_messages(self, group_id: str, messages: List[Dict]):
        """发送单独消息（适用于所有平台）"""
        logger.info(f"逐个发送 {len(messages)} 条消息")

        platform_name = self.config.get("platform_name", "aiocqhttp")
        unified_msg_origin = f"{platform_name}:GroupMessage:{group_id}"
        logger.debug(f"发送单独消息，unified_msg_origin: {unified_msg_origin}")

        for msg in messages:
            content = []
            if msg.get("image_url"):
                content.append(Comp.Image.fromURL(msg["image_url"]))
            content.append(Comp.Plain(msg["message_text"]))

            message_chain = MessageChain(chain=content)
            await self.context.send_message(unified_msg_origin, message_chain)

        logger.info(f"成功逐个发送 {len(messages)} 条消息")

    @filter.command("webhook_status")
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

    @filter.command("webhook_test")
    async def webhook_test(self, event: AstrMessageEvent, data_source: str = "static", include_image: str = "auto"):
        """测试Webhook功能

        Args:
            data_source: 数据源 (static/bgm)，默认为 static
            include_image: 是否包含图片测试 (yes/no/auto)，默认为 auto
        """
        # 根据数据源获取测试数据
        if data_source.lower() in ["bgm", "bangumi"]:
            yield event.plain_result("🔄 正在从 BGM.TV 获取随机剧集数据...")
            test_data = await self.fetch_bgm_data()

            if not test_data:
                yield event.plain_result("❌ 无法从 BGM.TV 获取数据，使用默认测试数据")
                test_data = self.get_default_test_data()
            else:
                yield event.plain_result("✅ 成功获取 BGM.TV 数据")
        else:
            test_data = self.get_default_test_data()

        # 处理图片设置
        if include_image.lower() == "auto":
            # 如果是 BGM 数据且有图片URL，则包含图片
            include_image = "yes" if (data_source.lower() in ["bgm", "bangumi"] and test_data.get("image_url")) else "no"

        # 如果明确不要图片，移除图片URL
        if include_image.lower() in ["no", "n", "false", "0"]:
            test_data.pop("image_url", None)
        elif include_image.lower() in ["yes", "y", "true", "1"] and not test_data.get("image_url"):
            # 如果要求图片但没有图片URL，使用默认图片
            test_data["image_url"] = "https://picsum.photos/300/450"

        message_text = self.generate_message_text(test_data)

        content = []
        image_url = test_data.get("image_url")
        if image_url:
            try:
                content.append(Comp.Image.fromURL(str(image_url)))
            except Exception as e:
                logger.warning(f"无法加载测试图片: {e}")
                content.append(Comp.Plain(f"[图片加载失败: {image_url}]\n\n"))
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

    @filter.command("webhook_test_simple")
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

        message_text = self.generate_message_text(test_data)
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

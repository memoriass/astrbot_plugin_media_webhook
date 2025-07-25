"""
媒体处理模块
提供 Emby、Plex、Jellyfin 数据转换和标准化功能
自动集成 TMDB 数据丰富功能
"""

import html
import os
import re
import time
from typing import Optional

from astrbot.api import logger

from .tmdb_enricher import TMDBEnricher


class MediaHandler:
    """媒体处理器 - 处理 Emby、Plex、Jellyfin 等媒体服务器数据"""

    def __init__(self, tmdb_api_key: str = "", fanart_api_key: str = ""):
        # 初始化 TMDB 丰富器
        if tmdb_api_key:
            self.tmdb_enricher = TMDBEnricher(tmdb_api_key, fanart_api_key)
            self.tmdb_enabled = True
            logger.info("媒体处理器: TMDB 丰富功能已启用")
        else:
            self.tmdb_enricher = None
            self.tmdb_enabled = False
            logger.info("媒体处理器: 未配置 TMDB API 密钥，跳过数据丰富")

        # 媒体类型映射
        self.media_type_map = {
            "Movie": "电影",
            "Series": "剧集",
            "Season": "剧季",
            "Episode": "剧集",
            "Album": "专辑",
            "Song": "歌曲",
            "Video": "视频",
            "Audio": "音频",
            "Book": "图书",
            "AudioBook": "有声书",
        }

        self.type_emoji_map = {
            "Movie": "🎬",
            "Series": "📺",
            "Season": "📺",
            "Episode": "📺",
            "Album": "🎵",
            "Song": "🎶",
            "Video": "📹",
            "Audio": "🎧",
            "Book": "📚",
            "AudioBook": "🎧",
            "Default": "🌟",
        }

    def detect_media_source(self, data: dict, headers: dict) -> str:
        """检测媒体通知来源（增强版 - 支持 Authorization 特征校验）"""
        try:
            # 检查 User-Agent 中的特征
            user_agent = headers.get("user-agent", "").lower()

            # 检查 Authorization 头中的特征
            authorization = headers.get("authorization", "").lower()
            auth_type = self.detect_auth_type(authorization)

            logger.debug(
                f"媒体来源检测: User-Agent={user_agent}, Auth-Type={auth_type}"
            )

            # 优先检查 User-Agent
            if "emby server" in user_agent:
                logger.info("通过 User-Agent 检测到 Emby")
                return "emby"
            if "jellyfin" in user_agent:
                logger.info("通过 User-Agent 检测到 Jellyfin")
                return "jellyfin"
            if "plex" in user_agent:
                logger.info("通过 Plex-Token 检测到 Plex")
                return "plex"

            # 检查 Authorization 特征
            if auth_type:
                if auth_type == "emby":
                    logger.info("通过 Authorization 检测到 Emby")
                    return "emby"
                if auth_type == "jellyfin":
                    logger.info("通过 Authorization 检测到 Jellyfin")
                    return "jellyfin"
                if auth_type == "plex":
                    logger.info("通过 Authorization 检测到 Plex")
                    return "plex"

            # 检查数据结构特征
            if "Item" in data and "Server" in data:
                logger.info("通过数据结构检测到 Emby")
                return "emby"
            if "ItemType" in data or "SeriesName" in data:
                logger.info("通过数据结构检测到 Jellyfin")
                return "jellyfin"
            if "Metadata" in data or "Player" in data:
                logger.info("通过数据结构检测到 Plex")
                return "plex"

            # 检查其他请求头特征
            source_from_headers = self.detect_source_from_headers(headers)
            if source_from_headers != "unknown":
                logger.info(f"通过请求头特征检测到 {source_from_headers}")
                return source_from_headers

            logger.warning("无法确定媒体来源，返回 unknown")
            return "unknown"

        except Exception as e:
            logger.error(f"检测媒体来源失败: {e}")
            return "unknown"

    def detect_auth_type(self, authorization: str) -> str:
        """从 Authorization 头检测媒体服务器类型"""
        try:
            if not authorization:
                return ""

            # Emby 通常使用 MediaBrowser 或 Emby 作为认证前缀
            if "mediabrowser" in authorization or "emby" in authorization:
                return "emby"

            # Jellyfin 通常使用 MediaBrowser 或 Jellyfin 作为认证前缀
            if "jellyfin" in authorization:
                return "jellyfin"

            # Plex 使用 X-Plex-Token 或在 Authorization 中包含 plex
            if "plex" in authorization or "x-plex-token" in authorization:
                return "plex"

            # 检查 Bearer token 格式
            if authorization.startswith("bearer "):
                # 可以根据 token 格式进一步判断
                token = authorization[7:]  # 去掉 "bearer " 前缀
                if len(token) == 32:  # Emby/Jellyfin 通常是32位
                    return "jellyfin"  # 默认返回 jellyfin，因为格式相似

            return ""

        except Exception as e:
            logger.error(f"检测 Authorization 类型失败: {e}")
            return ""

    def detect_source_from_headers(self, headers: dict) -> str:
        """从其他请求头检测媒体服务器类型"""
        try:
            # 检查 X-Plex-Token 头（Plex 特有）
            if headers.get("x-plex-token"):
                return "plex"

            # 检查 X-Emby-Token 头（Emby 特有）
            if headers.get("x-emby-token"):
                return "emby"

            # 检查 X-MediaBrowser-Token 头（Emby/Jellyfin 共用）
            if headers.get("x-mediabrowser-token"):
                # 需要结合其他信息判断是 Emby 还是 Jellyfin
                user_agent = headers.get("user-agent", "").lower()
                if "emby" in user_agent:
                    return "emby"
                if "jellyfin" in user_agent:
                    return "jellyfin"
                return "jellyfin"  # 默认返回 jellyfin

            # 检查 Content-Type 中的特征
            content_type = headers.get("content-type", "").lower()
            if "application/json" in content_type:
                # 检查其他可能的特征头
                if headers.get("x-forwarded-for"):
                    # 可能是通过代理的请求，检查更多特征
                    pass

            # 检查 Referer 头中的特征
            referer = headers.get("referer", "").lower()
            if "emby" in referer:
                return "emby"
            if "jellyfin" in referer:
                return "jellyfin"
            if "plex" in referer:
                return "plex"

            return "unknown"

        except Exception as e:
            logger.error(f"从请求头检测媒体来源失败: {e}")
            return "unknown"

    async def process_media_data(
        self, raw_data: dict, source: str, headers: dict
    ) -> dict:
        """
        处理媒体数据的主入口
        自动进行数据转换和 TMDB 丰富
        """
        try:
            logger.info(f"开始处理 {source.title()} 媒体数据")

            # 1. 转换为标准格式
            media_data = self.convert_to_standard_format(raw_data, source, headers)

            if not media_data:
                logger.warning(f"{source.title()} 数据转换失败")
                return self.create_fallback_payload(raw_data, source)

            # 2. 自动进行 TMDB 数据丰富（如果启用）
            if self.tmdb_enabled and self.tmdb_enricher:
                logger.info("开始 TMDB 数据丰富")
                enriched_data = await self.tmdb_enricher.enrich_media_data(media_data)
                if enriched_data.get("tmdb_enriched"):
                    media_data = enriched_data
                    logger.info("TMDB 数据丰富成功")
                else:
                    logger.info("TMDB 数据丰富未找到匹配结果，使用原始数据")

            # 3. 生成标准消息载荷
            message_payload = self.create_message_payload(media_data, source)

            logger.info(f"{source.title()} 媒体数据处理完成")
            return message_payload

        except Exception as e:
            logger.error(f"处理 {source.title()} 媒体数据失败: {e}")
            return self.create_fallback_payload(raw_data, source)

    def convert_to_standard_format(
        self, raw_data: dict, source: str, headers: Optional[dict] = None
    ) -> dict:
        """将不同来源的数据转换为标准格式"""
        try:
            if source == "emby":
                return self.convert_emby_to_standard(raw_data)
            if source == "jellyfin":
                return self.convert_jellyfin_to_standard(raw_data, headers or {})
            if source == "plex":
                return self.convert_plex_to_standard(raw_data)
            # 通用转换
            return self.convert_generic_to_standard(raw_data)

        except Exception as e:
            logger.error(f"转换 {source.title()} 数据格式失败: {e}")
            return {}

    def convert_emby_to_standard(self, data: dict) -> dict:
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

            # 提取图片信息
            image_url = ""
            if item.get("ImageTags", {}).get("Primary"):
                server_info = data.get("Server", {})
                server_url = server_info.get("Url", "")
                item_id = item.get("Id", "")
                if server_url and item_id:
                    image_url = f"{server_url}/Items/{item_id}/Images/Primary"

            return {
                "item_type": item_type,
                "series_name": series_name,
                "item_name": item_name,
                "season_number": str(season_number) if season_number else "",
                "episode_number": str(episode_number) if episode_number else "",
                "year": str(year) if year else "",
                "overview": overview,
                "runtime": runtime,
                "image_url": image_url,
                "source_data": "emby",
            }

        except Exception as e:
            logger.error(f"转换 Emby 数据失败: {e}")
            return {}

    def convert_jellyfin_to_standard(
        self, data: dict, headers: Optional[dict] = None
    ) -> dict:
        """将 Jellyfin 数据转换为标准格式（优化版）"""
        try:
            # 基本类型
            item_type = data.get("Type", "Episode")

            # 剧集和集名称处理
            item_name = data.get("Name", "")
            series_name = ""

            # 优先从 SeriesName 获取，如果没有则从文件路径提取
            if data.get("SeriesName"):
                series_name = data.get("SeriesName")
            elif data.get("Path"):
                # 从文件路径提取剧集名称
                file_name = os.path.basename(data.get("Path", ""))
                if " - " in file_name:
                    # 假设格式为 "剧集名 - 集号 .扩展名"
                    potential_series = file_name.split(" - ")[0]
                    series_name = potential_series

            # 如果还是没有，使用 Name 作为剧集名称
            if not series_name:
                series_name = item_name

            # 季集号处理
            season_number = ""
            episode_number = str(
                data.get("IndexNumber", "")
            )  # 使用 IndexNumber 而不是 EpisodeNumber

            # 从 SeasonName 提取季号
            season_name = data.get("SeasonName", "")
            if season_name and season_name != "Season Unknown":
                # 尝试从 SeasonName 提取数字
                season_match = re.search(r"Season (\d+)", season_name)
                if season_match:
                    season_number = season_match.group(1)
                else:
                    # 如果没有匹配到，尝试其他格式
                    season_match = re.search(r"第(\d+)季", season_name)
                    if season_match:
                        season_number = season_match.group(1)

            # 如果季号还是空，尝试从文件路径提取
            if not season_number and data.get("Path"):
                file_name = os.path.basename(data.get("Path", ""))
                # 尝试匹配 S01E01 格式
                season_episode_match = re.search(
                    r"S(\d+)E(\d+)", file_name, re.IGNORECASE
                )
                if season_episode_match:
                    season_number = season_episode_match.group(1)
                    if not episode_number:
                        episode_number = season_episode_match.group(2)

            # 处理年份
            year = str(data.get("ProductionYear", ""))

            # 处理简介
            overview = data.get("Overview", "")

            # 处理时长
            runtime = ""
            if data.get("RunTimeTicks"):
                runtime_ticks = data.get("RunTimeTicks", 0)
                runtime = (
                    f"{runtime_ticks // 600000000}分钟" if runtime_ticks > 0 else ""
                )

            # 图片 URL 构建
            server_url = ""
            if headers:
                server_url = self.extract_jellyfin_server_url(headers)
            image_url = self.build_jellyfin_image_url(data, server_url)

            return {
                "item_type": item_type,
                "series_name": series_name,
                "item_name": item_name,
                "season_number": season_number,
                "episode_number": episode_number,
                "year": year,
                "overview": overview,
                "runtime": runtime,
                "image_url": image_url,
                "source_data": "jellyfin",
                "jellyfin_id": data.get("Id", ""),
                "jellyfin_server_id": data.get("ServerId", ""),
            }

        except Exception as e:
            logger.error(f"转换 Jellyfin 数据失败: {e}")
            return {}

    def build_jellyfin_image_url(self, data: dict, server_url: str = "") -> str:
        """构建 Jellyfin 图片 URL"""
        try:
            # 检查是否有图片标签
            image_tags = data.get("ImageTags", {})
            if not image_tags.get("Primary"):
                return ""

            item_id = data.get("Id", "")
            if not item_id:
                return ""

            image_tag = image_tags["Primary"]

            # 如果没有提供服务器 URL，返回相对路径格式
            if not server_url:
                # 返回相对路径，可以在后续处理中替换
                image_url = f"/Items/{item_id}/Images/Primary?tag={image_tag}"
                logger.debug(f"构建 Jellyfin 相对图片 URL: {image_url}")
                return image_url

            # 构建完整的图片 URL
            # 确保服务器 URL 不以 / 结尾
            server_url = server_url.rstrip("/")
            image_url = f"{server_url}/Items/{item_id}/Images/Primary?tag={image_tag}"

            logger.debug(f"构建 Jellyfin 完整图片 URL: {image_url}")
            return image_url

        except Exception as e:
            logger.error(f"构建 Jellyfin 图片 URL 失败: {e}")
            return ""

    def extract_jellyfin_server_url(self, headers: dict) -> str:
        """从请求头中提取 Jellyfin 服务器 URL"""
        try:
            # 尝试从常见的请求头中提取服务器信息
            host = headers.get("host", "")
            x_forwarded_host = headers.get("x-forwarded-host", "")

            # 优先使用 x-forwarded-host，然后是 host
            server_host = x_forwarded_host or host

            if server_host:
                # 检查是否包含端口
                if ":" in server_host:
                    # 假设是 HTTP，实际使用时可能需要检测 HTTPS
                    server_url = f"http://{server_host}"
                else:
                    # 默认端口
                    server_url = f"http://{server_host}:8096"

                logger.debug(f"提取到 Jellyfin 服务器 URL: {server_url}")
                return server_url

            return ""

        except Exception as e:
            logger.error(f"提取 Jellyfin 服务器 URL 失败: {e}")
            return ""

    def convert_plex_to_standard(self, data: dict) -> dict:
        """将 Plex 数据转换为标准格式"""
        try:
            # Plex 通常在 Metadata 字段中包含信息
            metadata = data.get("Metadata", {})

            item_type = metadata.get("type", "episode").title()
            if item_type.lower() == "episode":
                item_type = "Episode"
            elif item_type.lower() == "movie":
                item_type = "Movie"
            elif item_type.lower() == "show":
                item_type = "Series"

            # 提取信息
            series_name = metadata.get("grandparentTitle", "")
            item_name = metadata.get("title", "")
            season_number = str(metadata.get("parentIndex", ""))
            episode_number = str(metadata.get("index", ""))
            year = str(metadata.get("year", ""))
            overview = metadata.get("summary", "")

            # Plex 时长通常以毫秒为单位
            duration = metadata.get("duration", 0)
            runtime = f"{duration // 60000}分钟" if duration > 0 else ""

            return {
                "item_type": item_type,
                "series_name": series_name,
                "item_name": item_name,
                "season_number": season_number,
                "episode_number": episode_number,
                "year": year,
                "overview": overview,
                "runtime": runtime,
                "image_url": "",  # Plex 图片需要特殊处理
                "source_data": "plex",
            }

        except Exception as e:
            logger.error(f"转换 Plex 数据失败: {e}")
            return {}

    def convert_generic_to_standard(self, data: dict) -> dict:
        """通用数据转换"""
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
                "source_data": "generic",
            }

        except Exception as e:
            logger.error(f"通用数据转换失败: {e}")
            return {}

    def create_message_payload(self, media_data: dict, source: str) -> dict:
        """创建标准消息载荷（避免图片重复显示）"""
        try:
            # 获取图片 URL
            image_url = media_data.get("image_url", "")

            # 生成消息文本（包含首行图片标记）
            message_text = self.generate_message_text(media_data)

            # 创建消息载荷
            # 注意：如果消息文本中已包含图片标记，则不在载荷中重复设置 image_url
            # 这样可以避免协议端重复显示图片
            message_payload = {
                "image_url": (
                    image_url if not self.has_image_line_in_text(message_text) else ""
                ),
                "message_text": message_text,
                "source": source,
                "media_data": media_data,
                "timestamp": time.time(),
                "has_inline_image": bool(
                    image_url and self.has_image_line_in_text(message_text)
                ),
            }

            logger.debug(
                f"创建消息载荷: 图片URL={'有' if image_url else '无'}, 内联图片={'有' if message_payload['has_inline_image'] else '无'}"
            )
            return message_payload

        except Exception as e:
            logger.error(f"创建消息载荷失败: {e}")
            return self.create_fallback_payload({}, source)

    def has_image_line_in_text(self, message_text: str) -> bool:
        """检查消息文本中是否包含图片标记行"""
        try:
            if not message_text:
                return False

            # 检查是否包含图片标记
            lines = message_text.split("\n")
            return any(line.strip().startswith("🖼️") for line in lines)

        except Exception as e:
            logger.error(f"检查图片标记行失败: {e}")
            return False

    def create_fallback_payload(self, raw_data: dict, source: str) -> dict:
        """创建降级消息载荷"""
        return {
            "image_url": "",
            "message_text": f"来自 {source.title()} 的媒体通知",
            "source": source,
            "media_data": raw_data,
            "timestamp": time.time(),
            "fallback": True,
        }

    def generate_message_text(self, data: dict) -> str:
        """生成消息文本（紧凑排列优化 + 首行图片）"""
        try:
            item_type = data.get("item_type", "")
            cn_type = self.media_type_map.get(item_type, item_type)
            emoji = self.type_emoji_map.get(item_type, self.type_emoji_map["Default"])

            message_parts = []

            # 首行图片（如果有图片 URL）
            image_url = data.get("image_url", "")
            if image_url:
                # 添加图片标记到首行
                image_line = self.generate_image_line(image_url, data)
                if image_line:
                    message_parts.append(image_line)

            # 生成标题
            title = self.generate_title_by_type(item_type, cn_type, emoji, "上线", data)
            message_parts.append(title)

            # 主要信息（紧凑排列）
            main_section = self.generate_main_section(data)
            if main_section:
                message_parts.append(main_section)

            # 只显示第一段剧情简介
            overview = data.get("overview", "")
            if overview:
                decoded_overview = html.unescape(overview)
                # 只取第一段
                first_paragraph = self.get_first_paragraph(decoded_overview)
                if first_paragraph:
                    if item_type == "Movie" or item_type in [
                        "Series",
                        "Season",
                        "Episode",
                    ]:
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
                elif item_type in ["Episode", "Video"] or item_type == "Song":
                    message_parts.append(f"时长: {runtime}")
                else:
                    message_parts.append(f"时长: {runtime}")

            # 数据来源标记
            if data.get("tmdb_enriched"):
                message_parts.append("✨ 数据来源: TMDB")
            elif data.get("bgm_enriched"):
                message_parts.append("✨ 数据来源: BGM.TV")

            return "\n".join(message_parts)

        except Exception as e:
            logger.error(f"生成消息文本失败: {e}")
            return f"媒体通知 - {data.get('item_type', 'Unknown')}"

    def generate_image_line(self, image_url: str, data: dict) -> str:
        """生成首行图片信息"""
        try:
            if not image_url:
                return ""

            # 检查图片来源并生成相应的标记
            image_source = self.detect_image_source(image_url, data)

            # 根据不同的图片来源生成不同的标记
            if image_source == "tmdb":
                return "🖼️ [TMDB 海报]"
            if image_source == "fanart":
                return "🖼️ [Fanart.tv 海报]"
            if image_source == "jellyfin":
                return "🖼️ [Jellyfin 海报]"
            if image_source == "emby":
                return "🖼️ [Emby 海报]"
            if image_source == "plex":
                return "🖼️ [Plex 海报]"
            if image_source == "local":
                return "🖼️ [本地海报]"
            return "🖼️ [海报图片]"

        except Exception as e:
            logger.error(f"生成图片行失败: {e}")
            return ""

    def detect_image_source(self, image_url: str, data: dict) -> str:
        """检测图片来源"""
        try:
            if not image_url:
                return ""

            image_url_lower = image_url.lower()

            # 检查 TMDB 图片
            if (
                "image.tmdb.org" in image_url_lower
                or "themoviedb.org" in image_url_lower
            ):
                return "tmdb"

            # 检查 Fanart.tv 图片
            if "fanart.tv" in image_url_lower or "assets.fanart.tv" in image_url_lower:
                return "fanart"

            # 检查 Jellyfin 图片
            if "/Items/" in image_url and "/Images/" in image_url:
                if data.get("source_data") == "jellyfin" or data.get("jellyfin_id"):
                    return "jellyfin"
                if data.get("source_data") == "emby":
                    return "emby"

            # 检查 Plex 图片
            elif "plex" in image_url_lower or "/library/metadata/" in image_url:
                return "plex"

            # 检查本地文件路径
            elif image_url.startswith(("file://", "/")) or "\\" in image_url:
                return "local"

            # 检查数据中的标记
            if data.get("tmdb_enriched"):
                return "tmdb"
            if data.get("bgm_enriched"):
                return "bgm"

            return "unknown"

        except Exception as e:
            logger.error(f"检测图片来源失败: {e}")
            return "unknown"

    def generate_title_by_type(
        self, item_type: str, cn_type: str, emoji: str, action: str, data: dict
    ) -> str:
        """根据媒体类型生成合适的标题"""
        if item_type == "Movie":
            return f"{emoji} 新电影{action}"
        if item_type in ["Series", "Season"]:
            return f"{emoji} 剧集{action}"
        if item_type == "Episode":
            # 对于剧集，显示更具体的信息
            season_num = data.get("season_number", "")
            episode_num = data.get("episode_number", "")
            if season_num and episode_num:
                return f"{emoji} 新剧集{action}"
            return f"{emoji} 剧集{action}"
        if item_type == "Album":
            return f"{emoji} 新专辑{action}"
        if item_type == "Song":
            return f"{emoji} 新歌曲{action}"
        if item_type == "Video":
            return f"{emoji} 新视频{action}"
        if item_type in ["Audio", "AudioBook"]:
            return f"{emoji} 新音频{action}"
        if item_type == "Book":
            return f"{emoji} 新图书{action}"
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

    def generate_main_section(self, data: dict) -> str:
        """生成消息主要部分（紧凑排列）"""
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
            if series_name and series_name != item_name:
                sections.append(f"艺术家: {series_name}")
            if year:
                sections.append(f"年份: {year}")

        # 其他类型
        elif item_name:
            year_text = f" ({year})" if year else ""
            sections.append(f"名称: {item_name}{year_text}")
        elif series_name:
            year_text = f" ({year})" if year else ""
            sections.append(f"名称: {series_name}{year_text}")

        return "\n".join(sections)

    def validate_media_data(self, media_data: dict) -> bool:
        """验证媒体数据"""
        try:
            # 检查必要字段
            required_fields = ["item_type"]
            for field in required_fields:
                if field not in media_data:
                    logger.error(f"媒体数据缺少必要字段: {field}")
                    return False

            # 检查是否有基本的名称信息
            if not (media_data.get("series_name") or media_data.get("item_name")):
                logger.error("媒体数据缺少名称信息")
                return False

            return True

        except Exception as e:
            logger.error(f"媒体数据验证失败: {e}")
            return False

    def get_processing_stats(self) -> dict:
        """获取处理统计信息"""
        stats = {
            "tmdb_enabled": self.tmdb_enabled,
            "supported_sources": ["emby", "jellyfin", "plex", "generic"],
            "supported_types": list(self.media_type_map.keys()),
        }

        if self.tmdb_enricher:
            stats["tmdb_cache_stats"] = self.tmdb_enricher.get_cache_stats()

        return stats

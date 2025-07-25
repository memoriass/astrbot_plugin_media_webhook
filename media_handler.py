"""
媒体处理模块
提供 Emby、Plex、Jellyfin 数据转换和标准化功能
自动集成 TMDB 数据丰富功能
"""

import time
from typing import Dict, Optional

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

    def detect_media_source(self, data: Dict, headers: Dict) -> str:
        """检测媒体通知来源"""
        try:
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

        except Exception as e:
            logger.error(f"检测媒体来源失败: {e}")
            return "unknown"

    async def process_media_data(
        self, raw_data: Dict, source: str, headers: Dict
    ) -> Dict:
        """
        处理媒体数据的主入口
        自动进行数据转换和 TMDB 丰富
        """
        try:
            logger.info(f"开始处理 {source.title()} 媒体数据")

            # 1. 转换为标准格式
            media_data = self.convert_to_standard_format(raw_data, source)

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

    def convert_to_standard_format(self, raw_data: Dict, source: str) -> Dict:
        """将不同来源的数据转换为标准格式"""
        try:
            if source == "emby":
                return self.convert_emby_to_standard(raw_data)
            elif source == "jellyfin":
                return self.convert_jellyfin_to_standard(raw_data)
            elif source == "plex":
                return self.convert_plex_to_standard(raw_data)
            else:
                # 通用转换
                return self.convert_generic_to_standard(raw_data)

        except Exception as e:
            logger.error(f"转换 {source.title()} 数据格式失败: {e}")
            return {}

    def convert_emby_to_standard(self, data: Dict) -> Dict:
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

    def convert_jellyfin_to_standard(self, data: Dict) -> Dict:
        """将 Jellyfin 数据转换为标准格式"""
        try:
            # Jellyfin 通常使用类似 Emby 的结构，但字段名可能略有不同
            item_type = data.get("ItemType") or data.get("Type", "Episode")

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
                "source_data": "jellyfin",
            }

        except Exception as e:
            logger.error(f"转换 Jellyfin 数据失败: {e}")
            return {}

    def convert_plex_to_standard(self, data: Dict) -> Dict:
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

    def convert_generic_to_standard(self, data: Dict) -> Dict:
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

    def create_message_payload(self, media_data: Dict, source: str) -> Dict:
        """创建标准消息载荷"""
        try:
            # 生成消息文本
            message_text = self.generate_message_text(media_data)

            # 获取图片 URL
            image_url = media_data.get("image_url", "")

            # 创建消息载荷
            message_payload = {
                "image_url": image_url,
                "message_text": message_text,
                "source": source,
                "media_data": media_data,
                "timestamp": time.time(),
            }

            return message_payload

        except Exception as e:
            logger.error(f"创建消息载荷失败: {e}")
            return self.create_fallback_payload({}, source)

    def create_fallback_payload(self, raw_data: Dict, source: str) -> Dict:
        """创建降级消息载荷"""
        return {
            "image_url": "",
            "message_text": f"来自 {source.title()} 的媒体通知",
            "source": source,
            "media_data": raw_data,
            "timestamp": time.time(),
            "fallback": True,
        }

    def generate_message_text(self, data: Dict) -> str:
        """生成消息文本（紧凑排列优化）"""
        try:
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
                import html

                decoded_overview = html.unescape(overview)
                # 只取第一段
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

        except Exception as e:
            logger.error(f"生成消息文本失败: {e}")
            return f"媒体通知 - {data.get('item_type', 'Unknown')}"

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

    def generate_main_section(self, data: Dict) -> str:
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

        else:
            # 其他类型
            if item_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"名称: {item_name}{year_text}")
            elif series_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"名称: {series_name}{year_text}")

        return "\n".join(sections)

    def validate_media_data(self, media_data: Dict) -> bool:
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

    def get_processing_stats(self) -> Dict:
        """获取处理统计信息"""
        stats = {
            "tmdb_enabled": self.tmdb_enabled,
            "supported_sources": ["emby", "jellyfin", "plex", "generic"],
            "supported_types": list(self.media_type_map.keys()),
        }

        if self.tmdb_enricher:
            stats["tmdb_cache_stats"] = self.tmdb_enricher.get_cache_stats()

        return stats

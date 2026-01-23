"""
媒体处理模块
提供 Emby、Plex、Jellyfin 数据转换和标准化功能
自动集成多源数据丰富功能
"""

import html
import time
from typing import Optional

from astrbot.api import logger

from .processors import ProcessorManager
from .enrichment import EnrichmentManager


class MediaHandler:
    """媒体处理器 - 处理 Emby、Plex、Jellyfin 等媒体服务器数据"""

    def __init__(self, config: Optional[dict] = None):
        # 初始化处理器管理器
        self.processor_manager = ProcessorManager()

        # 初始化数据丰富管理器
        self.enrichment_manager = EnrichmentManager(config)


        logger.info("媒体处理器初始化完成")

    def detect_media_source(self, data: dict, headers: dict) -> str:
        """检测媒体通知来源"""
        try:
            return self.processor_manager.detect_source(data, headers)
        except Exception as e:
            logger.error(f"媒体来源检测失败: {e}")
            return "generic"

    async def process_media_data(
        self, raw_data: dict, source: str, headers: dict
    ) -> dict:
        """
        处理媒体数据的主入口
        自动进行数据转换和多源数据丰富
        """
        try:
            logger.info(f"开始处理 {source.title()} 媒体数据")

            # 1. 转换为标准格式
            media_data = self.convert_to_standard_format(raw_data, source, headers)
            logger.debug(f"转换后的媒体数据: {media_data}")

            if not media_data:
                logger.warning(f"{source.title()} 数据转换失败")
                return self.create_fallback_payload(raw_data, source)

            # 2. 自动进行多源数据丰富
            logger.info("开始数据丰富")
            logger.debug(f"  原始图片URL: {media_data.get('image_url', '无')}")
            enriched_data = await self.enrichment_manager.enrich_media_data(media_data)


            # 4. 获取图片（如果还没有图片）
            if not enriched_data.get("image_url"):
                logger.info("尝试获取图片")
                image_url = await self.enrichment_manager.get_media_image(enriched_data)
                if image_url:
                    enriched_data["image_url"] = image_url
                    logger.info(f"  获取到图片URL: {image_url}")

            media_data = enriched_data
            logger.info(f"  最终图片URL: {media_data.get('image_url', '无')}")

            # 4. 生成标准消息载荷
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
            return self.processor_manager.convert_to_standard(raw_data, source, headers)

        except Exception as e:
            logger.error(f"转换 {source.title()} 数据格式失败: {e}")
            return {}

    def validate_media_data(self, media_data: dict) -> bool:
        """验证媒体数据"""
        try:
            # 使用处理器管理器的验证功能
            processor = self.processor_manager.get_processor("generic")
            return processor.validate_standard_data(media_data)
        except Exception as e:
            logger.error(f"媒体数据验证失败: {e}")
            return False

    def get_processing_stats(self) -> dict:
        """获取处理统计信息"""
        stats = {
            "processor_info": self.processor_manager.get_processor_info(),
        }
        return stats

    def create_message_payload(self, media_data: dict, source: str) -> dict:
        """创建标准消息载荷（图片嵌入到消息中）"""
        try:
            # 获取图片 URL
            image_url = media_data.get("image_url", "")

            # 生成消息文本（不包含图片标记，因为图片将直接嵌入）
            message_text = self.generate_message_text_without_image_line(media_data)

            # 创建消息载荷
            message_payload = {
                "image_url": image_url,  # 始终包含图片URL（如果有）
                "message_text": message_text,
                "source": source,
                "media_data": media_data,
                "timestamp": time.time(),
            }

            # 详细日志
            if image_url:
                image_source = self.detect_image_source(image_url, media_data)
                logger.info(f"[MSG] 创建消息载荷: 包含图片 (来源: {image_source})")
                logger.debug(f"  图片URL: {image_url}")
            else:
                logger.warning("[MSG] 创建消息载荷: [WARN] 无图片URL")
                logger.debug(f"  media_data keys: {list(media_data.keys())}")

            logger.debug(f"  消息文本长度: {len(message_text)}")
            return message_payload

        except Exception as e:
            logger.error(f"创建消息载荷失败: {e}")
            return self.create_fallback_payload({}, source)

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
            # 使用处理器的类型映射
            processor = self.processor_manager.get_processor("generic")
            cn_type = processor.get_media_type_display(item_type)

            message_parts = []

            # 首行图片（如果有图片 URL）
            image_url = data.get("image_url", "")
            if image_url:
                # 添加图片标记到首行
                image_line = self.generate_image_line(image_url, data)
                if image_line:
                    message_parts.append(image_line)

            # 生成标题
            title = self.generate_title_by_type(item_type, cn_type, "上线", data)
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
                message_parts.append(f"时长: {runtime}")

            # 数据来源标记
            if data.get("tmdb_enriched"):
                message_parts.append(f"[*] 数据来源: TMDB")
            elif data.get("bgm_enriched"):
                message_parts.append(f"[*] 数据来源: BGM.TV")

            return "\n".join(message_parts)

        except Exception as e:
            logger.error(f"生成消息文本失败: {e}")
            return f"媒体通知 - {data.get('item_type', 'Unknown')}"

    def generate_message_text_without_image_line(self, data: dict) -> str:
        """生成消息文本（不包含图片行，图片将直接嵌入）"""
        try:
            item_type = data.get("item_type", "")
            # 使用处理器的类型映射
            processor = self.processor_manager.get_processor("generic")
            cn_type = processor.get_media_type_display(item_type)

            message_parts = []

            # 生成标题（不包含图片行）
            title = self.generate_title_by_type(item_type, cn_type, "上线", data)
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
                        message_parts.append(f"剧情: {first_paragraph}")
                    else:
                        message_parts.append(f"简介: {first_paragraph}")

            # 时长信息
            runtime = data.get("runtime", "")
            if runtime:
                if item_type == "Movie":
                    message_parts.append(f"时长: {runtime}")
                else:
                    message_parts.append(f"时长: {runtime}")

            # 数据来源标记
            if data.get("tmdb_enriched"):
                message_parts.append("[*] 数据来源: TMDB")
            elif data.get("bgm_enriched"):
                message_parts.append("[*] 数据来源: BGM.TV")

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
                return "[IMG] [TMDB 海报]"
            if image_source == "fanart":
                return "[IMG] [Fanart.tv 海报]"
            if image_source == "jellyfin":
                return "[IMG] [Jellyfin 海报]"
            if image_source == "emby":
                return "[IMG] [Emby 海报]"
            if image_source == "plex":
                return "[IMG] [Plex 海报]"
            if image_source == "local":
                return "[IMG] [本地海报]"
            return "[IMG] [海报图片]"

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
        self, item_type: str, cn_type: str, action: str, data: dict
    ) -> str:
        """根据媒体类型生成合适的标题"""
        if item_type == "Movie":
            return f"新电影{action}"
        if item_type in ["Series", "Season"]:
            return f"剧集{action}"
        if item_type == "Episode":
            # 对于剧集，显示更具体的信息
            season_num = data.get("season_number", "")
            episode_num = data.get("episode_number", "")
            if season_num and episode_num:
                return f"新剧集{action}"
            return f"剧集{action}"
        if item_type == "Album":
            return f"新专辑{action}"
        if item_type == "Song":
            return f"新歌曲{action}"
        if item_type == "Video":
            return f"新视频{action}"
        if item_type in ["Audio", "AudioBook"]:
            return f"新音频{action}"
        if item_type == "Book":
            return f"新图书{action}"
        # 默认格式
        return f"新{cn_type}{action}"

    def get_first_paragraph(self, text: str) -> str:
        """获取文本的第一段"""
        if not text:
            return ""

        # 按句号分割
        sentences = text.split("。")
        if len(sentences) > 1 and sentences[0]:
            first_sentence = sentences[0].strip() + "。"
            # 限制长度（扩展到200字符）
            if len(first_sentence) > 200:
                return first_sentence[:197] + "..."
            return first_sentence

        # 按换行符分割
        lines = text.split("\n")
        first_line = lines[0].strip()
        if first_line:
            # 限制长度（扩展到200字符）
            if len(first_line) > 200:
                return first_line[:197] + "..."
            return first_line

        # 如果都没有，直接截取前200个字符
        if len(text) > 200:
            return text[:197] + "..."
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
                sections.append(f"名称: {item_name}{year_text}")
            elif series_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"名称: {series_name}{year_text}")

        elif item_type in ["Series", "Season"]:
            # 剧集/剧季信息
            if series_name:
                year_text = f" ({year})" if year else ""
                sections.append(f"名称: {series_name}{year_text}")
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

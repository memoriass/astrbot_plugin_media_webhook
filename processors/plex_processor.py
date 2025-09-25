"""
Plex媒体处理器
专门处理Plex媒体服务器的webhook数据
"""

from typing import Optional

from astrbot.api import logger

from .base_processor import BaseMediaProcessor


class PlexProcessor(BaseMediaProcessor):
    """Plex媒体处理器"""

    def can_handle(self, data: dict, headers: Optional[dict] = None) -> bool:
        """检查是否为Plex数据"""
        # Plex特征：包含Metadata或Player字段
        if "Metadata" in data or "Player" in data:
            logger.debug("检测到Plex数据结构特征")
            return True

        # 检查User-Agent
        if headers:
            user_agent = headers.get("User-Agent", "").lower()
            if "plex" in user_agent:
                logger.debug("通过User-Agent检测到Plex")
                return True

        return False

    def convert_to_standard(self, data: dict, headers: Optional[dict] = None) -> dict:
        """将Plex数据转换为标准格式"""
        try:
            logger.debug(f"Plex 原始数据结构: {data}")

            metadata = data.get("Metadata", {})
            if not metadata:
                logger.warning("Plex数据中未找到Metadata字段")
                return {}

            # 提取基本信息
            item_type = metadata.get("type", "episode")
            # Plex类型映射
            plex_type_map = {
                "movie": "Movie",
                "episode": "Episode",
                "season": "Season",
                "show": "Series",
                "track": "Song",
                "album": "Album",
            }
            item_type = plex_type_map.get(item_type.lower(), item_type.title())

            item_name = metadata.get("title", "")

            # 提取剧集信息
            series_name = ""
            season_number = ""
            episode_number = ""

            if item_type == "Episode":
                series_name = metadata.get("grandparentTitle", "")
                season_number = metadata.get("parentIndex", "")
                episode_number = metadata.get("index", "")
            elif item_type == "Season":
                series_name = metadata.get("parentTitle", "")
                season_number = metadata.get("index", "")
            elif item_type == "Series":
                series_name = item_name

            # 提取其他信息
            year = metadata.get("year", "")
            overview = self.clean_text(metadata.get("summary", ""))

            # 处理时长（Plex使用毫秒）
            runtime = ""
            duration = metadata.get("duration", 0)
            if duration and isinstance(duration, (int, float)) and duration > 0:
                # Plex的duration是毫秒，转换为分钟
                runtime_minutes = int(duration // 60000)
                if runtime_minutes > 0:
                    runtime = f"{runtime_minutes}分钟"

            # 提取图片信息
            image_url = ""
            thumb = metadata.get("thumb", "")
            if thumb:
                # Plex的thumb通常是相对路径，需要拼接服务器地址
                server_info = data.get("Server", {})
                if server_info:
                    server_url = server_info.get("url", "")
                    if server_url and thumb.startswith("/"):
                        server_url = server_url.rstrip("/")
                        image_url = f"{server_url}{thumb}"
                    elif not thumb.startswith("http"):
                        # 如果没有服务器信息，尝试从其他字段获取
                        image_url = thumb
                else:
                    image_url = thumb

            logger.debug(f"Plex 图片URL: {image_url}")

            result = self.create_standard_data(
                item_type=item_type,
                series_name=series_name,
                item_name=item_name,
                season_number=season_number,
                episode_number=episode_number,
                year=year,
                overview=overview,
                runtime=runtime,
                image_url=image_url,
                source_data="plex",
            )

            logger.debug(f"Plex 转换结果: {result}")
            return result

        except Exception as e:
            logger.error(f"Plex 数据转换失败: {e}")
            logger.debug(f"Plex 转换失败详情: {e}", exc_info=True)
            return {}

    def extract_plex_metadata(self, metadata: dict) -> dict:
        """提取Plex特有的元数据"""
        plex_metadata = {}

        # 提取评分
        if metadata.get("rating"):
            plex_metadata["rating"] = metadata.get("rating")

        if metadata.get("audienceRating"):
            plex_metadata["audience_rating"] = metadata.get("audienceRating")

        # 提取制片公司
        if metadata.get("studio"):
            plex_metadata["studio"] = metadata.get("studio")

        # 提取内容评级
        if metadata.get("contentRating"):
            plex_metadata["content_rating"] = metadata.get("contentRating")

        # 提取标签
        if metadata.get("Genre"):
            genres = metadata.get("Genre", [])
            if isinstance(genres, list):
                plex_metadata["genres"] = [g.get("tag", "") for g in genres]

        # 提取导演
        if metadata.get("Director"):
            directors = metadata.get("Director", [])
            if isinstance(directors, list):
                plex_metadata["directors"] = [d.get("tag", "") for d in directors]

        # 提取演员
        if metadata.get("Role"):
            actors = metadata.get("Role", [])
            if isinstance(actors, list):
                plex_metadata["actors"] = [
                    a.get("tag", "") for a in actors[:5]
                ]  # 限制前5个

        return plex_metadata

    def get_plex_player_info(self, data: dict) -> dict:
        """获取Plex播放器信息"""
        player_info = {}

        player = data.get("Player", {})
        if player:
            player_info["player_title"] = player.get("title", "")
            player_info["player_uuid"] = player.get("uuid", "")
            player_info["player_local"] = player.get("local", False)

        account = data.get("Account", {})
        if account:
            player_info["user_title"] = account.get("title", "")
            player_info["user_id"] = account.get("id", "")

        return player_info

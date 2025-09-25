"""
Emby媒体处理器
专门处理Emby媒体服务器的webhook数据
"""

from typing import Optional

from astrbot.api import logger

from .base_processor import BaseMediaProcessor


class EmbyProcessor(BaseMediaProcessor):
    """Emby媒体处理器"""

    def can_handle(self, data: dict, headers: Optional[dict] = None) -> bool:
        """检查是否为Emby数据"""
        # Emby特征：包含Item和Server字段
        if "Item" in data and "Server" in data:
            logger.debug("检测到Emby数据结构特征")
            return True

        # 检查User-Agent
        if headers:
            user_agent = headers.get("User-Agent", "").lower()
            if "emby" in user_agent:
                logger.debug("通过User-Agent检测到Emby")
                return True

        return False

    def convert_to_standard(self, data: dict, headers: Optional[dict] = None) -> dict:
        """将Emby数据转换为标准格式"""
        try:
            item = data.get("Item", {})
            logger.debug(f"Emby 原始数据结构: {data}")
            logger.debug(f"Emby Item 数据: {item}")

            # 提取基本信息
            item_type = item.get("Type", "Unknown")
            item_name = item.get("Name", "")
            logger.debug(f"Emby 提取的基本信息: type={item_type}, name={item_name}")

            # 提取剧集信息
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
            else:
                # 对于电影等其他类型，使用item_name
                pass

            # 提取其他信息
            year = item.get("ProductionYear", "")
            overview = self.clean_text(item.get("Overview", ""))
            runtime_ticks = item.get("RunTimeTicks", 0)
            runtime = self.safe_get_runtime(runtime_ticks)

            # 提取图片信息
            image_url = ""
            image_tags = item.get("ImageTags", {})
            logger.debug(f"Emby ImageTags: {image_tags}")

            if image_tags.get("Primary"):
                server_info = data.get("Server", {})
                server_url = server_info.get("Url", "")
                item_id = item.get("Id", "")
                logger.debug(
                    f"Emby 图片信息: server_url={server_url}, item_id={item_id}"
                )

                if server_url and item_id:
                    # 确保服务器URL不以/结尾
                    server_url = server_url.rstrip("/")
                    image_url = f"{server_url}/Items/{item_id}/Images/Primary"
                    logger.debug(f"Emby 构建的图片URL: {image_url}")
                else:
                    logger.debug("Emby 图片URL构建失败：缺少server_url或item_id")

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
                source_data="emby",
            )

            logger.debug(f"Emby 转换结果: {result}")
            return result

        except Exception as e:
            logger.error(f"Emby 数据转换失败: {e}")
            logger.debug(f"Emby 转换失败详情: {e}", exc_info=True)
            return {}

    def extract_emby_metadata(self, item: dict) -> dict:
        """提取Emby特有的元数据"""
        metadata = {}

        # 提取演员信息
        people = item.get("People", [])
        actors = [
            person.get("Name", "") for person in people if person.get("Type") == "Actor"
        ]
        if actors:
            metadata["actors"] = actors[:5]  # 限制前5个演员

        # 提取导演信息
        directors = [
            person.get("Name", "")
            for person in people
            if person.get("Type") == "Director"
        ]
        if directors:
            metadata["directors"] = directors

        # 提取制片公司
        studios = item.get("Studios", [])
        if studios:
            metadata["studios"] = [studio.get("Name", "") for studio in studios]

        # 提取评分
        community_rating = item.get("CommunityRating")
        if community_rating:
            metadata["rating"] = community_rating

        # 提取标签
        tags = item.get("Tags", [])
        if tags:
            metadata["tags"] = tags

        return metadata

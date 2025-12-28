"""
TMDB 媒体数据提供者
提供 TMDB API 的媒体数据丰富和图片获取功能
"""

import asyncio
import time
from typing import Optional

import aiohttp

from astrbot.api import logger

from .base_provider import MediaEnrichmentProvider, MediaImageProvider


class TMDBProvider(MediaEnrichmentProvider, MediaImageProvider):
    """TMDB 媒体数据和图片提供者"""

    def __init__(self, api_key: str, fanart_api_key: str = ""):
        self.tmdb_api_key = api_key
        self.fanart_api_key = fanart_api_key
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.fanart_base_url = "https://webservice.fanart.tv/v3"

        # 缓存机制
        self.tmdb_cache: dict[str, dict] = {}
        self.cache_ttl = 3600  # 缓存1小时
        self.cache_timestamps: dict[str, float] = {}

        # 请求限制
        self.last_request_time = 0
        self.request_interval = 0.25  # 250ms 间隔，避免超过 TMDB 限制

    @property
    def name(self) -> str:
        return "TMDB"

    @property
    def priority(self) -> int:
        return 1  # TMDB 作为主要数据源

    async def enrich_media_data(self, media_data: dict) -> dict:
        """使用 TMDB API 丰富媒体数据"""
        try:
            if not self.tmdb_api_key:
                logger.debug("未配置 TMDB API 密钥，跳过数据丰富")
                return media_data

            item_type = media_data.get("item_type", "")

            # 只处理剧集类型
            if item_type != "Episode":
                logger.debug(f"跳过非剧集类型: {item_type}")
                return media_data

            series_name = media_data.get("series_name", "")
            episode_number = media_data.get("episode_number", "")

            if not all([series_name, episode_number]):
                logger.warning("缺少必要信息，跳过 TMDB 查询")
                return media_data

            logger.info(f"开始 TMDB 数据丰富: {series_name} 第{episode_number}集")

            # 尝试 TMDB 丰富
            enriched_data = await self._try_tmdb_enrichment(media_data)
            if enriched_data.get("tmdb_enriched"):
                logger.info("TMDB 数据丰富成功")
                return enriched_data
            else:
                logger.info("TMDB 数据丰富未找到匹配结果")
                return media_data

        except Exception as e:
            logger.error(f"TMDB 数据丰富出错: {e}")
            return media_data

    async def get_media_image(self, media_data: dict) -> str:
        """获取媒体图片（兼容旧接口）"""
        return await self.get_image(media_data)

    async def get_image(self, media_data: dict) -> str:
        """获取媒体图片"""
        try:
            series_name = media_data.get("series_name", "")
            season_number = media_data.get("season_number", "")
            episode_number = media_data.get("episode_number", "")

            if not series_name:
                logger.debug("缺少剧集名称，跳过图片获取")
                return ""

            logger.info(f"TMDB 获取图片: {series_name} S{season_number}E{episode_number}")

            # 1. 尝试从 TMDB 获取剧集截图
            if season_number and episode_number:
                still_image = await self._get_tmdb_episode_still(
                    series_name, season_number, episode_number
                )
                if still_image:
                    logger.info("TMDB 剧集截图获取成功")
                    return still_image

            # 2. 尝试从 Fanart.tv 获取海报
            if self.fanart_api_key:
                fanart_image = await self._get_fanart_image(media_data)
                if fanart_image:
                    logger.info("Fanart.tv 图片获取成功")
                    return fanart_image

            # 3. 尝试从 TMDB 获取剧集海报
            poster_image = await self._get_tmdb_poster(series_name)
            if poster_image:
                logger.info("TMDB 剧集海报获取成功")
                return poster_image

            logger.info("所有 TMDB 图片来源都未获取到图片")
            return ""

        except Exception as e:
            logger.error(f"TMDB 图片获取出错: {e}")
            return ""

    async def _try_tmdb_enrichment(self, media_data: dict) -> dict:
        """尝试使用 TMDB 丰富数据"""
        try:
            series_name = media_data.get("series_name", "")
            season_number = media_data.get("season_number", "")
            episode_number = media_data.get("episode_number", "")

            # 搜索 TV 节目
            tv_show = await self._search_tmdb_tv_show(series_name)
            if not tv_show:
                return media_data

            tv_id = tv_show.get("id")
            if not tv_id:
                return media_data

            # 获取剧集详情
            try:
                season_num = int(season_number) if season_number.strip() else 1
                episode_num = int(episode_number) if episode_number.strip() else 1
                episode_details = await self._get_tmdb_episode_details(tv_id, season_num, episode_num)

                if episode_details:
                    enriched_data = media_data.copy()
                    enriched_data["tmdb_enriched"] = True
                    enriched_data["tmdb_tv_id"] = tv_id
                    enriched_data["tmdb_episode_id"] = episode_details.get("id")

                    # 添加剧集信息
                    if episode_details.get("name"):
                        enriched_data["episode_title"] = episode_details["name"]
                    if episode_details.get("overview"):
                        enriched_data["episode_description"] = episode_details["overview"]
                    if episode_details.get("air_date"):
                        enriched_data["air_date"] = episode_details["air_date"]
                    if episode_details.get("vote_average"):
                        enriched_data["rating"] = episode_details["vote_average"]

                    # 添加剧集海报信息
                    if episode_details.get("still_path"):
                        enriched_data["episode_still_path"] = episode_details["still_path"]

                    return enriched_data

            except (ValueError, TypeError) as e:
                logger.debug(f"季数或集数转换失败: {e}")

            return media_data

        except Exception as e:
            logger.error(f"TMDB 丰富处理出错: {e}")
            return media_data

    async def _get_tmdb_episode_still(self, series_name: str, season_number: str, episode_number: str) -> str:
        """从 TMDB 获取剧集截图"""
        try:
            if not self.tmdb_api_key:
                return ""

            # 搜索 TV 节目
            tv_show = await self._search_tmdb_tv_show(series_name)
            if not tv_show:
                return ""

            tv_id = tv_show.get("id")
            if not tv_id:
                return ""

            # 获取剧集详情
            try:
                season_num = int(season_number) if season_number.strip() else 1
                episode_num = int(episode_number) if episode_number.strip() else 1
                episode_details = await self._get_tmdb_episode_details(tv_id, season_num, episode_num)

                if episode_details:
                    still_path = episode_details.get("still_path")
                    if still_path:
                        return f"https://image.tmdb.org/t/p/w500{still_path}"
            except (ValueError, TypeError) as e:
                logger.debug(f"季数或集数转换失败: {e}")

            return ""

        except Exception as e:
            logger.error(f"TMDB 剧集截图获取出错: {e}")
            return ""

    async def _get_fanart_image(self, media_data: dict) -> str:
        """从 Fanart.tv 获取图片"""
        try:
            if not self.fanart_api_key:
                return ""

            tmdb_tv_id = media_data.get("tmdb_tv_id")
            if not tmdb_tv_id:
                # 如果没有 TMDB ID，先搜索获取
                series_name = media_data.get("series_name", "")
                if series_name:
                    tv_show = await self._search_tmdb_tv_show(series_name)
                    if tv_show:
                        tmdb_tv_id = tv_show.get("id")

            if not tmdb_tv_id:
                return ""

            # 检查缓存
            cache_key = f"fanart_{tmdb_tv_id}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                return cached_result

            # 请求限制
            await self._rate_limit()

            fanart_url = f"{self.fanart_base_url}/tv/{tmdb_tv_id}"
            params = {"api_key": self.fanart_api_key}

            async with aiohttp.ClientSession() as session:
                async with session.get(fanart_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        # 优先选择 tvposter，然后是 tvbanner
                        image_url = ""
                        if data.get("tvposter"):
                            image_url = data["tvposter"][0]["url"]
                        elif data.get("tvbanner"):
                            image_url = data["tvbanner"][0]["url"]

                        if image_url:
                            self._set_cache(cache_key, image_url)
                            return image_url

            # 缓存空结果
            self._set_cache(cache_key, "")
            return ""

        except Exception as e:
            logger.error(f"Fanart.tv 图片获取出错: {e}")
            return ""

    async def _get_tmdb_poster(self, series_name: str) -> str:
        """从 TMDB 获取剧集海报"""
        try:
            if not self.tmdb_api_key:
                return ""

            # 搜索 TV 节目
            tv_show = await self._search_tmdb_tv_show(series_name)
            if not tv_show:
                return ""

            poster_path = tv_show.get("poster_path")
            if poster_path:
                return f"https://image.tmdb.org/t/p/w500{poster_path}"

            return ""

        except Exception as e:
            logger.error(f"TMDB 海报获取出错: {e}")
            return ""

    async def _search_tmdb_tv_show(self, series_name: str) -> Optional[dict]:
        """搜索 TMDB TV 节目"""
        if not series_name or not self.tmdb_api_key:
            return None

        try:
            # 检查缓存
            cache_key = f"tv_search_{series_name}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                return cached_result if cached_result else None

            # 请求限制
            await self._rate_limit()

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
                            # 返回第一个结果
                            tv_show = results[0]
                            self._set_cache(cache_key, tv_show)
                            return tv_show

            # 缓存空结果
            self._set_cache(cache_key, None)
            return None

        except Exception as e:
            logger.error(f"TMDB TV 搜索出错: {e}")
            return None

    async def _get_tmdb_episode_details(self, tv_id: int, season_num: int, episode_num: int) -> Optional[dict]:
        """获取 TMDB 剧集详情"""
        try:
            if not self.tmdb_api_key:
                return None

            # 检查缓存
            cache_key = f"episode_{tv_id}_s{season_num}_e{episode_num}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                return cached_result if cached_result else None

            # 请求限制
            await self._rate_limit()

            episode_url = f"{self.tmdb_base_url}/tv/{tv_id}/season/{season_num}/episode/{episode_num}"
            params = {"api_key": self.tmdb_api_key}

            async with aiohttp.ClientSession() as session:
                async with session.get(episode_url, params=params) as response:
                    if response.status == 200:
                        episode_data = await response.json()
                        self._set_cache(cache_key, episode_data)
                        return episode_data

            # 缓存空结果
            self._set_cache(cache_key, None)
            return None

        except Exception as e:
            logger.error(f"TMDB 剧集详情获取出错: {e}")
            return None

    def _get_from_cache(self, key: str) -> Optional[dict]:
        """从缓存获取数据"""
        if key in self.cache_timestamps:
            if time.time() - self.cache_timestamps[key] < self.cache_ttl:
                return self.tmdb_cache.get(key)
            else:
                # 缓存过期，删除
                self.tmdb_cache.pop(key, None)
                self.cache_timestamps.pop(key, None)
        return None

    def _set_cache(self, key: str, value: Optional[dict]):
        """设置缓存"""
        self.tmdb_cache[key] = value
        self.cache_timestamps[key] = time.time()

    async def _rate_limit(self):
        """请求频率限制"""
        current_time = time.time()
        time_diff = current_time - self.last_request_time
        if time_diff < self.request_interval:
            await asyncio.sleep(self.request_interval - time_diff)
        self.last_request_time = time.time()
"""
TVDB 媒体数据提供者
提供 TheTVDB API 的媒体数据丰富功能
"""

import asyncio
import time
from typing import Optional

import aiohttp

from astrbot.api import logger

from .base_provider import MediaEnrichmentProvider


class TVDBProvider(MediaEnrichmentProvider):
    """TVDB 媒体数据提供者"""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "https://api4.thetvdb.com/v4"

        # 认证
        self.jwt_token = ""
        self.token_expires = 0

        # 缓存机制
        self.cache: dict[str, dict] = {}
        self.cache_ttl = 3600  # 缓存1小时
        self.cache_timestamps: dict[str, float] = {}

        # 请求限制
        self.last_request_time = 0
        self.request_interval = 0.1  # 100ms 间隔

    @property
    def name(self) -> str:
        return "TVDB"

    @property
    def priority(self) -> int:
        return 2  # TVDB 作为辅助数据源

    async def enrich_media_data(self, media_data: dict) -> dict:
        """使用 TVDB API 丰富媒体数据"""
        try:
            if not self.api_key:
                logger.debug("未配置 TVDB API 密钥，跳过数据丰富")
                return media_data

            item_type = media_data.get("item_type", "")

            # 只处理剧集类型
            if item_type != "Episode":
                logger.debug(f"跳过非剧集类型: {item_type}")
                return media_data

            series_name = media_data.get("series_name", "")
            season_number = media_data.get("season_number", "")
            episode_number = media_data.get("episode_number", "")

            if not all([series_name, season_number, episode_number]):
                logger.warning("缺少必要信息，跳过 TVDB 查询")
                return media_data

            logger.info(f"开始 TVDB 数据丰富: {series_name} S{season_number}E{episode_number}")

            # 确保已认证
            await self._authenticate()

            # 尝试 TVDB 丰富
            enriched_data = await self._try_tvdb_enrichment(media_data)
            if enriched_data.get("tvdb_enriched"):
                logger.info("TVDB 数据丰富成功")
                return enriched_data
            else:
                logger.info("TVDB 数据丰富未找到匹配结果")
                return media_data

        except Exception as e:
            logger.error(f"TVDB 数据丰富出错: {e}")
            return media_data

    async def get_media_image(self, media_data: dict) -> str:
        """TVDB 不提供图片服务，返回空字符串"""
        return ""

    async def _authenticate(self):
        """TVDB 认证"""
        try:
            if self.jwt_token and time.time() < self.token_expires:
                return  # token 仍然有效

            if not self.api_key:
                return

            auth_url = f"{self.base_url}/login"
            auth_data = {"apikey": self.api_key}

            async with aiohttp.ClientSession() as session:
                async with session.post(auth_url, json=auth_data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self.jwt_token = token_data.get("data", {}).get("token", "")
                        # TVDB token 默认24小时有效
                        self.token_expires = time.time() + 24 * 3600 - 60
                        logger.info("TVDB 认证成功")

        except Exception as e:
            logger.error(f"TVDB 认证出错: {e}")

    async def _try_tvdb_enrichment(self, media_data: dict) -> dict:
        """尝试使用 TVDB 丰富数据"""
        try:
            series_name = media_data.get("series_name", "")
            season_number = media_data.get("season_number", "")
            episode_number = media_data.get("episode_number", "")

            # 搜索系列
            series = await self._search_series(series_name)
            if not series:
                return media_data

            series_id = series.get("id")
            if not series_id:
                return media_data

            # 获取剧集详情
            try:
                season_num = int(season_number)
                episode_num = int(episode_number)
                episode_details = await self._get_episode_details(series_id, season_num, episode_num)

                if episode_details:
                    enriched_data = media_data.copy()
                    enriched_data["tvdb_enriched"] = True
                    enriched_data["tvdb_series_id"] = series_id
                    enriched_data["tvdb_episode_id"] = episode_details.get("id")

                    # 添加剧集信息
                    if episode_details.get("name"):
                        enriched_data["episode_title"] = episode_details["name"]
                    if episode_details.get("overview"):
                        enriched_data["episode_description"] = episode_details["overview"]
                    if episode_details.get("aired"):
                        enriched_data["air_date"] = episode_details["aired"]

                    return enriched_data

            except (ValueError, TypeError) as e:
                logger.debug(f"季数或集数转换失败: {e}")

            return media_data

        except Exception as e:
            logger.error(f"TVDB 丰富处理出错: {e}")
            return media_data

    async def _search_series(self, series_name: str) -> Optional[dict]:
        """搜索 TVDB 系列"""
        try:
            # 检查缓存
            cache_key = f"tvdb_search_{series_name}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                return cached_result if cached_result else None

            # 请求限制
            await self._rate_limit()

            search_url = f"{self.base_url}/search"
            params = {"query": series_name, "type": "series"}
            headers = {"Authorization": f"Bearer {self.jwt_token}"}

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("data", [])

                        if results:
                            # 返回第一个结果
                            series = results[0]
                            self._set_cache(cache_key, series)
                            return series

            # 缓存空结果
            self._set_cache(cache_key, None)
            return None

        except Exception as e:
            logger.error(f"TVDB 系列搜索出错: {e}")
            return None

    async def _get_episode_details(self, series_id: str, season_num: int, episode_num: int) -> Optional[dict]:
        """获取 TVDB 剧集详情"""
        try:
            # 检查缓存
            cache_key = f"tvdb_episode_{series_id}_s{season_num}_e{episode_num}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                return cached_result if cached_result else None

            # 请求限制
            await self._rate_limit()

            episode_url = f"{self.base_url}/series/{series_id}/episodes/{season_num}/{episode_num}"
            headers = {"Authorization": f"Bearer {self.jwt_token}"}

            async with aiohttp.ClientSession() as session:
                async with session.get(episode_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        episode_data = data.get("data")
                        if episode_data:
                            self._set_cache(cache_key, episode_data)
                            return episode_data

            # 缓存空结果
            self._set_cache(cache_key, None)
            return None

        except Exception as e:
            logger.error(f"TVDB 剧集详情获取出错: {e}")
            return None

    def _get_from_cache(self, key: str) -> Optional[dict]:
        """从缓存获取数据"""
        if key in self.cache_timestamps:
            if time.time() - self.cache_timestamps[key] < self.cache_ttl:
                return self.cache.get(key)
            else:
                # 缓存过期，删除
                self.cache.pop(key, None)
                self.cache_timestamps.pop(key, None)
        return None

    def _set_cache(self, key: str, value: Optional[dict]):
        """设置缓存"""
        self.cache[key] = value
        self.cache_timestamps[key] = time.time()

    async def _rate_limit(self):
        """请求频率限制"""
        current_time = time.time()
        time_diff = current_time - self.last_request_time
        if time_diff < self.request_interval:
            await asyncio.sleep(self.request_interval - time_diff)
        self.last_request_time = time.time()
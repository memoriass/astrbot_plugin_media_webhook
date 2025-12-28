"""
BGM.tv 图片提供者
提供 BGM.tv (Bangumi.tv) 的动漫图片获取功能
"""

import asyncio
import time
from typing import Optional

import aiohttp

from astrbot.api import logger

from .base_provider import MediaImageProvider


class BGMTVImageProvider(MediaImageProvider):
    """BGM.tv 图片提供者"""

    def __init__(self, app_id: str = "", app_secret: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = "https://api.bgm.tv"

        # 缓存机制
        self.cache: dict[str, str] = {}
        self.cache_ttl = 3600  # 缓存1小时
        self.cache_timestamps: dict[str, float] = {}

        # 请求限制
        self.last_request_time = 0
        self.request_interval = 1.0  # 1秒间隔，避免请求过频

        # OAuth token
        self.access_token = ""
        self.token_expires = 0

    @property
    def name(self) -> str:
        return "BGM.tv"

    @property
    def priority(self) -> int:
        return 3  # BGM.tv 作为动漫图片来源，优先级较低

    async def get_image(self, media_data: dict) -> str:
        """获取 BGM.tv 图片"""
        try:
            series_name = media_data.get("series_name", "")
            if not series_name:
                logger.debug("缺少剧集名称，跳过 BGM.tv 图片获取")
                return ""

            logger.info(f"BGM.tv 获取图片: {series_name}")

            # 检查缓存
            cache_key = f"bgm_{series_name}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                return cached_result

            # 搜索作品
            subject = await self._search_subject(series_name)
            if not subject:
                self._set_cache(cache_key, "")
                return ""

            # 获取图片
            image_url = await self._get_subject_image(subject)
            if image_url:
                self._set_cache(cache_key, image_url)
                logger.info("BGM.tv 图片获取成功")
                return image_url

            # 缓存空结果
            self._set_cache(cache_key, "")
            logger.info("BGM.tv 未找到图片")
            return ""

        except Exception as e:
            logger.error(f"BGM.tv 图片获取出错: {e}")
            return ""

    async def _search_subject(self, series_name: str) -> Optional[dict]:
        """搜索 BGM.tv 作品"""
        try:
            # 请求限制
            await self._rate_limit()

            search_url = f"{self.base_url}/search/subject/{series_name}"
            params = {"type": 2}  # 2 = Anime

            headers = {}
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("list", [])

                        if results:
                            # 返回第一个结果
                            return results[0]

            return None

        except Exception as e:
            logger.error(f"BGM.tv 搜索出错: {e}")
            return None

    async def _get_subject_image(self, subject: dict) -> str:
        """获取作品图片"""
        try:
            subject_id = subject.get("id")
            if not subject_id:
                return ""

            # 请求限制
            await self._rate_limit()

            subject_url = f"{self.base_url}/v0/subjects/{subject_id}"

            headers = {}
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"

            async with aiohttp.ClientSession() as session:
                async with session.get(subject_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()

                        # 优先选择 large 图片，然后是 common
                        images = data.get("images", {})
                        if images.get("large"):
                            return images["large"]
                        elif images.get("common"):
                            return images["common"]

            return ""

        except Exception as e:
            logger.error(f"BGM.tv 图片获取出错: {e}")
            return ""

    async def _authenticate(self):
        """OAuth 认证（如果需要）"""
        try:
            if self.access_token and time.time() < self.token_expires:
                return  # token 仍然有效

            if not self.app_id or not self.app_secret:
                return  # 没有认证信息

            auth_url = f"{self.base_url}/oauth/access_token"
            auth_data = {
                "grant_type": "client_credentials",
                "client_id": self.app_id,
                "client_secret": self.app_secret
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(auth_url, data=auth_data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self.access_token = token_data.get("access_token", "")
                        expires_in = token_data.get("expires_in", 3600)
                        self.token_expires = time.time() + expires_in - 60  # 提前60秒过期
                        logger.info("BGM.tv OAuth 认证成功")

        except Exception as e:
            logger.error(f"BGM.tv 认证出错: {e}")

    def _get_from_cache(self, key: str) -> Optional[str]:
        """从缓存获取数据"""
        if key in self.cache_timestamps:
            if time.time() - self.cache_timestamps[key] < self.cache_ttl:
                return self.cache.get(key)
            else:
                # 缓存过期，删除
                self.cache.pop(key, None)
                self.cache_timestamps.pop(key, None)
        return None

    def _set_cache(self, key: str, value: Optional[str]):
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
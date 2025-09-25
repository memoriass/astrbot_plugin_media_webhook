"""
TMDB 元数据丰富模块
提供 TMDB API 数据获取和媒体信息丰富功能
"""

import asyncio
import time
from typing import Optional

import aiohttp

from astrbot.api import logger


class TMDBEnricher:
    """TMDB 元数据丰富器"""

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
            enriched_data = await self.try_tmdb_enrichment(media_data)
            if enriched_data.get("tmdb_enriched"):
                logger.info("TMDB 数据丰富成功")

                # 如果没有图片，尝试从 Fanart.tv 获取
                if not enriched_data.get("image_url") and self.fanart_api_key:
                    fanart_image = await self.get_fanart_image(enriched_data)
                    if fanart_image:
                        enriched_data["image_url"] = fanart_image
                        logger.info("Fanart.tv 图片获取成功")

                return enriched_data
            else:
                logger.info("TMDB 数据丰富未找到匹配结果，尝试仅获取图片")

                # 即使TMDB丰富失败，如果原始数据无图片且启用了图片降级，也尝试获取图片
                if not media_data.get("image_url") and self.tmdb_api_key:
                    image_enriched_data = await self.try_image_only_enrichment(
                        media_data
                    )
                    if image_enriched_data.get("image_url"):
                        logger.info("图片获取成功")
                        return image_enriched_data

                logger.info("TMDB 数据丰富失败，返回原始数据")
                return media_data

        except Exception as e:
            logger.error(f"TMDB 数据丰富出错: {e}")
            return media_data

    async def try_tmdb_enrichment(self, media_data: dict) -> dict:
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
            try:
                season_num = (
                    int(season_number) if season_number and season_number.strip() else 1
                )
                episode_num = (
                    int(episode_number)
                    if episode_number and episode_number.strip()
                    else 1
                )
                episode_details = await self.get_tmdb_episode_details(
                    tv_id, season_num, episode_num
                )
            except (ValueError, TypeError) as e:
                logger.debug(
                    f"季数或集数转换失败: season={season_number}, episode={episode_number}, error={e}"
                )
                # 即使剧集详情获取失败，也尝试使用剧集海报
                enriched_data = media_data.copy()
                if tv_show.get("poster_path") and not enriched_data.get("image_url"):
                    poster_path = tv_show.get("poster_path")
                    enriched_data["image_url"] = (
                        f"https://image.tmdb.org/t/p/w500{poster_path}"
                    )
                    enriched_data["tmdb_enriched"] = True
                    enriched_data["tmdb_tv_id"] = tv_id
                    logger.info(
                        f"TMDB 剧集海报获取成功（降级）: {enriched_data['image_url']}"
                    )
                    return enriched_data
                return media_data

            if episode_details:
                # 更新媒体数据
                enriched_data = media_data.copy()
                enriched_data["tmdb_tv_show"] = tv_show  # 保存TV节目信息供后续使用

                # 更新剧集名称
                episode_name = episode_details.get("name")
                if episode_name:
                    enriched_data["item_name"] = episode_name

                # 更新剧情简介
                overview = episode_details.get("overview")
                if overview and not enriched_data.get("overview"):
                    enriched_data["overview"] = overview

                # 更新时长
                runtime = episode_details.get("runtime")
                if runtime and not enriched_data.get("runtime"):
                    enriched_data["runtime"] = f"{runtime}分钟"

                # 更新图片
                still_path = episode_details.get("still_path")
                logger.debug(f"TMDB 剧集截图路径: {still_path}")
                if still_path and not enriched_data.get("image_url"):
                    enriched_data["image_url"] = (
                        f"https://image.tmdb.org/t/p/w500{still_path}"
                    )
                    logger.info(f"TMDB 剧集截图获取成功: {enriched_data['image_url']}")
                elif not still_path:
                    logger.debug("TMDB 剧集截图路径为空，尝试获取剧集海报")
                    # 如果没有剧集截图，尝试获取剧集海报
                    tv_show_data = enriched_data.get("tmdb_tv_show", {})
                    if (
                        tv_show_data
                        and tv_show_data.get("poster_path")
                        and not enriched_data.get("image_url")
                    ):
                        poster_path = tv_show_data.get("poster_path")
                        enriched_data["image_url"] = (
                            f"https://image.tmdb.org/t/p/w500{poster_path}"
                        )
                        logger.info(
                            f"TMDB 剧集海报获取成功: {enriched_data['image_url']}"
                        )

                # 添加 TMDB 标记和 ID
                enriched_data["tmdb_enriched"] = True
                enriched_data["tmdb_tv_id"] = tv_id
                enriched_data["tmdb_episode_id"] = episode_details.get("id")

                return enriched_data
            else:
                # 如果没有获取到剧集详情，但有TV节目信息，尝试使用剧集海报
                logger.debug("未获取到剧集详情，尝试使用剧集海报")
                enriched_data = media_data.copy()
                if tv_show.get("poster_path") and not enriched_data.get("image_url"):
                    poster_path = tv_show.get("poster_path")
                    enriched_data["image_url"] = (
                        f"https://image.tmdb.org/t/p/w500{poster_path}"
                    )
                    enriched_data["tmdb_enriched"] = True
                    enriched_data["tmdb_tv_id"] = tv_id
                    logger.info(
                        f"TMDB 剧集海报获取成功（无剧集详情）: {enriched_data['image_url']}"
                    )
                    return enriched_data

            return media_data

        except Exception as e:
            logger.error(f"TMDB 丰富处理出错: {e}")
            return media_data

    async def try_image_only_enrichment(self, media_data: dict) -> dict:
        """仅尝试获取图片，不修改其他数据"""
        try:
            series_name = media_data.get("series_name", "")
            if not series_name:
                return media_data

            # 搜索 TV 节目
            tv_show = await self.search_tmdb_tv_show(series_name)
            if not tv_show:
                return media_data

            tv_id = tv_show.get("id")
            if not tv_id:
                return media_data

            # 创建包含TMDB ID的数据副本，用于fanart查询
            enriched_data = media_data.copy()
            enriched_data["tmdb_tv_id"] = tv_id

            # 首先尝试从TMDB获取剧集截图
            season_number = media_data.get("season_number", "")
            episode_number = media_data.get("episode_number", "")

            if season_number and episode_number:
                try:
                    season_num = (
                        int(season_number)
                        if season_number and season_number.strip()
                        else 1
                    )
                    episode_num = (
                        int(episode_number)
                        if episode_number and episode_number.strip()
                        else 1
                    )
                    episode_details = await self.get_tmdb_episode_details(
                        tv_id, season_num, episode_num
                    )

                    if episode_details:
                        still_path = episode_details.get("still_path")
                        if still_path:
                            enriched_data["image_url"] = (
                                f"https://image.tmdb.org/t/p/w500{still_path}"
                            )
                            logger.info("TMDB 剧集截图获取成功")
                            return enriched_data
                except (ValueError, TypeError) as e:
                    logger.debug(f"季数或集数转换失败，跳过剧集截图: {e}")

            # 如果没有获取到剧集截图，尝试从 Fanart.tv 获取海报
            if self.fanart_api_key:
                fanart_image = await self.get_fanart_image(enriched_data)
                if fanart_image:
                    enriched_data["image_url"] = fanart_image
                    logger.info("Fanart.tv 海报获取成功")
                    return enriched_data

            # 如果都失败了，尝试从TMDB获取剧集海报
            poster_path = tv_show.get("poster_path")
            if poster_path:
                enriched_data["image_url"] = (
                    f"https://image.tmdb.org/t/p/w500{poster_path}"
                )
                logger.info("TMDB 剧集海报获取成功")
                return enriched_data

            return media_data

        except Exception as e:
            logger.error(f"图片获取处理出错: {e}")
            return media_data

    async def search_tmdb_tv_show(self, series_name: str) -> Optional[dict]:
        """搜索 TMDB TV 节目"""
        if not series_name:
            return None

        try:
            # 检查缓存
            cache_key = f"tv_search_{series_name}"
            cached_result = self.get_from_cache(cache_key)
            if cached_result is not None:
                logger.debug(f"使用 TMDB TV 搜索缓存: {series_name}")
                return cached_result

            # 请求限制
            await self.rate_limit()

            # 搜索 TV 节目
            search_url = f"{self.tmdb_base_url}/search/tv"
            params = {
                "api_key": self.tmdb_api_key,
                "query": series_name,
                "language": "zh-CN",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])

                        if results:
                            # 返回第一个匹配结果
                            tv_show = results[0]
                            self.set_cache(cache_key, tv_show)
                            logger.info(f"TMDB TV 搜索成功: {series_name}")
                            return tv_show
                        logger.warning(f"TMDB TV 搜索无结果: {series_name}")
                    else:
                        logger.warning(f"TMDB TV 搜索失败: {response.status}")

            # 缓存空结果
            self.set_cache(cache_key, None)
            return None

        except Exception as e:
            logger.error(f"TMDB TV 搜索出错: {e}")
            return None

    async def get_tmdb_episode_details(
        self, tv_id: int, season_number: int, episode_number: int
    ) -> Optional[dict]:
        """获取 TMDB 剧集详情"""
        try:
            # 检查缓存
            cache_key = f"episode_{tv_id}_{season_number}_{episode_number}"
            cached_result = self.get_from_cache(cache_key)
            if cached_result is not None:
                logger.debug(f"使用 TMDB 剧集缓存: {cache_key}")
                return cached_result

            # 请求限制
            await self.rate_limit()

            # 获取剧集详情
            episode_url = f"{self.tmdb_base_url}/tv/{tv_id}/season/{season_number}/episode/{episode_number}"
            params = {"api_key": self.tmdb_api_key, "language": "zh-CN"}

            async with aiohttp.ClientSession() as session:
                async with session.get(episode_url, params=params) as response:
                    if response.status == 200:
                        episode_data = await response.json()
                        self.set_cache(cache_key, episode_data)
                        logger.info(f"TMDB 剧集详情获取成功: {cache_key}")
                        return episode_data
                    logger.warning(f"TMDB 剧集详情获取失败: {response.status}")

            # 缓存空结果
            self.set_cache(cache_key, None)
            return None

        except Exception as e:
            logger.error(f"TMDB 剧集详情获取出错: {e}")
            return None

    async def get_fanart_image(self, media_data: dict) -> str:
        """从 Fanart.tv 获取图片"""
        try:
            if not self.fanart_api_key:
                return ""

            tmdb_tv_id = media_data.get("tmdb_tv_id")
            if not tmdb_tv_id:
                return ""

            # 检查缓存
            cache_key = f"fanart_{tmdb_tv_id}"
            cached_result = self.get_from_cache(cache_key)
            if cached_result is not None:
                logger.debug(f"使用 Fanart.tv 缓存: {cache_key}")
                return cached_result or ""

            # 请求限制
            await self.rate_limit()

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

                        self.set_cache(cache_key, image_url)
                        if image_url:
                            logger.info(f"Fanart.tv 图片获取成功: {cache_key}")
                        return image_url
                    logger.warning(f"Fanart.tv 请求失败: {response.status}")

            # 缓存空结果
            self.set_cache(cache_key, "")
            return ""

        except Exception as e:
            logger.error(f"Fanart.tv 图片获取失败: {e}")
            return ""

    async def rate_limit(self):
        """请求限制"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.request_interval:
            sleep_time = self.request_interval - time_since_last
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    def get_from_cache(self, key: str) -> Optional[dict]:
        """从缓存获取数据"""
        if key not in self.tmdb_cache:
            return None

        # 检查是否过期
        if key in self.cache_timestamps:
            cache_time = self.cache_timestamps[key]
            if time.time() - cache_time > self.cache_ttl:
                # 清理过期缓存
                del self.tmdb_cache[key]
                del self.cache_timestamps[key]
                return None

        return self.tmdb_cache[key]

    def set_cache(self, key: str, value: dict):
        """设置缓存"""
        self.tmdb_cache[key] = value
        self.cache_timestamps[key] = time.time()

        # 清理过期缓存
        self.cleanup_expired_cache()

    def cleanup_expired_cache(self):
        """清理过期缓存"""
        current_time = time.time()
        expired_keys = []

        for key, cache_time in self.cache_timestamps.items():
            if current_time - cache_time > self.cache_ttl:
                expired_keys.append(key)

        for key in expired_keys:
            if key in self.tmdb_cache:
                del self.tmdb_cache[key]
            if key in self.cache_timestamps:
                del self.cache_timestamps[key]

        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 个过期 TMDB 缓存条目")

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        return {
            "cache_size": len(self.tmdb_cache),
            "cache_keys": list(self.tmdb_cache.keys()),
        }

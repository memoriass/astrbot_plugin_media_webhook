"""
TMDB 媒体数据提供者
提供 TMDB API 的媒体数据丰富和图片获取功能
"""

import re
from typing import Any

from astrbot.api import logger

from .base_provider import BaseProvider, MediaEnrichmentProvider, MediaImageProvider


class TMDBProvider(MediaEnrichmentProvider, MediaImageProvider, BaseProvider):
    """TMDB 媒体数据和图片提供者"""

    def __init__(self, api_key: str, fanart_api_key: str = ""):
        BaseProvider.__init__(self, request_interval=0.2)
        self.tmdb_api_key = api_key
        self.fanart_api_key = fanart_api_key
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.fanart_base_url = "https://webservice.fanart.tv/v3"

    @property
    def name(self) -> str:
        return "TMDB"

    @property
    def priority(self) -> int:
        return 1

    async def enrich_media_data(self, media_data: dict) -> dict:
        """使用 TMDB API 丰富媒体数据"""
        try:
            if not self.tmdb_api_key:
                return media_data

            item_type = media_data.get("item_type", "")
            if item_type not in ["Movie", "Episode", "Series", "Season"]:
                return media_data

            # 优先尝试使用 ProviderIDs 里的 TMDB ID
            p_ids = media_data.get("provider_ids", {})
            tmdb_id = p_ids.get("TMDB") or p_ids.get("Tmdb")
            imdb_id = p_ids.get("IMDB") or p_ids.get("Imdb")

            # 如果已知 ID，直接获取详情
            if tmdb_id:
                if item_type == "Movie":
                    return await self._enrich_movie_by_id(media_data, tmdb_id)
                else:
                    return await self._enrich_tv_by_id(media_data, tmdb_id)

            # 如果只有 IMDB ID
            if imdb_id and not tmdb_id:
                tmdb_id = await self._find_tmdb_id_by_external(imdb_id, "imdb_id")
                if tmdb_id:
                    if item_type == "Movie":
                        return await self._enrich_movie_by_id(media_data, tmdb_id)
                    else:
                        return await self._enrich_tv_by_id(media_data, tmdb_id)

            # 如果没有 ID，按照标题搜索
            if item_type == "Movie":
                return await self._enrich_movie_by_search(media_data)
            else:
                return await self._enrich_tv_by_search(media_data)

        except Exception as e:
            logger.error(f"TMDB 数据丰富出错: {e}")
            return media_data

    async def get_media_image(self, media_data: dict) -> str:
        return await self.get_image(media_data)

    async def get_image(self, media_data: dict) -> str:
        """获取媒体图片"""
        try:
            item_type = media_data.get("item_type", "")
            season_number = media_data.get("season_number")
            episode_number = media_data.get("episode_number")

            # 1. 如果是剧集且有截图需求，尝试从剧集详情获取 still_path
            if item_type == "Episode" and season_number and episode_number:
                tmdb_id = media_data.get("tmdb_tv_id") or media_data.get("tmdb_id")
                if tmdb_id:
                    details = await self._get_tmdb_episode_details(
                        tmdb_id, season_number, episode_number
                    )
                    if details and details.get("still_path"):
                        return f"https://image.tmdb.org/t/p/w500{details['still_path']}"

            # 2. 尝试从 Fanart.tv 获取海报
            if self.fanart_api_key and item_type != "Movie":
                fanart_image = await self._get_fanart_image(media_data)
                if fanart_image:
                    return fanart_image

            # 3. 尝试从 TMDB 获取 Poster
            poster_path = media_data.get("poster_path")
            if poster_path:
                return f"https://image.tmdb.org/t/p/w500{poster_path}"

            return ""
        except Exception as e:
            logger.error(f"TMDB 图片获取出错: {e}")
            return ""

    # --- 私有方法：详情获取 ---

    async def _enrich_movie_by_id(self, media_data: dict, movie_id: str) -> dict:
        url = f"{self.tmdb_base_url}/movie/{movie_id}"
        data = await self._http_get(
            url, params={"api_key": self.tmdb_api_key, "language": "zh-CN"}
        )
        if data:
            media_data.update(
                {
                    "tmdb_id": data.get("id"),
                    "overview": data.get("overview") or media_data.get("overview"),
                    "year": (data.get("release_date") or "")[:4],
                    "poster_path": data.get("poster_path"),
                    "tmdb_enriched": True,
                }
            )
        return media_data

    async def _enrich_tv_by_id(self, media_data: dict, tv_id: str) -> dict:
        url = f"{self.tmdb_base_url}/tv/{tv_id}"
        data = await self._http_get(
            url, params={"api_key": self.tmdb_api_key, "language": "zh-CN"}
        )
        if data:
            media_data.update(
                {
                    "tmdb_tv_id": data.get("id"),
                    "poster_path": data.get("poster_path"),
                    "year": (data.get("first_air_date") or "")[:4],
                }
            )
            season = media_data.get("season_number")
            episode = media_data.get("episode_number")
            if season and episode:
                ep_data = await self._get_tmdb_episode_details(
                    data.get("id"), season, episode
                )
                if ep_data:
                    media_data.update(
                        {
                            "item_name": ep_data.get("name")
                            or media_data.get("item_name"),
                            "overview": ep_data.get("overview")
                            or media_data.get("overview"),
                            "tmdb_enriched": True,
                        }
                    )
        return media_data

    # --- 私有方法：搜索逻辑 ---

    async def _enrich_movie_by_search(self, media_data: dict) -> dict:
        name = media_data.get("item_name")
        year = media_data.get("year")
        if not name:
            return media_data

        search_url = f"{self.tmdb_base_url}/search/movie"
        params = {"api_key": self.tmdb_api_key, "query": name, "language": "zh-CN"}
        if year:
            params["year"] = year

        results = await self._http_get(search_url, params=params)
        if results and results.get("results"):
            # 强化匹配：检查名称相似度
            best_match = self._find_best_match(name, results["results"], "title")
            if best_match:
                return await self._enrich_movie_by_id(media_data, best_match["id"])
        return media_data

    async def _enrich_tv_by_search(self, media_data: dict) -> dict:
        name = media_data.get("series_name")
        year = media_data.get("year")
        if not name:
            return media_data

        search_url = f"{self.tmdb_base_url}/search/tv"
        params = {"api_key": self.tmdb_api_key, "query": name, "language": "zh-CN"}
        if year:
            params["first_air_date_year"] = year

        results = await self._http_get(search_url, params=params)
        if results and results.get("results"):
            best_match = self._find_best_match(name, results["results"], "name")
            if best_match:
                return await self._enrich_tv_by_id(media_data, best_match["id"])
        return media_data

    def _find_best_match(self, query: str, results: list, key: str) -> dict | None:
        """寻找最佳匹配（简单的名称清理和包含检查）"""
        query_clean = self._clean_title(query)
        for res in results:
            res_title = res.get(key, "")
            res_clean = self._clean_title(res_title)
            # 1. 完全一致
            if query_clean == res_clean:
                return res
            # 2. 包含关系
            if query_clean in res_clean or res_clean in query_clean:
                return res
        return results[0]  # 默认返回第一个

    def _clean_title(self, title: str) -> str:
        """清理标题，去除特殊字符和年份"""
        if not title:
            return ""
        # 去除 (2024) 这种年份
        title = re.sub(r"\(.*?\)", "", title)
        # 去除特殊字符
        title = re.sub(r"[^\w\s\u4e00-\u9fa5]", "", title)
        return title.lower().strip()

    async def _find_tmdb_id_by_external(
        self, external_id: str, source: str
    ) -> str | None:
        url = f"{self.tmdb_base_url}/find/{external_id}"
        params = {"api_key": self.tmdb_api_key, "external_source": source}
        data = await self._http_get(url, params=params)
        if data:
            for key in ["movie_results", "tv_results", "tv_episode_results"]:
                if data.get(key):
                    return data[key][0].get("id")
        return None

    async def _get_tmdb_episode_details(
        self, tv_id: Any, season: Any, episode: Any
    ) -> dict | None:
        cache_key = f"ep_detail_{tv_id}_{season}_{episode}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.tmdb_base_url}/tv/{tv_id}/season/{season}/episode/{episode}"
        data = await self._http_get(
            url, params={"api_key": self.tmdb_api_key, "language": "zh-CN"}
        )
        if data:
            self._set_cache(cache_key, data)
        return data

    async def _get_fanart_image(self, media_data: dict) -> str:
        tmdb_id = media_data.get("tmdb_tv_id") or media_data.get("tmdb_id")
        if not tmdb_id:
            return ""

        cache_key = f"fanart_{tmdb_id}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.fanart_base_url}/tv/{tmdb_id}"
        data = await self._http_get(url, params={"api_key": self.fanart_api_key})
        if data:
            for key in ["tvposter", "tvbanner"]:
                if data.get(key):
                    img_url = data[key][0].get("url")
                    self._set_cache(cache_key, img_url)
                    return img_url
        return ""

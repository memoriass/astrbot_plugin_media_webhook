"""
媒体数据丰富管理器
统一管理各种媒体数据和图片提供者，提供统一的接口
"""

import os
from typing import Dict, List, Optional

from astrbot.api import logger

from .base_provider import MediaEnrichmentProvider, MediaImageProvider, BaseProvider
from .tmdb_provider import TMDBProvider
from .tvdb_provider import TVDBProvider
from .bgm_provider import BGMProvider
from ..cache_manager import CacheManager

class EnrichmentManager:
    """媒体数据丰富管理器"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.enrichment_providers: List[MediaEnrichmentProvider] = []
        self.image_providers: List[MediaImageProvider] = []

        # 初始化持久化缓存
        # 优先从配置获取数据路径
        db_dir = self.config.get("data_path")
        if not db_dir:
            # Fallback (old logic, ideally not hit)
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_dir = os.path.join(root_dir, "data")
        
        persistence_days = self.config.get("cache_persistence_days", 7)
        self.cache = CacheManager(db_dir, persistence_days)
        # 启动时简单清理一次
        self.cache.cleanup()

        # 初始化提供者
        self._initialize_providers()

        logger.info("数据丰富管理器初始化完成")

    def _initialize_providers(self):
        """初始化所有提供者"""
        # TMDB 提供者
        tmdb_api_key = self.config.get("tmdb_api_key", "")
        fanart_api_key = self.config.get("fanart_api_key", "")
        if tmdb_api_key:
            tmdb_provider = TMDBProvider(tmdb_api_key, fanart_api_key)
            self.enrichment_providers.append(tmdb_provider)
            self.image_providers.append(tmdb_provider)
            logger.info("TMDB 提供者已启用")

        # TVDB 提供者
        tvdb_api_key = self.config.get("tvdb_api_key", "")
        if tvdb_api_key:
            tvdb_provider = TVDBProvider(tvdb_api_key)
            self.enrichment_providers.append(tvdb_provider)
            logger.info("TVDB 提供者已启用")

        # BGM.tv 提供者 (同时支持丰富和图片)
        bgm_app_id = self.config.get("bgm_app_id", "")
        bgm_app_secret = self.config.get("bgm_app_secret", "")
        # BGM 不需要 API Key 也可以进行基础搜索，但有 ID 更好
        bgm_provider = BGMProvider(self.config)
        self.enrichment_providers.append(bgm_provider)
        self.image_providers.append(bgm_provider)
        logger.info("BGM.tv 提供者已启用")

        # 按优先级排序
        self.enrichment_providers.sort(key=lambda p: p.priority)
        self.image_providers.sort(key=lambda p: p.priority)

        if not self.enrichment_providers:
            logger.warning("未配置任何媒体数据丰富提供者")
        if not self.image_providers:
            logger.warning("未配置任何图片提供者")

    async def enrich_media_data(self, media_data: dict) -> dict:
        """
        使用所有可用的提供者丰富媒体数据
        """
        try:
            # 1. 尝试从持久化缓存获取
            cache_key = self._generate_cache_key(media_data)
            cached_data = self.cache.get(cache_key)
            if cached_data:
                logger.info(f"使用持久化缓存数据: {media_data.get('item_name')}")
                # 合并缓存数据，但保留原始来源信息
                media_data.update(cached_data)
                media_data["enriched_from_cache"] = True
                return media_data

            # 2. 按优先级尝试各 Provider
            enriched_data = media_data.copy()
            enriched = False

            for provider in self.enrichment_providers:
                try:
                    logger.debug(f"尝试使用 {provider.name} 丰富数据")
                    result = await provider.enrich_media_data(enriched_data)

                    # 检查是否成功丰富
                    if result != enriched_data:
                        logger.info(f"{provider.name} 数据丰富成功")
                        enriched_data = result
                        enriched = True
                        break  # 成功后停止尝试其他提供者

                except Exception as e:
                    logger.error(f"{provider.name} 数据丰富失败: {e}")
                    continue

            # 3. 如果丰富成功，存入缓存
            if enriched:
                # 只缓存关键的丰富字段，不缓存 image_url（因为可能过快失效或需要动态构建）
                cache_data = {
                    "overview": enriched_data.get("overview"),
                    "tmdb_id": enriched_data.get("tmdb_id"),
                    "bgm_id": enriched_data.get("bgm_id"),
                    "tmdb_enriched": enriched_data.get("tmdb_enriched"),
                    "bgm_enriched": enriched_data.get("bgm_enriched"),
                    "year": enriched_data.get("year"),
                }
                self.cache.set(cache_key, cache_data)

            return enriched_data

        except Exception as e:
            logger.error(f"媒体数据丰富出错: {e}")
        return media_data

    def _generate_cache_key(self, media_data: dict) -> str:
        """根据媒体信息生成唯一的缓存 Key"""
        item_name = media_data.get("item_name", "")
        item_type = media_data.get("item_type", "")
        year = media_data.get("year", "")
        # 如果有 ProviderIds (来自 Emby/Plex)，优先使用 ID 作为 Key
        p_ids = media_data.get("provider_ids", {})
        if p_ids:
            for platform in ["TMDB", "IMDB", "TVDB"]:
                id_val = p_ids.get(platform) or p_ids.get(platform.capitalize()) or p_ids.get(platform.lower())
                if id_val:
                    return f"{platform}_{id_val}"
        
        # 兜底：使用 名称+类型+年份 的组合哈希
        key_str = f"{item_name}_{item_type}_{year}".lower().strip()
        import hashlib
        return hashlib.md5(key_str.encode()).hexdigest()

    async def get_media_image(self, media_data: dict) -> str:
        """
        获取媒体图片
        """
        try:
            for provider in self.image_providers:
                try:
                    logger.debug(f"尝试使用 {provider.name} 获取图片")
                    image_url = await provider.get_image(media_data)

                    if image_url:
                        logger.info(f"{provider.name} 图片获取成功")
                        return image_url

                except Exception as e:
                    logger.error(f"{provider.name} 图片获取失败: {e}")
                    continue

            return ""

        except Exception as e:
            logger.error(f"图片获取出错: {e}")
            return ""

    def get_provider_status(self) -> Dict:
        """获取提供者状态"""
        return {
            "enrichment_providers": [
                {"name": p.name, "priority": p.priority}
                for p in self.enrichment_providers
            ],
            "image_providers": [
                {"name": p.name, "priority": p.priority}
                for p in self.image_providers
            ]
        }

# 向后兼容的别名
MediaEnrichmentManager = EnrichmentManager
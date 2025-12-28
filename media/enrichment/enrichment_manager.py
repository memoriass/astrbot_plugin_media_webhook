"""
媒体数据丰富管理器
统一管理各种媒体数据和图片提供者，提供统一的接口
"""

from typing import Dict, List, Optional

from astrbot.api import logger

from .base_provider import MediaEnrichmentProvider, MediaImageProvider
from .tmdb_provider import TMDBProvider
from .tvdb_provider import TVDBProvider
from .bgm_provider import BGMTVImageProvider


class EnrichmentManager:
    """媒体数据丰富管理器"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.enrichment_providers: List[MediaEnrichmentProvider] = []
        self.image_providers: List[MediaImageProvider] = []

        # 初始化提供者
        self._initialize_providers()

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

        # BGM.tv 图片提供者
        bgm_app_id = self.config.get("bgm_app_id", "")
        bgm_app_secret = self.config.get("bgm_app_secret", "")
        if bgm_app_id and bgm_app_secret:
            bgm_provider = BGMTVImageProvider(bgm_app_id, bgm_app_secret)
            self.image_providers.append(bgm_provider)
            logger.info("BGM.tv 图片提供者已启用")

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

        按优先级尝试每个提供者，直到有一个成功丰富数据
        """
        try:
            enriched_data = media_data.copy()

            for provider in self.enrichment_providers:
                try:
                    logger.debug(f"尝试使用 {provider.name} 丰富数据")
                    result = await provider.enrich_media_data(enriched_data)

                    # 检查是否成功丰富
                    if result != enriched_data:
                        logger.info(f"{provider.name} 数据丰富成功")
                        enriched_data = result
                        break  # 成功后停止尝试其他提供者

                except Exception as e:
                    logger.error(f"{provider.name} 数据丰富失败: {e}")
                    continue

            return enriched_data

        except Exception as e:
            logger.error(f"媒体数据丰富出错: {e}")
            return media_data

    async def get_media_image(self, media_data: dict) -> str:
        """
        获取媒体图片

        按优先级尝试每个图片提供者，直到获取到图片
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

            logger.info("所有图片提供者都未获取到图片")
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

    def add_enrichment_provider(self, provider: MediaEnrichmentProvider):
        """添加数据丰富提供者"""
        self.enrichment_providers.append(provider)
        self.enrichment_providers.sort(key=lambda p: p.priority)
        logger.info(f"添加数据丰富提供者: {provider.name}")

    def add_image_provider(self, provider: MediaImageProvider):
        """添加图片提供者"""
        self.image_providers.append(provider)
        self.image_providers.sort(key=lambda p: p.priority)
        logger.info(f"添加图片提供者: {provider.name}")

    def remove_enrichment_provider(self, name: str):
        """移除数据丰富提供者"""
        self.enrichment_providers = [p for p in self.enrichment_providers if p.name != name]
        logger.info(f"移除数据丰富提供者: {name}")

    def remove_image_provider(self, name: str):
        """移除图片提供者"""
        self.image_providers = [p for p in self.image_providers if p.name != name]
        logger.info(f"移除图片提供者: {name}")


# 向后兼容的别名
MediaEnrichmentManager = EnrichmentManager
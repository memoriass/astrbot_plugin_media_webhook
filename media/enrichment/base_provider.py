"""
媒体数据丰富提供者基础接口
定义了媒体数据丰富和图片获取的标准接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional

from astrbot.api import logger


class MediaEnrichmentProvider(ABC):
    """媒体数据丰富提供者基础接口"""

    @abstractmethod
    async def enrich_media_data(self, media_data: dict) -> dict:
        """
        丰富媒体数据

        Args:
            media_data: 原始媒体数据

        Returns:
            丰富后的媒体数据
        """
        pass

    @abstractmethod
    async def get_media_image(self, media_data: dict) -> str:
        """
        获取媒体图片

        Args:
            media_data: 媒体数据

        Returns:
            图片URL，如果获取失败返回空字符串
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """提供者名称"""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """优先级，数字越小优先级越高"""
        pass


class MediaImageProvider(ABC):
    """媒体图片提供者基础接口"""

    @abstractmethod
    async def get_image(self, media_data: dict) -> str:
        """
        获取媒体图片

        Args:
            media_data: 媒体数据

        Returns:
            图片URL，如果获取失败返回空字符串
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """提供者名称"""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """优先级，数字越小优先级越高"""
        pass
"""
媒体处理模块
包含媒体数据预处理、核心处理和数据丰富功能
按照处理流程组织：预处理 -> 核心处理 -> 数据丰富
"""

from .data_processor import MediaDataProcessor
from .media_handler import MediaHandler
from .enrichment import EnrichmentManager
from .image_renderer import ImageRenderer
from .processors import (
    BaseMediaProcessor,
    EmbyProcessor,
    JellyfinProcessor,
    PlexProcessor,
    GenericProcessor,
    ProcessorManager,
)

__all__ = [
    "MediaDataProcessor",
    "MediaHandler",
    "EnrichmentManager",
    "BaseMediaProcessor",
    "EmbyProcessor",
    "JellyfinProcessor",
    "PlexProcessor",
    "GenericProcessor",
    "ProcessorManager",
]
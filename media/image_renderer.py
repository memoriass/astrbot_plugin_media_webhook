"""
图片渲染模块
将图文消息渲染成单张图片，避免合并转发图文失败的问题
"""

import asyncio
import io
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from astrbot.api import logger


class ImageRenderer:
    """图片渲染器 - 将文本和图片渲染成单张图片"""

    def __init__(self):
        """初始化渲染器"""
        if not PIL_AVAILABLE:
            logger.warning("PIL/Pillow 未安装，图片渲染功能不可用")
            self.available = False
            return
        
        self.available = True
        self.bg_color = (245, 245, 247)  # 浅灰色背景
        self.text_color = (0, 0, 0)  # 黑色文字
        self.title_color = (33, 33, 33)  # 深灰色标题
        self.subtitle_color = (153, 153, 153)  # 浅灰色副标题
        
        # 尝试加载系统字体
        self.title_font = self._get_font(size=28, bold=True)
        self.content_font = self._get_font(size=16)
        self.small_font = self._get_font(size=12)

    def _get_font(self, size: int = 16, bold: bool = False) -> ImageFont.FreeTypeFont:
        """获取字体对象"""
        try:
            # Windows 系统字体路径
            font_paths = [
                "C:\\Windows\\Fonts\\msyh.ttc",  # 微软雅黑
                "C:\\Windows\\Fonts\\arial.ttf",
                "/System/Library/Fonts/PingFang.ttc",  # macOS
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
            ]
            
            for font_path in font_paths:
                try:
                    return ImageFont.truetype(font_path, size)
                except (FileNotFoundError, OSError):
                    continue
            
            # 如果没有找到系统字体，使用默认字体
            logger.warning("未找到系统字体，使用默认字体")
            return ImageFont.load_default()
        except Exception as e:
            logger.warning(f"加载字体失败: {e}，使用默认字体")
            return ImageFont.load_default()

    async def render_message_with_image(
        self,
        message_text: str,
        image_url: Optional[str] = None,
        poster_image: Optional[str] = None,
        max_width: int = 800,
    ) -> Optional[bytes]:
        """
        渲染消息和图片为单张图片
        
        Args:
            message_text: 消息文本内容
            image_url: 背景/海报图片 URL（可选）
            poster_image: 海报图片数据（可选）
            max_width: 最大宽度像素
            
        Returns:
            渲染后的图片字节数据，失败则返回 None
        """
        if not PIL_AVAILABLE:
            logger.error("PIL/Pillow 未安装，无法渲染图片")
            return None
            
        try:
            logger.info("开始渲染消息图片")
            
            # 如果有海报图片，使用海报作为背景
            if poster_image:
                base_image = await self._process_poster_image(
                    poster_image, max_width
                )
            else:
                base_image = None
            
            # 创建文本层
            text_image = self._render_text_layer(message_text, max_width)
            
            # 合并图片
            if base_image:
                result_image = await self._combine_images(
                    base_image, text_image
                )
            else:
                result_image = text_image
            
            # 转换为字节
            img_byte_arr = io.BytesIO()
            result_image.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            logger.info(f"✓ 消息图片渲染完成 (大小: {result_image.size})")
            return img_byte_arr.getvalue()
            
        except Exception as e:
            logger.error(f"渲染消息图片失败: {e}")
            return None

    def _render_text_layer(self, text: str, max_width: int = 800) -> Image.Image:
        """渲染纯文本层"""
        try:
            # 分割文本为行
            lines = text.split('\n')
            
            # 计算所需尺寸
            padding = 40
            line_height = 40
            
            # 简单估算高度
            estimated_height = len(lines) * line_height + padding * 2
            
            # 创建图片
            img = Image.new(
                'RGB',
                (max_width, max(300, estimated_height)),
                self.bg_color
            )
            draw = ImageDraw.Draw(img)
            
            # 绘制背景装饰
            self._draw_decorative_background(draw, img.size)
            
            # 绘制文本
            y_offset = padding
            for line in lines:
                draw.text(
                    (padding, y_offset),
                    line,
                    font=self.content_font,
                    fill=self.text_color
                )
                y_offset += line_height
            
            # 重新调整图片高度
            actual_height = y_offset + padding
            img_final = img.crop((0, 0, max_width, actual_height))
            
            return img_final
            
        except Exception as e:
            logger.error(f"渲染文本层失败: {e}")
            # 返回默认图片
            return Image.new('RGB', (max_width, 300), self.bg_color)

    def _draw_decorative_background(
        self, draw: ImageDraw.ImageDraw, size: tuple
    ):
        """绘制装饰性背景元素"""
        try:
            # 绘制顶部渐变条
            width, height = size
            
            # 顶部蓝色条
            draw.rectangle(
                [(0, 0), (width, 60)],
                fill=(52, 152, 219)
            )
            
            # 添加白色标题背景
            draw.rectangle(
                [(0, 60), (width, 80)],
                fill=(240, 240, 240)
            )
            
        except Exception as e:
            logger.debug(f"绘制装饰背景失败: {e}")

    async def _process_poster_image(
        self, poster_data: bytes, max_width: int
    ) -> Optional[Image.Image]:
        """处理海报图片"""
        try:
            poster_img = Image.open(io.BytesIO(poster_data))
            
            # 调整大小
            ratio = max_width / poster_img.width if poster_img.width > max_width else 1
            new_size = (
                int(poster_img.width * ratio),
                int(poster_img.height * ratio)
            )
            poster_img = poster_img.resize(new_size, Image.Resampling.LANCZOS)
            
            # 添加阴影效果
            return self._add_shadow_effect(poster_img)
            
        except Exception as e:
            logger.warning(f"处理海报图片失败: {e}")
            return None

    def _add_shadow_effect(self, image: Image.Image) -> Image.Image:
        """添加阴影效果"""
        try:
            # 创建带阴影的图片
            shadow_size = 5
            shadow_color = (200, 200, 200, 128)
            
            # 暂时不实现复杂的阴影效果，直接返回原图
            return image
            
        except Exception as e:
            logger.debug(f"添加阴影效果失败: {e}")
            return image

    async def _combine_images(
        self, bg_image: Image.Image, text_image: Image.Image
    ) -> Image.Image:
        """合并背景图和文本图"""
        try:
            # 调整图片大小
            text_width = text_image.width
            
            if bg_image.width > text_width:
                bg_image = bg_image.crop((0, 0, text_width, bg_image.height))
            
            # 创建合并后的图片
            total_height = bg_image.height + text_image.height
            combined = Image.new(
                'RGB',
                (text_width, total_height),
                self.bg_color
            )
            
            # 粘贴图片
            combined.paste(bg_image, (0, 0))
            combined.paste(text_image, (0, bg_image.height))
            
            return combined
            
        except Exception as e:
            logger.error(f"合并图片失败: {e}")
            return text_image

    async def render_simple_text_image(
        self, text: str, max_width: int = 800
    ) -> Optional[bytes]:
        """渲染简单的文本图片"""
        if not PIL_AVAILABLE:
            logger.error("PIL/Pillow 未安装，无法渲染图片")
            return None
            
        try:
            img = self._render_text_layer(text, max_width)
            
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            return img_byte_arr.getvalue()
            
        except Exception as e:
            logger.error(f"渲染简单文本图片失败: {e}")
            return None

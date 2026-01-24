from pathlib import Path

from .browser import render_template


class HtmlRenderer:
    def __init__(self):
        # Path to templates
        self.template_path = Path(__file__).parent / "templates"

    async def render(
        self, text: str, image_url: str = None, template_name: str = "css_news_card.html"
    ) -> bytes:
        # Parse text into title and items
        lines = text.strip().split("\n")
        title = lines[0] if lines else ""
        items = []

        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            # Simple heuristic for key-value pairs
            if "：" in line:
                parts = line.split("：", 1)
                items.append(
                    {"type": "kv", "label": parts[0] + "：", "value": parts[1].strip()}
                )
            elif ":" in line:
                parts = line.split(":", 1)
                items.append(
                    {"type": "kv", "label": parts[0] + ":", "value": parts[1].strip()}
                )
            else:
                items.append({"type": "text", "text": line})

        # 读取Base64字体文件
        font_base64_regular = ""
        font_base64_bold = ""
        try:
            fonts_base64_dir = Path(__file__).parent / "resources" / "fonts_base64"
            with open(fonts_base64_dir / "SourceHanSansCN-Regular.txt", "r") as f:
                font_base64_regular = f.read().strip()
            with open(fonts_base64_dir / "SourceHanSansCN-Bold.txt", "r") as f:
                font_base64_bold = f.read().strip()
        except Exception as e:
            logger.warning(f"读取内嵌字体失败: {e}")

        context = {
            "poster_url": image_url or "",
            "title": title,
            "items": items,
            "resource_path": (Path(__file__).parent / "resources").resolve().as_uri(),
            "font_base64_regular": font_base64_regular,
            "font_base64_bold": font_base64_bold,
        }

        return await render_template(
            template_path=self.template_path,
            template_name=template_name,
            context=context,
            viewport={"width": 1920, "height": 1080},
            selector=".card",
        )

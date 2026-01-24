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

        context = {
            "poster_url": image_url or "",
            "title": title,
            "items": items,
            "resource_path": (Path(__file__).parent / "resources").as_uri(),
        }

        return await render_template(
            template_path=self.template_path,
            template_name=template_name,
            context=context,
            viewport={"width": 1920, "height": 1080},
            selector=".card",
        )

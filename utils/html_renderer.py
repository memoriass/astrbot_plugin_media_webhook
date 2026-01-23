import base64
from pathlib import Path
from .browser import render_template

class HtmlRenderer:
    def __init__(self):
        # Path to templates
        self.template_path = Path(__file__).parent / "templates"

    async def render(self, text: str, image_url: str = None) -> bytes:
        # Parse text into title and items
        lines = text.strip().split('\n')
        title = lines[0] if lines else ""
        items = []
        
        for line in lines[1:]:
            line = line.strip()
            if not line: continue
            
            # Simple heuristic for key-value pairs
            # Check for colon, but ensure it's not part of a URL or timestamp likely
            # The UniversalRenderer looked for ":" and split.
            if "：" in line:
                parts = line.split("：", 1)
                items.append({'type': 'kv', 'label': parts[0] + "：", 'value': parts[1].strip()})
            elif ":" in line:
                # Avoid splitting things like "http://..." if it was in text (unlikely for label)
                # But labels usually don't have spaces before colon
                parts = line.split(":", 1)
                items.append({'type': 'kv', 'label': parts[0] + ":", 'value': parts[1].strip()})
            else:
                items.append({'type': 'text', 'text': line})

        context = {
            "poster_url": image_url or "",
            "title": title,
            "items": items
        }
        
        return await render_template(
            template_path=self.template_path,
            template_name="card.html",
            context=context,
            viewport={"width": 1920, "height": 1080}, 
            selector=".card" 
        )

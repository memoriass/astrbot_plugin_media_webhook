import jinja2
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page
from astrbot.api import logger

class BrowserManager:
    _playwright = None
    _browser: Optional[Browser] = None
    
    @classmethod
    async def get_browser(cls) -> Browser:
        if cls._browser is None:
            await cls.init()
        return cls._browser
        
    @classmethod
    async def init(cls):
        if cls._playwright is None:
            cls._playwright = await async_playwright().start()
        
        if cls._browser is None:
            try:
                cls._browser = await cls._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )
                logger.info("内嵌浏览器启动成功")
            except Exception as e:
                logger.error(f"启动浏览器失败: {e}")
                raise

    @classmethod
    async def close(cls):
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None

class PageContext:
    def __init__(self, viewport=None, device_scale_factor=1, **kwargs):
        self.viewport = viewport or {"width": 800, "height": 600}
        self.scale_factor = device_scale_factor
        self.page = None
        
    async def __aenter__(self) -> Page:
        browser = await BrowserManager.get_browser()
        context = await browser.new_context(
            viewport=self.viewport,
            device_scale_factor=self.scale_factor
        )
        self.page = await context.new_page()
        return self.page
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.page:
            await self.page.close()
            await self.page.context.close()

async def render_template(
    template_path: Path,
    template_name: str,
    context: dict,
    viewport: dict = None,
    selector: str = "body"
) -> bytes:
    """渲染模板并截图"""
    if viewport is None:
        viewport = {"width": 800, "height": 600}
        
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path)),
        enable_async=True,
        autoescape=jinja2.select_autoescape(['html', 'xml'])
    )
    template = env.get_template(template_name)
    html_content = await template.render_async(**context)
    
    async with PageContext(viewport=viewport, device_scale_factor=2) as page:
        await page.set_content(html_content)
        try:
            # 等待图片加载完成 (简单粗暴的等待网络空闲)
            # 或者等待特定元素
            await page.wait_for_load_state("networkidle", timeout=5000)
        except:
             pass 

        if selector == "body":
            return await page.screenshot(type="png", full_page=True)
        
        try:
            # Wait for selector to ensure it's ready
            try:
                await page.wait_for_selector(selector, state="visible", timeout=5000)
            except:
                logger.warning(f"Timeout waiting for selector {selector}")
                # Continue anyway, maybe it's there but not 'visible' in some way?

            locator = page.locator(selector)
            return await locator.screenshot(type="png")
        except Exception as e:
            logger.warning(f"Selector {selector} screenshot failed: {e}. Fallback to full page.")
            return await page.screenshot(type="png", full_page=True)

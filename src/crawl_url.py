import aiohttp
from loguru import logger
from playwright.async_api import async_playwright
from src.dynamic_website_crawling import scrape_comprehensive
from src.utills import fetch_static_content, is_dynamic_framework
from fastapi import WebSocket

CRAWLER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

async def fetch_js_rendered_content(url, return_metadata: bool = False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(user_agent=CRAWLER_USER_AGENT)
        result = await scrape_comprehensive(context, url)
        await browser.close()

    text_value = None
    if result and result.get("text", {}).get("visible"):
        candidate = result["text"]["visible"]["markdown"].strip()
        text_value = candidate if len(candidate) > 50 else None

    if return_metadata:
        return {
            "markdown": text_value,
            "raw_html": result.get("raw_html") if result else None,
            "links": result.get("links") if result else None,
        }

    return text_value

async def crawl_url(urls, websocket:WebSocket):
    async with aiohttp.ClientSession() as session:
            for url in urls:
                if not url:
                    continue

                try:
                    async with session.get(url, headers={"User-Agent": CRAWLER_USER_AGENT}, timeout=15) as response:

                        html_text = await response.text()

                        # Decide if dynamic rendering needed
                        if is_dynamic_framework(html_text):
                            logger.info(f"⚙️ Detected dynamic site for {url}, using Playwright")
                            content = await fetch_js_rendered_content(url, return_metadata=True)
                            markdown_content = content.get("markdown")
                            new_urls = content["links"]["all_links"]
                        else:
                            content = await fetch_static_content(html_text, url)
                            markdown_content = content.get("markdown")
                            new_urls = content["links"]
                        if content:
                            logger.info(f"✅ Successfully crawled {url} with content length: {len(content)}")
                            await websocket.send_json({
                                                        "new_urls": list(new_urls),
                                                        "markdown": markdown_content
                                                    })

                except Exception as e:
                    logger.error(f"❌ Error crawling {url}: {e}")

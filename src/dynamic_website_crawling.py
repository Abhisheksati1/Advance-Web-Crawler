from playwright.async_api import async_playwright
import asyncio
import time
from loguru import logger

from src.utills import fetch_static_content


async def auto_scroll(page, max_scrolls=10):
    logger.info("🔄 Auto-scrolling to load dynamic content...")
    last_height = await page.evaluate("() => document.body.scrollHeight")
    for _ in range(max_scrolls):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)
        new_height = await page.evaluate("() => document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


async def scrape_comprehensive(browser_context, url, wait_time=5):
    """
    Intelligently scrape a page by waiting for network idle and DOM stability.
    Replaces fixed waits with adaptive detection.
    """
    page = await browser_context.new_page()
    start_time = time.time()

    try:
        logger.info(f"🌐 Loading: {url}")
        logger.info(f"⏱️  Crawl started at: {time.strftime('%H:%M:%S', time.localtime(start_time))}")

        # Step 1: Load page and wait for DOM to be ready
        await page.goto(url=url, wait_until="domcontentloaded", timeout=30000.0)
        logger.info("✅ DOM content loaded")

        # Step 2: CRITICAL - Wait for network to be idle
        # This replaces the blind sleep(5) - waits until no network activity for 500ms
        try:
            logger.info("⏳ Waiting for network idle (API calls to finish)...")
            await page.wait_for_load_state("networkidle", timeout=15000)
            logger.info("✅ Network is idle - all API calls completed")
            
            # CRITICAL: Wait for React to render the API data into DOM
            # Network idle = HTTP response finished, but React needs time to:
            # 1. Parse JSON, 2. Update state, 3. Re-render, 4. Paint to DOM
            logger.info("⏳ Waiting 2s for React rendering...")
            await asyncio.sleep(2)
            logger.info("✅ React rendering time complete")
        except Exception as e:
            logger.warning(f"⚠ Network idle timeout (continuing anyway): {e}")

        # Step 3: Wait for meaningful content to appear
        try:
            await page.wait_for_function("""
                () => {
                    const body = document.body;
                    const textContent = body.innerText || body.textContent || '';
                    return textContent.length > 200;
                }
            """, timeout=10000)
            logger.info("✅ Found substantial text content")
        except:
            logger.warning("⚠ No substantial text content detected")

        # Step 4: Smart scroll - only if page has lazy-load indicators
        # Check if page height is increasing (sign of lazy loading)
        needs_scroll = await page.evaluate("""
            () => {
                // Check for common lazy-load indicators
                const hasLazyImages = document.querySelectorAll('img[loading="lazy"]').length > 0;
                const hasInfiniteScroll = document.body.innerText.toLowerCase().includes('load more');
                return hasLazyImages || hasInfiniteScroll;
            }
        """)
        
        if needs_scroll:
            logger.info("🔄 Detected lazy-loading, performing smart scroll...")
            # Quick single scroll to bottom to trigger lazy loads
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)  # Brief wait for lazy content
            await page.evaluate("window.scrollTo(0, 0)")  # Scroll back to top
        else:
            logger.info("✅ No lazy-loading detected, skipping scroll")

        # Step 5: Final brief wait for any animations/transitions
        await asyncio.sleep(0.5)

        logger.info(f"\n📄 Extracting HTML content...")

        visible_text = await page.evaluate("""
            () => {
                const clonedDoc = document.cloneNode(true);
                const scripts = clonedDoc.querySelectorAll('script, style, noscript');
                scripts.forEach(el => el.remove());
                return clonedDoc.body ? clonedDoc.body.innerText : '';
            }
        """)

        logger.info(f"🔗 Extracting links...")

        links_method1 = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                return links.map(link => ({
                    url: link.href,
                    text: (link.innerText || link.textContent || '').trim(),
                    title: link.title || '',
                    className: link.className || '',
                    target: link.target || '',
                    rel: link.rel || ''
                }));
            }
        """)

        links_method2 = await page.evaluate("""
            () => {
                const elements = Array.from(document.querySelectorAll('[href]'));
                return elements.filter(el => el.tagName.toLowerCase() === 'a').map(el => ({
                    url: el.href,
                    text: (el.innerText || el.textContent || '').trim(),
                    title: el.title || '',
                    className: el.className || '',
                    target: el.target || '',
                    rel: el.rel || ''
                }));
            }
        """)

        links_method3 = await page.evaluate("""
            () => {
                const containers = document.querySelectorAll('nav, header, main, .container, .content, footer, body');
                let allLinks = [];
                containers.forEach(container => {
                    const links = Array.from(container.querySelectorAll('a[href]'));
                    links.forEach(link => {
                        allLinks.push({
                            url: link.href,
                            text: (link.innerText || link.textContent || '').trim(),
                            title: link.title || '',
                            className: link.className || '',
                            target: link.target || '',
                            rel: link.rel || '',
                            container: container.tagName.toLowerCase()
                        });
                    });
                });
                const unique = allLinks.filter((link, index, self) => 
                    index === self.findIndex(l => l.url === link.url)
                );
                return unique;
            }
        """)

        # Choose best method
        links = []
        if links_method3:
            links.extend(links_method3)
        if links_method1:
            links.extend(links_method1)
        if links_method2:
            links.extend(links_method2)
        else:
            links = []


        all_links = set()

        for link in links:
            href = link['url']
            all_links.add(href)

        spa_patterns = await page.evaluate("""
            () => {
                const html = document.documentElement.outerHTML;
                return {
                    hasReact: html.includes('react') || html.includes('React'),
                    hasNext: html.includes('_next') || html.includes('__NEXT'),
                    hasVue: html.includes('vue') || html.includes('Vue'),
                    hasAngular: html.includes('angular') || html.includes('ng-'),
                    hasRouter: html.includes('router') || html.includes('Router')
                }
            }
        """)
        
        raw_html = await page.content()
        
        # Extract clean text using BeautifulSoup via fetch_static_content
        visible_text = await fetch_static_content(raw_html, url)
        
        logger.info(f"\n🕵️‍♂️ Framework Detection:", spa_patterns)

        print(f"all_links: {all_links}")
        print(f"spa_patterns: {spa_patterns}")
        
        # Calculate and log total time
        end_time = time.time()
        total_duration = end_time - start_time
        logger.info(f"⏱️  Crawl ended at: {time.strftime('%H:%M:%S', time.localtime(end_time))}")
        logger.info(f"⏱️  Total crawl duration: {total_duration:.2f} seconds")
        
        return {

            'text': {
                'visible': visible_text,
            },
            'links': {
                'all_links':all_links,
            },
            'raw_html': raw_html,
            'framework_detection': spa_patterns,
        }

    except Exception as e:
        logger.info(f"❌ Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        raise e
    finally:
            await page.close()

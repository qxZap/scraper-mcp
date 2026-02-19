#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fallback scraping module for web scraping tool

Implements progressive fallback strategy:
1. Plain HTTP requests (aiohttp)
2. Requests + BeautifulSoup with persistent sessions
3. Headless browser automation (Playwright)
4. Headful browser automation (last resort)

Integrates Trafilatura for clean content extraction.
Fully async for high concurrency.
"""

import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
import logging
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import trafilatura
from urllib.parse import urljoin
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FallbackScraper:
    """Progressive fallback scraping strategy"""
    
    def __init__(self, max_retries: int = 3, timeout: int = 30):
        self.max_retries = max_retries
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
        self.playwright = None
    
    async def setup_session(self) -> aiohttp.ClientSession:
        """Setup persistent aiohttp session"""
        if not self.session:
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=20, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Cache-Control': 'no-cache',
                }
            )
        return self.session
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
    
    async def close_playwright(self):
        """Close Playwright instance"""
        if self.playwright:
            await self.playwright.stop()
    
    async def _http_request(self, url: str) -> Dict[str, Any]:
        """Level 1: Plain HTTP request"""
        for attempt in range(self.max_retries):
            try:
                async with await self.setup_session() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            content = await response.text()
                            if content.strip():  # Check for non-empty
                                return {
                                    'method': 'http',
                                    'content': content,
                                    'status': 'success',
                                    'headers': dict(response.headers)
                                }
                            else:
                                logger.warning(f"Empty response from {url}")
                        else:
                            logger.warning(f"HTTP {response.status} for {url}")
                            if attempt == self.max_retries - 1:
                                return {'method': 'http', 'status': 'error', 'error': f'HTTP {response.status}'}
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
            except Exception as e:
                logger.error(f"HTTP attempt {attempt+1} failed for {url}: {str(e)}")
                if attempt == self.max_retries - 1:
                    return {'method': 'http', 'status': 'error', 'error': str(e)}
        return {'method': 'http', 'status': 'error'}
    
    async def _beautifulsoup_parse(self, url: str, html: str) -> Dict[str, Any]:
        """Level 2: BeautifulSoup parsing and content extraction"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script/style
            for script in soup(["script", "style", "nav", "footer"]):
                script.decompose()
            
            # Try to find main content
            main_selectors = ['main', 'article', '.content', '.post', '#content']
            main_content = None
            for selector in main_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            if not main_content:
                main_content = soup.body if soup.body else soup
            
            text = main_content.get_text(separator='\n', strip=True)
            
            # Use Trafilatura for better extraction if available
            try:
                extracted = trafilatura.extract(html, favor_precision=True, include_formatting=False)
                if extracted:
                    text = extracted
                    logger.info("Used Trafilatura for extraction")
            except ImportError:
                logger.warning("Trafilatura not available, using BS4")
            except Exception as e:
                logger.warning(f"Trafilatura failed: {e}")
            
            if text.strip():
                return {
                    'method': 'beautifulsoup',
                    'content': text,
                    'status': 'success',
                    'word_count': len(text.split())
                }
            else:
                return {'method': 'beautifulsoup', 'status': 'empty_content'}
                
        except Exception as e:
            logger.error(f"BeautifulSoup parsing failed: {str(e)}")
            return {'method': 'beautifulsoup', 'status': 'error', 'error': str(e)}
    
    async def _headless_browser(self, url: str) -> Dict[str, Any]:
        """Level 3: Headless Playwright"""
        playwright = await async_playwright().start()
        browser = None
        try:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # Navigate with wait
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)  # Allow JS to run
            
            # Check for bot detection or errors
            if 'captcha' in await page.content().lower() or page.url != urlparse(url).netloc:
                return {'method': 'headless', 'status': 'bot_detected'}
            
            html = await page.content()
            text = await page.text_content('body')
            
            # Trafilatura on HTML
            try:
                extracted = trafilatura.extract(html, favor_precision=True, include_formatting=False)
                if extracted:
                    text = extracted
            except Exception as e:
                logger.warning(f"Trafilatura in browser failed: {e}")
            
            if text and len(text.strip()) > 50:
                return {
                    'method': 'headless',
                    'content': text,
                    'status': 'success',
                    'url': page.url,
                    'word_count': len(text.split())
                }
            else:
                return {'method': 'headless', 'status': 'empty_content'}
                
        except Exception as e:
            logger.error(f"Headless browser failed: {str(e)}")
            return {'method': 'headless', 'status': 'error', 'error': str(e)}
        finally:
            if browser:
                await browser.close()
            await playwright.stop()
    
    async def _headful_browser(self, url: str) -> Dict[str, Any]:
        """Level 4: Headful Playwright (last resort)"""
        playwright = await async_playwright().start()
        browser = None
        try:
            browser = await playwright.chromium.launch(headless=False, slow_mo=500)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Wait longer for manual-like interaction
            await page.wait_for_timeout(5000)
            
            html = await page.content()
            text = await page.text_content('body')
            
            # Trafilatura
            try:
                extracted = trafilatura.extract(html, favor_precision=True, include_formatting=False)
                if extracted:
                    text = extracted
            except Exception as e:
                logger.warning(f"Trafilatura in headful failed: {e}")
            
            if text and len(text.strip()) > 50:
                return {
                    'method': 'headful',
                    'content': text,
                    'status': 'success',
                    'url': page.url,
                    'word_count': len(text.split())
                }
            else:
                return {'method': 'headful', 'status': 'empty_content'}
                
        except Exception as e:
            logger.error(f"Headful browser failed: {str(e)}")
            return {'method': 'headful', 'status': 'error', 'error': str(e)}
        finally:
            if browser:
                await browser.close()
            await playwright.stop()
    
    async def scrape_with_fallback(self, url: str) -> Dict[str, Any]:
        """
        Main scraping method with progressive fallbacks
        
        Triggers fallback on:
        - HTTP errors (4xx, 5xx)
        - Empty or minimal content (<100 words)
        - Bot protection indicators (captcha, blocked)
        - JS-rendered content (no main tags in HTML)
        
        Returns:
            Best available content or error
        """
        # Level 1: HTTP
        http_result = await self._http_request(url)
        if http_result['status'] == 'success':
            bs_result = await self._beautifulsoup_parse(url, http_result['content'])
            if bs_result['status'] == 'success' and bs_result['word_count'] > 100:
                await self.close_session()
                return {
                    'url': url,
                    'method_used': 'http+bs',
                    'content': bs_result['content'],
                    'extraction_notes': 'Clean text via BeautifulSoup + Trafilatura',
                    'status': 'success'
                }
        
        # Level 2: If BS failed or empty, but HTTP succeeded, retry BS? Already did.
        
        # Level 3: Headless
        headless_result = await self._headless_browser(url)
        if headless_result['status'] == 'success':
            await self.close_session()
            return {
                'url': url,
                'method_used': 'headless_browser',
                'content': headless_result['content'],
                'extraction_notes': 'JS-rendered via Playwright + Trafilatura',
                'status': 'success'
            }
        
        # Level 4: Headful
        headful_result = await self._headful_browser(url)
        if headful_result['status'] == 'success':
            await self.close_session()
            return {
                'url': url,
                'method_used': 'headful_browser',
                'content': headful_result['content'],
                'extraction_notes': 'Interactive via headful Playwright + Trafilatura',
                'status': 'success'
            }
        
        await self.close_session()
        return {
            'url': url,
            'method_used': 'failed_all',
            'content': '',
            'status': 'error',
            'error': 'All fallback methods failed'
        }

async def scrape_multiple(urls: List[str], max_concurrent: int = 10) -> List[Dict[str, Any]]:
    """Concurrent scraping with semaphore for rate limiting"""
    semaphore = asyncio.Semaphore(max_concurrent)
    scraper = FallbackScraper()
    
    async def bounded_scrape(url):
        async with semaphore:
            return await scraper.scrape_with_fallback(url)
    
    tasks = [bounded_scrape(u) for u in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    await scraper.close_session()
    await scraper.close_playwright()
    
    # Filter exceptions
    return [r for r in results if not isinstance(r, Exception)]

# Example usage
if __name__ == "__main__":
    async def main():
        url = "https://example.com"
        scraper = FallbackScraper()
        result = await scraper.scrape_with_fallback(url)
        print(f"Scraped {url} using {result.get('method_used', 'unknown')}:")
        if result['status'] == 'success':
            print(f"Content preview: {result['content'][:200]}...")
        else:
            print(f"Failed: {result.get('error', 'Unknown error')}")
        await scraper.close_session()
    
    asyncio.run(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Scraper Server using FastMCP

FastAPI-based MCP server for web scraping with progressive fallbacks.
Runs on port 8919, exposes MCP endpoints using FastMCP.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Union
from fastapi import FastAPI, HTTPException
from fastmcp import FastMCP
import uvicorn
from contextlib import asynccontextmanager
import base64
import uuid
import os

# Import modules
from search import SearchManager, search_with_concurrency
from fallback import FallbackScraper, scrape_multiple

# Playwright integration
from playwright.async_api import async_playwright

# Global state
_sessions: Dict[str, Any] = {}  # Browser sessions
_playwright_instance = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("MCP Scraper Server")

@mcp.tool()
async def search_query(
    query: str,
    num_results: int = 10
) -> str:
    """
    Perform search using Google and DuckDuckGo with fallbacks, returns list of URLs
    """
    manager = SearchManager()
    result = await manager.perform_search(query, num_results)
    await manager.close_all()
    return json.dumps(result)

@mcp.tool()
async def search_multiple(
    queries: List[str],
    num_results: int = 10,
    max_concurrent: int = 5
) -> str:
    """
    Concurrent search for multiple queries
    """
    results = await search_with_concurrency(queries, max_concurrent, num_results)
    return json.dumps(results)

@mcp.tool()
async def scrape_url(
    url: str,
    max_retries: int = 3
) -> str:
    """
    Scrape a single URL with progressive fallback chain
    """
    scraper = FallbackScraper(max_retries=max_retries)
    result = await scraper.scrape_with_fallback(url)
    await scraper.close_session()
    await scraper.close_playwright()
    return json.dumps(result)

@mcp.tool()
async def scrape_multiple(
    urls: List[str],
    max_concurrent: int = 10
) -> str:
    """
    Concurrent scraping of multiple URLs
    """
    results = await scrape_multiple(urls, max_concurrent)
    return json.dumps(results)

@mcp.tool()
async def extract_content(
    html: str,
    url: Optional[str] = None
) -> str:
    """
    Extract clean content from HTML using Trafilatura
    """
    try:
        from trafilatura import extract
        content = extract(html, url=url, favor_precision=True, include_formatting=False)
        if content:
            return content
        else:
            return "No content extracted"
    except Exception as e:
        return f"Extraction failed: {str(e)}"

@mcp.tool()
async def browser_navigate(
    url: str
) -> str:
    """
    Navigate to URL in browser session (creates if none)
    """
    global _sessions, _playwright_instance
    if not _playwright_instance:
        _playwright_instance = await async_playwright().start()
    
    if not any(s for s in _sessions.values() if s.get("page")):
        # Create new session
        browser = await _playwright_instance.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        session_id = str(uuid.uuid4())
        _sessions[session_id] = {"browser": browser, "context": context, "page": page}
    
    session_id = list(_sessions.keys())[-1]
    page = _sessions[session_id]["page"]
    await page.goto(url, wait_until="domcontentloaded")
    text_preview = (await page.text_content("body"))[:500] if await page.text_content("body") else ""
    return f"Navigated to {url}. Preview: {text_preview}"

@mcp.tool()
async def browser_click(
    selector: str
) -> str:
    """
    Click element by selector
    """
    global _sessions
    if not _sessions:
        return "No browser session. Navigate first."
    session_id = list(_sessions.keys())[-1]
    page = _sessions[session_id]["page"]
    await page.click(selector)
    return f"Clicked {selector}"

@mcp.tool()
async def browser_evaluate(
    script: str
) -> str:
    """
    Evaluate JS in browser
    """
    global _sessions
    if not _sessions:
        return "No browser session."
    session_id = list(_sessions.keys())[-1]
    page = _sessions[session_id]["page"]
    result = await page.evaluate(script)
    return f"Eval result: {result}"

@mcp.tool()
async def browser_screenshot(
    name: str,
    selector: Optional[str] = None
) -> str:
    """
    Take screenshot of page or element
    """
    global _sessions
    if not _sessions:
        return "No browser session."
    session_id = list(_sessions.keys())[-1]
    page = _sessions[session_id]["page"]
    if selector:
        await page.locator(selector).screenshot(path=f"{name}.png")
    else:
        await page.screenshot(path=f"{name}.png", full_page=True)
    with open(f"{name}.png", "rb") as f:
        encoded = base64.b64encode(f.read()).decode()
    os.remove(f"{name}.png")
    return f"data:image/png;base64,{encoded}"

@mcp.tool()
async def browser_get_text() -> str:
    """
    Get text content from page
    """
    global _sessions
    if not _sessions:
        return "No browser session."
    session_id = list(_sessions.keys())[-1]
    page = _sessions[session_id]["page"]
    text = await page.text_content("body")
    # Clean with Trafilatura if possible
    try:
        from trafilatura import extract
        html = await page.content()
        cleaned = extract(html, include_formatting=False)
        if cleaned:
            text = cleaned
    except:
        pass
    return text[:2000]  # Limit for tokens

@mcp.tool()
async def browser_close() -> str:
    """
    Close current browser session
    """
    global _sessions
    if _sessions:
        session_id = list(_sessions.keys())[-1]
        await _sessions[session_id]["browser"].close()
        del _sessions[session_id]
    return "Session closed"

from starlette.responses import JSONResponse

@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"status": "healthy", "sessions": len(_sessions)})

app = mcp.http_app(path="/mcp")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8919, log_level="info")

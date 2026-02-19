# MCP Web Scraper Server

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-orange.svg)](https://fastapi.tiangolo.com/)
[![Playwright](https://img.shields.io/badge/Playwright-latest-green.svg)](https://playwright.dev/python/)
[![FastMCP](https://img.shields.io/badge/FastMCP-2.13+-purple.svg)](https://gofastmcp.com/)

A production-ready **MCP (Model Context Protocol)** server for AI-powered web scraping with progressive fallbacks, browser automation, and Roo/VSCode integration. Handles search, scraping, JS rendering, interaction, and full text dumps.

## 🚀 Features

- **Progressive Fallbacks**: HTTP/aiohttp → BeautifulSoup → Headless Playwright → Headful (visual).
- **Search**: Google/DuckDuckGo (API + scraping).
- **Extraction**: Trafilatura for clean, AI-ready text.
- **Browser Automation**: Navigate, click, type, evaluate JS, screenshot, full text dump.
- **Concurrency**: Asyncio semaphores for parallel ops.
- **MCP Native**: JSON-RPC tools for Roo/Claude/GPT agents.
- **Modular**: `scraper-tools.py` for mounting on other MCP servers.
- **Tested**: pytest suite for AFM, LinkedIn (JS), UNEP crawling, interactions.

## 🛠 Tools (mcp--scraper-mcp--tool_name)

| Tool | Params | Description | Return |
|------|--------|-------------|--------|
| `search_query` | `query`, `num_results=10` | Google/DDG search | JSON `{"urls": [...], "status": "success"}` |
| `search_multiple` | `queries: list`, `max_concurrent=5` | Concurrent searches | JSON list |
| `scrape_url` | `url`, `max_retries=3` | Fallback scrape | JSON `{"content": clean text, "method_used": "..."}` |
| `scrape_multiple` | `urls: list`, `max_concurrent=10` | Batch scrape | JSON list |
| `extract_content` | `html`, `url?` | Trafilatura clean | str text |
| `browser_navigate` | `url` | Headless navigate | `"Navigated to {url}. Preview: ..."` |
| `browser_navigate_headful` | `url` | **Visible browser** (CAPTCHA/debug) | Same + "window open" |
| `browser_click` | `selector` | Click element | `"Clicked {selector}"` |
| `browser_type` | `selector`, `text`, `submit?` | Type/send keys | `"Typed {text}"` |
| `browser_evaluate` | `script` | Run JS (`querySelector`, `innerText`) | `"Eval result: {result}"` |
| `browser_screenshot` | `name`, `selector?` | PNG base64 | `data:image/png;base64,...` |
| `browser_get_text` | - | Body text (Trafilatura) | str (~2000 chars) |
| `browser_get_full_text` | - | **Full dump**: `innerText` + Trafilatura | str (~4000 chars) |
| `browser_close` | - | Close session | `"Session closed"` |

## ⚙️ Setup

1. **Install**:
   ```
   pip install aiohttp beautifulsoup4 trafilatura fastmcp uvicorn playwright fastapi
   playwright install chromium
   ```

2. **Run Server** (port 8919):
   ```
   cd scraper-mcp
   python server.py
   ```
   - Health: `curl http://127.0.0.1:8919/health`
   - MCP: `http://127.0.0.1:8919/mcp`

3. **Roo Integration** (VSCode):
   - Add to `mcp_settings.json`:
     ```json
     "scraper-mcp": {"url": "http://127.0.0.1:8919/mcp"}
     ```
   - Use `prompt.txt` as system prompt for agents.

4. **Modular Mount** (e.g., on another MCP):
   ```python
   from scraper_tools import mcp_tools
   mcp.mount(mcp_tools, prefix="scraper")  # scraper_search_query
   ```

## 🧪 Testing

```
pytest tests/test_scraper.py -v
```
- AFM scrape (BS fallback).
- LinkedIn JS (navigate + full text).
- Google interaction (type/click/eval).
- UNEP crawling (search → link → verify).
- Passes core; timeouts on anti-bot sites expected.

## 📖 Usage Examples

**CLI**:
```bash
curl -X POST http://127.0.0.1:8919/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"scrape_url","arguments":{"url":"https://example.com"}},"id":1}'
```

**Agent Prompt** (prompt.txt): Guides search → scrape → interact → dump.

**Interactive Crawl**:
1. `browser_navigate("https://www.unep.org/")`
2. `browser_type("input[placeholder*='search']", "publications")`
3. `browser_evaluate("document.querySelector('a[href*=\"publications\"]').href")`
4. `browser_get_full_text()` → Dump all.

## 🔧 Optimization

- **Stealth**: Rotate UAs/proxies (extend FallbackScraper).
- **Scale**: Docker + Redis sessions.
- **Ethics**: robots.txt, delays.

## 🚀 Future Enhancements / TODO

- **Proxy Rotation**: Integrate Zyte API (ScrapingBee/Zyte Smart Proxy) for residential IPs, CAPTCHA bypass.
- **Puppeteer Fallback**: Node.js Puppeteer integration for real-browser fingerprinting/stealth (via subprocess or hybrid server).
- **CAPTCHA Solver**: 2Captcha/Anti-Captcha service hook for headful mode.
- **Session Persistence**: Redis for shared browser contexts across requests/instances.
- **Docker/K8s**: Multi-container scaling with health checks.
- **Advanced Stealth**: Browser fingerprint randomization, human-like mouse/typing curves.
- **PDF Extraction**: pdfplumber/PyMuPDF for document scraping.
- **Vision AI**: Screenshot OCR (Tesseract/PaddleOCR) + LLM layout analysis.
- **Crawling Engine**: Link discovery, sitemap parsing, depth-limited spider.

Issues? Logs in terminal. Contribute via PRs!
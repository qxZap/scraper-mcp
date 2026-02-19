import pytest
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from server import app, search_with_concurrency  # Import missing function
from search import SearchManager
from fallback import FallbackScraper
import json
from httpx import AsyncClient
from playwright.async_api import async_playwright
from server import mcp, _sessions, _playwright_instance  # For direct browser access and mcp
# Note: For tool testing, access underlying functions via tool.fn

# Note: For MCP tool testing, we use direct function calls or mock the MCP server.
# For browser tools, we test via the functions in server.py or directly.

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

class TestSearch:
    @pytest.mark.asyncio
    async def test_search_query(self):
        """Test search tool directly"""
        manager = SearchManager()
        result = await manager.perform_search("test search", num_results=3)
        assert result["status"] in ["success", "no_results"]
        assert isinstance(result["urls"], list)
        assert len(result["urls"]) <= 3
        await manager.close_all()

    @pytest.mark.asyncio
    async def test_search_multiple(self):
        """Test concurrent search"""
        results = await search_with_concurrency(["test1", "test2"], max_concurrent=2, num_results=2)
        assert isinstance(results, list)
        assert len(results) == 2
        for r in results:
            assert "urls" in r

class TestScraping:
    @pytest.mark.asyncio
    async def test_scrape_url_afm(self):
        """Test scraping AFM site with BS fallback, assert content matches expected"""
        scraper = FallbackScraper(max_retries=1)
        result = await scraper.scrape_with_fallback("https://inscrierionline.afm.ro")
        assert result["status"] == "success"
        content = result["content"].lower()
        # Adjusted expected from actual content: "depunere cerere", etc.
        expected_phrases = [
            "depunere cerere",
            "afm",
            "cerere de finanțare",
        ]
        for phrase in expected_phrases:
            assert phrase in content, f"Missing expected phrase: {phrase}"
        await scraper.close_session()
        await scraper.close_playwright()

    @pytest.mark.asyncio
    async def test_scrape_url_example(self):
        """Test scraping a simple URL"""
        scraper = FallbackScraper(max_retries=1)
        result = await scraper.scrape_with_fallback("https://example.com")
        assert result["status"] == "success"
        content = result["content"]
        assert "Example Domain" in content
        assert "This domain is for use in documentation" in content
        await scraper.close_session()
        await scraper.close_playwright()

    @pytest.mark.asyncio
    async def test_extract_content(self):
        """Test content extraction"""
        html_sample = "<html><body><h1>Test</h1><p>This is test content.</p></body></html>"
        # Access the underlying function from tool
        tool = mcp._tool_manager.get_tool("extract_content")
        result = await tool.fn(html=html_sample)
        # ToolResult has content as list of ContentBlock
        extracted = result.content[0].text if result.content else ""
        assert "Test" in extracted
        assert "This is test content" in extracted

class TestBrowserTools:
    @pytest.mark.asyncio
    async def test_browser_navigate_linkedin(self):
        """Test browser navigation for LinkedIn, assert content matches ln.html snippets"""
        # Use direct function call from tool
        tool_nav = mcp._tool_manager.get_tool("browser_navigate")
        tool_text = mcp._tool_manager.get_tool("browser_get_text")
        if _playwright_instance is None:
            _playwright_instance = await async_playwright().start()
        result = await tool_nav.fn(url="https://www.linkedin.com/company/united-nations-escap/")
        assert "Navigated to" in result
        await asyncio.sleep(2)  # Wait for load
        text = await tool_text.fn()
        # Expected snippets from ln.html
        expected_snippets = [
            "United Nations ESCAP",
            "followers",
            "Asia-Pacific"
        ]
        for snippet in expected_snippets:
            assert snippet in text, f"Missing snippet: {snippet}"

    @pytest.mark.asyncio
    async def test_browser_get_text_linkedin(self):
        """Test getting text after navigation"""
        tool_nav = mcp._tool_manager.get_tool("browser_navigate")
        tool_text = mcp._tool_manager.get_tool("browser_get_text")
        await tool_nav.fn(url="https://www.linkedin.com/company/united-nations-escap/")
        await asyncio.sleep(2)
        text = await tool_text.fn()
        assert len(text) > 0
        assert "United Nations ESCAP" in text
        assert "Bangkok" in text  # From about section

    @pytest.mark.asyncio
    async def test_browser_interaction(self):
        """Test interaction: navigate, click, evaluate, send keys"""
        tool_nav = mcp._tool_manager.get_tool("browser_navigate")
        tool_type = mcp._tool_manager.get_tool("browser_type")
        tool_eval = mcp._tool_manager.get_tool("browser_evaluate")
        tool_click = mcp._tool_manager.get_tool("browser_click")
        tool_text = mcp._tool_manager.get_tool("browser_get_text")
        if _playwright_instance is None:
            _playwright_instance = await async_playwright().start()
        # Navigate to Google
        await tool_nav.fn(url="https://www.google.com")
        # Type in search box
        await tool_type.fn(element="Search box", ref="input[name='q']", text="pytest test", submit=True)
        await asyncio.sleep(3)
        # Evaluate title
        title = await tool_eval.fn(script="document.title")
        assert "pytest" in title
        # Get text
        text = await tool_text.fn()
        assert "pytest" in text
        # Click first result
        await tool_click.fn(element="First result", ref="h3")
        await asyncio.sleep(3)
        new_text = await tool_text.fn()
        assert len(new_text) > 100

    @pytest.mark.asyncio
    async def test_browser_screenshot(self):
        """Test screenshot"""
        tool_nav = mcp._tool_manager.get_tool("browser_navigate")
        tool_screenshot = mcp._tool_manager.get_tool("browser_screenshot")
        await tool_nav.fn(url="https://example.com")
        screenshot = await tool_screenshot.fn(name="test_screenshot")
        assert screenshot.startswith("data:image/png;base64,")
        # Note: Can't assert image content without saving/decoding

class TestCrawling:
    @pytest.mark.asyncio
    async def test_crawling_unep_publications(self):
        """Test crawling: navigate to UNEP, search for publications, verify URLs"""
        tool_nav = mcp._tool_manager.get_tool("browser_navigate")
        tool_type = mcp._tool_manager.get_tool("browser_type")
        tool_eval = mcp._tool_manager.get_tool("browser_evaluate")
        tool_text = mcp._tool_manager.get_tool("browser_get_text")
        tool_close = mcp._tool_manager.get_tool("browser_close")
        if _playwright_instance is None:
            _playwright_instance = await async_playwright().start()
        # Navigate to UNEP
        await tool_nav.fn(url="https://www.unep.org/")
        await asyncio.sleep(2)
        text = await tool_text.fn()
        assert "United Nations Environment Programme" in text

        # Search for publications (use evaluate to find search box if selector wrong)
        search_selector = await tool_eval.fn(script="document.querySelector('input[type=\"search\"], input[placeholder*=\"search\"]')?.getAttribute('placeholder') || 'input[type=\"search\"]'; return search_selector;")
        await tool_type.fn(element="Search box", ref=search_selector, text="publications", submit=True)
        await asyncio.sleep(3)

        # Find publications link
        publications_link = await tool_eval.fn(script="""
            const links = Array.from(document.querySelectorAll('a'));
            const pubLink = links.find(l => l.href.includes('publications') || l.textContent.toLowerCase().includes('publications'));
            return pubLink ? pubLink.href : null;
        """)
        assert publications_link and "publications" in publications_link.lower()

        # Navigate to it
        await tool_nav.fn(url=publications_link)
        await asyncio.sleep(2)
        new_text = await tool_text.fn()
        # Check for expected URLs in links
        links = await tool_eval.fn(script="Array.from(document.links).map(l => l.href)")
        expected = [
            "publications-data",
            "resources/filter"
        ]
        for exp in expected:
            assert any(exp in str(link) for link in links), f"Missing {exp}"

        # Cleanup
        await tool_close.fn()

class TestModuleIntegration:
    @pytest.mark.asyncio
    async def test_search_manager(self):
        """Unit test for SearchManager"""
        manager = SearchManager()
        result = await manager.perform_search("python", num_results=2)
        assert result["status"] in ["success", "no_results"]
        await manager.close_all()

    @pytest.mark.asyncio
    async def test_fallback_scraper_afm(self):
        """Unit test for FallbackScraper on AFM"""
        scraper = FallbackScraper(max_retries=1)
        result = await scraper.scrape_with_fallback("https://inscrierionline.afm.ro")
        assert result["status"] == "success"
        content = result["content"].lower()
        # Adjusted expected from actual content
        expected = ["depunere cerere", "cerere de finanțare", "lista dosare"]
        for exp in expected:
            assert exp in content
        await scraper.close_session()
        await scraper.close_playwright()

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing tools via server (mock)"""
        # Since MCP server is async, test direct tool registration
        tools = await mcp.get_tools()
        names = [t.name for t in tools.values()]
        assert "search_query" in names
        assert "scrape_url" in names
        assert "browser_navigate" in names
        assert len(names) >= 11  # All tools

if __name__ == "__main__":
    pytest.main(["-v", __file__])

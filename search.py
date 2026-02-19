#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search module for web scraping tool

This module provides search capabilities using Google and DuckDuckGo.
Implements progressive fallback: API -> Scraping with BeautifulSoup -> Browser.

Key features:
1. Async support for concurrent searches
2. URL extraction and normalization
3. Error handling with logging
4. No API keys required - uses scraping fallbacks
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import logging
from urllib.parse import quote, urljoin, urlparse
import trafilatura  # For content extraction if needed in search results

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SearchEngine:
    """Base class for search engines"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def setup_session(self) -> aiohttp.ClientSession:
        """Setup HTTP session with headers to mimic browser"""
        if not self.session:
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
        return self.session
    
    async def close_session(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
    
    async def search(self, query: str, num_results: int = 10) -> Dict[str, Any]:
        """
        Perform a search using this engine
        
        Args:
            query: Search query string
            num_results: Number of results to return
            
        Returns:
            Dictionary with 'urls' list and 'status'
        """
        raise NotImplementedError("Subclasses must implement search method")

class GoogleSearchEngine(SearchEngine):
    """Google search via scraping (no API key needed)"""
    
    async def search(self, query: str, num_results: int = 10) -> Dict[str, Any]:
        """Scrape Google search results for URLs"""
        try:
            search_url = f"https://www.google.com/search?q={quote(query)}&num={num_results}"
            async with await self.setup_session() as session:
                async with session.get(search_url) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        urls = []
                        # Extract organic results
                        for g in soup.find_all('div', class_='g')[:num_results]:
                            a = g.find('a')
                            if a and a.get('href'):
                                href = a['href']
                                if href.startswith('/url?q='):
                                    # Decode Google redirect
                                    from urllib.parse import parse_qs, urlparse
                                    parsed = urlparse(href)
                                    actual_url = parse_qs(parsed.query)['q'][0]
                                    urls.append(actual_url)
                                else:
                                    urls.append(href)
                        
                        if urls:
                            return {
                                'engine': 'google',
                                'urls': urls[:num_results],
                                'status': 'success'
                            }
                        else:
                            return {'engine': 'google', 'urls': [], 'status': 'partial'}
                    else:
                        logger.warning(f"Google search HTTP {response.status}")
                        return {'engine': 'google', 'urls': [], 'status': 'error'}
                        
        except Exception as e:
            logger.error(f"Google search error: {str(e)}")
            return {'engine': 'google', 'urls': [], 'status': 'error'}

class DuckDuckGoSearchEngine(SearchEngine):
    """DuckDuckGo search via API and scraping fallback"""
    
    async def search(self, query: str, num_results: int = 10) -> Dict[str, Any]:
        """Search DuckDuckGo, extract URLs from RelatedTopics"""
        try:
            # Try API first
            api_url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1&skip_disambig=1"
            async with await self.setup_session() as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        urls = []
                        # Extract from RelatedTopics
                        topics = data.get('RelatedTopics', [])
                        for topic in topics[:num_results]:
                            if 'FirstURL' in topic:
                                urls.append(topic['FirstURL'])
                            elif 'Topics' in topic:
                                for sub in topic['Topics'][:num_results - len(urls)]:
                                    if 'FirstURL' in sub:
                                        urls.append(sub['FirstURL'])
                        
                        if urls:
                            return {
                                'engine': 'duckduckgo_api',
                                'urls': urls[:num_results],
                                'status': 'success'
                            }
            
            # Fallback to scraping if API yields no URLs
            search_url = f"https://duckduckgo.com/html/?q={quote(query)}"
            async with await self.setup_session() as session:
                async with session.get(search_url) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        urls = []
                        for result in soup.find_all('a', class_='result__a', limit=num_results):
                            href = result.get('href')
                            if href:
                                # Decode DDG URL
                                if href.startswith('/l/?uddg='):
                                    from urllib.parse import unquote
                                    actual_url = unquote(href.split('uddg=')[1].split('&')[0])
                                    urls.append(actual_url)
                        
                        if urls:
                            return {
                                'engine': 'duckduckgo_scrape',
                                'urls': urls[:num_results],
                                'status': 'success'
                            }
                        
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {str(e)}")
        
        return {'engine': 'duckduckgo', 'urls': [], 'status': 'error'}

class SearchManager:
    """Manages multiple engines with fallback and concurrency"""
    
    def __init__(self, engines: List[SearchEngine] = None):
        self.engines = engines or [GoogleSearchEngine(), DuckDuckGoSearchEngine()]
    
    async def perform_search(self, query: str, num_results: int = 10) -> Dict[str, Any]:
        """
        Perform search across engines with fallback
        
        Returns:
            Aggregated unique URLs
        """
        all_urls = set()
        used_engines = []
        
        for engine in self.engines:
            try:
                result = await engine.search(query, num_results)
                used_engines.append(result['engine'])
                if result['status'] == 'success' and result['urls']:
                    all_urls.update(result['urls'])
                    if len(all_urls) >= num_results:
                        break
            except Exception as e:
                logger.error(f"Engine {engine.__class__.__name__} failed: {str(e)}")
                continue
        
        unique_urls = list(all_urls)[:num_results]
        return {
            'query': query,
            'urls': unique_urls,
            'engines_used': used_engines,
            'total_found': len(unique_urls),
            'status': 'success' if unique_urls else 'no_results'
        }
    
    async def close_all(self):
        """Close all sessions"""
        for engine in self.engines:
            await engine.close_session()

async def search_with_concurrency(queries: List[str], max_concurrent: int = 5, num_results: int = 10) -> List[Dict[str, Any]]:
    """
    Perform concurrent searches for multiple queries
    
    Args:
        queries: List of search queries
        max_concurrent: Max concurrent searches
        num_results: Results per query
        
    Returns:
        List of search results
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    manager = SearchManager()
    
    async def bounded_search(query):
        async with semaphore:
            return await manager.perform_search(query, num_results)
    
    tasks = [bounded_search(q) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Close sessions after searches
    await manager.close_all()
    
    # Filter out exceptions
    return [r for r in results if not isinstance(r, Exception)]

# Example usage
if __name__ == "__main__":
    async def main():
        query = "Python web scraping tools"
        manager = SearchManager()
        result = await manager.perform_search(query, num_results=5)
        print(f"Found {result['total_found']} URLs:")
        for url in result['urls']:
            print(f"- {url}")
        await manager.close_all()
    
    asyncio.run(main())

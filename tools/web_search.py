"""
Web Search Tool - Robust DuckDuckGo wrapper with retries and async support.
Fixes stability issues by handling rate limits and HTTP errors gracefully.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ddgs import DDGS
from langchain_core.tools import tool
from config import config
import time
import random

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # Seconds base delay

# Executor for non-blocking runs
_executor = ThreadPoolExecutor(max_workers=5)


def _safe_search(query: str, max_results: int = 5) -> list:
    """Synchronous search with retry logic and error handling."""
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            # Add delay on retries to avoid rate limiting
            if attempt > 0:
                delay = RETRY_DELAY * (attempt + 1) + random.random()
                print(f"   ⏳ Retry {attempt+1}/{MAX_RETRIES} after {delay:.1f}s delay...")
                time.sleep(delay)

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                print(f"   📥 Got {len(results)} results")
                return results
                
        except Exception as e:
            print(f"   ⚠ Search attempt {attempt+1} failed: {e}")
            last_error = e
            
    # All retries exhausted
    print(f"   ❌ All {MAX_RETRIES} retries failed for: {query}")
    return []


def _format_results(results: list) -> str:
    """Format search results for the LLM."""
    if not results:
        return ""
    
    formatted = []
    # Limit to top 4 results to prevent token explosion
    for i, res in enumerate(results[:4], 1):
        title = res.get("title", "No title")
        # SAFE LIMIT: 1000 chars is plenty for context without exploding tokens
        snippet = res.get("body", res.get("excerpt", "No content"))[:1000]
        url = res.get("href", res.get("url", "#"))
        formatted.append(f"SOURCE {i}: {title}\nURL: {url}\nCONTENT: {snippet}\n")

    return "\n---\n".join(formatted)


@tool
def web_search(query: str) -> str:
    """
    Search the web for current information.
    Useful for news, facts, current events, or specific data not in your memory.
    
    Args:
        query: The search query
    
    Returns:
        Formatted search results with titles, snippets, and URLs
    """
    print(f"🔎 [WEB_SEARCH] Query: '{query}'")
    
    if not config.enable_web_search:
        print("   ❌ Web search is disabled")
        return "Web search is disabled via config."

    try:
        # Perform search with retries
        results = _safe_search(query)

        if not results:
            return f"No results found for: {query}. Try rephrasing your query."

        output = _format_results(results)
        print(f"   ✅ Returning {len(output)} chars from {len(results)} sources")
        return output

    except Exception as e:
        print(f"   ❌ Search error: {e}")
        return f"Error performing web search: {str(e)}"


# Async version for use in FastAPI endpoints (non-blocking)
async def web_search_async(query: str) -> str:
    """
    Async web search - runs blocking I/O in a thread pool.
    Use this in FastAPI endpoints to avoid blocking the event loop.
    """
    print(f"🔎 [WEB_SEARCH_ASYNC] Query: '{query}'")
    
    if not config.enable_web_search:
        return "Web search is disabled via config."

    try:
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(_executor, _safe_search, query)

        if not results:
            return f"No results found for: {query}. Try rephrasing your query."

        return _format_results(results)

    except Exception as e:
        return f"Error performing web search: {str(e)}"


# Synchronous version for direct use (returns raw dicts)
def search_web_sync(query: str) -> list[dict]:
    """
    Synchronous web search for direct use (not as a LangChain tool).
    
    Args:
        query: The search query
    
    Returns:
        List of search result dictionaries
    """
    if not config.enable_web_search:
        return []
    
    return _safe_search(query)

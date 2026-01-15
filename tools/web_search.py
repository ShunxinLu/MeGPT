"""
Web Search Tool - DuckDuckGo wrapper for privacy-first web searches.
No API key required.
"""
from duckduckgo_search import DDGS
from langchain_core.tools import tool
from config import config


@tool
def web_search(query: str) -> str:
    """
    Search the web using DuckDuckGo for current information.
    Use this when you need up-to-date information that you don't have in your training data.
    
    Args:
        query: The search query
    
    Returns:
        Formatted search results with titles, snippets, and URLs
    """
    if not config.enable_web_search:
        return "Web search is disabled."
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        
        if not results:
            return f"No results found for: {query}"
        
        # Format results
        formatted = []
        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            snippet = result.get("body", "No description")
            url = result.get("href", "")
            formatted.append(f"{i}. **{title}**\n   {snippet}\n   Source: {url}")
        
        return "\n\n".join(formatted)
    except Exception as e:
        return f"Search failed: {str(e)}"


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
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        return results
    except Exception as e:
        print(f"⚠ Web search failed: {e}")
        return []

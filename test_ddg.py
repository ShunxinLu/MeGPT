"""Direct test of web search to see raw DuckDuckGo results."""
from ddgs import DDGS

print("=" * 60)
print("DIRECT DUCKDUCKGO SEARCH TEST")
print("=" * 60)

ddgs = DDGS()
query = "AAPL Apple stock price today January 2026"
results = list(ddgs.text(query, max_results=3))

print(f"\nQuery: {query}")
print(f"Results: {len(results)}")
print("=" * 60)

for i, result in enumerate(results, 1):
    print(f"\n--- RESULT {i} ---")
    print(f"TITLE: {result.get('title', 'N/A')}")
    print(f"BODY: {result.get('body', 'N/A')}")
    print(f"URL: {result.get('href', 'N/A')}")

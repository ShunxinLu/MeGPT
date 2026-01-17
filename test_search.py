"""Test script to debug web search and response synthesis."""
from agent_graph import run_agent

print("=" * 60)
print("TESTING STOCK PRICE SEARCH")
print("=" * 60)

response = run_agent("What is AAPL stock price today?")

print("\n" + "=" * 60)
print("FINAL RESPONSE:")
print("=" * 60)
print(response)

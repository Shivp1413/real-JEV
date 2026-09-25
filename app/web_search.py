"""Optional internet access for the decision engine.

When enabled in Settings, the engine runs a web search on the state/context and
question text, then appends the top results to the model's context so decisions can
use fresh information. Two providers are supported: Brave Search and Firecrawl.
"""

from __future__ import annotations

import requests

from . import settings


class SearchError(Exception):
    pass


def brave_search(query: str, count: int, api_key: str) -> list[dict]:
    r = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count},
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        timeout=20,
    )
    if r.status_code == 401:
        raise SearchError("Brave API rejected the key (401). Check your Brave Search API key.")
    r.raise_for_status()
    data = r.json()
    out = []
    for item in (data.get("web", {}) or {}).get("results", [])[:count]:
        out.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            }
        )
    return out


def firecrawl_search(query: str, count: int, api_key: str) -> list[dict]:
    r = requests.post(
        "https://api.firecrawl.dev/v1/search",
        json={"query": query, "limit": count},
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    if r.status_code in (401, 403):
        raise SearchError("Firecrawl rejected the key. Check your Firecrawl API key.")
    r.raise_for_status()
    data = r.json()
    results = data.get("data", data.get("results", [])) or []
    out = []
    for item in results[:count]:
        out.append(
            {
                "title": item.get("title", item.get("url", "")),
                "url": item.get("url", ""),
                "snippet": item.get("description") or item.get("snippet") or (item.get("markdown", "") or "")[:400],
            }
        )
    return out


def search(query: str) -> list[dict]:
    s = settings.get_all()
    provider = s.get("web_search_provider", "brave")
    count = int(s.get("web_search_results", 4))
    if provider == "firecrawl":
        key = s.get("firecrawl_api_key", "")
        if not key:
            raise SearchError("No Firecrawl API key set. Add one in the Web Search tab.")
        return firecrawl_search(query, count, key)
    key = s.get("brave_api_key", "")
    if not key:
        raise SearchError("No Brave API key set. Add one in the Web Search tab.")
    return brave_search(query, count, key)


def results_to_context(results: list[dict]) -> str:
    if not results:
        return ""
    lines = ["[WEB SEARCH RESULTS]"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
    return "\n".join(lines)

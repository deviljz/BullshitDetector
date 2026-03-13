import requests
from typing import List
from urllib.parse import quote_plus

from config import SEARCH_ENGINE, GOOGLE_SEARCH_API_KEY, GOOGLE_SEARCH_CX


def search_news(query: str, max_results: int = 5) -> List[dict]:
    """搜索相关新闻/事实，返回 [{title, snippet, url}, ...]"""
    if SEARCH_ENGINE == "google" and GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX:
        return _search_google(query, max_results)
    return _search_duckduckgo(query, max_results)


def _search_duckduckgo(query: str, max_results: int = 5) -> List[dict]:
    """使用 DuckDuckGo Instant Answer API 搜索"""
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []

        # Abstract (主要摘要)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", ""),
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
            })

        # RelatedTopics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if "Text" in topic:
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                })
            if len(results) >= max_results:
                break

        return results
    except Exception:
        return []


def _search_google(query: str, max_results: int = 5) -> List[dict]:
    """使用 Google Custom Search API 搜索"""
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": GOOGLE_SEARCH_API_KEY,
                "cx": GOOGLE_SEARCH_CX,
                "q": query,
                "num": min(max_results, 10),
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("items", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "url": item.get("link", ""),
            })
        return results
    except Exception:
        return []


def format_search_results(results: List[dict]) -> str:
    """将搜索结果格式化为文本，供 AI 参考"""
    if not results:
        return "（未找到相关搜索结果）"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   来源: {r['url']}")
    return "\n".join(lines)

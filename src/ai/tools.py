"""Function Calling 工具定义 + 搜索执行"""

from typing import List
from duckduckgo_search import DDGS


class SearchProvider:
    """封装搜索引擎，当前使用 DuckDuckGo"""

    def search(self, query: str, max_results: int = 5) -> List[dict]:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                return [
                    {"title": r["title"], "snippet": r["body"], "url": r["href"]}
                    for r in results
                ]
        except Exception:
            return [{"error": "搜索失败，请基于已有知识判断"}]


# 注册给大模型的工具定义
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索网络获取最新信息。用于验证时效性新闻、数据、事件、政策等事实性声明。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "精简的搜索关键词",
                    }
                },
                "required": ["query"],
            },
        },
    }
]


# 全局搜索实例
_search_provider = SearchProvider()


def execute_tool(name: str, arguments: dict) -> str:
    """执行工具调用，返回结果文本"""
    if name == "web_search":
        query = arguments.get("query", "")
        results = _search_provider.search(query)
        if results and "error" in results[0]:
            return results[0]["error"]
        if not results:
            return "未找到相关搜索结果"
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   来源: {r['url']}")
        return "\n".join(lines)
    return f"未知工具: {name}"

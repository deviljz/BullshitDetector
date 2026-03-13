"""向后兼容模块 —— 搜索逻辑已迁移至 ai.tools.SearchProvider"""

from typing import List
from ai.tools import SearchProvider

_provider = SearchProvider()


def search_news(query: str, max_results: int = 5) -> List[dict]:
    """搜索相关新闻/事实（兼容旧接口）"""
    return _provider.search(query, max_results)


def format_search_results(results: List[dict]) -> str:
    """将搜索结果格式化为文本"""
    if not results:
        return "（未找到相关搜索结果）"
    if results and "error" in results[0]:
        return results[0]["error"]
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   来源: {r['url']}")
    return "\n".join(lines)

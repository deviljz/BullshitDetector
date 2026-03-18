"""Function Calling 工具定义 + 搜索执行（支持 DuckDuckGo / Tavily / Google Vision）"""

from typing import List

# 求出处模式临时存放当前图片 base64（单用户桌面应用，无并发问题）
_current_image_b64: str | None = None
_last_vision_urls: list[str] = []


def set_source_image(b64: str | None) -> None:
    global _current_image_b64, _last_vision_urls
    _current_image_b64 = b64
    _last_vision_urls = []


def get_last_vision_urls() -> list[str]:
    return list(_last_vision_urls)


def _search_ddg(query: str, max_results: int = 5) -> List[dict]:
    try:
        from ddgs import DDGS
        with DDGS(timeout=15) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [
                {"title": r["title"], "snippet": r["body"], "url": r["href"]}
                for r in results
            ]
    except Exception as e:
        return [{"error": f"DuckDuckGo 搜索失败（可能需要代理）: {e}"}]


def _search_tavily(query: str, api_key: str, max_results: int = 5) -> List[dict]:
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        resp = client.search(query, max_results=max_results)
        return [
            {"title": r.get("title", ""), "snippet": r.get("content", ""), "url": r.get("url", "")}
            for r in resp.get("results", [])
        ]
    except Exception as e:
        return [{"error": f"Tavily 搜索失败: {e}"}]


class SearchProvider:
    """搜索引擎门面，根据 config 自动选择 DDG 或 Tavily。"""

    def search(self, query: str, max_results: int = 5) -> List[dict]:
        from config.manager import load as _load_cfg
        cfg = _load_cfg()
        provider = cfg.get("search_provider", "ddg")
        if provider == "tavily":
            key = cfg.get("tavily_api_key", "")
            if not key or key.startswith("tvly-xxx"):
                return [{"error": "Tavily API Key 未配置，请在 config.json 中填写 tavily_api_key"}]
            return _search_tavily(query, key, max_results)
        return _search_ddg(query, max_results)


def _reverse_image_search_vision(image_b64: str, api_key: str) -> str:
    """调用 Google Vision WEB_DETECTION 以图搜图。"""
    import requests as _req
    payload = {
        "requests": [{
            "image": {"content": image_b64},
            "features": [{"type": "WEB_DETECTION", "maxResults": 10}],
        }]
    }
    try:
        resp = _req.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
            json=payload, timeout=30,
        )
        if resp.status_code != 200:
            return f"Vision API 错误: {resp.status_code} {resp.text[:200]}"
        det = resp.json()["responses"][0].get("webDetection", {})
    except Exception as e:
        return f"Vision API 请求失败: {e}"

    lines = []
    entities = det.get("webEntities", [])
    if entities:
        lines.append("【作品名候选】")
        for e in entities[:6]:
            if e.get("description"):
                lines.append(f"  [{e.get('score', 0):.2f}] {e['description']}")
    pages = det.get("pagesWithMatchingImages", [])
    if pages:
        lines.append(f"\n【匹配页面（{len(pages)} 条）】")
        for p in pages[:5]:
            title = p.get("pageTitle", "").strip()
            url = p.get("url", "")
            lines.append(f"  {title} — {url}" if title else f"  {url}")
    # 参考图优先级：精确匹配 > 部分匹配 > 视觉相似（避免随机不相关图片）
    global _last_vision_urls
    full_match = det.get("fullMatchingImages", [])
    partial_match = det.get("partialMatchingImages", [])
    visual_similar = det.get("visuallySimilarImages", [])
    ref_pool = full_match or partial_match or visual_similar
    if ref_pool:
        _last_vision_urls = [s["url"] for s in ref_pool[:3] if s.get("url")]
        match_type = "精确匹配" if full_match else ("部分匹配" if partial_match else "视觉相似")
        lines.append(f"\n【参考图片（{match_type}，{len(ref_pool)} 条）】")
        for url in _last_vision_urls:
            lines.append(f"  {url}")
    return "\n".join(lines) if lines else "未找到匹配结果"


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

# 求出处专用工具集（含以图搜图）
SOURCE_TOOLS = [
    TOOLS[0],  # web_search
    {
        "type": "function",
        "function": {
            "name": "reverse_image_search",
            "description": (
                "对当前图片进行以图搜图，识别作品来源。"
                "返回匹配的网页标题和 URL、以及作品名候选列表。"
                "在视觉识别不确定时优先调用此工具。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
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

    if name == "reverse_image_search":
        if not _current_image_b64:
            return "当前没有图片可供搜索"
        from config.manager import load as _load_cfg
        api_key = _load_cfg().get("google_vision_api_key", "")
        if not api_key or api_key.startswith("AIzaSy-YOUR"):
            return "Google Vision API Key 未配置，请在 config.json 中填写 google_vision_api_key"
        return _reverse_image_search_vision(_current_image_b64, api_key)

    return f"未知工具: {name}"

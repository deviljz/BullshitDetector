"""fetch_url 工具单元测试（10 cases）

实现使用单次 httpx.get 拿 HTML + 浏览器 UA，再交 trafilatura.extract 抽正文，
失败回退 BS4。测试相应地 mock httpx.get 和 trafilatura.extract。
"""

import pytest
from unittest.mock import patch, MagicMock


def _mock_resp(text: str = "<html/>", status: int = 200):
    """构造 httpx.get 的 mock Response"""
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


# 每个 test 前清空 cache，保证隔离
@pytest.fixture(autouse=True)
def clear_cache():
    from src.ai.tools import _url_cache
    _url_cache.clear()
    yield
    _url_cache.clear()


# Case 1: trafilatura 抽正文成功路径
def test_trafilatura_success():
    extracted = "正文内容丰富全面"
    with patch("httpx.get", return_value=_mock_resp("<html><p>x</p></html>")) as mock_get, \
         patch("trafilatura.extract", return_value=extracted):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/article")
    assert "正文内容丰富全面" in result
    assert mock_get.call_count == 1


# Case 2: trafilatura 抽不到正文时回退 BS4
def test_fallback_to_bs4():
    html_content = "<html><body><p>BS4回退正文段落</p></body></html>"
    with patch("httpx.get", return_value=_mock_resp(html_content)), \
         patch("trafilatura.extract", return_value=None):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/fallback")
    assert "BS4回退正文段落" in result


# Case 3: httpx 异常 → fetch failed
def test_all_fail_returns_error():
    with patch("httpx.get", side_effect=Exception("network error")):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/broken")
    assert result.startswith("fetch failed:")


# Case 4: 超过 4000 字时截断
def test_hard_truncate_4000():
    long_text = "A" * 5000
    with patch("httpx.get", return_value=_mock_resp("<html/>")), \
         patch("trafilatura.extract", return_value=long_text):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/long")
    assert len(result) <= 4000 + len("...（已截断）")
    assert "已截断" in result


# Case 4b: snippet 超过 300 字时截断（_format_search_results）
def test_snippet_truncated_to_300():
    from src.ai.tools import _format_search_results
    long_snippet = "测试" * 200  # 400 字
    results = [{"title": "T", "snippet": long_snippet, "url": "https://x.com"}]
    out = _format_search_results(results)
    # 截断后 snippet 应 ≤ 300 字 + "..."
    # 单独提取 snippet 行：format 是 "1. T\n   <snippet>\n   来源: ..."
    snippet_line = out.split("\n")[1].strip()  # "<snippet>"
    assert len(snippet_line) <= 303  # 300 + "..."
    assert snippet_line.endswith("...")


# Case 5: URL cache 命中，httpx.get 只调一次
def test_url_cache_hit():
    with patch("httpx.get", return_value=_mock_resp("<html/>")) as mock_get, \
         patch("trafilatura.extract", return_value="缓存测试正文"):
        from src.ai.tools import fetch_url
        fetch_url("https://example.com/cached")
        fetch_url("https://example.com/cached")
    assert mock_get.call_count == 1


# Case 6: httpx.TimeoutException → fetch timeout
def test_timeout_returns_fetch_timeout():
    import httpx
    with patch("httpx.get", side_effect=httpx.TimeoutException("timed out")):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/timeout")
    assert result == "fetch timeout"


# Case 7: focus 命中段落优先，包含命中段落及其上下文
def test_focus_hit_paragraphs():
    # 5 段正文，第 3 段（index 2）含关键词；段落足够长保证命中 3 段合计 > 1000 字
    filler = "这是一段填充文字用于让段落内容足够长以超过最小阈值。" * 15  # ~300 chars each
    paragraphs = [
        "第一段特有标记" + filler,
        "第二段特有标记" + filler,
        "第三段特有标记，全球通史记载了重要历史事件。" + filler,
        "第四段特有标记" + filler,
        "第五段特有标记" + filler,
    ]
    full_text = "\n\n".join(paragraphs)
    with patch("httpx.get", return_value=_mock_resp("<html/>")), \
         patch("trafilatura.extract", return_value=full_text):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/focus", focus="全球通史 修改")
    # 第 2、3、4 段（index 1,2,3）应在结果中
    assert "第二段特有标记" in result
    assert "第三段特有标记" in result
    assert "第四段特有标记" in result
    # 第 1 段（index 0）不应出现
    assert "第一段特有标记" not in result


# Case 8: focus 无命中时回退头部 8000 字
def test_focus_no_hit_fallback_head():
    paragraphs = [
        "第一段内容，关于天气预报。",
        "第二段内容，关于经济数据分析。",
        "第三段内容，关于历史文化。",
        "第四段内容，关于科技发展趋势。",
        "第五段内容，关于文化交流活动。",
    ]
    full_text = "\n\n".join(paragraphs)
    with patch("httpx.get", return_value=_mock_resp("<html/>")), \
         patch("trafilatura.extract", return_value=full_text):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/nofocus", focus="量子纠缠超弦理论")
    # 无命中，回退头部，第一段应出现
    assert "第一段内容" in result


# Case 9: HTTP 4xx/5xx → fetch failed: HTTP <code>
def test_http_error_status_returns_fetch_failed():
    with patch("httpx.get", return_value=_mock_resp("<html/>", status=403)):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/forbidden")
    assert result == "fetch failed: HTTP 403"


# Case 10: reset_url_cache 清空缓存
def test_reset_url_cache_clears_entries():
    from src.ai.tools import fetch_url, reset_url_cache, _url_cache
    with patch("httpx.get", return_value=_mock_resp("<html/>")), \
         patch("trafilatura.extract", return_value="正文内容"):
        fetch_url("https://example.com/a")
    assert len(_url_cache) >= 1
    reset_url_cache()
    assert len(_url_cache) == 0


# Case 11: 浏览器 UA 实际传给 httpx.get（防反爬关键）
def test_browser_ua_passed_to_httpx():
    with patch("httpx.get", return_value=_mock_resp("<html/>")) as mock_get, \
         patch("trafilatura.extract", return_value="ok"):
        from src.ai.tools import fetch_url
        fetch_url("https://example.com/ua_check")
    _args, kwargs = mock_get.call_args
    headers = kwargs.get("headers", {})
    assert "User-Agent" in headers
    assert "Mozilla" in headers["User-Agent"]

"""fetch_url 工具单元测试（8 cases）"""

import pytest
from unittest.mock import patch, MagicMock


# 每个 test 前清空 cache，保证隔离
@pytest.fixture(autouse=True)
def clear_cache():
    from src.ai.tools import _url_cache
    _url_cache.clear()
    yield
    _url_cache.clear()


# Case 1: trafilatura 路径成功
def test_trafilatura_success():
    html = "<html><body><p>正文内容丰富全面</p></body></html>"
    extracted = "正文内容丰富全面"
    with patch("trafilatura.fetch_url", return_value=html) as mock_fetch, \
         patch("trafilatura.extract", return_value=extracted):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/article")
    assert "正文内容丰富全面" in result
    assert mock_fetch.call_count == 1


# Case 2: trafilatura 抽不到正文时回退 BS4
def test_fallback_to_bs4():
    html_content = "<html><body><p>BS4回退正文段落</p></body></html>"
    mock_resp = MagicMock()
    mock_resp.text = html_content

    with patch("trafilatura.fetch_url", return_value="<html/>"), \
         patch("trafilatura.extract", return_value=None), \
         patch("httpx.get", return_value=mock_resp):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/fallback")
    assert "BS4回退正文段落" in result


# Case 3: 全失败返回 fetch failed
def test_all_fail_returns_error():
    with patch("trafilatura.fetch_url", side_effect=Exception("traf error")), \
         patch("httpx.get", side_effect=Exception("httpx error")):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/broken")
    assert result.startswith("fetch failed:")


# Case 4: 超过 8000 字时截断
def test_hard_truncate_8000():
    long_text = "A" * 9000
    with patch("trafilatura.fetch_url", return_value="<html/>"), \
         patch("trafilatura.extract", return_value=long_text):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/long")
    assert len(result) <= 8000 + len("...（已截断）")
    assert "已截断" in result


# Case 5: URL cache 命中，trafilatura.fetch_url 只调一次
def test_url_cache_hit():
    html = "<html><body><p>缓存测试正文</p></body></html>"
    with patch("trafilatura.fetch_url", return_value=html) as mock_fetch, \
         patch("trafilatura.extract", return_value="缓存测试正文"):
        from src.ai.tools import fetch_url
        fetch_url("https://example.com/cached")
        fetch_url("https://example.com/cached")
    assert mock_fetch.call_count == 1


# Case 6: 超时返回 fetch timeout
def test_timeout_returns_fetch_timeout():
    with patch("trafilatura.fetch_url", side_effect=TimeoutError("timed out")):
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
    with patch("trafilatura.fetch_url", return_value="<html/>"), \
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
    with patch("trafilatura.fetch_url", return_value="<html/>"), \
         patch("trafilatura.extract", return_value=full_text):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/nofocus", focus="量子纠缠超弦理论")
    # 无命中，回退头部，第一段应出现
    assert "第一段内容" in result


# Case 9: httpx.TimeoutException 在 BS4 回退路径上正确返回 fetch timeout
def test_httpx_timeout_returns_fetch_timeout():
    import httpx
    # trafilatura 失败让流程走 BS4 回退；httpx.get 抛 TimeoutException 应被识别为 timeout
    with patch("trafilatura.fetch_url", return_value=None), \
         patch("httpx.get", side_effect=httpx.TimeoutException("read timeout")):
        from src.ai.tools import fetch_url
        result = fetch_url("https://example.com/timeout")
    assert result == "fetch timeout"


# Case 10: reset_url_cache 清空缓存
def test_reset_url_cache_clears_entries():
    from src.ai.tools import fetch_url, reset_url_cache, _url_cache
    with patch("trafilatura.fetch_url", return_value="<html/>"), \
         patch("trafilatura.extract", return_value="正文内容"):
        fetch_url("https://example.com/a")
    assert len(_url_cache) >= 1
    reset_url_cache()
    assert len(_url_cache) == 0

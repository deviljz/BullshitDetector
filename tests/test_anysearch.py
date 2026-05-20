"""单元测试：AnySearch provider 适配层"""

import sys
import pathlib
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from ai.tools import _parse_anysearch_markdown, _search_anysearch  # type: ignore


SAMPLE_MARKDOWN = """## 搜索结果 (共 3 条；耗时 2685ms)

### 1. Election 2026: Results, news and analysis | CNN Politics
- **链接**: https://www.cnn.com/election/2026
- Follow the latest news, results and analysis from every race in the 2026 midterm elections.
date: 4 hours ago

### 2. 2026 United States elections - Wikipedia
- **链接**: https://en.wikipedia.org/wiki/2026_United_States_elections
- The 2026 United States elections are scheduled to be held, in large part, on November 3, 2026.
date: 3 hours ago
sitelinks:
Background and campaign: https://en.wikipedia.org/wiki/2026_United_States_elections#Background

### 3. What to watch in Tuesday's primaries
- **链接**: https://www.washingtonpost.com/politics/2026/05/19/election-takeaways
- What to watch in Tuesday's primaries as Trump's endorsement is put to the test
"""


def test_parser_extracts_three_results():
    results = _parse_anysearch_markdown(SAMPLE_MARKDOWN)
    assert len(results) == 3


def test_parser_title_url_snippet():
    results = _parse_anysearch_markdown(SAMPLE_MARKDOWN)
    assert results[0]["title"] == "Election 2026: Results, news and analysis | CNN Politics"
    assert results[0]["url"] == "https://www.cnn.com/election/2026"
    assert "midterm elections" in results[0]["snippet"]


def test_parser_skips_sitelinks_in_snippet():
    results = _parse_anysearch_markdown(SAMPLE_MARKDOWN)
    # second result has sitelinks block — must NOT be part of snippet
    assert "sitelinks" not in results[1]["snippet"]
    assert "Background and campaign" not in results[1]["snippet"]


def test_parser_handles_empty():
    assert _parse_anysearch_markdown("") == []
    assert _parse_anysearch_markdown("## 搜索结果 (共 0 条)") == []


def test_parser_handles_missing_url_field():
    md = """### 1. Title only
- No proper link line here
- Snippet content
"""
    results = _parse_anysearch_markdown(md)
    assert len(results) == 1
    assert results[0]["title"] == "Title only"
    assert results[0]["url"] == ""


def test_search_anonymous_no_key():
    """匿名模式：不传 key，不报错，正常解析返回。"""
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": SAMPLE_MARKDOWN}]
        },
    }
    with patch("ai.tools.requests.post", return_value=fake_resp) as mock_post:
        results = _search_anysearch("test query", api_key="", max_results=3)
    assert len(results) == 3
    # 验证匿名模式不发 Authorization 头
    call_kwargs = mock_post.call_args.kwargs
    headers = call_kwargs.get("headers", {})
    assert "Authorization" not in headers


def test_search_with_key():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "result": {"content": [{"type": "text", "text": SAMPLE_MARKDOWN}]}
    }
    with patch("ai.tools.requests.post", return_value=fake_resp) as mock_post:
        _search_anysearch("q", api_key="mykey123", max_results=2)
    headers = mock_post.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer mykey123"


def test_search_jsonrpc_error_returns_error_dict():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "error": {"code": -32000, "message": "rate limit exceeded"}
    }
    with patch("ai.tools.requests.post", return_value=fake_resp):
        results = _search_anysearch("q", api_key="", max_results=3)
    assert len(results) == 1
    assert "error" in results[0]
    assert "rate limit" in results[0]["error"]


def test_search_http_error():
    fake_resp = MagicMock()
    fake_resp.status_code = 500
    fake_resp.text = "Internal Server Error"
    with patch("ai.tools.requests.post", return_value=fake_resp):
        results = _search_anysearch("q", api_key="", max_results=3)
    assert "error" in results[0]
    assert "500" in results[0]["error"]


def test_search_network_exception():
    with patch("ai.tools.requests.post", side_effect=Exception("connection refused")):
        results = _search_anysearch("q", api_key="", max_results=3)
    assert "error" in results[0]
    assert "connection refused" in results[0]["error"]

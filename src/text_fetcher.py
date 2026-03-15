"""text_fetcher.py —— 从 URL 提取网页正文"""

import requests
from readability import Document


def fetch_article(url: str) -> str:
    """
    拉取网页正文，返回纯文本（标题 + 正文）。
    失败时直接返回原始 url 字符串（让模型自己搜索）。
    """
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        doc = Document(resp.text)
        title = doc.title() or ""
        # readability 返回 HTML summary，转为纯文本
        import html
        import re
        body_html = doc.summary()
        # 去除 HTML 标签
        body_text = re.sub(r"<[^>]+>", " ", body_html)
        body_text = html.unescape(body_text)
        body_text = re.sub(r"\s+", " ", body_text).strip()
        return f"{title}\n\n{body_text}" if title else body_text
    except Exception:
        return url

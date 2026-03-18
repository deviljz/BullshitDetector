"""text_fetcher.py —— 从 URL 提取网页正文"""

import html
import re

import requests
from readability import Document

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _extract_wechat(html_text: str) -> str:
    """直接从 HTML 解析微信 #js_content，绕过 visibility:hidden。"""
    try:
        from lxml import etree

        def _text(node) -> str:
            return etree.tostring(node, method="text", encoding="unicode")

        root = etree.fromstring(html_text.encode(), etree.HTMLParser())
        # 提取标题（微信用 #activity-name）
        title_nodes = root.xpath('//*[@id="activity-name"]')
        title = _text(title_nodes[0]).strip() if title_nodes else ""
        # 提取正文
        content_nodes = root.xpath('//*[@id="js_content"]')
        if not content_nodes:
            return ""
        body_text = _text(content_nodes[0])
        body_text = re.sub(r"\s+", " ", body_text).strip()
        return f"{title}\n\n{body_text}" if title else body_text
    except Exception:
        return ""


def fetch_article(url: str) -> str:
    """
    拉取网页正文，返回纯文本（标题 + 正文）。
    失败时直接返回原始 url 字符串（让模型自己搜索）。
    """
    try:
        resp = requests.get(url, timeout=15, headers=_BROWSER_HEADERS)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"

        # 微信公众号文章正文在 #js_content（visibility:hidden），readability 无法提取
        if "mp.weixin.qq.com" in url:
            text = _extract_wechat(resp.text)
            if text:
                return text

        doc = Document(resp.text)
        title = doc.title() or ""
        body_html = doc.summary()
        body_text = re.sub(r"<[^>]+>", " ", body_html)
        body_text = html.unescape(body_text)
        body_text = re.sub(r"\s+", " ", body_text).strip()
        return f"{title}\n\n{body_text}" if title else body_text
    except Exception:
        return url

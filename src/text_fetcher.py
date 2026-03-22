"""text_fetcher.py —— 从 URL 提取网页正文"""

import html
import io as _io
import logging
import re

import requests
from readability import Document

_log = logging.getLogger(__name__)

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


def fetch_toutiao(url: str) -> tuple[str, list]:
    """用 Playwright 提取今日头条文章正文（文字 + 图片）。

    返回 (text, [PIL.Image, ...])。失败时返回 (url, [])。
    """
    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image as PILImage
    except ImportError:
        _log.warning("fetch_toutiao: playwright 未安装，跳过")
        return url, []

    try:
        _log.info("fetch_toutiao: 开始抓取 %s", url[:80])
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1500)

            # 点击"展开全文"按钮（头条默认折叠正文）
            try:
                btn = page.locator("text=点击展开").first
                if btn.count() > 0:
                    btn.click()
                    page.wait_for_timeout(800)
            except Exception:
                pass

            # 滚动触发懒加载（快速，每步 150ms）
            for pos in range(0, 12000, 700):
                page.evaluate(f"window.scrollTo(0, {pos})")
                page.wait_for_timeout(150)
            page.wait_for_timeout(800)

            # 提取正文文字（仅 .wtt-content 容器）
            raw_text = page.evaluate("""() => {
                const el = document.querySelector('.wtt-content');
                return el ? el.innerText : '';
            }""") or ""
            text = re.sub(r"[ \t]+", " ", raw_text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if len(text) > 3000:
                text = text[:3000] + "…（已截断）"

            # 提取正文图片（仅 .wtt-content 容器，排除头像）
            srcs = page.evaluate("""() => {
                const container = document.querySelector('.wtt-content');
                if (!container) return [];
                return Array.from(container.querySelectorAll('img'))
                    .map(img => img.src || img.dataset.src || '')
                    .filter(src => src.startsWith('http'));
            }""") or []
            srcs = [s for s in srcs if "user-avatar" not in s and "avatar" not in s]

            images = []
            for src in srcs[:12]:  # 最多尝试 12 张
                try:
                    resp = context.request.get(src, timeout=10000)
                    if not resp.ok:
                        continue
                    data = resp.body()
                    if len(data) < 15000:  # 跳过 <15KB 的图标/装饰图
                        continue
                    img = PILImage.open(_io.BytesIO(data)).convert("RGB")
                    if img.width < 200 or img.height < 100:  # 跳过过窄/矮的图
                        continue
                    images.append(img)
                    if len(images) >= 6:  # 最多发 6 张给 AI
                        break
                except Exception:
                    continue

            browser.close()
            _log.info("fetch_toutiao: 完成，文字 %d 字，图片 %d 张", len(text), len(images))
            return text or url, images
    except Exception as e:
        _log.error("fetch_toutiao: 失败 %s", e, exc_info=True)
        return url, []

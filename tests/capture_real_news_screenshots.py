"""
用 Playwright 截取真实新闻页面作为 fixture
运行：python tests/capture_real_news_screenshots.py
输出：tests/fixtures/real_web_*.jpg
"""
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)

# 真实存在的新闻页面（已通过 WebSearch 验证 URL 有效）
TARGETS = [
    (
        "real_web_stats_gdp_2024q3",
        "https://www.stats.gov.cn/sj/zxfb/202410/t20241018_1957044.html",
        "国家统计局：前三季度国民经济运行总体平稳（2024-10-18）",
    ),
    (
        "real_web_stats_gdp_2024q3_calc",
        "https://www.stats.gov.cn/sj/zxfb/202410/t20241019_1957083.html",
        "国家统计局：2024年三季度GDP初步核算结果（4.6%）",
    ),
    (
        "real_web_moe_gaokao_1342w",
        "http://www.moe.gov.cn/jyb_xwfb/xw_zt/moe_357/2024/2024_zt12/mtbd/202406/t20240603_1133631.html",
        "教育部：2024年全国高考报名人数达1342万人",
    ),
    (
        "real_web_moe_gaokao_start",
        "http://www.moe.gov.cn/jyb_xwfb/xw_zt/moe_357/2024/2024_zt12/mtbd/202406/t20240608_1134568.html",
        "教育部：2024年全国高考拉开帷幕",
    ),
    (
        "real_web_mps_network_rumor_2024",
        "https://www.mps.gov.cn/n2254098/n4904352/c9538664/content.html",
        "公安部：打击整治网络谣言专项行动10起典型案例（2024-04-12）",
    ),
    (
        "real_web_mps_network_rumor_2024b",
        "https://www.mps.gov.cn/n2254098/n4904352/c10267710/content.html",
        "公安部：打击整治网络谣言10起典型案例（更新批次）",
    ),
    (
        "real_web_xinhua_raisi_dead_2024",
        "http://www.xinhuanet.com/photo/20240520/90b7612455304244926c37f0c51dbb2b/c.html",
        "新华社：伊朗总统莱希在直升机事故中遇难（2024-05-20）",
    ),
    (
        "real_web_xinhua_syria_globe",
        "http://www.xinhuanet.com/globe/20250121/cc75a7fd15494011a6d5f58bff93f973/c.html",
        "新华报刊·环球：政局剧变后的叙利亚",
    ),
    (
        "real_web_jsdzj_hualien_eq_2024",
        "https://www.jsdzj.gov.cn/art/2024/4/3/art_91_18596.html",
        "江苏地震局：中国地震局开展台湾花莲县7.3级地震应急处置（2024-04-03）",
    ),
    (
        "real_web_stats_annual_2024",
        "https://www.stats.gov.cn/sj/zxfb/202502/t20250228_1958817.html",
        "国家统计局：中华人民共和国2024年国民经济和社会发展统计公报",
    ),
    (
        "real_web_xinhua_iran_israel_app",
        "https://app.xinhuanet.com/news/article.html?articleId=cd6f52ea161b8173af14e29d883a5fa8",
        "新华社：综合消息｜伊朗报复以色列 中东紧张局势升级（2024-10-01）",
    ),
    (
        "real_web_xinhua_olympic_2024",
        "https://app.xinhuanet.com/news/article.html?articleId=84db90d4fc50664b50e9e81d19ee950e",
        "新华社：奥运佳绩彰显新时代中国力量（2024巴黎奥运40金）",
    ),
]


def capture(playwright, name: str, url: str, desc: str) -> bool:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="zh-CN",
    )
    page = context.new_page()
    try:
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(3)  # 等动态内容
        out_path = FIXTURES_DIR / f"{name}.jpg"
        page.screenshot(path=str(out_path), full_page=False, type="jpeg", quality=90)
        size = out_path.stat().st_size
        print(f"  [OK] {out_path.name}  {size//1024}KB  {desc}")
        return True
    except Exception as e:
        print(f"  [FAIL] {name}  {e}")
        return False
    finally:
        browser.close()


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print(f"\n[DIR] {FIXTURES_DIR.resolve()}\n")
    ok = 0
    with sync_playwright() as p:
        for name, url, desc in TARGETS:
            if capture(p, name, url, desc):
                ok += 1
    print(f"\n完成：{ok}/{len(TARGETS)} 张截图成功")
    print("下一步：检查图片内容 → 更新 EXPECTATIONS")


if __name__ == "__main__":
    main()

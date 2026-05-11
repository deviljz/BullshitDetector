"""
生成测试图片 Fixtures — 模拟真实截图场景的 4 张高迷惑性图片。
运行：python tests/generate_test_images.py
输出：tests/fixtures/*.png
"""
import pathlib
import textwrap

from PIL import Image, ImageDraw, ImageFont

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)

# ── Windows 中文字体候选列表（按优先级排列）─────────────────────────────────
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑（最常见）
    "C:/Windows/Fonts/msyhbd.ttc",     # 微软雅黑 Bold
    "C:/Windows/Fonts/simhei.ttf",     # 黑体
    "C:/Windows/Fonts/simsun.ttc",     # 宋体
    "C:/Windows/Fonts/simkai.ttf",     # 楷体
    "/usr/share/fonts/noto/NotoSansCJK-Regular.ttc",  # Linux 备用
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, max_width: int, font, draw: ImageDraw.ImageDraw) -> list[str]:
    """按像素宽度自动折行"""
    lines = []
    for paragraph in text.split("\n"):
        words = list(paragraph)  # 中文逐字处理
        current = ""
        for char in words:
            test = current + char
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def make_screenshot(
    filename: str,
    title: str,
    source: str,
    body: str,
    title_color: str = "#c0392b",
    accent_color: str = "#2980b9",
    img_w: int = 900,
    img_h: int = 480,
) -> pathlib.Path:
    """
    渲染一张模拟新闻截图：
    ┌─────────────────────────────────────────┐
    │  [source bar]                           │
    │  TITLE（大字）                          │
    │                                         │
    │  body text（正文多行）                  │
    │                                         │
    │  [footer: 转发数/时间]                  │
    └─────────────────────────────────────────┘
    """
    img = Image.new("RGB", (img_w, img_h), "#ffffff")
    draw = ImageDraw.Draw(img)

    font_source = _load_font(16)
    font_title = _load_font(28)
    font_body = _load_font(20)
    font_small = _load_font(14)

    PAD = 36

    # ── 顶部来源栏 ──────────────────────────────────────────────────────────
    draw.rectangle([0, 0, img_w, 44], fill=accent_color)
    draw.text((PAD, 10), source, font=font_source, fill="#ffffff")

    # ── 标题 ────────────────────────────────────────────────────────────────
    y = 68
    title_lines = _wrap_text(title, img_w - PAD * 2, font_title, draw)
    for line in title_lines:
        draw.text((PAD, y), line, font=font_title, fill=title_color)
        y += 38

    # ── 分割线 ──────────────────────────────────────────────────────────────
    y += 8
    draw.line([(PAD, y), (img_w - PAD, y)], fill="#e0e0e0", width=1)
    y += 16

    # ── 正文 ────────────────────────────────────────────────────────────────
    body_lines = _wrap_text(body, img_w - PAD * 2, font_body, draw)
    for line in body_lines:
        draw.text((PAD, y), line, font=font_body, fill="#333333")
        y += 30
        if y > img_h - 60:
            break  # 防止溢出

    # ── 底部装饰 ─────────────────────────────────────────────────────────────
    draw.rectangle([0, img_h - 36, img_w, img_h], fill="#f5f5f5")
    draw.text(
        (PAD, img_h - 26),
        "转发 1.2万  |  评论 3451  |  点赞 8.9万   © 2026",
        font=font_small,
        fill="#999999",
    )

    out_path = FIXTURES_DIR / filename
    img.save(str(out_path), "PNG")
    print(f"  [OK] {out_path.name}  ({img_w}x{img_h})")
    return out_path


# ── 4 张测试图片定义 ──────────────────────────────────────────────────────────

FIXTURES: list[dict] = [
    {
        "filename": "01_fake_physics.png",
        "source": "🔬 科技前沿 · 独家 · 2026-03-12 23:47",
        "title": "震惊！清华量子实验室宣布成功向过去发送短信，人类首台时间机器雏形诞生！",
        "body": textwrap.dedent("""\
            【本报特约记者 北京报道】清华大学量子物理实验室昨夜召开紧急发布会，宣布
            团队历时八年，成功利用量子纠缠技术向 72 小时前发送了一条 10KB 的文本短信，
            并已获得接收端的回执确认。这一划时代突破标志着人类首台实用化时间通信装置
            雏形正式诞生。

            据悉，该项目获国家自然科学基金重点项目支持，相关论文已投《Nature》。
            外界评论称"这将彻底改写物理学教科书"。"""),
        "title_color": "#c0392b",
        "accent_color": "#8e44ad",
    },
    {
        "filename": "02_fake_fed.png",
        "source": "📈 Bloomberg 彭博社快讯 · 2026-03-13 09:31 ET",
        "title": "突发！美联储召开紧急会议，宣布一次性降息100个基点，全球资本市场沸腾！",
        "body": textwrap.dedent("""\
            据彭博社2026年3月13日最新独家消息，美联储主席杰罗姆·鲍威尔于北京时间
            今日凌晨 4 时召集 FOMC 全体委员举行紧急闭门会议，随后宣布将联邦基金利率
            目标区间一次性下调 100 个基点至 2.25%-2.50%，创下 2008 年金融危机以来
            最大单次降息幅度。

            受此消息刺激，纳斯达克期货盘前暴涨 4.7%，黄金每盎司突破 3500 美元，
            比特币单日涨幅超 18%。多国央行紧急开会商讨应对策略。"""),
        "title_color": "#c0392b",
        "accent_color": "#27ae60",
    },
    {
        "filename": "03_fake_lancet.png",
        "source": "🏥 健康科普Daily · 转自《柳叶刀》编译 · 2026-03-13",
        "title": "《柳叶刀》最新研究：长期饮用低于37℃温水导致胃部DNA突变，致癌率飙升400%！",
        "body": textwrap.dedent("""\
            《柳叶刀》（The Lancet）2026年3月刊发布了一项历时12年、覆盖全球 16 个
            国家共 42 万人的大规模队列研究。研究结果令人震惊：长期（超过10年）每日
            饮用温度低于 37℃ 温水的人群，其胃黏膜细胞线粒体 DNA 发生甲基化突变的
            概率比对照组高出 400%，胃腺癌发生率提升 3.8 倍。

            研究主导者、哈佛医学院 Dr. Wei Zhang 建议：日常饮水温度应保持在
            45-60℃ 之间，以维持"胃部微环境热稳态"。该研究已通过同行评审。"""),
        "title_color": "#c0392b",
        "accent_color": "#e67e22",
    },
    {
        "filename": "04_real_news.png",
        "source": "📰 新华社 · 2026-03-13 10:05",
        "title": "国家统计局：2026年1-2月全国规模以上工业增加值同比增长5.8%",
        "body": textwrap.dedent("""\
            国家统计局今日发布数据，2026年1-2月份，全国规模以上工业增加值同比增长
            5.8%，增速较上年全年加快 0.3 个百分点。分行业看，制造业增长 6.1%，
            其中高技术制造业增长 10.2%，新能源汽车产量同比增长 38.5%。

            统计局发言人表示，开年经济运行总体平稳，工业生产延续回升向好态势，
            市场预期持续改善。分析人士认为，全年 GDP 目标完成具备坚实基础。"""),
        "title_color": "#1a5276",
        "accent_color": "#2471a3",
    },
]


def main():
    # 强制 stdout 使用 utf-8（Windows 默认 GBK 不支持 emoji）
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print(f"\n[DIR] 输出目录: {FIXTURES_DIR.resolve()}\n")
    for spec in FIXTURES:
        make_screenshot(**spec)
    print(f"\n[OK] 全部完成，共生成 {len(FIXTURES)} 张测试图片。")
    print("下一步：python tests/run_vision_eval.py")


if __name__ == "__main__":
    main()

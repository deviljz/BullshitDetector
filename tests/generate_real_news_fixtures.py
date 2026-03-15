"""
生成"真实新闻"类 fixture — 模拟微博/官方公告截图
目标：填充 expected_fake=False 的测试样本，暴露 false positive
共 12 张，含伊朗战争、国际局势、国内政策等可搜索的真实事件

运行：python tests/generate_real_news_fixtures.py
"""
import io
import pathlib
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]


def _font(size: int):
    for p in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _wrap(text: str, max_w: int, font, draw) -> list[str]:
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            test = cur + ch
            if draw.textbbox((0, 0), test, font=font)[2] > max_w and cur:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            lines.append(cur)
    return lines


def make_weibo(
    filename: str,
    username: str,
    verified: bool,
    timestamp: str,
    content: str,
    likes: str = "3.2万",
    comments: str = "8641",
    reposts: str = "1.4万",
    avatar_color: str = "#e74c3c",
    img_w: int = 800,
    img_h: int = 440,
) -> pathlib.Path:
    img = Image.new("RGB", (img_w, img_h), "#ffffff")
    draw = ImageDraw.Draw(img)

    f_name = _font(20)
    f_body = _font(19)
    f_meta = _font(14)

    PAD = 24

    # 顶部导航栏
    draw.rectangle([0, 0, img_w, 46], fill="#ff8200")
    draw.text((PAD, 12), "微博 Weibo", font=_font(18), fill="#ffffff")

    # 头像圆圈
    av_r, av_cx, av_cy = 28, PAD + 28, 84
    draw.ellipse([av_cx - av_r, av_cy - av_r, av_cx + av_r, av_cy + av_r], fill=avatar_color)
    init = username[0]
    bb = draw.textbbox((0, 0), init, font=_font(24))
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.text((av_cx - tw // 2, av_cy - th // 2 - 2), init, font=_font(24), fill="#ffffff")

    # 昵称 + 认证标记
    name_x = av_cx + av_r + 12
    draw.text((name_x, 64), username, font=f_name, fill="#333333")
    if verified:
        vb = draw.textbbox((0, 0), username, font=f_name)
        nx2 = name_x + vb[2] + 8
        draw.ellipse([nx2, 68, nx2 + 18, 86], fill="#ff8200")
        draw.text((nx2 + 3, 68), "V", font=_font(13), fill="#ffffff")
    draw.text((name_x, 88), timestamp, font=f_meta, fill="#999999")

    # 正文
    y = 124
    for line in _wrap(content, img_w - PAD * 2, f_body, draw):
        draw.text((PAD, y), line, font=f_body, fill="#333333")
        y += 30
        if y > img_h - 56:
            break

    # 互动栏
    draw.rectangle([0, img_h - 44, img_w, img_h], fill="#f7f7f7")
    draw.line([(0, img_h - 44), (img_w, img_h - 44)], fill="#e0e0e0", width=1)
    draw.text((PAD, img_h - 30),
              f"♻ 转发 {reposts}    💬 评论 {comments}    ❤ 赞 {likes}",
              font=f_meta, fill="#666666")

    out = FIXTURES_DIR / filename
    img.save(str(out), "PNG")
    print(f"  [OK] {out.name}")
    return out


def make_notice(
    filename: str,
    org: str,
    title: str,
    body: str,
    date: str,
    img_w: int = 800,
    img_h: int = 520,
) -> pathlib.Path:
    img = Image.new("RGB", (img_w, img_h), "#fafafa")
    draw = ImageDraw.Draw(img)

    f_org = _font(16)
    f_title = _font(21)
    f_body = _font(17)
    f_date = _font(14)

    PAD = 40

    draw.rectangle([0, 0, img_w, 52], fill="#c0392b")
    org_bb = draw.textbbox((0, 0), org, font=f_org)
    draw.text(((img_w - (org_bb[2] - org_bb[0])) // 2, 16), org, font=f_org, fill="#ffffff")

    draw.line([(PAD, 62), (img_w - PAD, 62)], fill="#c0392b", width=2)

    y = 80
    for line in _wrap(title, img_w - PAD * 2, f_title, draw):
        tb = draw.textbbox((0, 0), line, font=f_title)
        draw.text(((img_w - (tb[2] - tb[0])) // 2, y), line, font=f_title, fill="#c0392b")
        y += 34
    y += 10
    draw.line([(PAD, y), (img_w - PAD, y)], fill="#e0e0e0", width=1)
    y += 18

    for line in _wrap(body, img_w - PAD * 2, f_body, draw):
        draw.text((PAD, y), line, font=f_body, fill="#333333")
        y += 28
        if y > img_h - 60:
            break

    draw.rectangle([0, img_h - 44, img_w, img_h], fill="#f0f0f0")
    draw.line([(0, img_h - 44), (img_w, img_h - 44)], fill="#e0e0e0", width=1)
    draw.text((img_w - PAD - 260, img_h - 30), date, font=f_date, fill="#666666")

    out = FIXTURES_DIR / filename
    img.save(str(out), "PNG")
    print(f"  [OK] {out.name}")
    return out


def main():
    print(f"\n[DIR] {FIXTURES_DIR.resolve()}\n")

    # ── 国际局势 / 伊朗战争相关 ───────────────────────────────────────────────

    # 1. 伊朗袭击以色列（2024年4月14日，可搜索）
    make_weibo(
        filename="real_xinhua_weibo_iran_attack_israel_2024.png",
        username="新华社",
        verified=True,
        timestamp="2024-04-14 06:22  来自 新华社官方微博",
        content=(
            "【伊朗向以色列发动大规模无人机和导弹袭击】新华社消息：当地时间13日深夜，"
            "伊朗伊斯兰革命卫队宣布对以色列发动代号'真正承诺'的军事行动，"
            "向以境内发射逾300架无人机及数十枚弹道导弹。以军方称拦截绝大多数来袭目标，"
            "美、英、约旦等国协助拦截。目前以方报告无重大伤亡。"
            "联合国安理会紧急召开会议，多国呼吁各方保持克制。"
        ),
        likes="28.4万",
        comments="6.1万",
        reposts="19.7万",
        avatar_color="#c0392b",
    )

    # 2. 以色列反击伊朗（2024年4月19日，可搜索）
    make_weibo(
        filename="real_cctv_weibo_israel_strike_iran_2024.png",
        username="央视新闻",
        verified=True,
        timestamp="2024-04-19 08:45  来自 央视新闻官方微博",
        content=(
            "【以色列对伊朗实施打击】据多家媒体报道，当地时间4月19日凌晨，"
            "伊朗伊斯法罕省上空出现爆炸声，伊朗防空系统启动。美国媒体引述消息人士称，"
            "以色列对伊朗境内目标实施了有限军事打击，被视为对伊朗13日袭击的回应。"
            "伊朗官员表示已击落3架小型无人机，局势没有进一步升级。"
            "中方呼吁相关方保持冷静克制，避免局势失控。"
        ),
        likes="19.2万",
        comments="4.8万",
        reposts="13.5万",
        avatar_color="#1565c0",
    )

    # 3. 伊朗总统莱希直升机事故身亡（2024年5月19日，可搜索）
    make_weibo(
        filename="real_xinhua_weibo_raisi_death_2024.png",
        username="新华社",
        verified=True,
        timestamp="2024-05-20 06:10  来自 新华社官方微博",
        content=(
            "【伊朗总统莱希在直升机事故中遇难】新华社德黑兰5月20日电：伊朗官方媒体宣布，"
            "伊朗总统易卜拉欣·莱希在乘坐直升机视察西北部东阿塞拜疆省途中失联，"
            "经搜救后确认在直升机坠毁事故中遇难，外长阿卜杜拉希扬等同机人员亦全部罹难。"
            "事故发生于当地时间19日下午，直升机坠于山区雾气浓厚地带，恶劣天气导致搜救困难。"
            "伊朗宣布进行全国哀悼，第一副总统穆赫贝尔将暂代总统职务。"
        ),
        likes="35.7万",
        comments="8.2万",
        reposts="24.1万",
        avatar_color="#c0392b",
    )

    # 4. 黎以停火协议（2024年11月27日，可搜索）
    make_weibo(
        filename="real_rmrb_weibo_lebanon_ceasefire_2024.png",
        username="人民日报",
        verified=True,
        timestamp="2024-11-27 16:30  来自 人民日报官方微博",
        content=(
            "【黎巴嫩与以色列停火协议生效】据报道，以色列与黎巴嫩真主党在美国、法国斡旋下"
            "于当地时间26日达成停火协议，协议于27日凌晨4时正式生效，为期60天。"
            "以军将逐步从黎南部撤离，黎巴嫩军队将部署至南部边境地区。"
            "这是持续逾14个月的武装冲突中双方首次达成停火。"
            "中方对此表示欢迎，呼吁各方全面落实停火协议，推动实现持久和平。"
        ),
        likes="12.6万",
        comments="3.1万",
        reposts="9.4万",
        avatar_color="#c0392b",
    )

    # 5. 叙利亚阿萨德政权倒台（2024年12月8日，可搜索）
    make_weibo(
        filename="real_xinhua_weibo_syria_assad_fall_2024.png",
        username="新华社",
        verified=True,
        timestamp="2024-12-08 18:05  来自 新华社官方微博",
        content=(
            "【叙利亚总统阿萨德离开叙利亚，反对派武装宣布控制大马士革】"
            "新华社报道：当地时间8日，叙利亚反对派武装攻入首都大马士革，"
            "总统巴沙尔·阿萨德已离开叙利亚，其执政24年的政权宣告终结。"
            "叙利亚境内俄罗斯军事基地人员已撤离。"
            "中国外交部表示，中方支持叙利亚人民自主决定本国前途命运，"
            "希望叙利亚尽快实现稳定和重建。"
        ),
        likes="42.1万",
        comments="11.3万",
        reposts="29.8万",
        avatar_color="#c0392b",
    )

    # ── 国内重要新闻 ──────────────────────────────────────────────────────────

    # 6. 2024年全国两会开幕（2024年3月5日，可搜索）
    make_weibo(
        filename="real_rmrb_weibo_lianghui_2024.png",
        username="人民日报",
        verified=True,
        timestamp="2024-03-05 09:02  来自 人民日报官方微博",
        content=(
            "【十四届全国人大二次会议开幕】第十四届全国人民代表大会第二次会议"
            "今日上午9时在北京人民大会堂隆重开幕，3000余名全国人大代表出席。"
            "国务院总理李强代表国务院向大会作政府工作报告，提出2024年国内生产总值"
            "增长目标为5%左右，城镇新增就业1200万人以上，居民消费价格涨幅3%左右。"
        ),
        likes="20.5万",
        comments="3.8万",
        reposts="14.2万",
        avatar_color="#c0392b",
    )

    # 7. 2024年高考报名人数（2024年6月，可搜索）
    make_weibo(
        filename="real_xinhua_weibo_gaokao_2024.png",
        username="新华社",
        verified=True,
        timestamp="2024-06-07 07:30  来自 新华社官方微博",
        content=(
            "【2024年高考今日开考，报名人数创历史新高】教育部数据显示，"
            "2024年全国高考报名人数达1342万人，比去年增加51万人，再创历史新高。"
            "高考于6月7日至8日举行，部分省份延至6月10日。"
            "全国共设考场约6万个，监考人员约94万人次。"
            "预祝全体考生发挥出色！#2024高考#"
        ),
        likes="8.4万",
        comments="1.9万",
        reposts="5.6万",
        avatar_color="#c0392b",
    )

    # 8. 2024巴黎奥运会中国代表团金牌榜（2024年8月11日，可搜索）
    make_weibo(
        filename="real_cctv_weibo_paris_olympics_2024.png",
        username="央视体育",
        verified=True,
        timestamp="2024-08-11 23:45  来自 央视体育官方微博",
        content=(
            "【中国代表团2024巴黎奥运会成绩单】2024巴黎奥运会今日落幕！"
            "中国体育代表团共获得40枚金牌、27枚银牌、24枚铜牌，"
            "金牌数与美国并列第一（均为40金）。郑钦文夺得中国奥运史上首枚网球金牌，"
            "樊振东/孙颖莎包揽乒乓球男女单打金牌。全体健儿，实至名归！🏅"
        ),
        likes="46.8万",
        comments="9.1万",
        reposts="22.3万",
        avatar_color="#1565c0",
    )

    # 9. 台湾花莲7.3级地震（2024年4月3日，可搜索）
    make_weibo(
        filename="real_xinhua_weibo_hualien_eq_2024.png",
        username="新华社",
        verified=True,
        timestamp="2024-04-03 08:15  来自 新华社官方微博",
        content=(
            "【台湾花莲发生7.3级地震】中国地震台网正式测定：北京时间2024年4月3日"
            "07时58分，台湾花莲县海域发生7.3级地震，震源深度15公里。"
            "震感波及福建、浙江、广东等沿海省份。台湾当局已启动救援响应，"
            "花莲部分建筑受损，伤亡情况正在统计中。新华社持续关注。"
        ),
        likes="11.3万",
        comments="2.4万",
        reposts="8.7万",
        avatar_color="#c0392b",
    )

    # 10. 地方性通报：武汉市防汛Ⅲ级应急响应（2024年7月，地方事件，不触发铁律一否决权）
    make_notice(
        filename="real_local_wuhan_flood_notice_2024.png",
        org="武汉市防汛抗旱指挥部",
        title="关于启动防汛Ⅲ级应急响应的通知",
        body=(
            "全市各区、各单位：\n"
            "受上游来水影响，长江武汉段水位持续上涨，汉口站水位已超警戒水位0.38米。"
            "根据《武汉市防汛应急预案》，市防汛抗旱指挥部决定于2024年7月2日12时启动"
            "防汛Ⅲ级应急响应。\n"
            "各区防指要立即进入临战状态，加强堤防24小时巡逻值守，"
            "严禁市民进入江滩公园游泳、垂钓。各单位按预案做好相应准备。"
        ),
        date="武汉市防汛抗旱指挥部  2024年7月2日",
    )

    # 11. 国家市场监管总局食品安全抽检通告（2024年，定期发布，可搜索到同类通告）
    make_notice(
        filename="real_samr_food_safety_2024q3.png",
        org="国家市场监督管理总局",
        title="2024年第三季度食品安全监督抽检情况通告",
        body=(
            "2024年第三季度，全国市场监管部门共完成食品安全监督抽检202.49万批次，"
            "检出不合格样品3.97万批次，不合格率为1.96%，与上年同期基本持平。\n"
            "主要问题：农药残留超标占不合格总数28.3%；微生物污染占21.6%；"
            "食品添加剂超量使用占17.4%。\n"
            "总局已依法责令相关企业停止销售并召回问题产品，不合格产品名单"
            "已在国家市场监督管理总局官网公示。"
        ),
        date="国家市场监督管理总局  2024年10月18日",
    )

    # 12. 伊朗核谈判新进展（2024年，可搜索）
    make_weibo(
        filename="real_xinhua_weibo_iran_nuclear_talks_2024.png",
        username="新华社",
        verified=True,
        timestamp="2024-09-14 14:20  来自 新华社官方微博",
        content=(
            "【伊朗新政府表示愿意重启核谈判】新华社报道：伊朗新任总统马苏德·佩泽希齐扬"
            "在联合国大会期间表示，伊朗愿意在相互尊重的基础上重启伊核问题谈判，"
            "并寻求解除制裁。美国国务院回应称正在评估伊朗立场，并表示外交渠道仍然开放。"
            "分析人士认为，在莱希政府强硬立场之后，佩泽希齐扬政府释放出相对温和的外交信号，"
            "但伊核问题结构性矛盾短期内难以根本化解。"
        ),
        likes="4.2万",
        comments="1.1万",
        reposts="3.8万",
        avatar_color="#c0392b",
    )

    print(f"\n[OK] 共生成 12 张真实新闻 fixture。")
    print("下一步：python -X utf8 tests/run_vision_eval.py")


if __name__ == "__main__":
    main()

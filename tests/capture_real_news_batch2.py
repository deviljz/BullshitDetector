"""
第二批真实新闻页面截图（50张）
重点：蓝底白字警方公告、政府政策通知、食品安全公告、司法公告等
运行：python tests/capture_real_news_batch2.py
"""
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)

TARGETS = [
    # ── 公安/警方公告 ──────────────────────────────────────────────────────────
    ("real_web_gz_police_qktb",        "https://gaj.gz.gov.cn/gaxw/qktb/",                                                              "广州市公安局：情况通报列表页（警方蓝底公告）"),
    ("real_web_gz_police_jingwang2024","https://gaj.gz.gov.cn/gkmlpt/content/10/10083/post_10083846.html",                              "广州警方：净网2024专项行动通报"),
    ("real_web_gz_police_car_void",    "https://gaj.gz.gov.cn/gkmlpt/content/10/10613/post_10613937.html",                              "广州交管：机动车登记证书/号牌作废公告"),
    ("real_web_sz_police_admin2024",   "http://ga.sz.gov.cn/gkmlpt/content/11/11141/post_11141456.html",                                "深圳公安：2024年1月治安行政许可数据"),
    ("real_web_sz_police_fraud_case",  "http://ga.sz.gov.cn/gkmlpt/content/11/11152/post_11152096.html",                                "深圳公安：某区4人被骗1710万反诈案例"),
    ("real_web_mps_jingwang2024",      "https://www.mps.gov.cn/n2254098/n4904352/c9947046/content.html",                               "公安部：净网2024取得显著成效"),
    ("real_web_mps_jingwang2025",      "https://www.mps.gov.cn/n2254098/n4904352/c10237151/content.html",                              "公安部：净网2025专项工作10起典型案例"),
    ("real_web_mps_gonggao",           "https://www.mps.gov.cn/n6557558/c10269791/content.html",                                       "公安部：资金分析标准化工作组公示"),
    ("real_web_hunan_imigraton",       "http://gat.hunan.gov.cn/gat/jwgk/jwzx/jqfb/202502/t20250218_33589920.html",                    "湖南省移民管理局：2024十起重大典型案例通报"),
    ("real_web_baiyin_police_conf",    "https://www.baiyin.gov.cn/sgaj/fdzdgknr/xwfbh/art/2024/art_7f7ea51ac27448f7b8fc8095e64abfee.html","白银市公安：2024夏季治安打击整治行动发布会"),
    ("real_web_yiwu_police",           "https://www.yw.gov.cn/art/2024/9/26/art_1229133960_59502642.html",                              "义乌市公安局：公告"),
    ("real_web_liuzhou_police_jqtb",   "http://gaj.liuzhou.gov.cn/xwzx/jqtb/",                                                         "柳州市公安局：警情通报列表"),
    ("real_web_putian_police_jqtb",    "http://gaj.putian.gov.cn/zwgk/jqtb/",                                                          "莆田市公安局：警情通报列表"),

    # ── 司法/法院 ────────────────────────────────────────────────────────────
    ("real_web_court_guideline2024",   "https://www.court.gov.cn/zixun/xiangqing/451431.html",                                          "最高人民法院：2024年审判工作提质增效指导意见"),
    ("real_web_court_ipc_2024h1",      "https://ipc.court.gov.cn/zh-cn/news/view-3244.html",                                           "最高法知识产权法庭：2024年上半年司法审判数据"),
    ("real_web_court_notice_list",     "https://www.court.gov.cn/fabu/gengduo/22.html",                                                 "最高人民法院：通知公告列表"),

    # ── 市场监管/食品安全 ────────────────────────────────────────────────────
    ("real_web_samr_gas_cert2024",     "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/rzjgs/art/2024/art_173693fdaf6e431fa242886c7a953631.html","市场监管总局：商用燃气产品强制性认证公告"),
    ("real_web_samr_std_sys2024",      "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/wszx/art/2024/art_84e045e639da4adb9d6a2efe8d269aa6.html","市场监管总局：行业标准管理系统上线通告"),
    ("real_web_bj_food_44th",          "https://scjgj.beijing.gov.cn/zwxx/gs/spzlgs/202408/t20240809_3771103.html",                    "北京市市监局：食品安全监督抽检公告第44期（2024年）"),
    ("real_web_bj_food_61st",          "https://scjgj.beijing.gov.cn/zwxx/gs/202411/t20241103_3933270.html",                           "北京市市监局：食品安全监督抽检公告第61期（2024年）"),
    ("real_web_bj_food_69th",          "https://scjgj.beijing.gov.cn/zwxx/gs/202412/t20241206_3959116.html",                           "北京市市监局：食品安全监督抽检公告第69期（2024年）"),
    ("real_web_yuhang_food_2024",      "http://www.yuhang.gov.cn/art/2024/10/29/art_1229511712_4309803.html",                          "余杭区市监局：食品安全监督抽检第13期（2024年）"),
    ("real_web_kashi_food_2024",       "https://www.kashi.gov.cn/ksdqxzgs/c112186/202412/461531c1e7f84dd3892bb101ffbd2130.shtml",      "喀什地区：2024年食品安全监督抽检公告第24期"),
    ("real_web_bj_drug_2025",          "https://yjj.beijing.gov.cn/yjj/xxcx/zlgg/yp30/543515983/index.html",                          "北京药监局：2025年第1期药品质量安全公告"),

    # ── 卫生健康 ─────────────────────────────────────────────────────────────
    ("real_web_nhc_2024_report",       "https://www.nhc.gov.cn/bgt/c100022/202501/34dd4c530ad142579a01219871ead871.shtml",             "国家卫健委：2024年政府信息公开工作年度报告"),

    # ── 应急管理 ─────────────────────────────────────────────────────────────
    ("real_web_mem_2024_report",       "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202501/t20250126_513843.shtml",                    "应急管理部：2024年政府信息公开工作报告"),
    ("real_web_mem_2024_std_notice",   "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202403/t20240319_481899.shtml",                    "应急管理部：2024年第2号公告（批准3项行业标准）"),
    ("real_web_gov_jialayuan_fire",    "https://www.gov.cn/yaowen/liebiao/202409/content_6975746.htm",                                  "国务院：江西新余佳乐苑特别重大火灾事故调查报告公布"),
    ("real_web_mem_accident_2024",     "https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/2024dcbg/",                                          "应急管理部：2024年特别重大事故调查报告列表"),
    ("real_web_mem_gdg_notice",        "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202411/t20241129_513848.shtml",                    "应急管理部：2024年应急通信装备创新工作通知"),

    # ── 人力资源与社会保障 ────────────────────────────────────────────────────
    ("real_web_mohrss_hr_market",      "https://www.mohrss.gov.cn/xxgk2020/fdzdgknr/zcfg/gfxwj/jy/202408/t20240829_524827.html",      "人社部：进一步加强人力资源市场规范管理通知（2024年）"),
    ("real_web_mohrss_law_promo",      "https://www.mohrss.gov.cn/xxgk2020/fdzdgknr/qt/gztz/202404/t20240428_517586.html",             "人社部：2024年人力资源社会保障法律法规宣传月通知"),
    ("real_web_mohrss_emp_assist",     "https://www.mohrss.gov.cn/SYrlzyhshbzb/jiuye/zcwj/jiuyekunnanrenyuan/202412/t20241209_531972.html","人社部等：进一步做好就业援助工作通知（2024年）"),
    ("real_web_mohrss_grad_emp",       "http://chinajob.mohrss.gov.cn/c/2024-06-21/414236.shtml",                                      "人社部教育部财政部：做好高校毕业生就业创业工作通知（2024年）"),

    # ── 税务 ─────────────────────────────────────────────────────────────────
    ("real_web_tax_invoice_liaoning",  "https://liaoning.chinatax.gov.cn/art/2024/11/12/art_5869_7599.html",                           "税务总局辽宁：推广应用全面数字化电子发票公告（2024年）"),
    ("real_web_tax_lvat_jiangsu",      "https://jiangsu.chinatax.gov.cn/art/2024/11/29/art_7716_35697.html",                           "税务总局江苏：调整土地增值税预征率公告（2024年）"),
    ("real_web_tax_stamp_heilong",     "http://heilongjiang.chinatax.gov.cn/art/2024/9/13/art_8308_528929.html",                       "税务总局黑龙江：企业改制重组印花税政策公告（2024年）"),
    ("real_web_tax_stock_zhejiang",    "https://zhejiang.chinatax.gov.cn/art/2024/4/28/art_8409_83958.html",                           "税务总局浙江：上市公司股权激励个税政策公告（2024年）"),

    # ── 生态环境 ─────────────────────────────────────────────────────────────
    ("real_web_mee_hazard_waste",      "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk02/202411/t20241129_1097685.html",                    "生态环境部：国家危险废物名录（2025年版）公告"),
    ("real_web_mee_press_oct2024",     "https://www.mee.gov.cn/ywdt/xwfb/202410/t20241027_1090157.shtml",                              "生态环境部：2024年10月例行新闻发布会情况通报"),

    # ── 统计/经济数据 ─────────────────────────────────────────────────────────
    ("real_web_stats_2024_annual",     "https://www.stats.gov.cn/sj/zxfb/202501/t20250117_1958332.html",                               "国家统计局：2024年经济运行稳中有进（全年数据）"),
    ("real_web_stats_2025_annual",     "https://www.stats.gov.cn/sj/zxfb/202601/t20260119_1962330.html",                               "国家统计局：2025年经济发展预期目标实现情况"),

    # ── 教育 ─────────────────────────────────────────────────────────────────
    ("real_web_moe_gaokao_security",   "http://www.moe.gov.cn/jyb_xwfb/gzdt_gzdt/s5987/202405/t20240531_1133390.html",                "教育部：全力保障2024年高考安全公告"),
    ("real_web_moe_gaokao_enroll",     "http://www.moe.gov.cn/srcsite/A15/moe_776/s3258/202403/t20240320_1121360.html",                "教育部：关于做好2024年普通高校招生工作的通知"),

    # ── 民政 ─────────────────────────────────────────────────────────────────
    ("real_web_mca_recruit2024",       "https://www.mca.gov.cn/n152/n165/c1662004999979998292/content.html",                           "民政部：2024年度直属事业单位公开招聘应届毕业生公告"),
    ("real_web_mca_assoc_notice",      "https://www.mca.gov.cn/n152/n165/c1662004999980000482/content.html",                           "民政部：印发全国性行业协会商会章程示范文本通知"),

    # ── 住建/城市管理 ─────────────────────────────────────────────────────────
    ("real_web_gov_jialayuan_investigation","https://www.mem.gov.cn/xw/bndt/202409/t20240921_501982.shtml",                            "应急管理部：江西新余佳乐苑特别重大火灾调查报告公布"),

    # ── 军事/国防（已知可验证事件）───────────────────────────────────────────
    ("real_web_stats_cpi_oct2024",     "https://www.stats.gov.cn/sj/zxfb/202411/t20241113_1957234.html",                               "国家统计局：2024年10月CPI数据发布"),
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
        time.sleep(2)
        out_path = FIXTURES_DIR / f"{name}.jpg"
        page.screenshot(path=str(out_path), full_page=False, type="jpeg", quality=88)
        size = out_path.stat().st_size
        status = "BLANK" if size < 10_000 else "OK"
        print(f"  [{status}] {out_path.name}  {size//1024}KB  {desc[:50]}")
        return status == "OK"
    except Exception as e:
        print(f"  [FAIL] {name}  {str(e)[:80]}")
        return False
    finally:
        browser.close()


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print(f"\n[DIR] {FIXTURES_DIR.resolve()}\n")
    ok = fail = blank = 0
    with sync_playwright() as p:
        for name, url, desc in TARGETS:
            result = capture(p, name, url, desc)
            if result:
                ok += 1
            else:
                fail += 1
    print(f"\n完成：{ok} OK / {fail} FAIL+BLANK  共 {len(TARGETS)} 张")


if __name__ == "__main__":
    main()

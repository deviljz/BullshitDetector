"""
生成质量降级的 fixture（模拟现实中转发压缩/截图截图/拍屏等场景）
对现有清晰截图做以下处理后存为新文件：
  1. 缩小再放大（模糊化）
  2. 高JPEG压缩
  3. 加轻微噪声
  4. 模拟手机拍屏（加枕形变形+轻微旋转）
运行：python tests/generate_degraded_fixtures.py
输出：tests/fixtures/deg_*.jpg
"""
import pathlib
import random
import sys

from PIL import Image, ImageEnhance, ImageFilter

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

# 来源图 → 降级方式列表
# 每种降级方式会生成一张新图，命名为 deg_<mode>_<原文件名>

# 选取已验证内容丰富的真实截图作为来源
SOURCES_REAL = [
    # 食品安全
    "real_web_bj_food_44th.jpg",
    "real_web_bj_food_61st.jpg",
    "real_web_bj_food_69th.jpg",
    "real_web_kashi_food_2024.jpg",
    # 税务
    "real_web_tax_invoice_liaoning.jpg",
    "real_web_tax_lvat_jiangsu.jpg",
    "real_web_tax_stamp_heilong.jpg",
    "real_web_tax_stock_zhejiang.jpg",
    # 教育部
    "real_web_moe_gaokao_1342w.jpg",
    "real_web_moe_gaokao_security.jpg",
    "real_web_moe_gaokao_enroll.jpg",
    # 公安/警方
    "real_web_gz_police_qktb.jpg",
    "real_web_gz_police_jingwang2024.jpg",
    "real_web_putian_police_jqtb.jpg",
    "real_web_yiwu_police.jpg",
    # 应急/政府
    "real_web_gov_jialayuan_fire.jpg",
    "real_web_mem_2024_report.jpg",
    # 市场监管
    "real_web_samr_gas_cert2024.jpg",
    # 统计
    "real_web_stats_gdp_2024q3.jpg",
    "real_web_stats_cpi_oct2024.jpg",
    # 真实用户截图（已验证）
    "real_weibo_rmrb_iraq_engagement.jpg",
    "real_mps_waimai_rumor_case.png",
]

SOURCES_FAKE = [
    # 明确假的图片，降级后仍应被判假
    "fake_mileage_tax_policy.png",
    "fake_wechat_voice_charge.png",
    "fake_earthquake_beijing_warning.png",
    "fake_who_vaccine_ban_china.png",
    "fake_moe_gaokao_english_cancel.png",
    "fake_quantum_battery_perpetual.png",
    "fake_samr_baby_formula_recall.png",
    "fake_food_shrimp_tomato_warning.png",
]


def downscale_upscale(img: Image.Image, factor: float = 0.3) -> Image.Image:
    """缩小再放大（双线性）→ 明显模糊"""
    w, h = img.size
    small = img.resize((max(1, int(w * factor)), max(1, int(h * factor))), Image.BILINEAR)
    return small.resize((w, h), Image.BILINEAR)


def jpeg_compress(img: Image.Image, quality: int = 20) -> Image.Image:
    """高压缩JPEG再解码 → 块状伪影"""
    import io
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).copy()


def add_noise(img: Image.Image, amount: int = 30) -> Image.Image:
    """加随机噪声"""
    import numpy as np
    arr = np.array(img.convert("RGB"), dtype=np.int16)
    noise = np.random.randint(-amount, amount + 1, arr.shape, dtype=np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def phone_screenshot(img: Image.Image) -> Image.Image:
    """模拟手机拍屏：轻微旋转 + 降低对比度 + 枕形/桶形偏移（简化）"""
    angle = random.uniform(-2.0, 2.0)
    rotated = img.rotate(angle, expand=False, fillcolor=(240, 240, 240))
    enhancer = ImageEnhance.Contrast(rotated)
    return enhancer.enhance(0.8)


def multi_screenshot(img: Image.Image) -> Image.Image:
    """截图的截图：JPEG压缩 + 缩小再放大 + 微量噪声"""
    step1 = jpeg_compress(img, quality=50)
    step2 = downscale_upscale(step1, factor=0.5)
    return add_noise(step2, amount=10)


MODES = {
    "blur":  downscale_upscale,       # 缩小再放大
    "jpg":   lambda img: jpeg_compress(img, quality=25),  # 强JPEG压缩
    "noise": lambda img: add_noise(img, amount=25),        # 噪声
    "phone": phone_screenshot,        # 手机拍屏
    "multi": multi_screenshot,        # 截图的截图
}


def process(src_name: str, mode: str, is_fake: bool) -> pathlib.Path | None:
    src = FIXTURES_DIR / src_name
    if not src.exists():
        print(f"  [SKIP] {src_name} not found")
        return None
    img = Image.open(src).convert("RGB")
    fn = MODES[mode]
    result = fn(img)
    prefix = "fake" if is_fake else "real"
    stem = pathlib.Path(src_name).stem
    out_name = f"deg_{mode}_{stem}.jpg"
    out_path = FIXTURES_DIR / out_name
    result.save(str(out_path), "JPEG", quality=88)
    size = out_path.stat().st_size
    print(f"  [OK] {out_name}  {size//1024}KB")
    return out_path


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    random.seed(42)

    print(f"\n生成降级 fixtures → {FIXTURES_DIR.resolve()}\n")
    count = 0

    # 真实图：每张选2种降级方式
    real_modes = ["blur", "jpg", "noise", "phone", "multi"]
    for i, src in enumerate(SOURCES_REAL):
        selected = [real_modes[i % len(real_modes)], real_modes[(i + 2) % len(real_modes)]]
        for mode in selected:
            if process(src, mode, is_fake=False):
                count += 1

    # 假图：每张选2种降级方式
    fake_modes = ["blur", "jpg", "noise", "phone", "multi"]
    for i, src in enumerate(SOURCES_FAKE):
        selected = [fake_modes[i % len(fake_modes)], fake_modes[(i + 1) % len(fake_modes)]]
        for mode in selected:
            if process(src, mode, is_fake=True):
                count += 1

    print(f"\n完成：共生成 {count} 张降级图片")


if __name__ == "__main__":
    main()

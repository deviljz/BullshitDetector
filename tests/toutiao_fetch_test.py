"""测试 fetch_toutiao 的文字提取和图片过滤效果。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from text_fetcher import fetch_toutiao

URL = "https://www.toutiao.com/w/1860140032822272/"

print("开始提取…")
text, images = fetch_toutiao(URL)

print(f"\n=== 文字（前 500 字）===")
print(text[:500])
print(f"\n… 共 {len(text)} 字")

print(f"\n=== 图片：共 {len(images)} 张 ===")
for i, img in enumerate(images):
    print(f"[{i+1}] {img.width}x{img.height}")

# 保存图片供人工检查
out = Path(__file__).parent / "toutiao_test" / "final"
out.mkdir(parents=True, exist_ok=True)
for i, img in enumerate(images):
    p = out / f"result_{i+1}.jpg"
    img.save(p, "JPEG", quality=85)
    print(f"  saved {p.name}")

print("\nDone.")
